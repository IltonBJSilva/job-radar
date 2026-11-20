"""Fontes extras que alimentam a fila de candidaturas DIRETAMENTE (não passam
pelo radar/Telegram), escolhidas porque trazem descrição completa e, com
frequência, um e-mail para envio de currículo.

- GitHub "vagas" (backend-br, frontendbr, react-brasil...): comunidade
  brasileira publica vagas como issues; ~15% trazem e-mail no corpo.
  API pública, sem token: 60 req/h por IP (com GITHUB_TOKEN: 5.000/h).
- Remotar (api.remotar.com.br): vagas remotas em JSON com descrição.
"""

from __future__ import annotations

import os
import re

import requests

from candidatura import repositorio
from candidatura.contato import extrair_emails
from core.logger import get_logger
from scrapers.solides import html_para_texto

logger = get_logger()

REPOS_GITHUB = [
    "backend-br/vagas",
    "frontendbr/vagas",
    "react-brasil/vagas",
    "datascience-br/vagas",  # vagas de Python/dados, ~1/3 com e-mail
]

_UA = {"User-Agent": "job-radar-candidatura"}


def _empresa_do_titulo(titulo: str) -> str:
    """'[Remoto] Dev Backend Pleno na Empresa X' -> 'Empresa X'.
    '[Remoto] Dev Backend - Empresa X' -> 'Empresa X'."""
    sem_tags = re.sub(r"\[[^\]]*\]", "", titulo).strip()
    empresa = ""
    for sep in (" na ", " no ", " @ ", " at "):
        if sep in sem_tags:
            empresa = sem_tags.rsplit(sep, 1)[1].strip(" -|")
            break
    else:
        if " - " in sem_tags:
            empresa = sem_tags.rsplit(" - ", 1)[1].strip()
    # "Igma | PJ" -> "Igma"; "Kafka(Strider))" -> descartado abaixo
    empresa = re.split(r"\s*[|(\[]", empresa)[0].strip(" -,")
    if (empresa.lower() in _NAO_EMPRESA or len(empresa) < 3 or len(empresa) > 40
            or "," in empresa or re.fullmatch(r"[A-Z]{2}", empresa)):
        return ""
    return empresa


_RE_NAO_VAGA = re.compile(r"\bregras?\b|\bleia\b|aten[cç][aã]o|read\s*me|como (publicar|divulgar)", re.I)

_NAO_EMPRESA = {"remoto", "remote", "híbrido", "hibrido", "presencial", "pj", "clt", "júnior", "junior",
                "pleno", "sênior", "senior", "brasil", "home office", "temporário", "freelancer"}


def _modalidade_das_tags(textos: list[str]) -> str:
    alvo = " ".join(textos).lower()
    if "remot" in alvo:
        return "Remoto"
    if "híbrido" in alvo or "hibrido" in alvo:
        return "Híbrido"
    if "presencial" in alvo:
        return "Presencial"
    return ""


def issue_para_vaga(issue: dict, repo: str) -> dict | None:
    if "pull_request" in issue:
        return None
    titulo = (issue.get("title") or "").strip()
    if _RE_NAO_VAGA.search(titulo):
        return None
    corpo = issue.get("body") or ""
    rotulos = [l.get("name", "") for l in issue.get("labels", [])]
    emails = extrair_emails(corpo)
    titulo_limpo = re.sub(r"\s*\[[^\]]*\]\s*", " ", titulo).strip()
    empresa = _empresa_do_titulo(titulo)
    if empresa:
        # "Dev Backend na Empresa X" -> título "Dev Backend" (empresa vai no campo próprio)
        for sep in (" na ", " no ", " @ ", " at ", " - "):
            sufixo = f"{sep}{empresa}"
            if titulo_limpo.endswith(sufixo):
                titulo_limpo = titulo_limpo[: -len(sufixo)].strip(" -|")
                break
    return {
        "id": repositorio.gerar_id(issue.get("html_url", "")),
        "titulo": titulo_limpo,
        "empresa": empresa,
        "local": ", ".join(r for r in rotulos if r.lower() in {"remoto", "híbrido", "hibrido", "presencial"}),
        "modalidade": _modalidade_das_tags([titulo] + rotulos),
        "link": issue.get("html_url", ""),
        "site": f"GitHub {repo.split('/')[0]}",
        "origem": "github",
        "publicado_em": (issue.get("created_at") or "")[:10],
        "descricao": corpo[:20000],
        "emails_encontrados": emails,
        "email_destino": emails[0] if emails else None,
    }


def coletar_github(repos: list[str] | None = None, por_repo: int = 100) -> int:
    cabecalhos = dict(_UA, Accept="application/vnd.github+json")
    token = os.getenv("GITHUB_TOKEN")
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    novas = 0
    for repo in repos or REPOS_GITHUB:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page={min(por_repo, 100)}&sort=created&direction=desc"
        try:
            r = requests.get(url, headers=cabecalhos, timeout=20)
            if r.status_code != 200:
                logger.warning(f"[GitHub] {repo}: HTTP {r.status_code} {r.text[:120]}")
                continue
            for issue in r.json():
                vaga = issue_para_vaga(issue, repo)
                if not vaga or repositorio.existe_semelhante(vaga["titulo"], vaga.get("email_destino"), vaga.get("empresa")):
                    continue
                if repositorio.inserir(vaga):
                    novas += 1
        except Exception as e:
            logger.warning(f"[GitHub] {repo}: {e}")
    logger.info(f"[GitHub] {novas} vaga(s) nova(s) na fila")
    return novas


def remotar_para_vaga(item: dict) -> dict:
    descricao = html_para_texto(item.get("description") or "")
    empresa = (item.get("company") or {}).get("name") or item.get("companyDisplayName") or ""
    link = item.get("externalLink") if item.get("isExternalLink") else ""
    link = link or f"https://remotar.com.br/job/{item.get('id')}"
    emails = extrair_emails(descricao)
    return {
        "id": repositorio.gerar_id(f"remotar:{item.get('id')}"),
        "titulo": (item.get("title") or "").strip(),
        "empresa": empresa,
        "local": "Remoto",
        "modalidade": "Remoto" if item.get("type") == "remote" else "",
        "link": link,
        "site": "Remotar",
        "origem": "remotar",
        "publicado_em": (item.get("createdAt") or "")[:10],
        "descricao": descricao[:20000],
        "emails_encontrados": emails,
        "email_destino": emails[0] if emails else None,
    }


def coletar_remotar(termos: list[str], paginas: int = 1) -> int:
    novas = 0
    for termo in termos:
        for pagina in range(1, paginas + 1):
            try:
                r = requests.get(
                    "https://api.remotar.com.br/jobs",
                    params={"search": termo, "page": pagina},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=20,
                )
                if r.status_code != 200:
                    logger.warning(f"[Remotar] '{termo}': HTTP {r.status_code}")
                    break
                itens = r.json().get("data") or []
                for item in itens:
                    if item.get("expired") or item.get("active") is False:
                        continue
                    vaga = remotar_para_vaga(item)
                    if repositorio.existe_semelhante(vaga["titulo"], vaga.get("email_destino"), vaga.get("empresa")):
                        continue
                    if repositorio.inserir(vaga):
                        novas += 1
                if len(itens) < 50:
                    break
            except Exception as e:
                logger.warning(f"[Remotar] '{termo}': {e}")
                break
    logger.info(f"[Remotar] {novas} vaga(s) nova(s) na fila")
    return novas
