"""Follow-up e leitura de respostas — sem SMTP/IMAP reais."""

from datetime import datetime, timedelta

import pytest

from candidatura import acompanhamento, config, repositorio
from candidatura.perfil import candidato_de_dict

CANDIDATO = candidato_de_dict({"pessoal": {"nome": "Ana Teste", "titulo": "Dev", "email": "ana@teste.dev"}})


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", tmp_path / "cand.db")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "saida")
    monkeypatch.setattr(config, "INTERVALO_MIN_SEG", 0)
    monkeypatch.setattr(config, "INTERVALO_MAX_SEG", 0)
    repositorio.iniciar()
    return tmp_path


def _enviada(id_, dias_atras, simulado=0, followups=0, email="rh@acme.com"):
    repositorio.inserir({
        "id": id_, "titulo": "Dev Python", "empresa": "ACME", "status": "enviada", "simulado": simulado,
        "email_destino": email, "assunto": "Candidatura: Dev Python — Ana Teste", "message_id": f"<{id_}@x>",
        "enviada_em": (datetime.now() - timedelta(days=dias_atras)).isoformat(timespec="seconds"),
        "followups": followups,
    })


def test_so_quem_passou_do_prazo_recebe_followup(banco):
    _enviada("velha", 8)
    _enviada("nova", 2)
    _enviada("simulada", 10, simulado=1)
    _enviada("ja_teve", 20, followups=1)
    assert [v["id"] for v in acompanhamento.pendentes_de_followup(7)] == ["velha"]


def test_followup_responde_no_mesmo_fio(banco, monkeypatch):
    enviados = []
    monkeypatch.setattr(acompanhamento, "enviar_smtp", lambda msg: enviados.append(msg))
    _enviada("v1", 8)
    r = acompanhamento.enviar_followups(real=True, candidato=CANDIDATO)
    assert r["enviados"] == 1
    msg = enviados[0]
    assert msg["Subject"].startswith("Re: Candidatura")
    assert msg["In-Reply-To"] == "<v1@x>"
    assert "não enviarei novas mensagens" in msg.get_content()
    assert repositorio.obter("v1")["followups"] == 1
    # Não manda o segundo.
    assert acompanhamento.enviar_followups(real=True, candidato=CANDIDATO)["enviados"] == 0


def test_followup_conta_no_limite_diario(banco, monkeypatch):
    monkeypatch.setattr(config, "LIMITE_DIARIO", 1)
    monkeypatch.setattr(acompanhamento, "enviar_smtp", lambda msg: None)
    _enviada("a", 9, email="a@a.com")
    _enviada("b", 9, email="b@b.com")
    r = acompanhamento.enviar_followups(real=True, candidato=CANDIDATO)
    assert r["enviados"] == 1


def test_classifica_resposta_por_thread_e_por_remetente():
    vagas = [{"id": "v1", "email_destino": "rh@acme.com", "message_id": "<v1@x>"},
             {"id": "v2", "email_destino": "jobs@beta.io", "message_id": "<v2@x>"}]
    assert acompanhamento.classificar_mensagem("Maria <maria@acme.com>", "Re: Candidatura", "",
                                               {"In-Reply-To": "<v1@x>"}, vagas) == [("v1", "resposta", "Re: Candidatura")]
    assert acompanhamento.classificar_mensagem("Jobs <jobs@beta.io>", "Retorno", "", {}, vagas)[0][:2] == ("v2", "resposta")
    assert acompanhamento.classificar_mensagem("news@outro.com", "Promo", "", {}, vagas) == []


def test_classifica_bounce():
    vagas = [{"id": "v1", "email_destino": "rh@acme.com", "message_id": "<v1@x>"}]
    achado = acompanhamento.classificar_mensagem(
        "Mail Delivery Subsystem <mailer-daemon@googlemail.com>", "Delivery Status Notification (Failure)",
        "Your message wasn't delivered to rh@acme.com because the address couldn't be found", {}, vagas)
    assert achado == [("v1", "bounce", "E-mail não entregue para rh@acme.com")]


def test_migracao_adiciona_colunas_em_banco_antigo(tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "antigo.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE candidaturas (id TEXT PRIMARY KEY, titulo TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'nova')")
    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", db)
    repositorio.iniciar()
    with sqlite3.connect(db) as c:
        colunas = {l[1] for l in c.execute("PRAGMA table_info(candidaturas)")}
    assert {"message_id", "followups", "resposta_em", "email_destino"} <= colunas
