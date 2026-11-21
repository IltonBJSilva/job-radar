"""Lê um post de recrutador ("Estamos contratando Dev Python! Envie o CV para
vagas@empresa.com.br") e monta a vaga: cargo, empresa, e-mail, local e link.

Usado pelo "Colar post" (você cola o texto do LinkedIn/WhatsApp/Instagram) e
pela busca de posts públicos. Nada é inventado: o que não estiver no texto
fica vazio para você completar.
"""

from __future__ import annotations

import re

from candidatura.contato import email_valido, emails_com_relevancia

_DOMINIOS_PESSOAIS = ("gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br", "live.com",
                      "icloud.com", "bol.com.br", "uol.com.br", "terra.com.br", "protonmail.com")

_CARGO = re.compile(
    r"((?:pessoa\s+)?(?:desenvolvedor[a]?|developer|dev|engenheir[oa]|engineer|analista|programador[a]?|"
    r"arquitet[oa]|cientista|especialista|t[eé]cnic[oa]|coordenador[a]?|tech\s*lead|l[ií]der\s+t[eé]cnico|"
    r"estagi[aá]ri[oa]|est[aá]gio|trainee|scrum\s*master|product\s*(?:owner|manager)|designer|qa|sre|devops|"
    r"suporte|consultor[a]?|administrador[a]?)"
    r"(?:\s*\(a\))?(?:[ \t]+[^\n.!?,;:|#@()\[\]]{0,60}?)?)"
    r"(?=\s*(?:[\n.!?,;:|#@(\[]|\s-\s|\s–\s|\s+para\s|\s+em\s|\s+na\s|\s+no\s|\s+com\s|$))",
    re.I,
)
_EMPRESA = re.compile(
    r"(?:^|[\s,.!])(?i:a|o|na|no|da|do|aqui na|aqui no|time da|time do|equipe da|equipe do)\s+"
    r"((?:[A-Z0-9][\w&.'-]*)(?:\s+(?:[A-Z0-9&][\w&.'-]*)){0,3})\s+"
    r"(?i:est[áa]\s+contratando|contrata|est[áa]\s+com\s+vaga|abriu|abre|busca|procura|tem\s+vaga|est[áa]\s+buscando)",
)
_MODALIDADE = (("Remoto", r"\bremot[oa]\b|home\s*office|100%\s*remoto|\bremote\b"),
               ("Híbrido", r"h[ií]brid[oa]|\bhybrid\b"),
               ("Presencial", r"\bpresencial\b|on-?site"))
_URL = re.compile(r"https?://[^\s<>\"')]+", re.I)


def _limpar(texto: str) -> str:
    texto = re.sub(r"[\U0001F000-\U0001FFFF☀-➿️]", " ", texto or "")  # emojis
    return re.sub(r"[ \t]+", " ", texto)


def _empresa_do_email(email: str) -> str:
    dominio = email.split("@", 1)[1] if "@" in email else ""
    if not dominio or dominio in _DOMINIOS_PESSOAIS:
        return ""
    base = dominio.split(".")[0]
    return base.upper() if len(base) <= 4 else base.replace("-", " ").title()


def ler_post(texto: str) -> dict:
    """{titulo, empresa, email, emails, local, modalidade, link, descricao}."""
    limpo = _limpar(texto)
    relevancia = emails_com_relevancia(limpo)
    emails = [e for e in sorted(relevancia, key=lambda e: -relevancia[e]) if email_valido(e)]
    email = emails[0] if emails else ""

    titulo = ""
    for m in _CARGO.finditer(limpo):
        candidato = re.sub(r"\s+", " ", m.group(1)).strip(" -–")
        if len(candidato.split()) >= 2 or re.search(r"(?i)devops|sre|qa|trainee", candidato):
            titulo = candidato[:90]
            break
    titulo = re.sub(r"(?i)^pessoa\s+", "", titulo)
    titulo = titulo[:1].upper() + titulo[1:] if titulo else ""

    m = _EMPRESA.search(limpo)
    empresa = m.group(1).strip() if m else ""
    empresa = re.sub(r"(?i)(?:\s+(?:est[áa]|tem|j[áa]))+$", "", empresa)  # "Algar Tech ESTÁ contratando"
    if not empresa and email:
        empresa = _empresa_do_email(email)
    links_texto = _URL.findall(texto or "")
    if not empresa:  # "https://algar.gupy.io/jobs/1" -> "Algar"
        sub = next((m.group(1) for u in links_texto for m in [re.search(r"https?://([a-z0-9-]+)\.gupy\.io", u, re.I)] if m), "")
        empresa = sub.replace("-", " ").title() if sub else ""

    local = ""
    from candidatura import localidades

    for linha in limpo.splitlines():
        pedacos = re.split(r"[|•·,;()]|\s-\s|\s–\s", linha)
        # "... (SOC) em Belo Horizonte." -> também testa o que vem depois de "em"/"in".
        pedacos += [m.group(1) for m in re.finditer(r"\b(?:em|in)\s+([^\n.,;!?()|]{3,40})", linha)]
        for pedaco in pedacos:
            achado = localidades.extrair(pedaco)
            if achado["cidade"] and achado["uf"]:
                local = f"{achado['cidade']} - {achado['uf']}"
                break
        if local:
            break

    modalidade = next((nome for nome, padrao in _MODALIDADE if re.search(padrao, limpo, re.I)), "")
    links = [u.rstrip(".,;") for u in _URL.findall(texto or "")]
    link = next((u for u in links if "linkedin.com" in u), links[0] if links else "")
    return {
        "titulo": titulo, "empresa": empresa, "email": email, "emails": emails,
        "local": local or (modalidade if modalidade == "Remoto" else ""), "modalidade": modalidade,
        "link": link, "descricao": (texto or "").strip(),
    }
