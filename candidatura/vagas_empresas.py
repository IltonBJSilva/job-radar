"""Vagas abertas direto no site das empresas (não só nos sites de vaga).

Para cada empresa da lista (config/empresas*.yaml + tela "Empresas"):

1. acha onde ela publica as vagas — o portal já descoberto, ou testa os
   endereços mais comuns: <empresa>.gupy.io, Greenhouse e Lever (APIs públicas);
2. baixa as vagas abertas e fica só com as que combinam com o perfil;
3. guarda onde achou (coluna `ats`), para nas próximas vezes ir direto.

Empresas da cidade do "foco regional" (ex.: Uberlândia) vão primeiro.
"""

from __future__ import annotations

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

from candidatura import empresas, repositorio
from candidatura.compatibilidade import extrair_tecnologias
from core.logger import get_logger

logger = get_logger()

_UA = {"User-Agent": "Mozilla/5.0 (job-radar)", "Accept": "application/json,text/html"}
RECHECAR_DIAS = 14  # empresa sem portal conhecido: testa de novo depois disso
_PALAVRAS_TI = ("desenvolvedor", "desenvolvedora", "developer", "programador", "software", "sistemas", "dados",
                "data", "tecnologia", "infraestrutura", "devops", "cloud", "seguranca", "security", "qa", "testes",
                "suporte", "engenheiro", "engineer", "analista de ti", "ti", "backend", "frontend", "full stack",
                "mobile", "sre", "arquiteto", "scrum", "produto", "product", "ux", "ui", "bi", "ia", "ai")


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", texto).strip()


def _tem(frase: str, texto: str) -> bool:
    frase = _norm(frase)
    return bool(frase) and re.search(r"(?<![a-z0-9])" + re.escape(frase) + r"(?![a-z0-9])", texto) is not None


def combina_com_perfil(titulo: str, preferencias: dict) -> bool:
    """A vaga do site da empresa interessa? Cargo/termo do perfil, tecnologia
    conhecida ou palavra de TI no título (vaga de "Vendedor" não entra)."""
    alvo = _norm(titulo)
    frases = list(preferencias.get("cargos_alvo") or []) + list(preferencias.get("termos_busca")
                                                                or preferencias.get("termos_remotar") or [])
    if any(_tem(f, alvo) for f in frases):
        return True
    if extrair_tecnologias(titulo):
        return True
    return any(_tem(p, alvo) for p in _PALAVRAS_TI)


# ------------------------------------------------------------ portais (ATS)

def ats_do_link(link: str) -> str:
    """'https://algar.gupy.io/...' -> 'gupy:algar'; greenhouse/lever idem; '' se não reconhecer."""
    link = (link or "").lower()
    m = re.search(r"https?://([a-z0-9-]+)\.gupy\.io", link)
    if m and m.group(1) not in ("portal", "www", "login"):
        return f"gupy:{m.group(1)}"
    m = re.search(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)", link)
    if m:
        return f"greenhouse:{m.group(1)}"
    m = re.search(r"jobs\.lever\.co/([a-z0-9_-]+)", link)
    if m:
        return f"lever:{m.group(1)}"
    return ""


def _slugs(nome: str, site: str) -> list[str]:
    raiz = empresas.dominio_raiz(site).split(".")[0] if site else ""
    nome_n = _norm(nome)
    candidatos = [raiz, nome_n.replace(" ", ""), nome_n.split(" ")[0] if nome_n else "",
                  nome_n.replace(" ", "-")]
    return [s for s in dict.fromkeys(c for c in candidatos if c and len(c) >= 3)]


def _gupy_vagas(sub: str, sessao) -> list[dict] | None:
    r = sessao.get(f"https://{sub}.gupy.io/", headers=_UA, timeout=15)
    if r.status_code != 200:
        return None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        return None
    jobs = (json.loads(m.group(1)).get("props") or {}).get("pageProps", {}).get("jobs")
    if not isinstance(jobs, list):
        return None
    saida = []
    for j in jobs:
        if "talent_pool" in str(j.get("type") or ""):
            continue  # "banco de talentos" não é vaga aberta
        end = ((j.get("workplace") or {}).get("address") or {})
        cidade, uf = end.get("city") or "", end.get("stateShortName") or ""
        tipo = (j.get("workplace") or {}).get("workplaceType") or ""
        saida.append({"titulo": j.get("title") or "", "local": f"{cidade} - {uf}".strip(" -") or "Não informado",
                      "modalidade": {"remote": "Remoto", "hybrid": "Híbrido", "on-site": "Presencial"}.get(tipo, ""),
                      "link": f"https://{sub}.gupy.io/jobs/{j.get('id')}", "site": "Gupy (site da empresa)"})
    return saida


def _greenhouse_vagas(token: str, sessao) -> list[dict] | None:
    r = sessao.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", headers=_UA, timeout=15)
    if r.status_code != 200:
        return None
    return [{"titulo": j.get("title") or "", "local": (j.get("location") or {}).get("name") or "",
             "modalidade": "", "link": j.get("absolute_url") or "", "site": "Greenhouse (site da empresa)"}
            for j in r.json().get("jobs") or []]


def _lever_vagas(conta: str, sessao) -> list[dict] | None:
    r = sessao.get(f"https://api.lever.co/v0/postings/{conta}?mode=json", headers=_UA, timeout=15)
    if r.status_code != 200 or not isinstance(r.json(), list):
        return None
    return [{"titulo": j.get("text") or "", "local": (j.get("categories") or {}).get("location") or "",
             "modalidade": {"remote": "Remoto", "hybrid": "Híbrido", "onsite": "Presencial"}.get(
                 str(j.get("workplaceType") or ""), ""),
             "link": j.get("hostedUrl") or "", "site": "Lever (site da empresa)"}
            for j in r.json()]


_LEITORES = {"gupy": _gupy_vagas, "greenhouse": _greenhouse_vagas, "lever": _lever_vagas}


def vagas_do_ats(ats: str, sessao=None) -> list[dict] | None:
    tipo, _, ident = (ats or "").partition(":")
    leitor = _LEITORES.get(tipo)
    if not leitor or not ident:
        return None
    try:
        return leitor(ident, sessao or requests)
    except (requests.RequestException, ValueError) as e:
        logger.warning(f"[Sites das empresas] {ats}: {e}")
        return None


def descobrir_ats(nome: str, site: str, portal: str = "", sessao=None) -> str:
    """Portal já conhecido, ou testa <slug>.gupy.io, Greenhouse e Lever."""
    sessao = sessao or requests
    conhecido = ats_do_link(portal)
    if conhecido:
        return conhecido
    for slug in _slugs(nome, site):
        for tipo in ("gupy", "greenhouse", "lever"):
            # As três APIs devolvem 404 para empresa que não existe; lista (mesmo vazia) = portal achado.
            if vagas_do_ats(f"{tipo}:{slug}", sessao) is not None:
                return f"{tipo}:{slug}"
    return ""


# ------------------------------------------------------------ coleta

def _foco(preferencias: dict) -> str:
    foco = preferencias.get("foco_regional") or {}
    return _norm(foco.get("cidade") or "") if foco.get("ativo") else ""


def coletar(preferencias: dict, maximo_empresas: int = 120, paralelo: int = 6) -> int:
    """Puxa as vagas abertas nos sites das empresas da lista e põe na fila."""
    empresas.sincronizar_lista()
    with repositorio.conectar() as conn:
        linhas = [dict(l) for l in conn.execute("SELECT * FROM empresas")]
    foco = _foco(preferencias)
    agora = datetime.now()
    limite_recheck = (agora - timedelta(days=RECHECAR_DIAS)).isoformat(timespec="seconds")

    def prioridade(l):
        return (0 if foco and _norm(l.get("cidade") or "") == foco else 1, l.get("tipo") == "Big Tech", l["nome"])

    linhas = sorted(linhas, key=prioridade)[:maximo_empresas]

    def processar(linha: dict) -> tuple[dict, str, list[dict]]:
        sessao = requests.Session()
        ats = linha.get("ats") or ""
        if not ats and (linha.get("ats_verificado_em") or "") < limite_recheck:
            ats = descobrir_ats(linha["nome"], linha.get("site") or "", linha.get("portal") or "", sessao)
        vagas = vagas_do_ats(ats, sessao) if ats else None
        return linha, ats, vagas or []

    novas = 0
    with ThreadPoolExecutor(max_workers=paralelo) as pool:
        resultados = list(pool.map(processar, linhas))
    with repositorio.conectar() as conn:
        for linha, ats, _ in resultados:
            conn.execute("UPDATE empresas SET ats = ?, ats_verificado_em = ? WHERE dominio = ?",
                         (ats or None, agora.isoformat(timespec="seconds"), linha["dominio"]))
    for linha, ats, vagas in resultados:
        aceitas = 0
        for v in vagas:
            if not v["titulo"] or not v["link"] or not combina_com_perfil(v["titulo"], preferencias):
                continue
            vaga = {**v, "id": repositorio.gerar_id(v["link"]), "empresa": linha["nome"], "origem": "empresa",
                    "local": v["local"] or linha.get("cidade") or ""}
            if repositorio.existe_semelhante(vaga["titulo"], None, vaga["empresa"]):
                continue
            if repositorio.inserir(vaga):
                novas += 1
                aceitas += 1
        if ats:
            logger.info(f"[Sites das empresas] {linha['nome']} ({ats}): {len(vagas)} abertas, {aceitas} nova(s) p/ você")
    logger.info(f"[Sites das empresas] {novas} vaga(s) nova(s) de {sum(1 for _, a, _ in resultados if a)} portais")
    return novas
