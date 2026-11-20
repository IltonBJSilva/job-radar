"""Ajustes do radar para o perfil Backend (revisão de 20/11/2026)."""

import pytest

from core.config import TERMOS_BUSCA
from core.job import Job
from core.perfis import PERFIL_BR


def _vaga(titulo, texto="", local="Remoto", modalidade="Remoto"):
    return Job(titulo=titulo, empresa="E", local=local, link=f"https://x/{titulo}{len(texto)}",
               site="T", modalidade=modalidade, texto=texto)


def test_card_curto_nao_e_barrado_pela_regra_de_idioma():
    """MEDIDO: a regra zerava o radar porque o card não tem descrição."""
    assert _vaga("Desenvolvedor Python", "Desenvolvedor Python\nEmpresa\nRemoto").combina_com(PERFIL_BR.regras)


def test_descricao_longa_em_ingles_continua_barrada():
    texto = "We are looking for a backend engineer to join our team and build scalable services. " * 5
    assert not _vaga("Desenvolvedor Python", texto).combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("titulo", ["Analista de Sistemas", "Engenheiro Mecânico de Sistemas",
                                    "Analista de Suporte Python", "Especialista em Software"])
def test_qualificador_generico_nao_aprova_sozinho(titulo):
    assert not _vaga(titulo).combina_com(PERFIL_BR.regras)


def test_termos_de_busca_sem_duplicados_nem_genericos():
    assert len(TERMOS_BUSCA) == len(set(TERMOS_BUSCA))
    for generico in ("developer", "desenvolvedor", "engenheiro", "engineer", "programador"):
        assert generico not in TERMOS_BUSCA
