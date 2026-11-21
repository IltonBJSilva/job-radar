"""E-mail de RH das empresas pelo Hunter.io (opcional, com a SUA chave grátis).

O Hunter lista e-mails PÚBLICOS de um domínio por departamento. Usamos o de
RH ("hr") e escolhemos, nesta ordem: endereço genérico de recrutamento
(vagas@, rh@, talentos@...) e depois uma pessoa com cargo de recrutamento,
sempre com confiança >= 70% e do próprio domínio da empresa. O plano grátis
tem poucas buscas por mês, então só gastamos com empresa SEM e-mail.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import requests

from candidatura import areas, config, empresas, repositorio
from candidatura.contato import email_valido
from core.logger import get_logger

logger = get_logger()

URL = "https://api.hunter.io/v2"
CONFIANCA_MINIMA = 70
_CARGO_RECRUTAMENTO = re.compile(r"recrut|recruit|talent|talento|\brh\b|human resources|recursos humanos|people|"
                                 r"gente e gest|acquisition|hiring|selec", re.I)


def disponivel() -> bool:
    return bool(config.HUNTER_API_KEY)


def creditos(sessao=None) -> dict | None:
    """{"usadas": n, "disponiveis": n} das buscas do mês, ou None se a chave falhar."""
    try:
        r = (sessao or requests).get(f"{URL}/account", params={"api_key": config.HUNTER_API_KEY}, timeout=15)
        if r.status_code != 200:
            return None
        buscas = ((r.json().get("data") or {}).get("requests") or {}).get("searches") or {}
        return {"usadas": int(buscas.get("used") or 0), "disponiveis": int(buscas.get("available") or 0)}
    except (requests.RequestException, ValueError):
        return None


def escolher(emails: list[dict], dominio: str) -> dict | None:
    validos = [e for e in emails
               if e.get("value") and email_valido(e["value"]) and empresas.do_dominio(e["value"], dominio)
               and int(e.get("confidence") or 0) >= CONFIANCA_MINIMA]
    genericos = [e for e in validos if e.get("type") == "generic"
                 and e["value"].split("@")[0].startswith(empresas.PREFIXOS_RECRUTAMENTO)]
    pessoas = [e for e in validos if e.get("type") == "personal" and _CARGO_RECRUTAMENTO.search(e.get("position") or "")]
    for grupo in (genericos, pessoas):
        if grupo:
            return max(grupo, key=lambda e: int(e.get("confidence") or 0))
    return None


def email_de_rh(dominio: str, sessao=None) -> dict:
    """{"email", "descricao", "erro"} — descrição diz de onde veio (ex.: "Ana Lima, Talent Acquisition")."""
    try:
        r = (sessao or requests).get(f"{URL}/domain-search", timeout=20, params={
            "domain": dominio, "department": "hr", "limit": 10, "api_key": config.HUNTER_API_KEY})
    except requests.RequestException as e:
        return {"email": "", "descricao": "", "erro": f"Hunter fora do ar: {e}"}
    if r.status_code == 401:
        return {"email": "", "descricao": "", "erro": "chave do Hunter inválida"}
    if r.status_code == 429:
        return {"email": "", "descricao": "", "erro": "acabaram as buscas do mês no Hunter"}
    if r.status_code != 200:
        return {"email": "", "descricao": "", "erro": f"Hunter respondeu HTTP {r.status_code}"}
    escolhido = escolher((r.json().get("data") or {}).get("emails") or [], dominio)
    if not escolhido:
        return {"email": "", "descricao": "", "erro": "Hunter não tem e-mail de RH confiável"}
    pessoa = " ".join(x for x in (escolhido.get("first_name"), escolhido.get("last_name")) if x)
    descricao = ", ".join(x for x in (pessoa, escolhido.get("position")) if x) or "endereço de RH"
    return {"email": escolhido["value"].lower(), "descricao": f"{descricao} (Hunter, {escolhido.get('confidence')}%)",
            "erro": ""}


def completar_empresas(preferencias: dict | None = None, limite: int = 10, dominios: list[str] | None = None,
                       sessao=None) -> dict:
    """Procura no Hunter as empresas da lista que ainda não têm e-mail (cidade do foco primeiro)."""
    if not disponivel():
        raise RuntimeError("Configure a chave do Hunter em Configurações → Chaves.")
    empresas.sincronizar_lista()
    foco = areas.foco_regional(preferencias or {})
    with repositorio.conectar() as conn:
        linhas = [dict(l) for l in conn.execute("SELECT * FROM empresas WHERE email IS NULL")]
    linhas = [l for l in linhas if (l.get("tipo") or "").lower() != "big tech"
              and (dominios is None or l["dominio"] in dominios)]
    linhas.sort(key=lambda l: (not (foco and (l.get("cidade") or "").lower() == foco["cidade"].lower()), l["nome"]))
    achados, erros = 0, []
    for linha in linhas[:limite]:
        r = email_de_rh(linha["dominio"], sessao)
        if r["erro"] in ("chave do Hunter inválida", "acabaram as buscas do mês no Hunter"):
            erros.append(r["erro"])
            break
        with repositorio.conectar() as conn:
            if r["email"]:
                conn.execute("UPDATE empresas SET email = ?, emails = ?, erro = ?, verificada_em = ? WHERE dominio = ?",
                             (r["email"], json.dumps([r["email"]]), f"via {r['descricao']}",
                              datetime.now().isoformat(timespec="seconds"), linha["dominio"]))
                achados += 1
            else:
                conn.execute("UPDATE empresas SET erro = ? WHERE dominio = ?", (r["erro"], linha["dominio"]))
        logger.info(f"[Hunter] {linha['nome']}: {r['email'] or r['erro']}")
    return {"consultadas": min(len(linhas), limite), "achados": achados, "erros": erros}
