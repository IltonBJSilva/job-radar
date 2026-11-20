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
    repositorio.inserir({"id": "p1", "titulo": "Dev Python", "empresa": "ACME", "link": "", "status": "curtida",
                         "descricao": "Python e Django. Currículo para jobs@acme.com" + " x" * 200})
    v = servico.preparar("p1", candidato, usar_ia=False)
    assert v["status"] == "pronta"
    assert v["email_destino"] == "jobs@acme.com"
    assert Path(v["cv_path"]).exists() and Path(v["carta_path"]).exists()


# ------------------------------------------- regressões da revisão de código

def test_cv_usa_o_termo_declarado_e_nao_o_sinonimo():
    perfil = dict(PERFIL, habilidades={"Dados": ["MariaDB", "OpenSearch"], "Backend": ["Python"]})
    c = candidato_de_dict(perfil)
    vaga = {"titulo": "Backend Python", "empresa": "X", "descricao": "Python, MySQL e Elasticsearch"}
    pacote = montar_pacote(c, vaga, analisar(c, vaga["titulo"], vaga["descricao"]), usar_ia=False)
    texto = pacote.curriculo.titulo + pacote.curriculo.resumo + pacote.carta
    assert "MariaDB" in texto and "OpenSearch" in texto
    assert "MySQL" not in texto and "Elasticsearch" not in texto


@pytest.mark.parametrize("texto, esperado", [
    ("C#/.NET", {"C#", ".NET"}), (".NET/C#", {"C#", ".NET"}), ("Node/Express", {"Node.js", "Express"}),
])
def test_tecnologias_separadas_por_barra(texto, esperado):
    assert esperado <= set(extrair_tecnologias(texto))


@pytest.mark.parametrize("texto, proibido", [("Apoio no go-live do projeto", "Go"),
                                              ("Get some rest after the release", "REST")])
def test_palavra_comum_nao_vira_tecnologia(texto, proibido):
    assert proibido not in extrair_tecnologias(texto)


def test_pl_sql_nao_e_pleno():
    assert detectar_senioridade("Desenvolvedor PL/SQL") == ""
    assert detectar_senioridade("Desenvolvedor PL") == "Pleno"


@pytest.mark.parametrize("email", ["icon@3x.avif", "jose.@x.com", "rh@empresa..com", "vagas@remotar.com.br"])
def test_emails_invalidos(email):
    assert not email_valido(email)


def test_email_colado_no_texto_seguinte():
    assert extrair_emails("Envie para vagas@empresa.com.brRequisitos: Python") == ["vagas@empresa.com.br"]


def test_carta_nao_quebra_com_campos_vazios():
    perfil = dict(PERFIL, experiencias=[{"cargo": "Dev", "empresa": "ACME", "conquistas": ["", "  "]}],
                  projetos=[{"nome": "P", "descricao": ""}])
    c = candidato_de_dict(perfil)
    montar_pacote(c, {"titulo": "Dev", "empresa": "X", "descricao": ""}, analisar(c, "Dev", ""), usar_ia=False)


def test_envio_sem_anexo_no_disco_e_bloqueado(banco, candidato, monkeypatch):
    monkeypatch.setattr(servico, "enviar_smtp", lambda msg: pytest.fail("não podia enviar"))
    id_ = _vaga_pronta(banco)
    Path(repositorio.obter(id_)["cv_path"]).unlink()
    with pytest.raises(ErroEnvio, match="Anexo"):
        servico.enviar(id_, real=True, candidato=candidato)


def test_vaga_com_erro_nao_e_reenviada_sem_refazer(banco, candidato):
    id_ = _vaga_pronta(banco)
    repositorio.atualizar(id_, status="erro")
    with pytest.raises(ErroEnvio, match="status"):
        servico.enviar(id_, real=False, candidato=candidato)


def test_preparar_recusa_vaga_ja_enviada(banco, candidato):
    id_ = _vaga_pronta(banco)
    repositorio.atualizar(id_, status="enviada")
    with pytest.raises(ValueError):
        servico.preparar(id_, candidato, usar_ia=False)
    assert repositorio.obter(id_)["status"] == "enviada"


def test_desfazer_durante_preparo_nao_coloca_na_fila(banco, candidato, monkeypatch):
    class FakePDF:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def gerar(self, html, destino):
            repositorio.atualizar("d1", status="nova")  # usuário clicou em desfazer no meio
            Path(destino).write_bytes(b"%PDF")

    monkeypatch.setattr(servico, "GeradorPDF", FakePDF)
    repositorio.inserir({"id": "d1", "titulo": "Dev", "empresa": "E", "status": "curtida",
                         "descricao": "Envie currículo para rh@e.com " + "x " * 200})
    servico.preparar("d1", candidato, usar_ia=False)
    assert repositorio.obter("d1")["status"] == "nova"


def test_empresa_confidencial_nao_bloqueia_outras(banco, candidato, monkeypatch):
    monkeypatch.setattr(servico, "enviar_smtp", lambda msg: None)
    servico.enviar(_vaga_pronta(banco, "a", "a@x.com", "Confidencial"), real=True, candidato=candidato)
    servico.enviar(_vaga_pronta(banco, "b", "b@y.com", "Confidencial"), real=True, candidato=candidato)


def test_limite_do_gmail_interrompe_lote(banco, candidato, monkeypatch):
    import smtplib

    from candidatura import envio

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, *a, **k):
            raise smtplib.SMTPDataError(550, b"5.4.5 Daily user sending quota exceeded.")

    monkeypatch.setattr(envio.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(config, "SMTP_USUARIO", "eu@gmail.com")
    monkeypatch.setattr(config, "SMTP_SENHA", "x")
    monkeypatch.setattr(config, "INTERVALO_MIN_SEG", 0)
    monkeypatch.setattr(config, "INTERVALO_MAX_SEG", 0)
    monkeypatch.setattr(servico, "carregar_candidato", lambda: candidato)
    for i in range(3):
        _vaga_pronta(banco, f"q{i}", f"rh{i}@x{i}.com", f"E{i}")
    r = servico.enviar_lote(limite=3, real=True)
    assert r["enviadas"] == 0 and len(r["erros"]) == 1


def test_web_bloqueia_post_de_outro_site(banco, monkeypatch, tmp_path):
    import yaml

    perfil = tmp_path / "c.yaml"
    perfil.write_text(yaml.safe_dump(PERFIL, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config, "PERFIL_PATH", perfil)
    from web.app import criar_app, link_seguro

    c = criar_app().test_client()
    assert c.post("/api/enviar-lote", json={}, headers={"Origin": "https://malicioso.com"}).status_code == 403
    assert c.post("/api/enviar-lote", json={}).status_code == 403  # sem Origin/Referer
    assert c.post("/vaga/x", data={"email_destino": "hacker@mal.com"},
                  headers={"Origin": "https://malicioso.com"}).status_code == 403
    ok = c.post("/api/decidir/inexistente", json={"acao": "descartar"}, headers={"Origin": "http://localhost"})
    assert ok.status_code == 200
    assert link_seguro("javascript:alert(1)") == "" and link_seguro("https://x.com") == "https://x.com"


# ------------------------------------------------ regressões de segurança

def test_dns_rebinding_bloqueado(banco, monkeypatch, tmp_path):
    import yaml

    perfil = tmp_path / "c.yaml"
    perfil.write_text(yaml.safe_dump(PERFIL, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config, "PERFIL_PATH", perfil)
    from web.app import criar_app

    c = criar_app().test_client()
    mal = {"Host": "evil.test:5000", "Origin": "http://evil.test:5000"}
    assert c.post("/api/enviar-lote", json={}, headers=mal).status_code == 403
    assert c.get("/fila", headers={"Host": "evil.test:5000"}).status_code == 403
    assert c.get("/fila", headers={"Host": "127.0.0.1:5000"}).status_code == 200


@pytest.mark.parametrize("url", ["http://127.0.0.1:5000/x", "http://localhost/", "http://192.168.0.1/",
                                 "http://10.0.0.5/", "http://169.254.169.254/latest", "ftp://x.com/", "file:///c:/x"])
def test_ssrf_recusa_enderecos_internos(url):
    from candidatura.contato import url_publica

    assert not url_publica(url)


def test_ia_que_cita_link_estranho_e_descartada(candidato):
    from candidatura.ia import saida_segura

    assert saida_segura("Veja https://golpe.com", candidato) is None
    assert saida_segura("Fale com pix@golpe.com", candidato) is None
    assert saida_segura("Meu GitHub: https://github.com/ana", candidato) == "Meu GitHub: https://github.com/ana"


@pytest.mark.parametrize("email, empresa, ok", [
    ("jobs@milkboxmail.com", "MilkBox", True),
    ("vagas@mimix.ai", "Mimix AI", True),
    ("fulano@gmail.com", "Mimix AI", False),
    ("rh@empresa.com", "", False),
])
def test_auto_so_envia_para_dominio_da_empresa(email, empresa, ok):
    assert servico.dominio_da_empresa(email, empresa) is ok


# ------------------------------------------ regressões: lógica (2ª revisão)

def test_dois_envios_simultaneos_da_mesma_vaga_saem_uma_vez(banco, candidato, monkeypatch):
    import threading
    import time as _t

    saidas = []

    def smtp_lento(msg):
        _t.sleep(0.2)
        saidas.append(msg["To"])

    monkeypatch.setattr(servico, "enviar_smtp", smtp_lento)
    monkeypatch.setattr(servico, "vaga_encerrada", lambda v: False)
    id_ = _vaga_pronta(banco)
    erros = []

    def tentar():
        try:
            servico.enviar(id_, real=True, candidato=candidato)
        except ErroEnvio as e:
            erros.append(str(e))

    ts = [threading.Thread(target=tentar) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert saidas == ["rh@acme.com.br"] and len(erros) == 1


def test_simulacao_nao_impede_envio_real_depois(banco, candidato, monkeypatch):
    enviados = []
    monkeypatch.setattr(servico, "enviar_smtp", lambda msg: enviados.append(msg["To"]))
    monkeypatch.setattr(servico, "vaga_encerrada", lambda v: False)
    monkeypatch.setattr(servico, "carregar_candidato", lambda: candidato)
    id_ = _vaga_pronta(banco)
    servico.enviar(id_, real=False, candidato=candidato)
    r = servico.enviar_lote(limite=5, real=True)
    assert r["enviadas"] == 1 and enviados == ["rh@acme.com.br"]
    assert repositorio.obter(id_)["simulado"] == 0


def test_lote_com_lista_de_ids_vazia_nao_envia_tudo(banco, candidato, monkeypatch):
    monkeypatch.setattr(servico, "carregar_candidato", lambda: candidato)
    _vaga_pronta(banco)
    with pytest.raises(ValueError):
        servico.enviar_lote(limite=5, real=False, ids=[])


def test_cli_enviar_id_vazio_aborta(banco, monkeypatch):
    import candidatar

    _vaga_pronta(banco)
    with pytest.raises(SystemExit):
        candidatar.main(["enviar", "--id"])
    assert repositorio.obter("v1")["status"] == "pronta"


def test_cli_preparar_id_nao_reabre_enviada(banco, monkeypatch):
    import candidatar

    id_ = _vaga_pronta(banco)
    repositorio.atualizar(id_, status="enviada")
    monkeypatch.setattr(servico, "preparar_lote", lambda ids, usar_ia=True: {"ids": ids})
    candidatar.main(["preparar", "--id", id_])
    assert repositorio.obter(id_)["status"] == "enviada"


@pytest.mark.parametrize("yaml_txt", [
    "pessoal: {nome: Ana, email: a@b.com}\nhabilidades: Python, Django\n",
    "pessoal: {nome: Ana, email: a@b.com}\nhabilidades: {Backend: 'Python, Django'}\nexperiencias: [null]\n",
    "pessoal: {nome: Ana, email: a@b.com, telefone: 34999999999}\nlinks: [x]\ncertificacoes: [null, AWS]\nresumo: 123\n",
])
def test_perfil_malformado_e_normalizado(tmp_path, yaml_txt):
    from candidatura.perfil import carregar_candidato

    p = tmp_path / "c.yaml"
    p.write_text(yaml_txt, encoding="utf-8")
    c = carregar_candidato(p)
    assert all(len(h) > 1 for h in c.todas_habilidades)  # nada de "P, y, t, h, o, n"
    assert "None" not in c.certificacoes


def test_perfil_com_erro_de_sintaxe_da_mensagem_clara(tmp_path):
    from candidatura.perfil import PerfilInvalido, carregar_candidato

    p = tmp_path / "c.yaml"
    p.write_text("pessoal: [nome: Ana\n", encoding="utf-8")
    with pytest.raises(PerfilInvalido):
        carregar_candidato(p)


def test_issue_de_regras_e_ignorada():
    for titulo in ("[PT-BR] - Regras para publicar vagas", "ATENÇÃO: Leia nossas regras"):
        assert issue_para_vaga({"title": titulo, "body": "", "html_url": "u", "labels": []}, "r/v") is None


@pytest.mark.parametrize("titulo, empresa", [
    ("[Remoto] Dev Backend - Igma | PJ", "Igma"),
    ("[Remoto] Dev Backend na React.js, Nest.js, Kafka(Strider))", ""),
    ("[Presencial] Dev Python - RJ", ""),
])
def test_empresa_extraida_com_limpeza(titulo, empresa):
    assert _empresa_do_titulo(titulo) == empresa


def test_mesma_vaga_em_dois_repos_entra_uma_vez(banco):
    base = {"body": "Python. Envie CV para vagas@rotha.ai", "labels": [], "created_at": ""}
    v1 = issue_para_vaga({**base, "title": "[Remoto] Dev Python na Rotha IA", "html_url": "https://github.com/a/v/issues/1"}, "a/v")
    v2 = issue_para_vaga({**base, "title": "[Remoto] Dev Python na Rotha IA", "html_url": "https://github.com/b/v/issues/9"}, "b/v")
    assert repositorio.inserir(v1)
    assert repositorio.existe_semelhante(v2["titulo"], v2["email_destino"], v2["empresa"])


# ----------------------------------- regressões: qualidade dos documentos

SENIOR = dict(PERFIL, pessoal={"nome": "Rafael Augusto Bittencourt de Oliveira", "titulo": "Engenheiro de Software Sênior",
                               "email": "r@x.dev"},
              habilidades={"Linguagens": ["Python", "Java"], "Práticas": ["TDD"]},
              experiencias=[
                  {"cargo": "Eng", "empresa": "Nubank", "tecnologias": ["Python"], "conquistas": ["Criei APIs em Python."]},
                  {"cargo": "Eng", "empresa": "Mercado Livre", "tecnologias": ["Python"], "conquistas": ["Escalei serviços."]},
                  {"cargo": "Dev", "empresa": "Totvs", "periodo": "2014 – 2016", "tecnologias": ["Java"],
                   "conquistas": ["Mantive sistema Java."]},
              ])


def test_carta_nao_afirma_uso_atual_de_tecnologia_antiga():
    c = candidato_de_dict(SENIOR)
    vaga = {"titulo": "Desenvolvedor Java Sênior", "empresa": "BHS", "descricao": "Java, Spring e TDD. " * 5}
    pacote = montar_pacote(c, vaga, analisar(c, vaga["titulo"], vaga["descricao"]), usar_ia=False)
    assert "atualmente com Java" not in pacote.carta
    assert "citadas na descrição" not in pacote.carta


@pytest.mark.parametrize("empresa", ["Grupo Boticário", "Itaú Unibanco", "Nubank"])
def test_carta_sem_artigo_errado_antes_da_empresa(candidato, empresa):
    vaga = {"titulo": "Dev Python", "empresa": empresa, "descricao": "Python"}
    pacote = montar_pacote(candidato, vaga, analisar(candidato, "Dev Python", "Python"), usar_ia=False)
    assert f"na {empresa}" not in pacote.carta and f"no {empresa}" not in pacote.carta
    assert f"({empresa})" in pacote.carta


def test_email_curto_nao_repete_a_carta(candidato):
    vaga = {"titulo": "Dev Python", "empresa": "ACME", "descricao": "Python e Django"}
    pacote = montar_pacote(candidato, vaga, analisar(candidato, "Dev Python", "Python e Django"), usar_ia=False)
    assert pacote.carta not in pacote.corpo_email
    assert "GitHub: https://github.com/ana" in pacote.corpo_email


def test_assunto_curto_e_nome_reduzido():
    c = candidato_de_dict(SENIOR)
    titulo = "Pessoa Desenvolvedora BackEnd Python/ NodeJs Especialista I (Venda Direta)"
    pacote = montar_pacote(c, {"titulo": titulo, "empresa": "X", "descricao": ""}, analisar(c, titulo, ""), usar_ia=False)
    assert "(Venda Direta)" not in pacote.assunto
    assert pacote.assunto.endswith("Rafael Oliveira")


def test_empresa_em_caixa_alta_vira_titulo(candidato):
    from candidatura.adaptador import nome_empresa

    assert nome_empresa("LOJAS TRÊS PASSOS") == "Lojas Três Passos"
    assert nome_empresa("IBM") == "IBM"
    assert nome_empresa("Confidencial") == ""


def test_score_vaga_de_outra_stack_com_cargo_igual(candidato):
    a = analisar(candidato, "Desenvolvedor Backend (Java)", "Java, Spring Boot, Maven, JUnit, Kafka")
    assert a.score < 45


def test_score_vaga_sem_descricao_nao_passa_do_automatico(candidato):
    assert analisar(candidato, "Desenvolvedor Python", "").score <= 55


def test_score_penaliza_senioridade_distante():
    junior = candidato_de_dict(dict(PERFIL, pessoal={"nome": "J", "titulo": "Desenvolvedora Backend Júnior", "email": "j@x.dev"}))
    desc = "Python, Django, PostgreSQL, Docker e Redis."
    assert analisar(junior, "Desenvolvedor Backend Python Sênior", desc).score + 15 < \
        analisar(junior, "Desenvolvedor Backend Python Júnior", desc).score


def test_ingles_basico_nao_atende_vaga_que_pede_ingles():
    c = candidato_de_dict(dict(PERFIL, idiomas=["Inglês — básico"]))
    assert "Inglês" in analisar(c, "Dev", "Inglês avançado obrigatório").faltando


def test_kafka_declarado_atende_mensageria():
    c = candidato_de_dict(dict(PERFIL, habilidades={"Backend": ["Python", "Kafka"]}))
    assert "Mensageria" in analisar(c, "Dev", "Experiência com mensageria e Python").em_comum


def test_vaga_em_ingles_nao_fica_pronta_para_envio(banco, candidato, monkeypatch):
    class FakePDF:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def gerar(self, html, destino): Path(destino).write_bytes(b"%PDF")

    monkeypatch.setattr(servico, "GeradorPDF", FakePDF)
    desc = ("We are looking for a Python developer to join our team. You will work with our clients and "
            "you are expected to build services with Django. Send your resume to jobs@acme.com. ") * 4
    repositorio.inserir({"id": "en1", "titulo": "Python Developer", "empresa": "ACME", "status": "curtida", "descricao": desc})
    v = servico.preparar("en1", candidato, usar_ia=False)
    assert v["status"] == "manual" and "inglês" in v["erro"]
