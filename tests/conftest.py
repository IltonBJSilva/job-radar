import os
import tempfile

# Antes de qualquer import do projeto: os testes não podem depender do seu
# .env (load_dotenv não sobrescreve variáveis já definidas) nem escrever no
# jobradar.log real.
_ISOLAMENTO = {
    "JOBRADAR_LOG_PATH": os.path.join(tempfile.gettempdir(), "jobradar-testes.log"),
    "JOBRADAR_PERFIL": "principal",  # nunca o perfil que você deixou ativo na interface
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
    "BRAVE_API_KEY": "",
    "TAVILY_API_KEY": "",
    "HUNTER_API_KEY": "",
    "IA_NO_RESUMO": "false",
    "LIMITE_DIARIO_ENVIOS": "30",
}
for _k, _v in _ISOLAMENTO.items():
    os.environ[_k] = _v

import pytest

# Localidades (IBGE + países): base pequena e fixa — teste nunca baixa nada.
from pathlib import Path as _Path

from candidatura import localidades as _localidades

_localidades.CACHE_PATH = _Path(__file__).parent / "dados" / "localidades_teste.json"
_localidades._indice.cache_clear()


@pytest.fixture(autouse=True)
def _nunca_tocar_config_real(tmp_path_factory, monkeypatch):
    """Nenhum teste grava no .env, em perfis/ ou em data/perfil_ativo.txt de verdade
    (a tela de Configurações grava o e-mail do perfil principal no .env)."""
    from candidatura import config as _config

    pasta = tmp_path_factory.mktemp("config_isolada")
    monkeypatch.setattr(_config, "ENV_PATH", pasta / ".env")
    monkeypatch.setattr(_config, "PERFIS_DIR", pasta / "perfis")
    monkeypatch.setattr(_config, "PERFIL_ATIVO_PATH", pasta / "perfil_ativo.txt")
    # A rotina diária nunca mexe no Agendador do Windows durante os testes.
    from candidatura import rotina as _rotina

    monkeypatch.setattr(_rotina, "_schtasks", lambda *a: __import__("subprocess").CompletedProcess(a, 1, "", ""))

from core.perfis import PERFIL_BR
from tests.apoio import CIDADES_REFERENCIA


@pytest.fixture(autouse=True)
def _cidades_de_referencia(monkeypatch):
    """Isola os testes da lista CIDADES do config.py (que é pessoal e muda)."""
    monkeypatch.setattr(PERFIL_BR.regras, "cidades", list(CIDADES_REFERENCIA))
