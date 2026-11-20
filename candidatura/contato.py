"""Achar a descrição completa de uma vaga e o e-mail para candidatura."""

from __future__ import annotations

import json
import re

import requests

from core.logger import get_logger

logger = get_logger()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# E-mails que aparecem em anúncio mas não recebem currículo.
_PREFIXOS_IGNORADOS = (
    "noreply", "no-reply", "nao-responda", "naoresponda", "donotreply", "do-not-reply",
    "privacidade", "privacy", "dpo", "lgpd", "suporte", "support", "sac", "ouvidoria",
    "abuse", "postmaster", "mailer-daemon", "notifications", "notificacoes",
)
_DOMINIOS_IGNORADOS = (
    "example.com", "exemplo.com", "email.com", "domain.com", "sentry.io", "linkedin.com",
    "gupy.io", "solides.com.br", "indeed.com", "catho.com.br", "github.com", "users.noreply.github.com",
    "wixpress.com", "sentry.wixpress.com",
)
_PALAVRAS_CANDIDATURA = ("curriculo", "currículo", "cv", "candidat", "envie", "enviar", "resume", "apply", "vaga", "rh", "talent", "recrut", "jobs", "carreira")


def email_valido(email: str) -> bool:
    email = (email or "").strip().lower()
    if not _RE_EMAIL.fullmatch(email):
        return False
    usuario, dominio = email.rsplit("@", 1)
    if any(usuario.startswith(p) for p in _PREFIXOS_IGNORADOS):
        return False
    if any(dominio == d or dominio.endswith("." + d) for d in _DOMINIOS_IGNORADOS):
        return False
    if dominio.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return False
    return True


def extrair_emails(texto: str) -> list[str]:
    """E-mails válidos do texto, priorizando os que aparecem perto de
    palavras como "currículo", "envie", "candidatura"."""
    if not texto:
        return []
    candidatos: dict[str, int] = {}
    for m in _RE_EMAIL.finditer(texto):
        email = m.group(0).strip(".").lower()
        if not email_valido(email):
            continue
        janela = texto[max(0, m.start() - 120): m.end() + 40].lower()
        relevancia = sum(1 for p in _PALAVRAS_CANDIDATURA if p in janela)
        relevancia += sum(1 for p in ("rh", "vagas", "jobs", "talent", "recrut", "carreira", "people") if p in email.split("@")[0])
        candidatos[email] = max(candidatos.get(email, 0), relevancia)
    return sorted(candidatos, key=lambda e: -candidatos[e])


def _texto_de_html(html: str) -> str:
    from bs4 import BeautifulSoup

    sopa = BeautifulSoup(html, "html.parser")

    # 1) JSON-LD JobPosting (Gupy, Sólides, Greenhouse, Lever e muitos ATS publicam).
    for bloco in sopa.find_all("script", type="application/ld+json"):
        try:
            dados = json.loads(bloco.string or "")
        except Exception:
            continue
        itens = dados if isinstance(dados, list) else [dados]
        for item in itens:
            if isinstance(item, dict) and item.get("@type") == "JobPosting" and item.get("description"):
                return BeautifulSoup(item["description"], "html.parser").get_text("\n", strip=True)

    # 2) Seções conhecidas de descrição.
    for seletor in (
        ".show-more-less-html__markup",       # LinkedIn
        "#jobDescriptionText",                # Indeed
        "[data-testid='job-description']",
        "article", "main",
    ):
        alvo = sopa.select_one(seletor)
        if alvo and len(alvo.get_text(strip=True)) > 200:
            return alvo.get_text("\n", strip=True)

    for lixo in sopa(["script", "style", "nav", "footer", "header", "noscript"]):
        lixo.decompose()
    return sopa.get_text("\n", strip=True)


def _url_linkedin_guest(link: str) -> str | None:
    m = re.search(r"linkedin\.com/jobs/view/(?:[^/?]*-)?(\d{6,})", link)
    if m:
        return f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}"
    return None


def buscar_descricao(link: str, timeout: int = 20) -> str:
    """Baixa a página da vaga e devolve só o texto da descrição ('' se falhar)."""
    if not link:
        return ""
    url = _url_linkedin_guest(link) or link
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}, timeout=timeout)
        if r.status_code != 200:
            logger.info(f"[Contato] HTTP {r.status_code} ao baixar {url}")
            return ""
        # mailto: costuma estar só no atributo href, fora do texto visível.
        mailtos = " ".join(re.findall(r"mailto:([^\"'?>\s]+)", r.text))
        texto = _texto_de_html(r.text)
        return (texto + ("\n" + mailtos if mailtos else "")).strip()
    except Exception as e:
        logger.info(f"[Contato] Falha ao baixar {url}: {e}")
        return ""
