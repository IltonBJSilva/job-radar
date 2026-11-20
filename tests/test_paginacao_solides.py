"""Sólides via API JSON: conversão de item em Job (sem rede)."""

from scrapers.solides import html_para_texto, normalizar_modalidade, parsear_item

ITEM = {
    "id": "954500",
    "title": " Desenvolvedor Python ",
    "description": "<p><strong>Sobre</strong><br />Envie para <b>rh@empresa.com.br</b></p><ul><li>Python</li></ul>",
    "companyName": "Empresa X",
    "state": {"id": 23, "name": "Rio Grande do Sul", "code": "RS"},
    "city": {"id": 4931, "name": "Porto Alegre", "stateId": 23},
    "slug": "empresax",
    "jobType": "remoto",
    "createdAt": "2026-11-16",
}


def test_parsear_item_campos_basicos():
    job = parsear_item(ITEM)
    assert job.titulo == "Desenvolvedor Python"
    assert job.empresa == "Empresa X"
    assert job.local == "Porto Alegre - RS"
    assert job.link == "https://empresax.vagas.solides.com.br/vaga/954500"
    assert job.publicado_em == "2026-11-16"
    assert job.site == "Solides"


def test_modalidade_no_formato_do_filtro():
    """O filtro compara com "Remoto"/"Híbrido"/"Presencial" — não minúsculo."""
    assert normalizar_modalidade("remoto") == "Remoto"
    assert normalizar_modalidade("hibrido") == "Híbrido"
    assert normalizar_modalidade("presencial") == "Presencial"
    assert normalizar_modalidade(None) == ""
    assert parsear_item(ITEM).modalidade == "Remoto"


def test_descricao_sem_html_preserva_email():
    texto = html_para_texto(ITEM["description"])
    assert "<" not in texto
    assert "rh@empresa.com.br" in texto


def test_item_sem_cidade():
    job = parsear_item({**ITEM, "city": None})
    assert job.local == "Não informado"
