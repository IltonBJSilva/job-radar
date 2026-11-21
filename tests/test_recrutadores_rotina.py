"""Colar post, posts públicos (Brave), Hunter, trava da IA, vaga encerrada,
aviso no Telegram, funil e rotina diária. Sem rede e sem Agendador."""

import pytest

from candidatura import alertas, busca_posts, config, funil, hunter, ia, repositorio, rotina
from candidatura.perfil import candidato_de_dict
from candidatura.posts import ler_post
from candidatura.servico import vaga_encerrada

LOCAL = {"Origin": "http://localhost"}


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", tmp_path / "cand.db")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "saida")
    repositorio.iniciar()
    return tmp_path


class _R:
    def __init__(self, status=200, dados=None, texto="", url="https://x/jobs/1"):
        self.status_code, self._dados, self.text, self.url = status, dados, texto, url

    def json(self):
        return self._dados

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(str(self.status_code))


# ---------------------------------------------------------------- colar post

def test_le_post_de_recrutador():
    r = ler_post("🚀 A Sankhya está contratando!\nVaga: Desenvolvedor Backend Python Pleno\n"
                 "📍 Uberlândia - MG | Híbrido\nEnvie o currículo para talentos@sankhya.com.br\n#vagas")
    assert (r["titulo"], r["empresa"], r["email"], r["local"], r["modalidade"]) == (
        "Desenvolvedor Backend Python Pleno", "Sankhya", "talentos@sankhya.com.br", "Uberlândia - MG", "Híbrido")


def test_le_post_com_cidade_no_meio_e_empresa_pelo_link():
    r = ler_post("Vaga para Analista de Segurança da Informação (SOC) em Belo Horizonte.\nEnvie para rh@seccorp.com.br")
    assert (r["titulo"], r["empresa"], r["local"]) == ("Analista de Segurança da Informação", "Seccorp", "Belo Horizonte - MG")
    r = ler_post("Estagiário de TI\nUberlândia/MG\nInscreva-se: https://algar.gupy.io/jobs/123")
    assert (r["titulo"], r["empresa"], r["email"], r["link"]) == ("Estagiário de TI", "Algar", "", "https://algar.gupy.io/jobs/123")


def test_le_post_com_email_pessoal_nao_inventa_empresa():
    r = ler_post("Buscamos pessoa Engenheira de Dados Sênior, 100% remoto. Mande o CV para joana.rh@gmail.com")
    assert r["email"] == "joana.rh@gmail.com" and r["empresa"] == "" and r["local"] == "Remoto"


# ---------------------------------------------------------------- posts públicos

def test_posts_publicos_so_entram_com_email_de_recrutamento(banco, monkeypatch):
    monkeypatch.setattr(config, "BRAVE_API_KEY", "chave")
    monkeypatch.setattr(busca_posts.time, "sleep", lambda s: None)
    resultados = {"web": {"results": [
        {"title": "Vaga Dev Python | Acme", "url": "https://www.linkedin.com/posts/a-1",
         "description": "Estamos contratando Desenvolvedor Python Pleno em Uberlândia. Envie o CV para vagas@acme.com.br"},
        {"title": "Post sem e-mail", "url": "https://www.linkedin.com/posts/b-2", "description": "Vaga de dev, me chama"},
        {"title": "Fale com a gente", "url": "https://www.linkedin.com/posts/c-3",
         "description": "Dúvidas comerciais: contato@outra.com.br"},
    ]}}

    class Sessao:
        def get(self, url, params=None, headers=None, timeout=None):
            assert headers["X-Subscription-Token"] == "chave"
            return _R(200, resultados)

    prefs = {"termos_busca": ["python"], "foco_regional": {"ativo": True, "cidade": "Uberlândia", "uf": "MG"}}
    assert busca_posts.coletar(prefs, Sessao(), baixar=lambda link: "") == 1
    v = repositorio.listar("nova")[0]
    assert (v["email_destino"], v["origem"], v["local"]) == ("vagas@acme.com.br", "post", "Uberlândia - MG")
    assert any("Uberlândia" in q for q in busca_posts.consultas(prefs))


def test_posts_sem_chave_nao_fazem_nada(banco, monkeypatch):
    monkeypatch.setattr(config, "BRAVE_API_KEY", "")
    assert busca_posts.coletar({"termos_busca": ["python"]}, sessao=None) == 0


# ---------------------------------------------------------------- Hunter

def test_hunter_prefere_generico_de_rh_depois_recrutadora():
    emails = [
        {"value": "joao@acme.com.br", "type": "personal", "confidence": 99, "position": "CFO"},
        {"value": "ana@acme.com.br", "type": "personal", "confidence": 92, "position": "Talent Acquisition"},
        {"value": "vagas@acme.com.br", "type": "generic", "confidence": 80},
        {"value": "rh@outra.com", "type": "generic", "confidence": 99},       # outro domínio
        {"value": "talentos@acme.com.br", "type": "generic", "confidence": 40},  # pouca confiança
    ]
    assert hunter.escolher(emails, "acme.com.br")["value"] == "vagas@acme.com.br"
    assert hunter.escolher(emails[:2], "acme.com.br")["value"] == "ana@acme.com.br"
    assert hunter.escolher(emails[:1], "acme.com.br") is None  # CFO não é recrutamento


def test_hunter_completa_empresas_sem_email_e_para_quando_acaba_a_cota(banco, monkeypatch):
    from candidatura import empresas

    monkeypatch.setattr(config, "HUNTER_API_KEY", "k")
    lista = [empresas.Empresa("Acme", "acme.com.br", "Produto", "Uberlândia"),
             empresas.Empresa("Beta", "beta.com.br", "Produto", "São Paulo")]
    monkeypatch.setattr(empresas, "carregar_empresas", lambda caminhos=None: lista)
    chamadas = []

    class Sessao:
        def get(self, url, params=None, timeout=None):
            chamadas.append(params["domain"])
            if params["domain"] == "acme.com.br":
                return _R(200, {"data": {"emails": [{"value": "vagas@acme.com.br", "type": "generic", "confidence": 90}]}})
            return _R(429)

    r = hunter.completar_empresas({"foco_regional": {"ativo": True, "cidade": "Uberlândia"}}, limite=5, sessao=Sessao())
    assert r["achados"] == 1 and r["erros"] == ["acabaram as buscas do mês no Hunter"]
    assert chamadas == ["acme.com.br", "beta.com.br"]  # cidade do foco primeiro
    with repositorio.conectar() as conn:
        assert conn.execute("SELECT email FROM empresas WHERE nome='Acme'").fetchone()[0] == "vagas@acme.com.br"


# ---------------------------------------------------------------- IA sem invenção

def test_ia_descarta_numero_inventado():
    from tests.test_candidatura import PERFIL

    c = candidato_de_dict({**PERFIL, "experiencias": [{**PERFIL["experiencias"][0],
                                                       "conquistas": ["Reduzi custos em 60%."]}]})
    assert ia.saida_segura("Reduziu custos em 60% na ACME.", c) is not None
    assert ia.saida_segura("Tem 8 anos de experiência.", c) is None          # 8 não está no perfil
    assert ia.saida_segura("Vaga de 2026 citada na vaga.", c, contexto="Vaga 2026") is not None


def test_resumo_e_do_perfil_por_padrao_mesmo_com_ia(monkeypatch):
    from candidatura.adaptador import montar_pacote
    from candidatura.compatibilidade import analisar
    from tests.test_candidatura import PERFIL

    monkeypatch.setattr(ia, "disponivel", lambda: True)
    monkeypatch.setattr(ia, "resumo_adaptado", lambda *a, **k: pytest.fail("não devia reescrever o resumo"))
    monkeypatch.setattr(ia, "carta_adaptada", lambda *a, **k: "Carta escrita pela IA para a ACME.")
    monkeypatch.setattr(config, "IA_NO_RESUMO", False)
    c = candidato_de_dict(PERFIL)
    p = montar_pacote(c, {"titulo": "Dev Python", "empresa": "ACME", "descricao": "Python"}, analisar(c, "Dev Python", "Python"))
    assert p.curriculo.resumo.startswith("Desenvolvedora backend.") and p.carta.startswith("Carta escrita pela IA")


# ---------------------------------------------------------------- vaga encerrada

@pytest.mark.parametrize("link, resposta, encerrada", [
    ("https://job-boards.greenhouse.io/acme/jobs/123", _R(404), True),
    ("https://job-boards.greenhouse.io/acme/jobs/123", _R(200, {}), False),
    ("https://jobs.lever.co/acme/0123456789abcdef01234567", _R(404), True),
    ("https://www.linkedin.com/jobs/view/dev-python-4412345678", _R(200, texto="No longer accepting applications"), True),
    ("https://www.linkedin.com/jobs/view/4412345678", _R(429), False),  # na dúvida, aberta
    # Gupy: "Inscrições encerradas" aparece em toda página (tradução da interface) — vale o status da vaga.
    ("https://acme.gupy.io/jobs/1", _R(200, texto='"closedApplications":"Inscrições encerradas"<script id="__NEXT_DATA__" '
                                     'type="application/json">{"props":{"pageProps":{"job":{"status":"published"}}}}</script>'), False),
    ("https://acme.gupy.io/jobs/1", _R(200, texto='<script id="__NEXT_DATA__" type="application/json">'
                                     '{"props":{"pageProps":{"job":{"status":"closed"}}}}</script>'), True),
    ("https://acme.gupy.io/jobs/1", _R(200, texto="login", url="https://acme.gupy.io/candidates/signin"), True),
    ("https://www.empresa.com.br/vaga", _R(404), False),  # fonte sem verificação confiável
])
def test_vaga_encerrada(link, resposta, encerrada):
    class Sessao:
        def get(self, url, headers=None, timeout=None):
            return resposta

    assert vaga_encerrada({"link": link}, Sessao()) is encerrada


# ---------------------------------------------------------------- Telegram

def test_avisa_vaga_boa_da_cidade_uma_vez_so(banco):
    repositorio.inserir({"id": "a", "titulo": "Dev Python", "local": "Uberlândia - MG", "site": "Gupy", "score": 90,
                         "link": "https://x/a", "email_destino": "rh@x.com.br"})
    repositorio.inserir({"id": "b", "titulo": "Dev Python", "local": "Uberlândia - MG", "site": "Gupy", "score": 50})
    repositorio.inserir({"id": "c", "titulo": "Dev Python", "local": "São Paulo - SP", "site": "Gupy", "score": 95})
    prefs = {"foco_regional": {"ativo": True, "cidade": "Uberlândia", "uf": "MG", "alerta_telegram": True,
                               "alerta_limiar": 75}}
    enviadas = []
    assert alertas.avisar_vagas_boas(prefs, enviar=lambda t: enviadas.append(t) or True) == 1
    assert "Uberlândia" in enviadas[0] and "90%" in enviadas[0] and "rh@x.com.br" in enviadas[0]
    assert alertas.avisar_vagas_boas(prefs, enviar=lambda t: enviadas.append(t) or True) == 0  # já avisada
    desligado = {"foco_regional": {**prefs["foco_regional"], "alerta_telegram": False}}
    assert alertas.configuracao(desligado) is None


# ---------------------------------------------------------------- funil e etapa

def test_funil_por_fonte(banco):
    repositorio.inserir({"id": "1", "titulo": "A", "site": "LinkedIn", "origem": "busca", "status": "enviada",
                         "simulado": 0, "etapa": "entrevista"})
    repositorio.inserir({"id": "2", "titulo": "B", "site": "LinkedIn", "origem": "busca", "status": "respondida"})
    repositorio.inserir({"id": "3", "titulo": "C", "site": "Gupy (site da empresa)", "origem": "empresa", "status": "enviada",
                         "simulado": 1})
    repositorio.inserir({"id": "4", "titulo": "D", "origem": "post", "status": "pronta"})
    linhas = {f["fonte"]: f for f in funil.calcular()}
    assert linhas["LinkedIn"] == {"fonte": "LinkedIn", "curtidas": 2, "enviadas": 2, "respostas": 1, "entrevistas": 1,
                                  "taxa_resposta": 50, "taxa_entrevista": 50}
    assert linhas["Sites das empresas"]["enviadas"] == 0  # simulada não conta
    assert linhas["Posts de recrutadores"]["curtidas"] == 1


@pytest.fixture
def cliente(banco, tmp_path, monkeypatch):
    import yaml

    from tests.test_candidatura import PERFIL

    perfil = tmp_path / "c.yaml"
    perfil.write_text(yaml.safe_dump(PERFIL, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config, "PERFIL_PATH", perfil)
    from web.app import criar_app

    return criar_app().test_client()


def test_telas_funil_etapa_e_ler_post(cliente):
    repositorio.inserir({"id": "e1", "titulo": "Dev", "site": "LinkedIn", "status": "enviada"})
    assert cliente.post("/api/etapa/e1", json={"etapa": "entrevista"}, headers=LOCAL).status_code == 200
    assert repositorio.obter("e1")["etapa"] == "entrevista"
    assert cliente.post("/api/etapa/e1", json={"etapa": "xyz"}, headers=LOCAL).status_code == 400
    assert "LinkedIn" in cliente.get("/funil").get_data(as_text=True)
    assert "Etapa do processo" in cliente.get("/vaga/e1").get_data(as_text=True)
    r = cliente.post("/api/ler-post", json={"texto": "Vaga Desenvolvedor Python. Envie para vagas@acme.com.br"}, headers=LOCAL)
    assert r.get_json()["email"] == "vagas@acme.com.br"


def test_colar_post_com_enviar_usa_preparar_e_enviar(cliente, monkeypatch):
    from candidatura import servico

    chamadas = []
    monkeypatch.setattr(servico, "preparar_e_enviar", lambda i: chamadas.append(("enviar", i)))
    monkeypatch.setattr(servico, "preparar", lambda i: chamadas.append(("preparar", i)))
    cliente.post("/nova", data={"titulo": "Dev", "email": "vagas@acme.com.br", "enviar": "on", "link": "https://x/1"},
                 headers=LOCAL)
    cliente.post("/nova", data={"titulo": "Dev 2", "email": "vagas@beta.com.br", "link": "https://x/2"}, headers=LOCAL)
    import time

    for _ in range(50):
        if len(chamadas) == 2:
            break
        time.sleep(0.05)
    assert [c[0] for c in chamadas] == ["enviar", "preparar"]


def test_chaves_ficam_no_env_isolado(cliente):
    cliente.post("/configuracoes", headers=LOCAL, data={"termos_busca": "python", "ia_api_key": "gsk_teste",
                                                         "hunter_api_key": "h1", "ia_no_resumo": "on"})
    texto = config.ENV_PATH.read_text(encoding="utf-8")
    assert "IA_API_KEY=gsk_teste" in texto and "IA_PROVEDOR=groq" in texto and "HUNTER_API_KEY=h1" in texto
    assert config.IA_NO_RESUMO is True and config.HUNTER_API_KEY == "h1"
    cliente.post("/configuracoes", headers=LOCAL, data={"termos_busca": "python", "hunter_api_key": "-"})
    assert config.HUNTER_API_KEY == "" and config.IA_API_KEY == "gsk_teste" and config.IA_NO_RESUMO is False
    config.gravar_chaves({"IA_API_KEY": "", "IA_PROVEDOR": "", "IA_NO_RESUMO": "false"})


# ---------------------------------------------------------------- rotina

def test_rotina_diaria_busca_le_respostas_e_faz_followup(monkeypatch):
    monkeypatch.setattr(config, "SMTP_SENHA", "x")
    monkeypatch.setattr(config, "ENVIO_REAL", True)
    texto = rotina.conteudo("carla", auto=False)
    assert "--perfil carla importar" in texto and "respostas" in texto and "followup" in texto and " auto " not in texto
    assert " auto --limite 7" in rotina.conteudo("carla", auto=True, limite_auto=7)
    monkeypatch.setattr(config, "ENVIO_REAL", False)
    assert "followup" not in rotina.conteudo("carla")  # em simulação não manda follow-up de verdade
    assert rotina.nome_tarefa("principal") == "JobRadarCandidaturas" and rotina.nome_tarefa("carla") == "JobRadar-carla"
    with pytest.raises(ValueError):
        rotina.ativar("25:99")


def test_ia_troca_sozinha_de_modelo_quando_o_groq_tira_o_antigo(monkeypatch):
    monkeypatch.setattr(config, "IA_PROVEDOR", "groq")
    monkeypatch.setattr(config, "IA_API_KEY", "gsk_teste")
    monkeypatch.setattr(config, "IA_MODELO", "")
    monkeypatch.setattr(ia, "_modelo_descoberto", {})
    usados = []

    def post(url, headers=None, data=None, timeout=None):
        import json

        modelo = json.loads(data)["model"]
        usados.append(modelo)
        if modelo == "llama-3.3-70b-versatile":
            return _R(404, {"error": {"message": "The model `llama-3.3-70b-versatile` does not exist"}})
        return _R(200, {"choices": [{"message": {"content": "ok"}}]})

    def get(url, headers=None, timeout=None):
        return _R(200, {"data": [{"id": "whisper-large-v3"}, {"id": "openai/gpt-oss-120b"}]})

    monkeypatch.setattr(ia.requests, "post", post)
    monkeypatch.setattr(ia.requests, "get", get)
    assert ia.completar("s", "u") == "ok"
    assert usados == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
    assert ia.completar("s", "u") == "ok" and usados[-1] == "openai/gpt-oss-120b"  # lembra o modelo novo


def test_ia_chave_invalida_explica_o_erro(monkeypatch):
    monkeypatch.setattr(config, "IA_PROVEDOR", "groq")
    monkeypatch.setattr(config, "IA_API_KEY", "gsk_ruim")
    monkeypatch.setattr(ia.requests, "post", lambda *a, **k: _R(401, {"error": {"message": "Invalid API Key"}}))
    assert ia.completar("s", "u") is None and "401" in ia.ultimo_erro and "Invalid API Key" in ia.ultimo_erro


def test_ia_modelo_que_raciocina_ganha_folga_e_resposta_vazia_vira_erro_claro(monkeypatch):
    import json

    monkeypatch.setattr(config, "IA_PROVEDOR", "groq")
    monkeypatch.setattr(config, "IA_API_KEY", "gsk_teste")
    monkeypatch.setattr(config, "IA_MODELO", "openai/gpt-oss-120b")
    corpos = []

    def post(url, headers=None, data=None, timeout=None):
        corpos.append(json.loads(data))
        conteudo = "" if len(corpos) == 1 else "<think>pensando</think>ok"
        return _R(200, {"choices": [{"message": {"content": conteudo}, "finish_reason": "length"}]})

    monkeypatch.setattr(ia.requests, "post", post)
    assert ia.completar("s", "u", max_tokens=60) is None and "vazia" in ia.ultimo_erro
    assert corpos[0]["reasoning_effort"] == "low" and corpos[0]["max_tokens"] > 1000
    assert ia.completar("s", "u", max_tokens=60) == "ok"  # o raciocínio <think> não vai para a carta
    assert not ia.raciocina("meta-llama/llama-4-maverick-17b-128e-instruct")
    assert ia.escolher_modelo(["openai/gpt-oss-120b", "meta-llama/llama-4-scout-17b-16e-instruct"]) == \
        "meta-llama/llama-4-scout-17b-16e-instruct"  # direto antes do que raciocina
