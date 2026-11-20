"""Sólides (https://vagas.solides.com.br) via API pública JSON.

A versão antiga renderizava a página com Playwright e adivinhava fim de
paginação pelo texto da tela. A API devolve os mesmos dados estruturados,
incluindo a DESCRIÇÃO COMPLETA da vaga — que é o que o módulo de candidatura
usa para adaptar o currículo e achar e-mail de contato.
"""

import html
import re
import urllib.parse

import requests

from core.job import Job
from core.logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

MAX_PAGINAS = 3
POR_PAGINA = 14
URL_API = "https://vagas.solides.com.br/api/vacancies"

_MODALIDADES = {
    "remoto": "Remoto",
    "hibrido": "Híbrido",
    "híbrido": "Híbrido",
    "presencial": "Presencial",
}


def html_para_texto(conteudo: str) -> str:
    """Remove tags preservando quebras de parágrafo (útil para ler e-mails)."""
    if not conteudo:
        return ""
    texto = re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>", "\n", conteudo, flags=re.I)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = html.unescape(texto)
    texto = re.sub(r"[ \t\xa0]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n", texto)
    return texto.strip()


def normalizar_modalidade(valor: str | None) -> str:
    return _MODALIDADES.get((valor or "").strip().lower(), "")


def parsear_item(v: dict) -> Job:
    """Converte um item da API em Job. Função pura — testável sem rede."""
    cidade = "Não informado"
    city_obj, state_obj = v.get("city"), v.get("state")
    if isinstance(city_obj, dict) and isinstance(state_obj, dict):
        cidade = f"{city_obj.get('name', '')} - {state_obj.get('code', '')}"

    slug = v.get("slug") or "vagas"
    link = f"https://{slug}.vagas.solides.com.br/vaga/{v.get('id', '')}"

    return Job(
        titulo=(v.get("title") or "").strip(),
        empresa=v.get("companyName") or "Não informado",
        local=cidade,
        link=link,
        site="Solides",
        publicado_em=v.get("createdAt") or "",
        texto=html_para_texto(v.get("description") or ""),
        modalidade=normalizar_modalidade(v.get("jobType")),
    )


class SolidesScraper(BaseScraper):
    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        })

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))
        logger.info(f"[Solides] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[Solides] Buscando: {termo}")
        vagas: list[Job] = []

        for pagina in range(1, MAX_PAGINAS + 1):
            url = (
                f"{URL_API}?page={pagina}&take={POR_PAGINA}"
                f"&title={urllib.parse.quote(termo.strip())}&locations="
            )
            try:
                resposta = self.session.get(url, timeout=15)
                if resposta.status_code != 200:
                    logger.warning(f"[Solides] HTTP {resposta.status_code} para '{termo}' (página {pagina}).")
                    break
                itens = resposta.json().get("data", [])
            except Exception as e:
                logger.error(f"[Solides] Erro ao buscar '{termo}': {e}")
                break

            if not itens:
                break

            for item in itens:
                try:
                    vagas.append(parsear_item(item))
                except Exception as e:
                    logger.warning(f"[Solides] Item ignorado: {e}")

            if len(itens) < POR_PAGINA:
                break

        return vagas
