"""Vagas nos sites das empresas, foco regional (ex.: Uberlândia) e a
separação "falta enviar" x "já enviadas" em Prontas. Sem rede."""

import pytest

from candidatura import areas, config, empresas, repositorio, vagas_empresas

PREFS_DEV = {"cargos_alvo": ["backend", "desenvolvedor python"], "termos_busca": ["python", "backend"]}
LOCAL = {"Origin": "http://localhost"}


@pytest.mark.parametrize("link, ats", [
    ("https://algar.gupy.io/", "gupy:algar"),
    ("https://algar.gupy.io/jobs/123?x=1", "gupy:algar"),
    ("https://job-boards.greenhouse.io/zupinnovation", "greenhouse:zupinnovation"),
    ("https://boards.greenhouse.io/nubank/jobs/1", "greenhouse:nubank"),
    ("https://jobs.lever.co/acme/abc", "lever:acme"),
    ("https://portal.gupy.io/job-search", ""),
    ("https://www.empresa.com.br/carreiras", ""),
])
def test_ats_do_link(link, ats):
    assert vagas_empresas.ats_do_link(link) == ats


def test_so_entra_vaga_que_combina_com_o_perfil():
    assert vagas_empresas.combina_com_perfil("Desenvolvedor Java SR", PREFS_DEV)          # tecnologia
    assert vagas_empresas.combina_com_perfil("Pessoa Engenheira de Software", PREFS_DEV)  # palavra de TI
    assert vagas_empresas.combina_com_perfil("Backend Pleno", PREFS_DEV)                  # cargo do perfil
    assert not vagas_empresas.combina_com_perfil("Vendedor Externo", PREFS_DEV)
    assert not vagas_empresas.combina_com_perfil("Auxiliar de Logística", PREFS_DEV)


class _Resposta:
    def __init__(self, status, texto="", dados=None):
        self.status_code, self.text, self._dados = status, texto, dados

    def json(self):
        return self._dados


def test_le_vagas_da_pagina_gupy_e_ignora_banco_de_talentos():
    html = ('<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"jobs":['
            '{"id":1,"title":"Desenvolvedor Python","type":"vacancy_type_effective","workplace":{"address":'
            '{"city":"Uberlândia","stateShortName":"MG"},"workplaceType":"hybrid"}},'
            '{"id":2,"title":"Banco de Talentos","type":"vacancy_type_talent_pool","workplace":{}}]}}}</script>')

    class Sessao:
        def get(self, url, **k):
            return _Resposta(200, html) if url == "https://algar.gupy.io/" else _Resposta(404)

    vagas = vagas_empresas.vagas_do_ats("gupy:algar", Sessao())
    assert vagas == [{"titulo": "Desenvolvedor Python", "local": "Uberlândia - MG", "modalidade": "Híbrido",
                      "link": "https://algar.gupy.io/jobs/1", "site": "Gupy (site da empresa)"}]
    assert vagas_empresas.vagas_do_ats("gupy:naoexiste", Sessao()) is None


def test_descobre_portal_testando_os_enderecos_comuns():
    class Sessao:
        def get(self, url, **k):
            if "boards-api.greenhouse.io/v1/boards/zup/" in url:
                return _Resposta(200, dados={"jobs": []})
            return _Resposta(404)

    assert vagas_empresas.descobrir_ats("Zup", "zup.com.br", "", Sessao()) == "greenhouse:zup"
    assert vagas_empresas.descobrir_ats("X", "x.com", "https://jobs.lever.co/xis", Sessao()) == "lever:xis"


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", tmp_path / "cand.db")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "saida")
    repositorio.iniciar()
    return tmp_path


def test_coleta_prioriza_empresas_da_cidade_e_guarda_o_portal(banco, monkeypatch):
    lista = [empresas.Empresa("Empresa SP", "sp.com.br", "Produto", "São Paulo"),
             empresas.Empresa("Empresa Udia", "udia.com.br", "Produto", "Uberlândia")]
    monkeypatch.setattr(empresas, "carregar_empresas", lambda caminhos=None: lista)
    ordem = []

    def descobrir(nome, site, portal="", sessao=None):
        ordem.append(nome)
        return "gupy:udia" if nome == "Empresa Udia" else ""

    monkeypatch.setattr(vagas_empresas, "descobrir_ats", descobrir)
    monkeypatch.setattr(vagas_empresas, "vagas_do_ats", lambda ats, sessao=None: [
        {"titulo": "Desenvolvedor Python", "local": "Uberlândia - MG", "modalidade": "",
         "site": "Gupy (site da empresa)", "link": "https://udia.gupy.io/jobs/1"},
        {"titulo": "Vendedor", "local": "", "modalidade": "", "site": "x", "link": "https://udia.gupy.io/jobs/2"},
    ] if ats else None)
    prefs = {**PREFS_DEV, "foco_regional": {"ativo": True, "cidade": "Uberlândia", "uf": "MG"}}
    assert vagas_empresas.coletar(prefs, paralelo=1) == 1  # o "Vendedor" não entra
    assert ordem[0] == "Empresa Udia"  # cidade do foco primeiro
    v = repositorio.listar("nova")[0]
    assert (v["empresa"], v["origem"]) == ("Empresa Udia", "empresa")
    with repositorio.conectar() as conn:
        assert conn.execute("SELECT ats FROM empresas WHERE nome='Empresa Udia'").fetchone()[0] == "gupy:udia"
    # Segunda vez: vai direto ao portal guardado; quem não tinha portal só é testado de novo em 14 dias.
    ordem.clear()
    vagas_empresas.coletar(prefs, paralelo=1)
    assert ordem == []


def test_foco_regional_liga_e_desliga():
    assert areas.foco_regional({"foco_regional": {"ativo": True, "cidade": "Uberlândia", "uf": "mg"}}) == \
        {"cidade": "Uberlândia", "uf": "MG"}
    assert areas.foco_regional({"foco_regional": {"ativo": False, "cidade": "Uberlândia"}}) is None
    assert areas.foco_regional({}) is None


def test_linkedin_busca_tambem_na_cidade_do_foco():
    from candidatura.fontes import _scraper

    s = _scraper("linkedin", ["python"], {"cidade": "Uberlândia", "uf": "MG"})
    assert s.locations_cidades_presencial == ["Uberlândia, Minas Gerais, Brazil"]
    assert _scraper("linkedin", ["python"]).locations_cidades_presencial == []


@pytest.fixture
def cliente(banco, tmp_path, monkeypatch):
    import yaml

    from tests.test_candidatura import PERFIL

    perfil = tmp_path / "c.yaml"
    dados = {**PERFIL, "preferencias": {**PERFIL["preferencias"],
                                        "foco_regional": {"ativo": True, "cidade": "Uberlândia", "uf": "MG"}}}
    perfil.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config, "PERFIL_PATH", perfil)
    from web.app import criar_app

    return criar_app().test_client()


def test_swipe_poe_a_cidade_do_foco_primeiro(cliente):
    repositorio.inserir({"id": "sp", "titulo": "Desenvolvedor Python", "local": "São Paulo - SP", "site": "Gupy",
                         "score": 95})
    repositorio.inserir({"id": "ud", "titulo": "Desenvolvedor Python", "local": "Uberlândia - MG", "site": "Gupy",
                         "score": 60})
    vagas = cliente.get("/api/proximas?n=5").get_json()
    assert [v["id"] for v in vagas] == ["ud", "sp"] and vagas[0]["foco"] and not vagas[1]["foco"]


def test_configuracoes_liga_e_desliga_o_foco(cliente):
    from candidatura.perfil import carregar_candidato

    base = {"termos_busca": "python", "smtp_usuario": ""}
    r = cliente.post("/configuracoes", headers=LOCAL, data={**base, "foco_ativo": "on", "foco_cidade": "udia"})
    assert r.status_code == 302, r.get_data(as_text=True)[:3000]
    foco = carregar_candidato().preferencias["foco_regional"]
    assert {k: foco[k] for k in ("ativo", "cidade", "uf")} == {"ativo": True, "cidade": "Uberlândia", "uf": "MG"}
    assert foco["alerta_telegram"] is False and foco["alerta_limiar"] == 75
    cliente.post("/configuracoes", headers=LOCAL, data={**base, "foco_cidade": "Uberlândia - MG"})
    assert carregar_candidato().preferencias["foco_regional"]["ativo"] is False


def test_prontas_separa_falta_enviar_de_ja_enviadas(cliente):
    repositorio.inserir({"id": "p1", "titulo": "Vaga Pronta", "empresa": "ACME", "status": "pronta",
                         "email_destino": "rh@acme.com.br"})
    repositorio.inserir({"id": "e1", "titulo": "Vaga Enviada", "empresa": "Beta", "status": "enviada",
                         "email_destino": "rh@beta.com.br", "enviada_em": "2026-11-20T10:00:00"})
    repositorio.inserir({"id": "p2", "titulo": "Outra da Beta", "empresa": "Beta", "status": "pronta",
                         "email_destino": "vagas@beta.com.br"})
    falta = cliente.get("/fila?aba=pronta").get_data(as_text=True)
    assert "Vaga Pronta" in falta and "Vaga Enviada" not in falta
    assert "Falta enviar" in falta and "Já enviadas" in falta
    assert falta.count("já mandou para este e-mail/empresa") == 1  # só a da Beta, que já recebeu
    assert "descartar('p2'" in falta and "enviar('p2'" not in falta and "enviar('p1'" in falta
    enviadas = cliente.get("/fila?aba=pronta&ver=enviadas").get_data(as_text=True)
    assert "Vaga Enviada" in enviadas and "Vaga Pronta" not in enviadas and "✅" in enviadas
