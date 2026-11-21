"""Renderiza currículo/carta em HTML e converte para PDF com o Chromium do
Playwright (já é dependência do radar — nada novo para instalar)."""

from __future__ import annotations

import base64
import io
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from candidatura import config

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=select_autoescape(["html"]))

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def slug(texto: str, maximo: int = 40) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    texto = re.sub(r"[^A-Za-z0-9]+", "-", texto).strip("-").lower()
    return texto[:maximo].strip("-") or "vaga"


def data_extenso(d: date | None = None) -> str:
    d = d or date.today()
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


PAGINAS_CURRICULO = 2


@dataclass(frozen=True)
class Layout:
    """Tipografia do currículo (do mais folgado ao mais compacto)."""
    fonte: float
    entrelinha: float
    espaco: float
    margem: float = 9
    margem_lado: float = 10


LAYOUTS = [
    Layout(11.2, 1.34, 1.45),
    Layout(11.0, 1.30, 1.30),
    Layout(10.8, 1.27, 1.15),
    Layout(10.5, 1.24, 1.0),
    Layout(10.2, 1.21, .9),
    Layout(10.0, 1.19, .85),  # a partir daqui, se ainda não couber, começam os cortes de conteúdo
    Layout(9.6, 1.15, .75),
    Layout(9.2, 1.11, .65),
]
LAYOUT_PADRAO = 3
_LAYOUT_DOS_CORTES = 5


def plano_de_cortes(curriculo) -> list[tuple[str, int]]:
    """Ordem em que o conteúdo sai quando não cabe em 2 páginas: um item por
    vez, do menos importante ao mais importante. Experiências antigas perdem
    tópicos antes das recentes; os tópicos já vêm ordenados por aderência à
    vaga, então sai sempre o último. A seção de IA nunca some por completo.

    ("exp", i) tira o último tópico da experiência i; ("proj", j) tira o
    projeto j; ("item", j) tira o último tópico do projeto j."""
    exps = [len(e.conquistas) for e in curriculo.experiencias]
    projs = [len(p.itens) if p.itens else 1 for p in curriculo.projetos]
    vivos = [True] * len(projs)
    ia = [j for j, p in enumerate(curriculo.projetos) if p.ia]
    outros = [j for j, p in enumerate(curriculo.projetos) if not p.ia]
    plano: list[tuple[str, int]] = []

    def tirar_projetos(lista, manter):
        for j in reversed(lista[manter:]):
            if vivos[j]:
                vivos[j] = False
                plano.append(("proj", j))

    def topicos_exp(teto):
        for i in reversed(range(len(exps))):  # da mais antiga para a mais recente
            limite = max(teto + (1 if i <= 2 else 0), 2)  # as 3 mais recentes guardam 1 a mais
            while exps[i] > limite:
                exps[i] -= 1
                plano.append(("exp", i))

    def topicos_proj(lista, teto):
        for j in reversed(lista):
            while vivos[j] and projs[j] > max(teto, 1) and curriculo.projetos[j].itens:
                projs[j] -= 1
                plano.append(("item", j))

    tirar_projetos(outros, 2)
    topicos_exp(5)
    tirar_projetos(outros, 1)
    topicos_proj(ia[1:], 2)
    topicos_exp(4)
    topicos_proj(ia[:1], 4)
    topicos_exp(3)
    tirar_projetos(outros, 0)
    topicos_proj(ia[1:], 1)
    topicos_proj(ia[:1], 3)
    topicos_exp(2)
    tirar_projetos(ia, 2)
    return plano


def aplicar_cortes(curriculo, cortes: list[tuple[str, int]]):
    exps = [list(e.conquistas) for e in curriculo.experiencias]
    itens = [list(p.itens) for p in curriculo.projetos]
    fora = set()
    for tipo, k in cortes:
        if tipo == "exp":
            exps[k].pop()
        elif tipo == "item":
            itens[k].pop()
        else:
            fora.add(k)
    return replace(
        curriculo,
        experiencias=[replace(e, conquistas=c) for e, c in zip(curriculo.experiencias, exps)],
        projetos=[replace(p, itens=i) for k, (p, i) in enumerate(zip(curriculo.projetos, itens)) if k not in fora],
    )

_ROTULOS_LINKS = {"linkedin": "LinkedIn", "github": "GitHub", "portfolio": "Portfólio", "site": "Site",
                  "gitlab": "GitLab", "behance": "Behance"}
_FONTES = _TEMPLATES / "fontes"
_fontes_css: str | None = None


def fontes_css() -> str:
    """CMU Serif (a fonte do LaTeX/Overleaf) embutida no HTML: o PDF sai igual
    em qualquer máquina, sem depender de fonte instalada nem de internet."""
    global _fontes_css
    if _fontes_css is None:
        regras = []
        for arquivo, peso, estilo in (("cmunrm", 400, "normal"), ("cmunbx", 700, "normal"),
                                      ("cmunti", 400, "italic"), ("cmunbi", 700, "italic")):
            caminho = _FONTES / f"{arquivo}.woff"
            if caminho.exists():
                dados = base64.b64encode(caminho.read_bytes()).decode()
                regras.append(f'@font-face {{ font-family: "CMU Serif"; font-weight: {peso}; font-style: {estilo}; '
                              f'src: url(data:font/woff;base64,{dados}) format("woff"); }}')
        _fontes_css = "\n".join(regras)
    return _fontes_css


def html_curriculo(curriculo, nivel: int = LAYOUT_PADRAO) -> str:
    layout = LAYOUTS[max(0, min(nivel, len(LAYOUTS) - 1))]
    return _env.get_template("curriculo.html").render(
        c=curriculo, L=layout, fontes_css=fontes_css(), rotulos=_ROTULOS_LINKS)


def contar_paginas(pdf: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(pdf)).pages)


def html_carta(candidato, carta: str, titulo: str, empresa: str, espontanea: bool = False) -> str:
    referencia = f"candidatura espontânea ({titulo})" if espontanea else f"vaga {titulo}"
    return _env.get_template("carta.html").render(
        candidato=candidato, carta=carta, titulo=titulo, referencia=referencia, empresa=empresa, data=data_extenso()
    )


def pasta_da_vaga(vaga: dict) -> Path:
    pasta = config.SAIDA_DIR / f"{slug(vaga.get('empresa') or 'empresa', 30)}_{slug(vaga.get('titulo'), 40)}_{vaga['id'][:6]}"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


class GeradorPDF:
    """Abre o Chromium uma vez e reutiliza para vários PDFs (lote de 100 vagas
    não pode abrir 200 navegadores)."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc):
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def _pdf(self, html: str) -> bytes:
        pagina = self._browser.new_page()
        try:
            pagina.set_content(html, wait_until="load")
            pagina.evaluate("document.fonts.ready")
            return pagina.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            pagina.close()

    def gerar(self, html: str, destino: Path) -> Path:
        destino.write_bytes(self._pdf(html))
        return destino

    def gerar_curriculo(self, curriculo, destino: Path, paginas: int = PAGINAS_CURRICULO) -> tuple[str, int]:
        """Escolhe a versão mais folgada e mais completa que cabe em `paginas`.

        Estados, do mais folgado ao mais enxuto: tipografias com o conteúdo
        inteiro; depois, na tipografia compacta, os cortes um a um; por fim,
        tipografias menores com todos os cortes. O nº de páginas nunca aumenta
        ao longo da lista, então uma busca binária acha o ponto com ~6 PDFs."""
        cortes = plano_de_cortes(curriculo)
        estados = ([(n, 0) for n in range(_LAYOUT_DOS_CORTES + 1)]
                   + [(_LAYOUT_DOS_CORTES, k) for k in range(1, len(cortes) + 1)]
                   + [(n, len(cortes)) for n in range(_LAYOUT_DOS_CORTES + 1, len(LAYOUTS))])
        cache: dict[int, tuple[str, bytes, int]] = {}

        def render(indice: int) -> int:
            if indice not in cache:
                nivel, k = estados[indice]
                html = html_curriculo(aplicar_cortes(curriculo, cortes[:k]), nivel)
                pdf = self._pdf(html)
                cache[indice] = (html, pdf, contar_paginas(pdf))
            return cache[indice][2]

        baixo, alto = 0, len(estados) - 1
        if render(alto) > paginas:  # nem o mais compacto cabe: usa ele mesmo
            escolhido = alto
        else:
            while baixo < alto:
                meio = (baixo + alto) // 2
                if render(meio) <= paginas:
                    alto = meio
                else:
                    baixo = meio + 1
            escolhido = baixo
        render(escolhido)
        html, pdf, total = cache[escolhido]
        destino.write_bytes(pdf)
        return html, total
