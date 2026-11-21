"""Vários perfis (pessoas) na mesma instalação, áreas, fontes por perfil,
vocabulário de outras áreas e leitura de PDF do LaTeX. Sem rede."""

import pytest
import yaml

from candidatura import areas, compatibilidade, config, repositorio, servico
from candidatura.importar_perfil import corrigir_acentos_latex
from candidatura.perfil import candidato_de_dict, carregar_candidato, salvar_preferencias

LOCAL = {"Origin": "http://localhost"}

PERFIL_CIBER = {
    "pessoal": {"nome": "Carla Souza", "titulo": "Analista de Segurança da Informação", "email": "carla@teste.dev"},
    "resumo": "Analista de SOC.",
    "habilidades": {"Segurança": ["SIEM", "Splunk", "Pentest", "ISO 27001", "Firewall", "Python"]},
    "experiencias": [{"cargo": "Analista SOC", "empresa": "SecCorp", "periodo": "2023 – Atual",
                      "conquistas": ["Monitoramento com Splunk e resposta a incidentes."]}],
}


@pytest.fixture
def instalacao(tmp_path, monkeypatch):
    """Instalação isolada: principal + pasta perfis/ dentro de tmp_path."""
    principal = {
        "PERFIL_PATH": tmp_path / "config" / "candidato.yaml",
        "CANDIDATURAS_DB_PATH": tmp_path / "data" / "candidaturas.db",
        "SAIDA_DIR": tmp_path / "saida",
        "SMTP_HOST": "smtp.gmail.com", "SMTP_PORTA": 587, "SMTP_USUARIO": "dono@gmail.com", "SMTP_SENHA": "senha-dono",
        "EMAIL_COPIA_PARA_MIM": False, "ENVIO_REAL": True, "ENVIAR_AO_CURTIR": False,
    }
    monkeypatch.setattr(config, "_PADRAO_PRINCIPAL", principal)
    monkeypatch.setattr(config, "PERFIS_DIR", tmp_path / "perfis")
    monkeypatch.setattr(config, "PERFIL_ATIVO_PATH", tmp_path / "data" / "perfil_ativo.txt")
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    for chave in list(principal) + ["PERFIL_ATIVO"]:
        monkeypatch.setattr(config, chave, getattr(config, chave))  # restaura tudo no fim do teste
    principal["PERFIL_PATH"].parent.mkdir(parents=True)
    from tests.test_candidatura import PERFIL

    principal["PERFIL_PATH"].write_text(yaml.safe_dump(PERFIL, allow_unicode=True), encoding="utf-8")
    config.ativar_perfil("principal")
    repositorio.iniciar()
    return tmp_path


def test_perfil_novo_isola_curriculo_fila_e_email(instalacao):
    repositorio.inserir({"id": "v-dono", "titulo": "Dev Python"})
    (config.PERFIS_DIR / "carla").mkdir(parents=True)
    config.ativar_perfil("carla")
    # Perfil novo NÃO herda e-mail/senha nem o envio real do dono.
    assert (config.SMTP_USUARIO, config.SMTP_SENHA, config.ENVIO_REAL) == ("", "", False)
    assert config.PERFIL_PATH == instalacao / "perfis" / "carla" / "candidato.yaml"
    repositorio.iniciar()
    assert repositorio.obter("v-dono") is None  # fila separada
    config.gravar_config_perfil("carla", {"SMTP_USUARIO": "carla@gmail.com", "SMTP_SENHA": "abc", "ENVIO_REAL": "true"})
    assert (config.SMTP_USUARIO, config.ENVIO_REAL) == ("carla@gmail.com", True)
    assert "SMTP_SENHA=abc" in (instalacao / "perfis" / "carla" / "config.env").read_text(encoding="utf-8")
    # Volta para o dono: tudo dele de novo.
    config.ativar_perfil("principal")
    assert (config.SMTP_USUARIO, config.SMTP_SENHA) == ("dono@gmail.com", "senha-dono")
    assert repositorio.obter("v-dono") is not None
    assert config.PERFIL_ATIVO_PATH.read_text(encoding="utf-8") == "principal"
    assert config.listar_perfis() == ["principal", "carla"]


def test_id_de_perfil_invalido_nao_escapa_da_pasta(instalacao):
    for ruim in ("../etc", "a/b", "", "Maiúscula", "x" * 50):
        with pytest.raises(ValueError):
            config.ativar_perfil(ruim)


def test_gravar_config_mantem_o_resto_do_arquivo(instalacao):
    env = config.ENV_PATH
    env.write_text("# comentario\nTELEGRAM_BOT_TOKEN=xyz\nSMTP_USUARIO=antigo@gmail.com\n", encoding="utf-8")
    config.gravar_config_perfil("principal", {"SMTP_USUARIO": "novo@gmail.com", "ENVIAR_AO_CURTIR": "true"})
    texto = env.read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=xyz" in texto and "# comentario" in texto
    assert "SMTP_USUARIO=novo@gmail.com" in texto and "antigo" not in texto and "ENVIAR_AO_CURTIR=true" in texto
    assert config.SMTP_USUARIO == "novo@gmail.com" and config.ENVIAR_AO_CURTIR is True


def test_salvar_preferencias_preserva_curriculo_e_cabecalho(instalacao):
    texto = "# Meu perfil\n# não apague\n" + config.PERFIL_PATH.read_text(encoding="utf-8")
    config.PERFIL_PATH.write_text(texto, encoding="utf-8")
    salvar_preferencias({"area": "ciberseguranca", "termos_busca": ["SOC"]})
    novo = config.PERFIL_PATH.read_text(encoding="utf-8")
    assert novo.startswith("# Meu perfil\n# não apague\n")
    c = carregar_candidato()
    assert c.preferencias["area"] == "ciberseguranca" and c.preferencias["cargos_alvo"] == ["backend", "python"]
    assert c.nome == "Ana Teste" and config.PERFIL_PATH.with_suffix(".yaml.bak").exists()


# ------------------------------------------------------------ áreas e fontes

def test_area_preenche_preferencias_e_fontes():
    p = areas.preferencias_da_area("ciberseguranca")
    assert "radar" not in p["fontes"] and "linkedin" in p["fontes"]  # radar só tem vaga de dev
    assert "seguranca da informacao" in p["cargos_alvo"] and p["termos_busca"]
    assert areas.preferencias_da_area("inexistente")["area"] == "outra"
    # Perfil antigo (sem "fontes"/"termos_busca") continua como antes.
    assert areas.fontes({}) == ["radar", "github", "gupy", "remotar"]
    assert areas.termos_busca({"termos_remotar": ["python"]}) == ["python"]


def test_importar_do_perfil_usa_fontes_e_termos_do_perfil(monkeypatch):
    chamadas = {}
    from candidatura import fontes

    monkeypatch.setattr(repositorio, "iniciar", lambda: None)
    monkeypatch.setattr(repositorio, "importar_do_radar", lambda: chamadas.setdefault("radar", 1))
    monkeypatch.setattr(fontes, "coletar_github", lambda: chamadas.setdefault("github", 1))
    monkeypatch.setattr(fontes, "coletar_gupy", lambda termos: chamadas.setdefault("gupy", termos))
    monkeypatch.setattr(fontes, "coletar_remotar", lambda termos: chamadas.setdefault("remotar", termos))
    monkeypatch.setattr(fontes, "coletar_scrapers", lambda nomes, termos, foco=None: chamadas.setdefault("local", (nomes, termos)) and {})
    monkeypatch.setattr(servico, "pontuar_novas", lambda: 0)
    c = candidato_de_dict({**PERFIL_CIBER, "preferencias": {"fontes": ["linkedin", "gupy", "catho"],
                                                             "termos_busca": ["analista SOC", "pentest"]}})
    servico.importar_do_perfil(c)
    assert chamadas == {"gupy": ["analista SOC", "pentest"],
                        "local": (["linkedin", "catho"], ["analista SOC", "pentest"])}


def test_job_do_scraper_vira_vaga():
    from candidatura.fontes import job_para_vaga
    from core.job import Job

    v = job_para_vaga(Job(titulo="Analista SOC", empresa="SecCorp", local="Recife - PE", link="https://x/1",
                          site="LinkedIn", modalidade="Remoto", texto="Envie para vagas@seccorp.com.br"))
    assert v["origem"] == "busca" and v["email_destino"] == "vagas@seccorp.com.br" and v["local"] == "Recife - PE"


# ------------------------------------------------------- outras áreas na nota

def test_vocabulario_de_ciberseguranca_pontua():
    c = candidato_de_dict({**PERFIL_CIBER, "preferencias": areas.preferencias_da_area("ciberseguranca")})
    desc = "Buscamos analista com SIEM (Splunk), pentest, firewall Fortinet e conhecimento de ISO 27001."
    a = compatibilidade.analisar(c, "Analista de Segurança da Informação Pleno", desc)
    assert {"SIEM", "Splunk", "Pentest", "Firewall", "ISO 27001"} <= set(a.em_comum)
    assert a.score >= 80


def test_termos_extras_do_perfil_viram_competencia():
    base = {**PERFIL_CIBER, "habilidades": {"ERP": ["SAP", "AutoCAD"]}}
    sem = candidato_de_dict(base)
    com = candidato_de_dict({**base, "preferencias": {"termos_extras": ["SAP", "AutoCAD"]}})
    desc = "Experiência com SAP e AutoCAD."
    assert compatibilidade.analisar(sem, "Analista", desc).em_comum == []
    assert set(compatibilidade.analisar(com, "Analista", desc).em_comum) == {"SAP", "AutoCAD"}
    compatibilidade.usar_termos_extras([])  # não vaza para os outros testes
    assert "SAP" not in compatibilidade.extrair_tecnologias("SAP")


def test_acentos_do_latex():
    assert corrigir_acentos_latex("ILTON J ´UNIOR") == "ILTON JÚNIOR"
    assert corrigir_acentos_latex("FORMAC¸ ˜AO e automa¸c˜ao") == "FORMAÇÃO e automação"
    assert corrigir_acentos_latex("Ass´ıncrono, experiˆencia") == "Assíncrono, experiência"
    assert corrigir_acentos_latex("aten¸c˜ao `a experiˆencia") == "atenção à experiência"


# ------------------------------------------------------------------ telas

@pytest.fixture
def cliente(instalacao):
    from web.app import criar_app

    return criar_app().test_client()


def test_tela_cria_troca_e_configura_perfil(cliente, instalacao):
    assert "+ Novo perfil" in cliente.get("/fila").get_data(as_text=True)
    r = cliente.post("/perfis/novo", data={"nome": "Carla Souza"}, headers=LOCAL)
    assert r.status_code == 302 and r.headers["Location"].endswith("/perfil")
    assert config.PERFIL_ATIVO == "carla-souza" and (instalacao / "perfis" / "carla-souza").is_dir()
    # Ainda sem currículo: configurações mandam para o cadastro.
    assert cliente.get("/configuracoes").headers["Location"].endswith("/perfil")
    config.PERFIL_PATH.write_text(yaml.safe_dump(PERFIL_CIBER, allow_unicode=True), encoding="utf-8")
    pagina = cliente.get("/configuracoes").get_data(as_text=True)
    assert "Configurações de Carla Souza" in pagina and "Cibersegurança" in pagina
    r = cliente.post("/configuracoes", headers=LOCAL, data={
        "area": "ciberseguranca", "termos_busca": "analista SOC, pentest", "cargos_alvo": "soc, seguranca",
        "fontes": ["linkedin", "gupy"], "senioridade": "Pleno", "smtp_usuario": "carla@gmail.com",
        "smtp_senha": "abcd efgh ijkl mnop", "envio_real": "on"})
    assert r.status_code == 302
    c = carregar_candidato()
    assert c.preferencias["termos_busca"] == ["analista SOC", "pentest"] and c.preferencias["fontes"] == ["linkedin", "gupy"]
    assert (config.SMTP_USUARIO, config.SMTP_SENHA, config.ENVIO_REAL) == ("carla@gmail.com", "abcdefghijklmnop", True)
    # Senha em branco mantém a salva.
    cliente.post("/configuracoes", headers=LOCAL, data={"area": "ciberseguranca", "termos_busca": "SOC",
                                                         "smtp_usuario": "carla@gmail.com", "smtp_senha": ""})
    assert config.SMTP_SENHA == "abcdefghijklmnop"
    # Troca de volta pelo seletor (espera o recálculo que o "salvar" agendou).
    import time

    for _ in range(100):
        estado = cliente.get("/api/estado").get_json()
        if not estado["ocupado"] and not estado["pendentes"]:
            break
        time.sleep(0.05)
    assert cliente.post("/api/perfil/ativar", json={"id": "principal"}, headers=LOCAL).status_code == 200
    assert config.PERFIL_ATIVO == "principal" and config.SMTP_USUARIO == "dono@gmail.com"
    assert cliente.post("/api/perfil/ativar", json={"id": "../x"}, headers=LOCAL).status_code == 404


def test_configuracoes_recusa_email_invalido_e_sem_termos(cliente):
    r = cliente.post("/configuracoes", headers=LOCAL, data={"termos_busca": "x", "smtp_usuario": "nao-e-email"})
    assert "E-mail inválido" in r.get_data(as_text=True)
    r = cliente.post("/configuracoes", headers=LOCAL, data={"termos_busca": "", "smtp_usuario": ""})
    assert "pelo menos um termo" in r.get_data(as_text=True)


def test_importador_nao_supoe_que_a_pessoa_e_dev():
    from candidatura.importar_perfil import montar_perfil, titulo_do_texto

    cv = ("CARLA SOUZA\ncarla@gmail.com | (31) 99999-0000 | Belo Horizonte - MG\n\nRESUMO\n"
          "Analista de Segurança da Informação com 3 anos em SOC e SIEM (Splunk).\n")
    p = montar_perfil(cv)
    assert p["pessoal"]["titulo"] == "Analista de Segurança da Informação"
    assert p["pessoal"]["cidade"] == "Belo Horizonte - MG"
    assert p["preferencias"]["termos_busca"] == ["analista de segurança da informação"]
    assert titulo_do_texto("", [{"cargo": "Analista de SOC Pleno"}]) == "Analista de SOC"
    assert titulo_do_texto("Engenheiro de Software com foco em backend.", []) == "Engenheiro de Software"


def test_curtidas_pendentes_retomam_o_envio_ao_reabrir(instalacao, monkeypatch):
    chamadas = []
    monkeypatch.setattr(servico, "preparar_e_enviar", lambda i: chamadas.append(("enviar", i)))
    monkeypatch.setattr(servico, "preparar", lambda i: chamadas.append(("preparar", i)))
    repositorio.inserir({"id": "c1", "titulo": "Dev", "status": "curtida"})
    monkeypatch.setattr(config, "ENVIAR_AO_CURTIR", True)
    from web.app import criar_app

    criar_app()
    import time

    for _ in range(50):
        if chamadas:
            break
        time.sleep(0.05)
    assert chamadas == [("enviar", "c1")]
