"""Cidades, estados e países a partir de fontes públicas, para o filtro de
localização entender qualquer jeito de escrever o lugar.

- Brasil: API de localidades do IBGE (5.570 municípios com UF e região).
- Países: pacote `world-countries` (nome em inglês, português, espanhol e
  grafias alternativas — o LinkedIn escreve "Spain", a pessoa digita "Espanha").

Os dados são baixados e guardados em data/localidades.json; a cópia é
renovada em segundo plano quando passa de 7 dias. Sem internet, usa a cópia;
sem cópia, cai nas tabelas embutidas do radar (capitais e estados).

O casamento tolera maiúsculas, acentos, apelidos ("Udia", "BH", "Floripa",
"Sampa") e erro de digitação ("Uberlandai").
"""

from __future__ import annotations

import difflib
import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from candidatura import config
from core.logger import get_logger

logger = get_logger()

URL_IBGE_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado"
URL_PAISES = "https://cdn.jsdelivr.net/npm/world-countries@5.1.0/countries.json"
CACHE_PATH = config.RAIZ / "data" / "localidades.json"
VALIDADE_DIAS = 7

# Apelidos e abreviações comuns em anúncio e no que a pessoa digita.
APELIDOS = {
    "udia": ("Uberlândia", "MG"), "udi": ("Uberlândia", "MG"), "bh": ("Belo Horizonte", "MG"),
    "bhz": ("Belo Horizonte", "MG"), "beaga": ("Belo Horizonte", "MG"), "sampa": ("São Paulo", "SP"),
    "sao paulo capital": ("São Paulo", "SP"), "floripa": ("Florianópolis", "SC"), "poa": ("Porto Alegre", "RS"),
    "cwb": ("Curitiba", "PR"), "bsb": ("Brasília", "DF"), "rio": ("Rio de Janeiro", "RJ"),
    "sjc": ("São José dos Campos", "SP"), "sjrp": ("São José do Rio Preto", "SP"),
    "rio preto": ("São José do Rio Preto", "SP"), "jampa": ("João Pessoa", "PB"), "jp": ("João Pessoa", "PB"),
    "ssa": ("Salvador", "BA"), "fortal": ("Fortaleza", "CE"), "gyn": ("Goiânia", "GO"), "vix": ("Vitória", "ES"),
    "sbc": ("São Bernardo do Campo", "SP"), "bauru": ("Bauru", "SP"), "cps": ("Campinas", "SP"),
    "ribeirao": ("Ribeirão Preto", "SP"), "sao jose": ("São José", "SC"),
}

_NOMES_UF = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}
_ESTADOS_EXTRA = {"federal district": "DF", "sao paulo state": "SP", "state of sao paulo": "SP"}

# Palavras que cercam o nome do lugar e não fazem parte dele.
_RUIDO = re.compile(r"\b(greater|metropolitan|metro|area|region|regiao|metropolitana|e regiao|and region|"
                    r"state of|estado de|estado do|province|provincia|community of|capital district|cidades?|"
                    r"remoto|remote|hibrido|hybrid|presencial|on site)\b|^grande ")
# Siglas de UF que também são estado americano: só valem com uma cidade brasileira junto.
_UF_AMBIGUAS = {"AL", "MA", "MT", "MS", "PA", "SC"}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


@dataclass(frozen=True)
class Lugar:
    tipo: str        # "cidade" | "estado" | "pais"
    nome: str        # "Uberlândia", "Minas Gerais", "Espanha"
    uf: str = ""     # "MG" (cidade/estado do Brasil)
    pais: str = ""   # nome do país em português ("Brasil", "Espanha")

    @property
    def rotulo(self) -> str:
        if self.tipo == "cidade":
            if self.uf:
                return f"{self.nome} - {self.uf}"
            return f"{self.nome} (vários estados)" if self.pais == "Brasil" else f"{self.nome} ({self.pais})"
        if self.tipo == "estado":
            return f"{self.nome} ({self.uf})"
        return self.nome

    def como_dict(self) -> dict:
        return {"tipo": self.tipo, "nome": self.nome, "uf": self.uf, "pais": self.pais, "rotulo": self.rotulo}


# ----------------------------------------------------------------- download

def baixar(timeout: int = 30) -> dict:
    import requests

    municipios = requests.get(URL_IBGE_MUNICIPIOS, timeout=timeout).json()
    paises = requests.get(URL_PAISES, timeout=timeout).json()
    dados = {
        "baixado_em": time.time(),
        "municipios": [[m["municipio-nome"], m["UF-sigla"]] for m in municipios
                       if m.get("municipio-nome") and m.get("UF-sigla")],
        "paises": [],
    }
    for p in paises:
        por = (p.get("translations") or {}).get("por") or {}
        spa = (p.get("translations") or {}).get("spa") or {}
        nome_pt = por.get("common") or p["name"]["common"]
        variantes = {p["name"]["common"], p["name"].get("official", ""), por.get("common", ""),
                     por.get("official", ""), spa.get("common", ""), p.get("cca3", "")}
        variantes |= {a for a in p.get("altSpellings") or [] if len(a) > 3}
        dados["paises"].append([nome_pt, sorted(v for v in variantes if v)])
    if len(dados["municipios"]) < 5000 or len(dados["paises"]) < 150:
        raise ValueError("resposta incompleta das fontes de localidades")
    return dados


def _ler_cache() -> dict | None:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def atualizar(forcar: bool = False) -> bool:
    """Baixa de novo se a cópia local não existe ou passou da validade."""
    cache = _ler_cache()
    if cache and not forcar and time.time() - cache.get("baixado_em", 0) < VALIDADE_DIAS * 86400:
        return False
    try:
        dados = baixar()
    except Exception as e:  # sem internet: segue com o que tiver
        logger.warning(f"[Localidades] não consegui atualizar ({e}); usando a cópia local")
        return False
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    _indice.cache_clear()
    logger.info(f"[Localidades] {len(dados['municipios'])} municípios e {len(dados['paises'])} países atualizados")
    return True


def atualizar_em_segundo_plano() -> None:
    threading.Thread(target=atualizar, daemon=True, name="localidades").start()


# ----------------------------------------------------------------- índice

class _Indice:
    def __init__(self, dados: dict | None):
        from core.job import _CAPITAIS_BRASIL  # noqa: F401 (garante o fallback do radar disponível)
        from candidatura.localizacao import _OUTRAS_CIDADES, _UF_DA_CAPITAL

        self.cidades: dict[str, list[tuple[str, str]]] = {}
        if dados and dados.get("municipios"):
            for nome, uf in dados["municipios"]:
                self.cidades.setdefault(normalizar(nome), []).append((nome, uf))
        else:  # sem internet e sem cópia: só capitais e cidades grandes
            for cidade, uf in {**_UF_DA_CAPITAL, **_OUTRAS_CIDADES}.items():
                self.cidades.setdefault(cidade, []).append((cidade.title(), uf.upper()))
        self.estados = {normalizar(nome): uf for uf, nome in _NOMES_UF.items()}
        self.estados.update(_ESTADOS_EXTRA)
        self.paises: dict[str, str] = {}
        if dados and dados.get("paises"):
            for nome_pt, variantes in dados["paises"]:
                for v in [nome_pt, *variantes]:
                    chave = normalizar(v)
                    if len(chave) > 2 or chave in ("usa", "uk", "eua"):
                        self.paises.setdefault(chave, nome_pt)
        from candidatura.localizacao import _PAISES

        for chave, (nome, _idioma) in _PAISES.items():
            self.paises.setdefault(chave, nome)
        self.paises.update({"eua": "Estados Unidos", "usa": "Estados Unidos", "uk": "Reino Unido"})
        self.apelidos = {k: v for k, v in APELIDOS.items()}
        self._nomes_fuzzy = list(self.cidades) + list(self.estados) + list(self.paises) + list(self.apelidos)

    # -- identificação de um pedaço de texto --------------------------------

    def _cidade(self, chave: str, uf: str = "") -> Lugar | None:
        if chave in self.apelidos:
            nome, uf_ap = self.apelidos[chave]
            return Lugar("cidade", nome, uf_ap, "Brasil")
        opcoes = self.cidades.get(chave)
        if not opcoes:
            return None
        escolhida = next((o for o in opcoes if o[1] == uf), None) if uf else None
        if escolhida is None and len(opcoes) == 1:
            escolhida = opcoes[0]
        if escolhida is None and not uf:  # "Campo Grande": a capital é de longe a mais anunciada
            from candidatura.localizacao import _UF_DA_CAPITAL

            capital = _UF_DA_CAPITAL.get(chave, "").upper()
            escolhida = next((o for o in opcoes if o[1] == capital), None)
        if escolhida is None:  # nome repetido em vários estados e sem UF no texto
            return Lugar("cidade", opcoes[0][0], "", "Brasil")
        return Lugar("cidade", escolhida[0], escolhida[1], "Brasil")

    def exato(self, texto: str) -> Lugar | None:
        # Rótulos que o próprio sistema sugere: "Uberlândia - MG", "Minas Gerais (MG)", "X (vários estados)".
        texto = re.sub(r"\s*\((varios estados|vários estados)\)\s*$", "", texto or "", flags=re.I)
        com_uf = re.fullmatch(r"\s*(.+?)\s*(?:-|,|\()\s*([A-Za-z]{2})\)?\s*", texto)
        if com_uf and com_uf.group(2).upper() in _NOMES_UF:
            nome, uf = normalizar(com_uf.group(1)), com_uf.group(2).upper()
            if self.estados.get(nome) == uf:
                return Lugar("estado", _NOMES_UF[uf], uf, "Brasil")
            cidade = self._cidade(nome, uf)
            if cidade and cidade.uf == uf:
                return cidade
        chave = normalizar(texto)
        if not chave:
            return None
        if len(chave) == 2 and chave.upper() in _NOMES_UF:
            return Lugar("estado", _NOMES_UF[chave.upper()], chave.upper(), "Brasil")
        if chave in self.estados:
            uf = self.estados[chave]
            return Lugar("estado", _NOMES_UF[uf], uf, "Brasil")
        if chave in ("brasil", "brazil"):
            return Lugar("pais", "Brasil", "", "Brasil")
        cidade = self._cidade(chave)
        if cidade:
            return cidade
        if chave in self.paises:
            return Lugar("pais", self.paises[chave], "", self.paises[chave])
        return None

    def sugerir(self, texto: str, limite: int = 8) -> list[Lugar]:
        """Para o campo de busca: exato, depois começo do nome, depois parecido."""
        chave = normalizar(texto)
        if len(chave) < 2:
            return []
        achados: list[Lugar] = []

        def add(lugar):
            if lugar and lugar not in achados:
                achados.append(lugar)

        add(self.exato(texto))  # texto cru: preserva o "- UF" de "Campo Grande - RN"
        add(self.exato(chave))
        if chave in self.cidades and len(self.cidades[chave]) > 1:
            for nome, uf in self.cidades[chave]:
                add(Lugar("cidade", nome, uf, "Brasil"))
        if len(chave) >= 3:
            for nome in sorted(self.estados):
                if nome.startswith(chave):
                    add(self.exato(nome))
            for nome in sorted(self.cidades, key=len):
                if nome.startswith(chave):
                    for n, uf in self.cidades[nome][:3]:
                        add(Lugar("cidade", n, uf, "Brasil"))
                if len(achados) >= limite:
                    break
            for nome in sorted(self.paises):
                if nome.startswith(chave) and len(achados) < limite:
                    add(Lugar("pais", self.paises[nome], "", self.paises[nome]))
        if len(achados) < 3:  # erro de digitação: "uberlandai", "florianopols"
            for nome in difflib.get_close_matches(chave, self._nomes_fuzzy, n=5, cutoff=0.8):
                add(self.exato(nome))
        return achados[:limite]

    def resolver(self, texto: str) -> Lugar | None:
        sugestoes = self.sugerir(texto, limite=1)
        return sugestoes[0] if sugestoes else None

    # -- leitura do campo "local" da vaga -----------------------------------

    def extrair(self, local: str) -> dict:
        """{"cidade", "uf", "pais"} encontrados no texto de local da vaga."""
        pedacos = [normalizar(_RUIDO.sub(" ", normalizar(p))) for p in re.split(r"[,\-–—/()+|;]", local or "")]
        pedacos = [p for p in pedacos if p]
        uf = pais = ""
        for p in pedacos:
            if len(p) == 2 and p.upper() in _NOMES_UF and not uf:
                uf = p.upper()
            elif p in self.estados and not uf:
                uf = self.estados[p]
            elif p in self.paises and not pais and p not in self.cidades:
                pais = self.paises[p]
        cidade = None
        for p in pedacos:
            if p in self.estados and p not in self.cidades:
                continue
            lugar = self._cidade(p, uf)
            if lugar:
                cidade = lugar
                break
        if cidade and not uf:
            uf = cidade.uf
        if uf in _UF_AMBIGUAS and not cidade and "brasil" not in pedacos and "brazil" not in pedacos:
            uf = ""  # "Huntsville, AL" é Alabama, não Alagoas
        if pais and pais != "Brasil":
            return {"cidade": "", "uf": "", "pais": pais}
        if cidade or uf:
            return {"cidade": cidade.nome if cidade else "", "uf": uf, "pais": "Brasil"}
        return {"cidade": "", "uf": "", "pais": pais}


_trava = threading.Lock()
_cache_indice: dict[str, _Indice] = {}


def _indice() -> _Indice:
    with _trava:
        if "i" not in _cache_indice:
            _cache_indice["i"] = _Indice(_ler_cache())
        return _cache_indice["i"]


_indice.cache_clear = _cache_indice.clear  # type: ignore[attr-defined]


def sugerir(texto: str, limite: int = 8) -> list[Lugar]:
    return _indice().sugerir(texto, limite)


def resolver(texto: str) -> Lugar | None:
    return _indice().resolver(texto)


def extrair(local: str) -> dict:
    return _indice().extrair(local)
