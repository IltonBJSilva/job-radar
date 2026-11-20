"""Renderiza currículo/carta em HTML e converte para PDF com o Chromium do
Playwright (já é dependência do radar — nada novo para instalar)."""

from __future__ import annotations

import re
import unicodedata
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


def html_curriculo(curriculo) -> str:
    return _env.get_template("curriculo.html").render(c=curriculo)


def html_carta(candidato, carta: str, titulo: str, empresa: str) -> str:
    return _env.get_template("carta.html").render(
        candidato=candidato, carta=carta, titulo=titulo, empresa=empresa, data=data_extenso()
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

    def gerar(self, html: str, destino: Path) -> Path:
        pagina = self._browser.new_page()
        try:
            pagina.set_content(html, wait_until="load")
            pagina.pdf(path=str(destino), format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            pagina.close()
        return destino
