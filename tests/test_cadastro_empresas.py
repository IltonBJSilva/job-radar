"""Cadastro único (perfil a partir do currículo/GitHub) e candidatura
espontânea para empresas. Sem rede: downloads e API do GitHub são simulados."""

import io
import zipfile

import pytest
import yaml

from candidatura import config, empresas, importar_perfil, repositorio, servico
from candidatura.adaptador import montar_pacote
from candidatura.compatibilidade import analisar
from candidatura.perfil import candidato_de_dict

CV = """JOÃO DA SILVA
Desenvolvedor Backend Python
joao.silva@gmail.com | (34) 99999-1234 | linkedin.com/in/joaosilva | github.com/joaosilva

Resumo
Desenvolvedor backend com 3 anos em APIs REST com Python e Django.

Experiência
Desenvolvedor Backend na Acme Tecnologia
mar/2022 – atual
• Criei APIs REST em Django com PostgreSQL usadas por 40 mil clientes.
• Automatizei o deploy com Docker e GitHub Actions.
Estagiário de TI | Loja Exemplo
2020 - 2022
• Mantive scripts de automação em Python.

Formação
Universidade Federal de Uberlândia
Bacharelado em Ciência da Computação 2016 - 2020

Idiomas
Inglês — intermediário
"""

PERFIL = {
    "pessoal": {"nome": "Ana Teste", "titulo": "Desenvolvedora Backend | Python", "email": "ana@teste.dev"},
    "habilidades": {"Backend": ["Python", "Django"]},
    "experiencias": [{"cargo": "Dev", "empresa": "ACME", "periodo": "2024 – atual",
                      "tecnologias": ["Python"], "conquistas": ["Criei APIs em Django."]}],
}


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", tmp_path / "cand.db")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "saida")
    repositorio.iniciar()
    return tmp_path


# ------------------------------------------------------- cadastro único

def test_contatos_do_curriculo():
    c = importar_perfil.extrair_contatos(CV)
    assert c["email"] == "joao.silva@gmail.com"
    assert "99999-1234" in c["telefone"]
    assert c["links"]["linkedin"] == "https://linkedin.com/in/joaosilva"
    assert c["links"]["github"] == "https://github.com/joaosilva"


@pytest.mark.parametrize("entrada, esperado", [
    ("https://github.com/fulano", "fulano"), ("@fulano", "fulano"), ("fulano-dev", "fulano-dev"),
    ("github.com/fulano/repo", "fulano"), ("../../etc", ""), ("", ""),
])
def test_usuario_github(entrada, esperado):
    assert importar_perfil.usuario_github(entrada) == esperado


def test_leitura_por_secoes_sem_ia():
    p = importar_perfil.perfil_por_secoes(CV)
    assert p["nome"] == "João Da Silva"
    assert p["titulo"] == "Desenvolvedor Backend Python"
    assert "APIs REST" in p["resumo"]
    exps = p["experiencias"]
    assert [e["empresa"] for e in exps] == ["Acme Tecnologia", "Loja Exemplo"]
    assert exps[0]["cargo"] == "Desenvolvedor Backend"
    assert "atual" in exps[0]["periodo"]
    assert len(exps[0]["conquistas"]) == 2 and "40 mil" in exps[0]["conquistas"][0]
    assert {"Django", "PostgreSQL", "Docker"} <= set(exps[0]["tecnologias"])
    assert exps[1]["conquistas"] == ["Mantive scripts de automação em Python."]
    assert p["formacao"][0]["instituicao"].startswith("Universidade")
    assert p["idiomas"] == ["Inglês — intermediário"]


def _resposta(json_, status=200):
    class R:
        status_code = status

        def json(self):
            return json_

        def raise_for_status(self):
            if status >= 400:
                raise RuntimeError(status)
    return R()


def test_github_vira_projetos_sem_forks(monkeypatch):
    repos = [
        {"name": "api-pagamentos", "description": "API em FastAPI", "language": "Python", "topics": ["docker"],
         "stargazers_count": 5, "html_url": "https://github.com/joaosilva/api-pagamentos", "pushed_at": "2025"},
        {"name": "fork-legal", "fork": True, "language": "Go", "stargazers_count": 99},
        {"name": "joaosilva", "description": "readme do perfil", "language": None},
        {"name": "velho", "archived": True, "language": "PHP"},
        {"name": "front", "description": "", "language": "TypeScript", "stargazers_count": 0, "pushed_at": "2024"},
    ]

    def falso_get(url, **kw):
        return _resposta(repos if url.endswith("/repos") else
                         {"name": "João Silva", "bio": "Backend dev", "location": "Uberlândia",
                          "html_url": "https://github.com/joaosilva", "blog": ""})

    monkeypatch.setattr(importar_perfil.requests, "get", falso_get)
    gh = importar_perfil.dados_github("joaosilva")
    assert [p["nome"] for p in gh["projetos"]] == ["api-pagamentos", "front"]
    assert {"Python", "FastAPI", "Docker"} <= set(gh["projetos"][0]["tecnologias"])
    assert "Go" not in gh["tecnologias"] and "PHP" not in gh["tecnologias"]


def test_github_inexistente(monkeypatch):
    monkeypatch.setattr(importar_perfil.requests, "get", lambda url, **kw: _resposta({}, 404))
    with pytest.raises(importar_perfil.ErroImportacao):
        importar_perfil.dados_github("naoexiste")


def test_montar_perfil_completo_e_carregavel(monkeypatch):
    monkeypatch.setattr(importar_perfil, "dados_github", lambda u, **kw: {
        "link": "https://github.com/joaosilva", "projetos": [{"nome": "x", "descricao": "d", "link": "l",
                                                               "tecnologias": ["FastAPI"]}],
        "tecnologias": ["FastAPI"], "blog": "https://joao.dev"})
    exemplo = yaml.safe_load(config.PERFIL_EXEMPLO_PATH.read_text(encoding="utf-8"))
    perfil = importar_perfil.montar_perfil(CV, base=exemplo, usar_ia=False)
    # Dados fictícios do exemplo NÃO vazam para o seu perfil.
    assert perfil["pessoal"]["email"] == "joao.silva@gmail.com"
    assert perfil["pessoal"]["telefone"] != exemplo["pessoal"]["telefone"]
    assert perfil["links"]["portfolio"] == "https://joao.dev"
    assert "FastAPI" in perfil["habilidades"]["Frameworks & Ferramentas"]
    assert "Python" in perfil["habilidades"]["Linguagens"]
    assert perfil["preferencias"]["cargos_alvo"][0] == "desenvolvedor backend python"
    # O YAML gerado volta a ser um candidato válido.
    c = candidato_de_dict(yaml.safe_load(importar_perfil.perfil_para_yaml(perfil)))
    assert c.nome == "João Da Silva" and c.experiencias and c.projetos
    assert importar_perfil.faltando_no_perfil(perfil) == []


def test_ia_que_inventa_empresa_e_descartada(monkeypatch):
    monkeypatch.setattr(importar_perfil.ia, "disponivel", lambda: True)
    monkeypatch.setattr(importar_perfil.ia, "completar", lambda *a, **k: (
        '{"nome":"João","experiencias":[{"empresa":"Acme Tecnologia","conquistas":'
        '["Criei APIs REST em Django com PostgreSQL","Liderei 50 engenheiros na Microsoft"]},'
        '{"empresa":"Google Brasil","conquistas":["Fiz tudo"]}]}'))
    p = importar_perfil.perfil_por_ia(CV)
    assert [e["empresa"] for e in p["experiencias"]] == ["Acme Tecnologia"]
    assert p["experiencias"][0]["conquistas"] == ["Criei APIs REST em Django com PostgreSQL"]


def test_texto_de_docx_e_txt():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:p><w:r><w:t>Fulano &amp; Cia</w:t></w:r></w:p>"
                                        "<w:p><w:t>Python</w:t></w:p></w:document>")
    assert importar_perfil.texto_de_arquivo("cv.docx", buf.getvalue()).splitlines() == ["Fulano & Cia", "Python"]
    assert importar_perfil.texto_de_arquivo("cv.txt", "olá".encode()) == "olá"
    with pytest.raises(importar_perfil.ErroImportacao):
        importar_perfil.texto_de_arquivo("cv.exe", b"MZ")


# -------------------------------------------------------- empresas

@pytest.mark.parametrize("url, raiz", [
    ("https://www.ciandt.com/br/pt-br", "ciandt.com"), ("carreiras.empresa.com.br", "empresa.com.br"),
    ("https://compass.uol", "compass.uol"), ("https://jobs.sap.com/x", "sap.com"),
])
def test_dominio_raiz(url, raiz):
    assert empresas.dominio_raiz(url) == raiz


def test_do_dominio():
    assert empresas.do_dominio("rh@empresa.com.br", "https://www.empresa.com.br")
    assert empresas.do_dominio("talentos@carreiras.empresa.com.br", "empresa.com.br")
    assert not empresas.do_dominio("rh.empresa@gmail.com", "empresa.com.br")
    assert not empresas.do_dominio("rh@empresa.com.br.golpe.io", "empresa.com.br")


SITE = {
    "https://acme.com.br": """<html><body><a href="/sobre">Sobre</a><a href="/trabalhe-conosco">Trabalhe conosco</a>
        <a href="https://acme.gupy.io/">Vagas</a><footer>contato@acme.com.br · fulano@gmail.com</footer></body></html>""",
    "https://acme.com.br/trabalhe-conosco": """<p>Envie seu currículo para <a href="mailto:talentos@acme.com.br">nosso time</a>.
        Parceiros: rh@outraempresa.com.br</p>""",
}


def test_descobrir_prefere_recrutamento_do_dominio():
    visitadas = []

    def baixar(url):
        visitadas.append(url)
        return SITE.get(url)

    r = empresas.descobrir(empresas.Empresa("Acme", "https://acme.com.br"), baixar=baixar, pausa=0)
    assert r["email"] == "talentos@acme.com.br"
    assert "fulano@gmail.com" not in r["emails"] and "rh@outraempresa.com.br" not in r["emails"]
    assert "contato@acme.com.br" in r["emails"]
    assert r["portal"] == "https://acme.gupy.io/"
    assert "https://acme.com.br/sobre" not in visitadas  # só segue links de carreira/contato


def test_descobrir_so_contato_generico_nao_vira_destino():
    r = empresas.descobrir(empresas.Empresa("Acme", "https://acme.com.br"), pausa=0,
                           baixar=lambda u: "<footer>comercial@acme.com.br</footer>" if u == "https://acme.com.br" else None)
    assert r["email"] == "" and r["emails"] == ["comercial@acme.com.br"]


def test_comercial_perto_de_link_vagas_nao_vira_destino():
    html = "<footer>Carreiras · Vagas · Envie seu currículo · comercial@acme.com.br · fale com a gente</footer>"
    r = empresas.descobrir(empresas.Empresa("Acme", "https://acme.com.br"), pausa=0,
                           baixar=lambda u: html if u == "https://acme.com.br" else None)
    assert r["email"] == ""


def test_site_em_javascript_usa_navegador():
    renderizadas = []

    def renderizar(url):
        renderizadas.append(url)
        return '<a href="mailto:vagas@acme.com.br">vagas</a>' if url == "https://acme.com.br" else None

    r = empresas.descobrir(empresas.Empresa("Acme", "https://acme.com.br"), pausa=0,
                           baixar=lambda u: "<div id=root></div>", renderizar=renderizar)
    assert r["email"] == "vagas@acme.com.br" and renderizadas[0] == "https://acme.com.br"


def test_big_tech_nao_e_visitada():
    e = empresas.Empresa("Google", "https://google.com", tipo="Big tech", portal="https://careers.google.com")
    r = empresas.descobrir(e, baixar=lambda u: pytest.fail("não deveria baixar"))
    assert r["email"] == "" and r["portal"] == "https://careers.google.com"


def test_lista_exemplo_carrega_sem_duplicados():
    lista = empresas.carregar_empresas()
    dominios = [empresas.dominio_raiz(e.site) for e in lista]
    assert len(lista) >= 50 and len(dominios) == len(set(dominios))
    assert all(not e.email for e in lista)  # nenhum e-mail "chutado" na lista


def test_fluxo_espontaneo_um_email_por_empresa(banco, monkeypatch):
    candidato = candidato_de_dict(PERFIL)
    monkeypatch.setattr(empresas, "carregar_empresas", lambda caminhos=None: [
        empresas.Empresa("Acme", "https://acme.com.br"), empresas.Empresa("Beta", "https://beta.com"),
        empresas.Empresa("Gama", "https://gama.com"),
    ])
    empresas.sincronizar_lista()
    with repositorio.conectar() as conn:
        conn.execute("UPDATE empresas SET email='rh@acme.com.br' WHERE dominio='acme.com.br'")
        conn.execute("UPDATE empresas SET email='vagas@beta.com' WHERE dominio='beta.com'")
    ids = empresas.criar_candidaturas(candidato=candidato)
    assert len(ids) == 2  # Gama não tem e-mail nem portal
    v = repositorio.obter(ids[0])
    assert v["origem"] == "espontanea" and v["status"] == "curtida" and v["titulo"] == "Desenvolvedora Backend"
    # Rodar de novo não duplica.
    assert sorted(empresas.criar_candidaturas(candidato=candidato)) == sorted(ids)
    assert len(repositorio.listar("curtida")) == 2


def test_carta_espontanea_nao_fala_de_vaga(banco):
    candidato = candidato_de_dict(PERFIL)
    vaga = {"titulo": "Desenvolvedora Backend", "empresa": "STEFANINI", "origem": "espontanea"}
    pacote = montar_pacote(candidato, vaga, analisar(candidato, vaga["titulo"], ""))
    assert pacote.assunto == "Candidatura espontânea: Desenvolvedora Backend — Ana Teste"
    assert "na empresa Stefanini" in pacote.carta
    assert "à vaga" not in pacote.carta and "à vaga" not in pacote.corpo_email
    assert "ACME: criei APIs em Django" in pacote.carta


def test_preparo_espontaneo_nao_baixa_site_nem_usa_contato(banco, monkeypatch):
    monkeypatch.setattr(servico, "buscar_descricao", lambda link: pytest.fail("não deveria baixar o site"))

    class GeradorFalso:
        def gerar(self, html, destino):
            destino.write_bytes(b"%PDF-falso")

    candidato = candidato_de_dict(PERFIL)
    repositorio.inserir({"id": "esp1", "titulo": "Dev Backend", "empresa": "Acme", "link": "https://acme.com.br",
                         "origem": "espontanea", "status": "curtida", "emails_encontrados": ["contato@acme.com.br"]})
    v = servico.preparar("esp1", candidato, GeradorFalso())
    assert v["status"] == "manual" and not v["email_destino"]  # contato@ não vira destino sozinho
    repositorio.inserir({"id": "esp2", "titulo": "Dev Backend", "empresa": "Beta", "link": "https://beta.com",
                         "origem": "espontanea", "status": "curtida", "email_destino": "rh@beta.com"})
    v = servico.preparar("esp2", candidato, GeradorFalso())
    assert v["status"] == "pronta" and v["score"] is None
    assert "espontânea" in (banco / "saida").joinpath(next(p.name for p in (banco / "saida").iterdir() if "beta" in p.name),
                                                     "carta.html").read_text(encoding="utf-8")


# ------------------------------------------------------------- web

LOCAL = {"Origin": "http://localhost"}


def test_paginas_perfil_e_empresas(banco, tmp_path, monkeypatch):
    from web.app import criar_app

    perfil_path = tmp_path / "candidato.yaml"
    perfil_path.write_text(config.PERFIL_EXEMPLO_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(config, "PERFIL_PATH", perfil_path)
    monkeypatch.setattr(empresas, "carregar_empresas", lambda caminhos=None: [empresas.Empresa("Acme", "acme.com.br")])
    c = criar_app().test_client()
    # Perfil de exemplo: a home manda para o cadastro único.
    r = c.get("/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/perfil")
    assert "Monte seu perfil" in c.get("/perfil").get_data(as_text=True)

    # Gera a partir de texto colado (sem GitHub) e mostra para revisão, sem salvar ainda.
    r = c.post("/perfil", data={"acao": "gerar", "texto": CV}, headers=LOCAL)
    html = r.get_data(as_text=True)
    assert "joao.silva@gmail.com" in html and "Confira" in html
    assert "seu.email@gmail.com" in perfil_path.read_text(encoding="utf-8")

    # Salvar com e-mail de exemplo é recusado; com dados reais, salva e faz backup.
    r = c.post("/perfil", data={"acao": "salvar", "yaml": config.PERFIL_EXEMPLO_PATH.read_text(encoding="utf-8")},
               headers=LOCAL)
    assert "Não salvei" in r.get_data(as_text=True)
    novo = yaml.safe_dump(PERFIL, allow_unicode=True)
    r = c.post("/perfil", data={"acao": "salvar", "yaml": novo}, headers=LOCAL)
    assert r.status_code == 302
    assert "ana@teste.dev" in perfil_path.read_text(encoding="utf-8")
    assert perfil_path.with_suffix(".yaml.bak").exists()

    html = c.get("/empresas").get_data(as_text=True)
    assert "Acme" in html and "ainda não procurado" in html
    assert c.post("/empresas", data={"nome": "Beta", "site": "beta.com", "email": "x@"}, headers=LOCAL).status_code == 302
    assert "Beta" not in c.get("/empresas").get_data(as_text=True)
    c.post("/empresas", data={"nome": "Beta", "site": "beta.com", "email": "rh@beta.com"}, headers=LOCAL)
    assert "rh@beta.com" in c.get("/empresas").get_data(as_text=True)
    assert c.post("/api/empresas/preparar", json={"dominios": "x"}, headers=LOCAL).status_code == 400
    # Rotas de escrita continuam protegidas contra outros sites.
    assert c.post("/empresas", data={"nome": "Mal", "site": "mal.com"},
                  headers={"Origin": "https://malicioso.com"}).status_code == 403
