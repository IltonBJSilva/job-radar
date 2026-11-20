"""Módulo de candidatura: compatibilidade, e-mails, adaptação honesta, fila
e travas de envio. Sem rede, sem navegador e sem SMTP."""

from pathlib import Path

import pytest

from candidatura import config, repositorio, servico
from candidatura.adaptador import montar_pacote
from candidatura.compatibilidade import analisar, detectar_senioridade, extrair_tecnologias
from candidatura.contato import email_valido, extrair_emails
from candidatura.envio import ErroEnvio, montar_mensagem
from candidatura.fontes import _empresa_do_titulo, issue_para_vaga
from candidatura.perfil import candidato_de_dict

PERFIL = {
    "pessoal": {"nome": "Ana Teste", "titulo": "Desenvolvedora Backend | Python", "email": "ana@teste.dev"},
    "links": {"github": "https://github.com/ana"},
    "resumo": "Desenvolvedora backend.",
    "habilidades": {"Backend": ["Python", "Django", "FastAPI", "Node.js"], "Dados": ["PostgreSQL", "Redis"],
                    "DevOps": ["Docker"]},
    "experiencias": [{
        "cargo": "Dev Backend", "empresa": "ACME", "periodo": "2024 – atual",
        "tecnologias": ["Python", "Django"],
        "conquistas": ["Mantive o site institucional.", "Criei APIs em Django com PostgreSQL."],
    }],
    "projetos": [{"nome": "Bot", "descricao": "Bot em Node.js", "tecnologias": ["Node.js"]}],
    "idiomas": ["Inglês — intermediário"],
    "preferencias": {"cargos_alvo": ["backend", "python"]},
}


@pytest.fixture
def candidato():
    return candidato_de_dict(PERFIL)


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", tmp_path / "cand.db")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "saida")
    repositorio.iniciar()
    return tmp_path


# ------------------------------------------------------- compatibilidade

@pytest.mark.parametrize("texto, esperado, proibido", [
    ("Experiência com Node.js e TypeScript", {"Node.js", "TypeScript"}, set()),
    ("Vaga no Google, MongoDB desejável", {"MongoDB"}, {"Go"}),
    ("Conhecimento em Golang", {"Go"}, set()),
    ("JavaScript e React", {"JavaScript", "React"}, {"Java"}),
    ("Java 17 com Spring Boot", {"Java", "Spring"}, {"JavaScript"}),
    ("C# e ASP.NET Core", {"C#", ".NET"}, set()),
    ("APIs RESTful e Postgres", {"REST", "PostgreSQL"}, set()),
])
def test_extrair_tecnologias(texto, esperado, proibido):
    achadas = set(extrair_tecnologias(texto))
    assert esperado <= achadas
    assert not (proibido & achadas)


def test_score_alto_para_vaga_aderente(candidato):
    a = analisar(candidato, "Desenvolvedor Backend Python", "Python, Django, PostgreSQL e Docker.")
    assert a.score >= 80
    assert {"Python", "Django", "PostgreSQL", "Docker"} <= set(a.em_comum)


def test_score_baixo_para_vaga_de_outra_stack(candidato):
    a = analisar(candidato, "Desenvolvedor Java Sênior", "Java, Spring Boot, Kafka, Kubernetes, AWS.")
    assert a.score < 40
    assert "Java" in a.faltando


def test_uma_tecnologia_generica_nao_vira_100(candidato):
    a = analisar(candidato, "Tech Lead", "Inglês avançado.")
    assert a.score < 60


def test_senioridade():
    assert detectar_senioridade("Dev Backend Sr.") == "Sênior"
    assert detectar_senioridade("Desenvolvedor Júnior") == "Júnior"
    assert detectar_senioridade("Engenheiro de Software") == ""


# ------------------------------------------------------------- e-mails

def test_extrair_emails_prioriza_o_de_curriculo():
    texto = ("Dúvidas: privacidade@empresa.com. Envie seu currículo para talentos@empresa.com.br. "
             "logo@2x.png noreply@empresa.com")
    assert extrair_emails(texto)[0] == "talentos@empresa.com.br"
    assert "privacidade@empresa.com" not in extrair_emails(texto)
    assert "noreply@empresa.com" not in extrair_emails(texto)


def test_email_com_ponto_final_da_frase():
    assert extrair_emails("Mande para rh@acme.com.") == ["rh@acme.com"]


@pytest.mark.parametrize("email, ok", [
    ("rh@acme.com.br", True), ("foo@example.com", False), ("a@b", False), ("x@sentry.wixpress.com", False),
])
def test_email_valido(email, ok):
    assert email_valido(email) is ok


# ------------------------------------------------- adaptação honesta

def test_curriculo_nunca_inclui_tecnologia_nao_declarada(candidato):
    vaga = {"titulo": "Backend Python", "empresa": "X", "descricao": "Python, Django, Kubernetes, Kafka e Rust"}
    a = analisar(candidato, vaga["titulo"], vaga["descricao"])
    pacote = montar_pacote(candidato, vaga, a, usar_ia=False)
    habilidades_no_cv = {h for g in pacote.curriculo.grupos for h, _ in g.itens}
    declaradas = {h for grupo in PERFIL["habilidades"].values() for h in grupo}
    assert habilidades_no_cv == declaradas
    texto = pacote.carta + pacote.corpo_email + pacote.curriculo.titulo + pacote.curriculo.resumo
    for inventada in ("Kubernetes", "Kafka", "Rust"):
        assert inventada not in texto


def test_habilidade_pedida_vem_primeiro_e_destacada(candidato):
    vaga = {"titulo": "Dev", "empresa": "X", "descricao": "Redis obrigatório"}
    pacote = montar_pacote(candidato, vaga, analisar(candidato, "Dev", "Redis obrigatório"), usar_ia=False)
    dados = next(g for g in pacote.curriculo.grupos if g.nome == "Dados")
    assert dados.itens[0] == ("Redis", True)


def test_conquista_mais_relevante_sobe(candidato):
    vaga = {"titulo": "Dev Django", "empresa": "X", "descricao": "Django e PostgreSQL"}
    pacote = montar_pacote(candidato, vaga, analisar(candidato, vaga["titulo"], vaga["descricao"]), usar_ia=False)
    assert "Django" in pacote.curriculo.experiencias[0].conquistas[0]


def test_email_tem_assunto_e_links(candidato):
    vaga = {"titulo": "Dev Python", "empresa": "ACME", "descricao": "Python"}
    pacote = montar_pacote(candidato, vaga, analisar(candidato, "Dev Python", "Python"), usar_ia=False)
    assert pacote.assunto == "Candidatura: Dev Python — Ana Teste"
    assert "https://github.com/ana" in pacote.corpo_email


# ----------------------------------------------------------------- fontes

def test_issue_do_github_vira_vaga():
    issue = {
        "title": "[Remoto] Desenvolvedor Backend Pleno na Mimix AI",
        "body": "Python e Django. Envie o CV para vagas@mimix.ai",
        "html_url": "https://github.com/backend-br/vagas/issues/1",
        "labels": [{"name": "Remoto"}, {"name": "Pleno"}],
        "created_at": "2026-11-18T10:00:00Z",
    }
    v = issue_para_vaga(issue, "backend-br/vagas")
    assert v["titulo"] == "Desenvolvedor Backend Pleno"
    assert v["empresa"] == "Mimix AI"
    assert v["email_destino"] == "vagas@mimix.ai"
    assert v["modalidade"] == "Remoto"


def test_pull_request_e_ignorado():
    assert issue_para_vaga({"title": "x", "pull_request": {}}, "r/v") is None


def test_empresa_do_titulo_com_hifen():
    assert _empresa_do_titulo("[Remoto] Dev Backend Júnior - MKdigital") == "MKdigital"


# -------------------------------------------------------- fila e envio

def _vaga_pronta(tmp_path, id_="v1", email="rh@acme.com.br", empresa="ACME"):
    cv = tmp_path / f"{id_}.pdf"
    cv.write_bytes(b"%PDF-1.4 teste")
    repositorio.inserir({
        "id": id_, "titulo": "Dev Python", "empresa": empresa, "link": f"https://x/{id_}",
        "status": "pronta", "email_destino": email, "cv_path": str(cv),
        "assunto": "Candidatura", "corpo": "Olá",
    })
    return id_


def test_envio_simulado_gera_eml_e_nao_usa_smtp(banco, candidato, monkeypatch):
    monkeypatch.setattr(servico, "carregar_candidato", lambda: candidato)
    monkeypatch.setattr(servico, "enviar_smtp", lambda msg: pytest.fail("não podia chamar SMTP"))
    id_ = _vaga_pronta(banco)
    v = servico.enviar(id_, real=False, candidato=candidato)
    assert v["status"] == "enviada" and v["simulado"] == 1
    assert (banco / "email_simulado.eml").exists()


def test_padrao_e_simulacao(monkeypatch):
    """Sem ENVIO_REAL no ambiente, nada sai da máquina."""
    import importlib

    monkeypatch.delenv("ENVIO_REAL", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    try:
        assert importlib.reload(config).ENVIO_REAL is False
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_nao_envia_sem_email(banco, candidato):
    id_ = _vaga_pronta(banco, email="")
    with pytest.raises(ErroEnvio, match="sem e-mail"):
        servico.enviar(id_, real=False, candidato=candidato)


def test_limite_diario_bloqueia_envio_real(banco, candidato, monkeypatch):
    monkeypatch.setattr(config, "LIMITE_DIARIO", 1)
    enviados = []
    monkeypatch.setattr(servico, "enviar_smtp", lambda msg: enviados.append(msg["To"]))
    servico.enviar(_vaga_pronta(banco, "a", "a@x.com", "A"), real=True, candidato=candidato)
    with pytest.raises(ErroEnvio, match="limite diário"):
        servico.enviar(_vaga_pronta(banco, "b", "b@y.com", "B"), real=True, candidato=candidato)
    assert enviados == ["a@x.com"]


def test_nao_repete_empresa(banco, candidato, monkeypatch):
    monkeypatch.setattr(servico, "enviar_smtp", lambda msg: None)
    servico.enviar(_vaga_pronta(banco, "a", "rh@acme.com", "ACME"), real=True, candidato=candidato)
    with pytest.raises(ErroEnvio, match="já enviado"):
        servico.enviar(_vaga_pronta(banco, "b", "outro@acme.com", "acme"), real=True, candidato=candidato)


def test_mensagem_tem_anexo_e_reply_to(tmp_path):
    pdf = tmp_path / "Curriculo.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    msg = montar_mensagem("Ana", "ana.envio@gmail.com", "rh@x.com", "Assunto", "Corpo", [pdf], "ana@teste.dev")
    assert msg["Reply-To"] == "ana@teste.dev"
    anexos = [p.get_filename() for p in msg.iter_attachments()]
    assert anexos == ["Curriculo.pdf"]


def test_importar_do_radar(banco, tmp_path):
    import sqlite3

    radar = tmp_path / "jobs.db"
    with sqlite3.connect(radar) as c:
        c.execute("CREATE TABLE vagas_vistas (id TEXT PRIMARY KEY, titulo TEXT, empresa TEXT, local TEXT, link TEXT,"
                  " site TEXT, encontrada_em TEXT, publicado_em TEXT, modalidade TEXT, descricao TEXT)")
        c.execute("INSERT INTO vagas_vistas VALUES ('r1','Dev','E','L','https://l','S','2026-01-01','', 'Remoto', 'Python')")
    assert repositorio.importar_do_radar(radar_db=str(radar)) == 1
    assert repositorio.importar_do_radar(radar_db=str(radar)) == 0
    assert repositorio.obter("r1")["origem"] == "radar"


def test_preparar_sem_navegador(banco, candidato, monkeypatch):
    class FakePDF:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def gerar(self, html, destino):
            Path(destino).write_bytes(b"%PDF")
            return destino

    monkeypatch.setattr(servico, "GeradorPDF", FakePDF)
    monkeypatch.setattr(servico, "buscar_descricao", lambda link: "")
    repositorio.inserir({"id": "p1", "titulo": "Dev Python", "empresa": "ACME", "link": "",
                         "descricao": "Python e Django. Currículo para jobs@acme.com" + " x" * 200})
    v = servico.preparar("p1", candidato, usar_ia=False)
    assert v["status"] == "pronta"
    assert v["email_destino"] == "jobs@acme.com"
    assert Path(v["cv_path"]).exists() and Path(v["carta_path"]).exists()
