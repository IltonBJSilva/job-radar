import pytest

from core.perfis import PERFIL_BR
from tests.apoio import CIDADES_REFERENCIA


@pytest.fixture(autouse=True)
def _cidades_de_referencia(monkeypatch):
    """Isola os testes da lista CIDADES do config.py (que é pessoal e muda)."""
    monkeypatch.setattr(PERFIL_BR.regras, "cidades", list(CIDADES_REFERENCIA))
