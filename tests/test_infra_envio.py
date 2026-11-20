"""SMTP, IA e rotas de arquivo — com rede/servidores substituídos."""

import smtplib

import pytest

from candidatura import config, envio, ia, repositorio, servico
from candidatura.envio import ErroConexao, ErroFatalSMTP
from candidatura.perfil import candidato_de_dict

CAND = candidato_de_dict({"pessoal": {"nome": "Ana", "titulo": "Dev", "email": "ana@x.dev"}})


class _SMTPFalso:
    criados = []

    def __init__(self, host, porta, **k):
        self.host, self.porta, self.enviados = host, porta, []
        _SMTPFalso.criados.append(self)

    def __enter__(self): return self
    def __exit__(self, *a): pass
    def starttls(self, **k): self.tls = True
    def login(self, u, s): pass
    def send_message(self, msg, to_addrs=None): self.enviados.append(list(to_addrs or []))


@pytest.fixture
def smtp(monkeypatch):
    _SMTPFalso.criados = []
    monkeypatch.setattr(envio.smtplib, "SMTP", _SMTPFalso)
    monkeypatch.setattr(envio.smtplib, "SMTP_SSL", _SMTPFalso)
    monkeypatch.setattr(config, "SMTP_USUARIO", "eu@gmail.com")
    monkeypatch.setattr(config, "SMTP_SENHA", "x")
    return _SMTPFalso


def _msg():
    return envio.montar_mensagem("Ana", "eu@gmail.com", "rh@acme.com", "Assunto", "Corpo", [])


def test_porta_465_usa_ssl_e_587_usa_starttls(smtp, monkeypatch):
    monkeypatch.setattr(config, "SMTP_PORTA", 465)
    envio.enviar_smtp(_msg())
    assert smtp.criados[-1].porta == 465 and not hasattr(smtp.criados[-1], "tls")
    monkeypatch.setattr(config, "SMTP_PORTA", 587)
    envio.enviar_smtp(_msg())
    assert smtp.criados[-1].tls


def test_copia_para_mim(smtp, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_COPIA_PARA_MIM", True)
    envio.enviar_smtp(_msg())
    assert smtp.criados[-1].enviados == [["rh@acme.com", "eu@gmail.com"]]


def test_sem_credenciais_e_fatal(monkeypatch):
    monkeypatch.setattr(config, "SMTP_SENHA", "")
    with pytest.raises(ErroFatalSMTP):
        envio.enviar_smtp(_msg())


def test_senha_errada_vira_erro_fatal_com_dica(smtp, monkeypatch):
    def recusa(self, u, s):
        raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    monkeypatch.setattr(_SMTPFalso, "login", recusa)
    with pytest.raises(ErroFatalSMTP, match="SENHA DE APP"):
        envio.enviar_smtp(_msg())


def test_duas_quedas_de_conexao_param_o_lote(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", tmp_path / "c.db")
    monkeypatch.setattr(config, "INTERVALO_MIN_SEG", 0)
    monkeypatch.setattr(config, "INTERVALO_MAX_SEG", 0)
    repositorio.iniciar()
    for i in range(4):
        cv = tmp_path / f"{i}.pdf"
        cv.write_bytes(b"%PDF")
        repositorio.inserir({"id": f"v{i}", "titulo": "Dev", "empresa": f"E{i}", "status": "pronta",
                             "email_destino": f"rh@e{i}.com", "cv_path": str(cv), "assunto": "a", "corpo": "b"})
    tentativas = []

    def cai(msg):
        tentativas.append(msg["To"])
        raise ErroConexao("rede fora")

    monkeypatch.setattr(servico, "enviar_smtp", cai)
    monkeypatch.setattr(servico, "vaga_encerrada", lambda v: False)
    monkeypatch.setattr(servico, "carregar_candidato", lambda: CAND)
    r = servico.enviar_lote(limite=4, real=True)
    assert len(tentativas) == 2 and r["enviadas"] == 0


def test_ia_com_erro_http_volta_para_o_modelo_padrao(monkeypatch):
    class Resp:
        status_code = 500
        text = "erro"

    monkeypatch.setattr(config, "IA_PROVEDOR", "groq")
    monkeypatch.setattr(config, "IA_API_KEY", "k")
    monkeypatch.setattr(ia.requests, "post", lambda *a, **k: Resp())
    assert ia.completar("s", "u") is None


def test_ia_desligada_nao_chama_rede(monkeypatch):
    monkeypatch.setattr(config, "IA_PROVEDOR", "")
    monkeypatch.setattr(ia.requests, "post", lambda *a, **k: pytest.fail("não podia chamar a rede"))
    assert ia.completar("s", "u") is None


def test_rota_de_arquivo_rejeita_tipo_invalido(tmp_path, monkeypatch):
    import yaml

    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", tmp_path / "c.db")
    perfil = tmp_path / "p.yaml"
    perfil.write_text(yaml.safe_dump({"pessoal": {"nome": "Ana", "email": "a@x.dev"}}), encoding="utf-8")
    monkeypatch.setattr(config, "PERFIL_PATH", perfil)
    from web.app import criar_app

    c = criar_app().test_client()
    carta = tmp_path / "carta.pdf"
    carta.write_bytes(b"%PDF")
    repositorio.inserir({"id": "a1", "titulo": "Dev", "carta_path": str(carta)})
    assert c.get("/arquivo/a1/../../etc").status_code == 404
    assert c.get("/arquivo/a1/qualquer").status_code == 404
    assert c.get("/arquivo/a1/carta").status_code == 200
    assert c.get("/arquivo/naoexiste/cv").status_code == 404
