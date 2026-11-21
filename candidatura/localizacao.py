"""Classifica a vaga para os filtros da tela de swipe: país (Brasil ou
exterior), idioma do anúncio, modalidade, UF e região.

Só usa o que a vaga já tem (local, modalidade, site, título e descrição);
nada de rede. Quando não há sinal nenhum, devolve "indefinido" em vez de
chutar — o filtro mostra quantas vagas caem nesse balde.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from core.job import _CAPITAIS_BRASIL, _NOME_DO_ESTADO, _SIGLAS_ESTADOS_EUA, _SIGLAS_UF_AMBIGUAS, _SIGLAS_UF_BRASIL

REGIOES = {
    "Norte": {"ac", "ap", "am", "pa", "ro", "rr", "to"},
    "Nordeste": {"al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se"},
    "Centro-Oeste": {"df", "go", "mt", "ms"},
    "Sudeste": {"es", "mg", "rj", "sp"},
    "Sul": {"pr", "rs", "sc"},
}
_REGIAO_DA_UF = {uf: regiao for regiao, ufs in REGIOES.items() for uf in ufs}

_UF_DA_CAPITAL = {
    "rio branco": "ac", "maceio": "al", "macapa": "ap", "manaus": "am", "salvador": "ba", "fortaleza": "ce",
    "brasilia": "df", "vitoria": "es", "goiania": "go", "sao luis": "ma", "cuiaba": "mt", "campo grande": "ms",
    "belo horizonte": "mg", "belem": "pa", "joao pessoa": "pb", "curitiba": "pr", "recife": "pe",
    "teresina": "pi", "rio de janeiro": "rj", "natal": "rn", "porto alegre": "rs", "porto velho": "ro",
    "boa vista": "rr", "florianopolis": "sc", "sao paulo": "sp", "aracaju": "se", "palmas": "to",
}
assert set(_UF_DA_CAPITAL) == _CAPITAIS_BRASIL

# Cidades grandes que não são capital e aparecem sem UF ("Campinas", "Greater Campinas").
_OUTRAS_CIDADES = {
    "campinas": "sp", "barueri": "sp", "sao jose dos campos": "sp", "ribeirao preto": "sp", "santos": "sp",
    "sorocaba": "sp", "osasco": "sp", "santo andre": "sp", "sao bernardo do campo": "sp", "guarulhos": "sp",
    "uberlandia": "mg", "juiz de fora": "mg", "contagem": "mg", "uberaba": "mg", "betim": "mg",
    "joinville": "sc", "blumenau": "sc", "londrina": "pr", "maringa": "pr", "niteroi": "rj",
    "caxias do sul": "rs", "feira de santana": "ba", "campina grande": "pb", "caruaru": "pe",
}

# País -> idioma provável do anúncio quando o texto não diz nada.
_PAISES = {
    "brasil": ("Brasil", "pt"), "brazil": ("Brasil", "pt"),
    "portugal": ("Portugal", "pt"),
    "spain": ("Espanha", "es"), "espanha": ("Espanha", "es"), "espana": ("Espanha", "es"),
    "mexico": ("México", "es"), "chile": ("Chile", "es"), "colombia": ("Colômbia", "es"),
    "argentina": ("Argentina", "es"), "peru": ("Peru", "es"), "uruguay": ("Uruguai", "es"),
    "uruguai": ("Uruguai", "es"), "paraguay": ("Paraguai", "es"), "ecuador": ("Equador", "es"),
    "costa rica": ("Costa Rica", "es"), "latam": ("LATAM", ""), "latin america": ("LATAM", ""),
    "america latina": ("LATAM", ""),
    "united states": ("Estados Unidos", "en"), "usa": ("Estados Unidos", "en"), "us": ("Estados Unidos", "en"),
    "canada": ("Canadá", "en"), "united kingdom": ("Reino Unido", "en"), "uk": ("Reino Unido", "en"),
    "ireland": ("Irlanda", "en"), "germany": ("Alemanha", "en"), "netherlands": ("Holanda", "en"),
    "france": ("França", "en"), "italy": ("Itália", "en"), "poland": ("Polônia", "en"),
    "india": ("Índia", "en"), "europe": ("Europa", "en"), "emea": ("Europa", "en"),
    "worldwide": ("Mundo todo", "en"), "anywhere": ("Mundo todo", "en"),
}
_PADRAO_PAIS = re.compile(r"(?<![a-z])(" + "|".join(sorted(map(re.escape, _PAISES), key=len, reverse=True)) + r")(?![a-z])")

# Cidades estrangeiras frequentes que o LinkedIn escreve sem país.
_CIDADES_EXTERIOR = {
    "madrid": "Espanha", "barcelona": "Espanha", "valencia": "Espanha", "lisbon": "Portugal", "lisboa": "Portugal",
    "porto": "Portugal", "bogota": "Colômbia", "medellin": "Colômbia", "buenos aires": "Argentina",
    "santiago": "Chile", "mexico city": "México", "guadalajara": "México", "monterrey": "México",
    "lima": "Peru", "montevideo": "Uruguai", "bilbao": "Espanha", "sevilla": "Espanha", "malaga": "Espanha",
    "aveiro": "Portugal", "braga": "Portugal", "coimbra": "Portugal", "bucaramanga": "Colômbia",
    "barranquilla": "Colômbia", "cali": "Colômbia", "queretaro": "México", "cordoba": "Argentina",
    "rosario": "Argentina",
}

_SITES_BRASIL = ("gupy", "catho", "solides", "senior", "geekhunter", "trampos", "99jobs", "remotar", "indeed",
                 "github backend-br", "github frontendbr", "github react-brasil", "github datascience-br")
_SITES_EXTERIOR = ("linkedin internacional", "we work remotely")

_PALAVRAS_IDIOMA = {
    "pt": {"de", "e", "com", "para", "voce", "nossa", "nosso", "em", "da", "do", "que", "vaga", "desenvolvedor",
           "desenvolvedora", "engenheiro", "engenheira", "analista", "estagio", "estagiario", "pleno", "requisitos",
           "conhecimento", "experiencia", "trabalho", "beneficios", "dados", "sistemas", "programador"},
    "en": {"the", "and", "you", "with", "our", "will", "for", "are", "your", "we", "developer", "engineer",
           "software", "senior", "junior", "lead", "manager", "requirements", "experience", "team", "remote",
           "intern", "internship", "staff", "data"},
    "es": {"el", "los", "las", "con", "para", "una", "del", "que", "desarrollador", "desarrolladora", "ingeniero",
           "ingeniera", "programador", "trabajo", "experiencia", "conocimientos", "equipo", "empresa", "datos",
           "practicante", "becario", "requisitos", "somos", "buscamos"},
}
_PALAVRAS_SO_DE = {  # desempate: palavras que só existem num dos idiomas
    "pt": {"voce", "vaga", "desenvolvedor", "engenheiro", "estagio", "pleno", "nosso", "nossa", "beneficios"},
    "en": {"the", "you", "our", "your", "developer", "engineer", "requirements", "team", "internship", "analyst",
           "manager", "business", "engineering", "scientist", "architect", "consultant"},
    "es": {"el", "los", "las", "una", "desarrollador", "ingeniero", "conocimientos", "equipo", "buscamos", "somos"},
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", texto).strip()


@dataclass(frozen=True)
class Classificacao:
    pais: str        # "brasil" | "exterior" | "indefinido"
    pais_nome: str   # "Brasil", "Espanha", "LATAM", ... ou ""
    cidade: str      # "Uberlândia" ... ou "" (municípios do IBGE)
    idioma: str      # "pt" | "en" | "es" | "indefinido"
    modalidade: str  # "remoto" | "hibrido" | "presencial" | "indefinido"
    uf: str          # "MG" ... ou ""
    regiao: str      # "Sudeste" ... ou ""

    def como_dict(self) -> dict:
        return {"pais": self.pais, "pais_nome": self.pais_nome, "cidade": self.cidade, "idioma": self.idioma,
                "modalidade": self.modalidade, "uf": self.uf, "regiao": self.regiao}


def _uf(local: str) -> str:
    """UF brasileira declarada no local ("Recife - PE", "Belo Horizonte, Minas Gerais, Brazil",
    "Greater São Paulo Area", "Uberlândia")."""
    for pedaco in re.split(r"[,\-–—/()+]", local):
        pedaco = pedaco.strip(" .")
        if pedaco in _NOME_DO_ESTADO:
            return _NOME_DO_ESTADO[pedaco]
        if pedaco in _SIGLAS_UF_BRASIL and pedaco not in _SIGLAS_UF_AMBIGUAS:
            return pedaco
    for cidades in (_UF_DA_CAPITAL, _OUTRAS_CIDADES):
        for cidade, uf in cidades.items():
            if re.search(r"(?<![a-z])" + re.escape(cidade) + r"(?![a-z])", local):
                return uf
    # Siglas que também são estado americano (AL, MA, MT, MS, PA, SC): só valem com outra pista brasileira.
    for pedaco in re.split(r"[,\-–—/()+]", local):
        pedaco = pedaco.strip(" .")
        if pedaco in _SIGLAS_UF_AMBIGUAS and ("brazil" in local or "brasil" in local or "remoto" in local):
            return pedaco
    return ""


def _pais(local: str, site: str, uf: str) -> tuple[str, str]:
    achados = [_PAISES[m.group(1)][0] for m in _PADRAO_PAIS.finditer(local)]
    if "Brasil" in achados:
        return "brasil", "Brasil"
    if achados:
        return "exterior", achados[0]
    if uf:
        return "brasil", "Brasil"
    for cidade, pais in _CIDADES_EXTERIOR.items():
        if re.search(r"(?<![a-z])" + re.escape(cidade) + r"(?![a-z])", local):
            return "exterior", pais
    # "Chicago, IL": sigla de estado americano (as que colidem com UF já foram tratadas em _uf).
    if any(p.strip(" .") in _SIGLAS_ESTADOS_EUA - _SIGLAS_UF_BRASIL for p in re.split(r"[,\-–—/()]", local)):
        return "exterior", "Estados Unidos"
    if any(s == site or site.startswith(s) for s in _SITES_EXTERIOR):
        return "exterior", ""
    if any(s == site or site.startswith(s) for s in _SITES_BRASIL):
        return "brasil", "Brasil"
    # LinkedIn em português ("Remoto", "Não informado") vem das buscas no Brasil.
    if site.startswith("linkedin") and re.search(r"remoto|nao informado|cidades", local):
        return "brasil", "Brasil"
    # "Greater Bilbao Metropolitan Area": as áreas brasileiras já saíram com UF acima.
    if site.startswith("linkedin") and re.search(r"greater|metropolitan|area", local):
        return "exterior", ""
    return "indefinido", ""


def _idioma(titulo: str, descricao: str, pais_nome: str) -> str:
    def contar(texto: str) -> dict[str, float]:
        palavras = re.findall(r"[a-z]+", normalizar(texto))
        pontos = {k: sum(1 for p in palavras if p in v) for k, v in _PALAVRAS_IDIOMA.items()}
        for k, v in _PALAVRAS_SO_DE.items():
            pontos[k] += 0.5 * sum(1 for p in palavras if p in v)
        return pontos

    if len(re.findall(r"\w+", descricao or "")) >= 40:
        pontos = contar(descricao)
        melhor = max(pontos, key=pontos.get)
        if pontos[melhor] >= 3:
            return melhor
    pontos = contar(titulo)
    if pais_nome == "Brasil":
        # Só o título: vaga brasileira com título em inglês ("Back-End Developer") quase sempre tem
        # anúncio em português. Só vira inglês com sinal forte e nenhuma palavra em português.
        return "en" if pontos["en"] >= 3 and pontos["pt"] == 0 else "pt"
    so = {k: sum(1 for p in re.findall(r"[a-z]+", normalizar(titulo)) if p in v) for k, v in _PALAVRAS_SO_DE.items()}
    maior = max(so.values())
    if maior and list(so.values()).count(maior) == 1:  # empate ("Desenvolvedor Developer") cai no país
        return max(so, key=so.get)
    padrao = next((idioma for nome, idioma in _PAISES.values() if nome == pais_nome and idioma), "")
    if padrao:
        return padrao
    melhor = max(pontos, key=pontos.get)
    return melhor if pontos[melhor] > 0 else "indefinido"


def _modalidade(modalidade: str, local: str, titulo: str) -> str:
    texto = f"{normalizar(modalidade)} | {normalizar(titulo)}"
    if re.search(r"hibrid|hybrid", texto):
        return "hibrido"
    if re.search(r"presencial|on-?site|on site|in-office", texto):
        return "presencial"
    if re.search(r"remot|home office|anywhere|teletrab", texto + " | " + local):
        return "remoto"
    if re.search(r"hibrid|hybrid", local):
        return "hibrido"
    if re.search(r"presencial|on-?site", local):
        return "presencial"
    return "indefinido"


def classificar(vaga: dict) -> Classificacao:
    from candidatura import localidades

    local = normalizar(vaga.get("local") or "")
    site = normalizar(vaga.get("site") or "")
    uf = _uf(local)
    pais, pais_nome = _pais(local, site, uf)
    # Base pública (IBGE + países): acha qualquer município e país, não só as capitais.
    achado = localidades.extrair(vaga.get("local") or "")
    cidade = ""
    if pais == "exterior":
        pais_nome = achado["pais"] if achado["pais"] and achado["pais"] != "Brasil" else pais_nome
    elif achado["pais"] and achado["pais"] != "Brasil":
        pais, pais_nome = "exterior", achado["pais"]
    elif achado["cidade"] or achado["uf"] or achado["pais"] == "Brasil":
        pais, pais_nome = "brasil", "Brasil"
        uf = (achado["uf"] or uf).lower()
        cidade = achado["cidade"]
    if pais != "brasil":
        uf, cidade = "", ""
    return Classificacao(
        pais=pais,
        pais_nome=pais_nome,
        cidade=cidade,
        idioma=_idioma(vaga.get("titulo") or "", vaga.get("descricao") or "", pais_nome or ("Brasil" if pais == "brasil" else "")),
        modalidade=_modalidade(vaga.get("modalidade") or "", local, vaga.get("titulo") or ""),
        uf=uf.upper(),
        regiao=_REGIAO_DA_UF.get(uf, ""),
    )


@dataclass
class Filtros:
    pais: str = ""                       # "", "brasil", "exterior"
    idioma: str = ""                     # "", "pt", "en", "es"
    modalidades: frozenset = frozenset()  # vazio = todas
    regiao: str = ""                     # "", "Norte", ..., "Sul"
    local: str = ""                      # texto livre: cidade, UF, estado ou país (com apelidos)
    so_email: bool = False

    @property
    def lugar(self):
        """O que a pessoa quis dizer no campo de localização ("udia" -> Uberlândia - MG)."""
        if not self.local:
            return None
        if "_lugar" not in self.__dict__:
            from candidatura import localidades

            self.__dict__["_lugar"] = localidades.resolver(self.local)
        return self.__dict__["_lugar"]

    @classmethod
    def de_args(cls, args) -> "Filtros":
        def um(nome, validos):
            v = (args.get(nome) or "").strip()
            return v if v in validos else ""
        modalidades = {m for m in (args.get("modalidade") or "").split(",") if m in ("remoto", "hibrido", "presencial")}
        return cls(
            pais=um("pais", ("brasil", "exterior")),
            idioma=um("idioma", ("pt", "en", "es")),
            modalidades=frozenset(modalidades),
            regiao=um("regiao", tuple(REGIOES)),
            local=(args.get("local") or "").strip()[:60],
            so_email=args.get("filtro") == "email" or args.get("email") in ("1", "true"),
        )

    def aceita(self, vaga: dict, c: Classificacao) -> bool:
        if self.so_email and not vaga.get("email_destino"):
            return False
        if self.pais and c.pais != self.pais:
            return False
        if self.idioma and c.idioma != self.idioma:
            return False
        if self.modalidades and c.modalidade not in self.modalidades:
            return False
        if self.regiao and c.regiao != self.regiao:
            return False
        if self.local and self.lugar is not None:
            lugar = self.lugar
            if lugar.tipo == "cidade":
                return (normalizar(c.cidade) == normalizar(lugar.nome)
                        and (not lugar.uf or not c.uf or c.uf == lugar.uf))
            if lugar.tipo == "estado":
                return c.uf == lugar.uf
            if lugar.nome == "Brasil":
                return c.pais == "brasil"
            return c.pais == "exterior" and normalizar(c.pais_nome) == normalizar(lugar.nome)
        if self.local:  # não reconheci o lugar: procura o texto no local da vaga
            alvo = normalizar(self.local)
            estado = next((nome for nome, uf in _NOME_DO_ESTADO.items() if uf == c.uf.lower()), "")
            onde = " | ".join([normalizar(vaga.get("local") or ""), c.uf.lower(), estado, normalizar(c.pais_nome)])
            if len(alvo) == 2:  # "MG", "SP": compara com a UF, não com pedaço de palavra
                if alvo != c.uf.lower():
                    return False
            elif alvo not in onde:
                return False
        return True
