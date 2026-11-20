import os
import tempfile

# Antes de qualquer import do projeto: os testes não podem depender do seu
# .env (load_dotenv não sobrescreve variáveis já definidas) nem escrever no
# jobradar.log real.
_ISOLAMENTO = {
    "JOBRADAR_LOG_PATH": os.path.join(tempfile.gettempdir(), "jobradar-testes.log"),
    "ENVIO_REAL": "false",
    "SMTP_HOST": "smtp.invalido.test",
    "SMTP_PORTA": "587",
    "SMTP_USUARIO": "",
    "SMTP_SENHA": "",
    "EMAIL_COPIA_PARA_MIM": "false",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "IA_PROVEDOR": "",
    "IA_API_KEY": "",
    "GITHUB_TOKEN": "",
    "LIMITE_DIARIO_ENVIOS": "30",
}
for _k, _v in _ISOLAMENTO.items():
    os.environ[_k] = _v

import pytest

from core.perfis import PERFIL_BR
from tests.apoio import CIDADES_REFERENCIA


@pytest.fixture(autouse=True)
def _cidades_de_referencia(monkeypatch):
    """Isola os testes da lista CIDADES do config.py (que é pessoal e muda)."""
    monkeypatch.setattr(PERFIL_BR.regras, "cidades", list(CIDADES_REFERENCIA))
