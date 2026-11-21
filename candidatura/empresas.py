"""Candidatura espontânea: envia seu currículo para empresas (fábricas de
software, consultorias, produto) mesmo sem vaga aberta anunciada.

Como o e-mail é achado (sem inventar endereço):
  1. lê a página inicial do site OFICIAL da empresa e as páginas de
     "Trabalhe conosco / Carreiras / Vagas / Contato" linkadas nela;
  2. guarda só e-mails do PRÓPRIO domínio da empresa (nunca gmail etc.);
  3. prioriza os de recrutamento (rh@, vagas@, talentos@, carreiras@...);
  4. se a empresa só recebe currículo por portal (Gupy, Greenhouse,
     Workday...), guarda o link do portal — essas ficam em "Sem e-mail" com o
     PDF pronto para você anexar lá. Big techs funcionam assim.

Lista de empresas: config/empresas.example.yaml (pronta) + config/empresas.yaml
(as suas, opcional). Cada candidatura vai num e-mail separado, 1 por empresa,
respeitando o limite diário e o intervalo entre envios.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse

import yaml

from candidatura import config, repositorio
from candidatura.contato import _baixar, email_valido, emails_com_relevancia
from core.logger import get_logger

logger = get_logger()

PREFIXOS_RECRUTAMENTO = ("rh", "vagas", "vaga", "talentos", "talento", "talent", "carreiras", "carreira",
                         "careers", "career", "jobs", "job", "recrutamento", "recruiting", "recruitment",
                         "selecao", "curriculo", "curriculos", "cv", "people", "pessoas", "gente", "trabalheconosco",
                         "hr", "hiring", "recrutamentoeselecao", "atracao")
PREFIXOS_GERAIS = ("contato", "contact", "faleconosco", "hello", "ola", "oi", "info", "comercial")

_RE_LINK_CARREIRA = re.compile(r"trabalhe|carreira|careers?|vagas|jobs|join|fa[cç]a parte|junte-se|talent|"
                               r"oportunidades|work with us|contato|contact|fale conosco", re.I)
PORTAIS_ATS = ("gupy.io", "kenoby.com", "solides.jobs", "vagas.solides.com.br", "greenhouse.io", "lever.co",
               "workable.com", "inhire.app", "abler.com.br", "pandape", "recrutei.com.br", "breezy.hr",
               "myworkdayjobs.com", "smartrecruiters.com", "taleo.net", "teamtailor.com", "factorialhr",
               "bamboohr.com", "jobvite.com", "successfactors", "icims.com", "ashbyhq.com", "99jobs.com")
CAMINHOS_COMUNS = ("/trabalhe-conosco", "/carreiras", "/careers", "/vagas", "/contato")


@dataclass
class Empresa:
    nome: str
    site: str
    tipo: str = ""
    cidade: str = ""
    email: str = ""      # se você já sabe o e-mail de RH, ele é usado direto
    portal: str = ""     # página de carreiras (quando só aceita por portal)


# --------------------------------------------------------------- lista

def _caminhos_lista() -> list:
    return [config.RAIZ / "config" / "empresas.example.yaml", config.RAIZ / "config" / "empresas.yaml"]


def carregar_empresas(caminhos: list | None = None) -> list[Empresa]:
    vistas: dict[str, Empresa] = {}
    for caminho in caminhos or _caminhos_lista():
        if not caminho.exists():
            continue
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
        for item in dados.get("empresas") or []:
            if not isinstance(item, dict) or not item.get("nome") or not item.get("site"):
                continue
            e = Empresa(nome=str(item["nome"]).strip(), site=_normalizar_site(str(item["site"])),
                        tipo=str(item.get("tipo") or ""), cidade=str(item.get("cidade") or ""),
                        email=str(item.get("email") or "").strip().lower(), portal=str(item.get("portal") or ""))
            vistas[dominio_raiz(e.site)] = e  # o seu arquivo sobrescreve o exemplo
    return list(vistas.values())


def _normalizar_site(site: str) -> str:
    site = site.strip()
    if not site.startswith(("http://", "https://")):
        site = "https://" + site
    return site.rstrip("/")


_SUFIXOS_DUPLOS = ("com.br", "org.br", "net.br", "gov.br", "edu.br", "ind.br", "co.uk", "com.ar", "com.mx")


def dominio_raiz(url_ou_dominio: str) -> str:
    """'https://www.carreiras.ciandt.com/x' -> 'ciandt.com'; 'sub.empresa.com.br' -> 'empresa.com.br'."""
    host = urlparse(url_ou_dominio if "//" in url_ou_dominio else "//" + url_ou_dominio).hostname or ""
    partes = host.lower().split(".")
    for sufixo in _SUFIXOS_DUPLOS:
        n = sufixo.count(".") + 1
        if len(partes) > n and ".".join(partes[-n:]) == sufixo:
            return ".".join(partes[-(n + 1):])
    return ".".join(partes[-2:])


def do_dominio(email: str, site: str) -> bool:
    dominio = email.rsplit("@", 1)[-1].lower()
    raiz = dominio_raiz(site)
    return bool(raiz) and (dominio == raiz or dominio.endswith("." + raiz))


def prioridade(email: str, relevancia: int = 0) -> int:
    """3 = recrutamento claro; 2 = citado como canal de currículo; 1 = genérico; 0 = outro."""
    usuario = re.sub(r"[^a-z]", "", email.split("@")[0].lower())
    if any(usuario == p or usuario.startswith(p) for p in PREFIXOS_RECRUTAMENTO):
        return 3
    # comercial@/contato@ nunca viram destino sozinhos, mesmo perto de um
    # link "Vagas" no rodapé: currículo ali costuma ser ignorado.
    if any(usuario.startswith(p) for p in PREFIXOS_GERAIS):
        return 1
    if relevancia > 0:
        return 2
    return 0


# ---------------------------------------------------------- descoberta

def _links_da_pagina(html: str, base: str) -> list[tuple[str, str]]:
    from bs4 import BeautifulSoup

    sopa = BeautifulSoup(html, "html.parser")
    saida = []
    for a in sopa.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        saida.append((urljoin(base, href), " ".join(a.get_text(" ", strip=True).split())[:80]))
    return saida


def _texto_e_mailtos(html: str) -> str:
    from bs4 import BeautifulSoup

    mailtos = " ".join(re.findall(r"mailto:([^\"'?>\s]+)", html))
    sopa = BeautifulSoup(html, "html.parser")
    for lixo in sopa(["script", "style", "noscript"]):
        lixo.decompose()
    # Rodapé fica: é lá que muitas empresas põem "trabalhe conosco: rh@...".
    return sopa.get_text("\n", strip=True) + "\n" + mailtos


def _varrer(empresa: Empresa, baixar, max_paginas: int, pausa: float, achados: dict, resultado: dict):
    raiz = dominio_raiz(empresa.site)
    fila = [empresa.site]
    vistos: set[str] = set()
    paginas = tentativas = 0
    while fila and paginas < max_paginas and tentativas < max_paginas * 2:
        url = fila.pop(0)
        if url in vistos:
            continue
        vistos.add(url)
        tentativas += 1
        try:
            html = baixar(url)
        except Exception as e:  # rede, TLS, timeout
            html = None
            resultado["erro"] = str(e)[:120]
        if pausa and paginas:
            time.sleep(pausa)
        if not html:
            continue
        paginas += 1
        resultado["paginas"] += 1
        for email, rel in emails_com_relevancia(_texto_e_mailtos(html)).items():
            if do_dominio(email, empresa.site):
                achados[email] = max(achados.get(email, 0), rel)
        for link, texto in _links_da_pagina(html, url):
            host = (urlparse(link).hostname or "").lower()
            if any(p in host or p in link.lower() for p in PORTAIS_ATS):
                resultado["portal"] = resultado["portal"] or link
                continue
            if dominio_raiz(link) == raiz and link not in vistos and _RE_LINK_CARREIRA.search(f"{texto} {link}"):
                fila.append(link.split("#")[0])
        if url == empresa.site:
            # Sites que não linkam a página de carreiras na home.
            fila += [empresa.site + c for c in CAMINHOS_COMUNS if empresa.site + c not in fila]


class NavegadorRenderizado:
    """Chromium (Playwright) para sites que só mostram o conteúdo com JavaScript."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        from candidatura.contato import UA

        self._pw = sync_playwright().start()
        self._navegador = self._pw.chromium.launch(headless=True)
        self._contexto = self._navegador.new_context(user_agent=UA, locale="pt-BR")
        # Sem imagens/fontes/vídeo: só o texto importa (bem mais rápido).
        self._contexto.route("**/*", lambda rota: rota.abort()
                             if rota.request.resource_type in ("image", "font", "media") else rota.continue_())
        return self

    def __exit__(self, *_):
        for fechar in (self._contexto.close, self._navegador.close, self._pw.stop):
            try:
                fechar()
            except Exception:
                pass

    def baixar(self, url: str) -> str | None:
        from candidatura.contato import url_publica

        if not url_publica(url):
            return None
        pagina = self._contexto.new_page()
        try:
            r = pagina.goto(url, wait_until="domcontentloaded", timeout=20000)
            if r is not None and r.status >= 400:
                return None
            pagina.wait_for_timeout(1500)
            return pagina.content()
        except Exception:
            return None
        finally:
            pagina.close()


def descobrir(empresa: Empresa, baixar=None, max_paginas: int = 6, pausa: float = 0.8, renderizar=None) -> dict:
    """Procura o e-mail de recrutamento e/ou o portal de carreiras da empresa."""
    baixar = baixar or (lambda url: _baixar(url, timeout=15))
    resultado = {"email": "", "emails": [], "portal": empresa.portal, "paginas": 0, "erro": ""}
    if empresa.email and email_valido(empresa.email):
        resultado.update(email=empresa.email, emails=[empresa.email])
        return resultado
    if empresa.tipo.lower() == "big tech" and empresa.portal:
        return resultado  # não recebem CV por e-mail: só o portal

    achados: dict[str, int] = {}
    _varrer(empresa, baixar, max_paginas, pausa, achados, resultado)
    if renderizar and not any(prioridade(e, r) >= 2 for e, r in achados.items()):
        # Site montado por JavaScript: o HTML "cru" vem vazio. Abre de verdade.
        _varrer(empresa, renderizar, 3, 0, achados, resultado)

    ordenados = sorted(achados, key=lambda e: (-prioridade(e, achados[e]), -achados[e], e))
    resultado["emails"] = ordenados
    # Só "recrutamento" vira destino automático; contato@/comercial@ ficam para você decidir.
    melhor = next((e for e in ordenados if prioridade(e, achados[e]) >= 2), "")
    resultado["email"] = melhor
    if resultado["paginas"]:
        resultado["erro"] = ""
    elif not resultado["erro"]:
        resultado["erro"] = "site não respondeu"
    return resultado


# -------------------------------------------------------- persistência

_TABELA = """
CREATE TABLE IF NOT EXISTS empresas (
    dominio TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    site TEXT,
    tipo TEXT,
    cidade TEXT,
    email TEXT,
    emails TEXT,
    portal TEXT,
    erro TEXT,
    verificada_em TEXT,
    candidatura_id TEXT
)
"""


def iniciar():
    repositorio.iniciar()
    with repositorio.conectar() as conn:
        conn.execute(_TABELA)
        # Onde a empresa publica as vagas ("gupy:algar", "greenhouse:zupinnovation"...), para não procurar de novo.
        existentes = {l[1] for l in conn.execute("PRAGMA table_info(empresas)")}
        for coluna in ("ats", "ats_verificado_em"):
            if coluna not in existentes:
                conn.execute(f"ALTER TABLE empresas ADD COLUMN {coluna} TEXT")


def sincronizar_lista(empresas: list[Empresa] | None = None) -> int:
    """Coloca na tabela as empresas da lista (sem apagar o que já foi descoberto)."""
    iniciar()
    empresas = carregar_empresas() if empresas is None else empresas
    novas = 0
    with repositorio.conectar() as conn:
        for e in empresas:
            cur = conn.execute(
                "INSERT OR IGNORE INTO empresas (dominio, nome, site, tipo, cidade, email, portal) VALUES (?,?,?,?,?,?,?)",
                (dominio_raiz(e.site), e.nome, e.site, e.tipo, e.cidade, e.email or None, e.portal or None),
            )
            novas += cur.rowcount
    return novas


def adicionar(nome: str, site: str, email: str = "", tipo: str = "") -> str:
    iniciar()
    site = _normalizar_site(site)
    dominio = dominio_raiz(site)
    if not nome.strip() or "." not in dominio:
        raise ValueError("Informe nome e site válido (ex.: empresa.com.br).")
    email = email.strip().lower()
    if email and not email_valido(email):
        raise ValueError(f"E-mail inválido: {email}")
    with repositorio.conectar() as conn:
        conn.execute(
            "INSERT INTO empresas (dominio, nome, site, tipo, email) VALUES (?,?,?,?,?) "
            "ON CONFLICT(dominio) DO UPDATE SET nome=excluded.nome, site=excluded.site, "
            "email=COALESCE(excluded.email, empresas.email)",
            (dominio, nome.strip(), site, tipo, email or None),
        )
    return dominio


def listar() -> list[dict]:
    iniciar()
    import json

    with repositorio.conectar() as conn:
        linhas = [dict(l) for l in conn.execute("SELECT * FROM empresas ORDER BY (email IS NULL), tipo, nome")]
    for l in linhas:
        try:
            l["emails"] = json.loads(l.get("emails") or "[]")
        except ValueError:
            l["emails"] = []
        cand = repositorio.obter(l["candidatura_id"]) if l.get("candidatura_id") else None
        l["status"] = cand["status"] if cand else ""
        l["simulado"] = cand.get("simulado") if cand else 0
    return linhas


def _salvar_descoberta(dominio: str, r: dict):
    import json

    with repositorio.conectar() as conn:
        conn.execute(
            "UPDATE empresas SET email = COALESCE(?, email), emails = ?, portal = COALESCE(?, portal), erro = ?, "
            "verificada_em = ? WHERE dominio = ?",
            (r["email"] or None, json.dumps(r["emails"]), r["portal"] or None, r["erro"] or None,
             datetime.now().isoformat(timespec="seconds"), dominio),
        )


def descobrir_todas(apenas_pendentes: bool = True, limite: int = 200, ao_progredir=None) -> dict:
    """Visita o site de cada empresa (devagar, para ser educado) e salva o que achar."""
    sincronizar_lista()
    alvo = [e for e in listar() if not (apenas_pendentes and (e.get("email") or e.get("verificada_em")))][:limite]
    com_email = 0
    try:
        navegador = NavegadorRenderizado().__enter__() if alvo else None
    except Exception as e:  # Playwright sem Chromium: segue só com HTML simples
        logger.warning(f"[Empresas] Sem navegador para sites em JavaScript: {e}")
        navegador = None
    try:
        com_email = _descobrir_lista(alvo, navegador, ao_progredir)
    finally:
        if navegador:
            navegador.__exit__(None, None, None)
    return {"visitadas": len(alvo), "com_email": com_email}


def _descobrir_lista(alvo: list[dict], navegador, ao_progredir) -> int:
    com_email = 0
    for i, linha in enumerate(alvo):
        empresa = Empresa(nome=linha["nome"], site=linha["site"], tipo=linha.get("tipo") or "",
                          email=linha.get("email") or "", portal=linha.get("portal") or "")
        try:
            r = descobrir(empresa, renderizar=navegador.baixar if navegador else None)
        except Exception as e:
            r = {"email": "", "emails": [], "portal": "", "erro": str(e)[:120]}
        _salvar_descoberta(linha["dominio"], r)
        com_email += bool(r["email"])
        logger.info(f"[Empresas] {linha['nome']}: {r['email'] or r['portal'] or r['erro'] or 'nada encontrado'}")
        if ao_progredir:
            ao_progredir(i + 1, len(alvo), linha["nome"])
        if i + 1 < len(alvo):
            time.sleep(random.uniform(0.5, 1.5))
    return com_email


# ------------------------------------------------------ candidaturas

def cargo_alvo(candidato) -> str:
    return (candidato.titulo.split("|")[0].strip() or "Desenvolvedor de Software")


def criar_candidaturas(dominios: list[str] | None = None, candidato=None) -> list[str]:
    """Cria (ou reaproveita) uma candidatura 'espontânea' por empresa, já
    marcada para preparo. Empresas contatadas há menos de 30 dias ficam de fora."""
    from candidatura.perfil import carregar_candidato

    candidato = candidato or carregar_candidato()
    cargo = cargo_alvo(candidato)
    ids = []
    for e in listar():
        if dominios is not None and e["dominio"] not in dominios:
            continue
        if not e.get("email") and not e.get("portal"):
            continue
        if e.get("status") in ("enviando", "respondida") or (e.get("status") == "enviada" and not e.get("simulado")):
            continue
        if e.get("email") and repositorio.ja_contatado(e["email"], e["nome"], config.DIAS_SEM_REPETIR_EMPRESA,
                                                      e.get("candidatura_id") or ""):
            continue
        id_ = repositorio.gerar_id(f"espontanea:{e['dominio']}")
        vaga = {
            "id": id_, "titulo": cargo, "empresa": e["nome"], "link": e.get("portal") or e["site"],
            "site": "Espontânea", "origem": "espontanea", "local": e.get("cidade") or "",
            "email_destino": e.get("email") or None, "emails_encontrados": e.get("emails") or [],
            "status": "curtida",
        }
        if not repositorio.inserir(vaga):
            atual = repositorio.obter(id_) or {}
            if atual.get("status") in ("enviando", "respondida") or (atual.get("status") == "enviada" and not atual.get("simulado")):
                continue
            repositorio.atualizar(id_, status="curtida", titulo=cargo, email_destino=e.get("email") or None,
                                  link=vaga["link"])
        with repositorio.conectar() as conn:
            conn.execute("UPDATE empresas SET candidatura_id = ? WHERE dominio = ?", (id_, e["dominio"]))
        ids.append(id_)
    return ids
