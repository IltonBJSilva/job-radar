"""Filtros do swipe (país, idioma, modalidade, região, localização) e o check
de candidatura feita pelo site. Sem rede, sem navegador."""

import pytest

from candidatura import config, repositorio
from candidatura.localizacao import Filtros, classificar


def _c(local="", site="LinkedIn", titulo="Desenvolvedor Python", modalidade="", descricao=""):
    return classificar({"local": local, "site": site, "titulo": titulo, "modalidade": modalidade,
                        "descricao": descricao})


@pytest.mark.parametrize("local, site, pais, nome, uf, regiao", [
    ("São Paulo, São Paulo, Brazil", "LinkedIn", "brasil", "Brasil", "SP", "Sudeste"),
    ("Recife - PE", "Catho", "brasil", "Brasil", "PE", "Nordeste"),
    ("Greater São Paulo Area", "LinkedIn", "brasil", "Brasil", "SP", "Sudeste"),
    ("Uberlândia, MG", "Gupy", "brasil", "Brasil", "MG", "Sudeste"),
    ("Remoto (Maceió, AL)", "LinkedIn", "brasil", "Brasil", "AL", "Nordeste"),
    ("Brasília, Federal District, Brazil", "LinkedIn", "brasil", "Brasil", "DF", "Centro-Oeste"),
    ("Remoto", "LinkedIn", "brasil", "Brasil", "", ""),
    ("", "Gupy", "brasil", "Brasil", "", ""),
    ("Madrid, Community of Madrid, Spain", "LinkedIn", "exterior", "Espanha", "", ""),
    ("Lisboa, Lisbon, Portugal", "LinkedIn", "exterior", "Portugal", "", ""),
    ("Bogota, D.C., Capital District, Colombia", "LinkedIn", "exterior", "Colômbia", "", ""),
    ("Remoto (New York, NY)", "LinkedIn", "exterior", "Estados Unidos", "", ""),
    ("Huntsville, AL", "LinkedIn", "indefinido", "", "", ""),  # AL sozinho pode ser Alabama ou Alagoas
    ("Greater Bilbao Metropolitan Area", "LinkedIn", "exterior", "Espanha", "", ""),
    ("", "We Work Remotely", "exterior", "", "", ""),
])
def test_pais_uf_e_regiao(local, site, pais, nome, uf, regiao):
    c = _c(local, site)
    assert (c.pais, c.pais_nome, c.uf, c.regiao) == (pais, nome, uf, regiao)


def test_idioma():
    desc_en = "We are looking for a developer to join our team. You will work with the product and our clients. " * 3
    desc_pt = "Estamos buscando uma pessoa desenvolvedora para o nosso time. Você vai trabalhar com o produto e com os clientes. " * 3
    assert _c("Madrid, Spain", titulo="Desarrollador Backend").idioma == "es"
    assert _c("Madrid, Spain", titulo="Backend Developer").idioma == "en"
    assert _c("Lisboa, Portugal", titulo="Senior Business Data Analyst").idioma == "en"
    # Vaga brasileira só com título em inglês: o anúncio quase sempre é em português.
    assert _c("Goiânia - GO", titulo="Back-End Developer").idioma == "pt"
    assert _c("Brazil", titulo="Senior Full-Stack Engineer - Remote Work").idioma == "en"
    # Com descrição, a descrição decide.
    assert _c("São Paulo, Brazil", titulo="Backend Developer", descricao=desc_en).idioma == "en"
    assert _c("Madrid, Spain", titulo="Backend Developer", descricao=desc_pt).idioma == "pt"


@pytest.mark.parametrize("modalidade, local, titulo, esperado", [
    ("Remoto", "", "Dev", "remoto"),
    ("", "", "Desenvolvedor Python (Híbrido)", "hibrido"),
    ("Remoto", "", "Desenvolvedor - Presencial", "presencial"),  # título contradiz a fonte
    ("", "Remote", "Dev", "remoto"),
    ("", "Uberlândia, MG", "Dev", "indefinido"),
])
def test_modalidade(modalidade, local, titulo, esperado):
    assert _c(local, titulo=titulo, modalidade=modalidade).modalidade == esperado


def test_filtros_combinados():
    vaga_mg = {"local": "Uberlândia, MG", "site": "Gupy", "titulo": "Desenvolvedor Python", "modalidade": "Híbrido",
               "email_destino": "rh@acme.com.br"}
    vaga_es = {"local": "Madrid, Spain", "site": "LinkedIn", "titulo": "Desarrollador", "modalidade": "Remoto"}
    c_mg, c_es = classificar(vaga_mg), classificar(vaga_es)
    f = Filtros.de_args({"pais": "brasil", "idioma": "pt", "modalidade": "hibrido,presencial", "regiao": "Sudeste"})
    assert f.aceita(vaga_mg, c_mg) and not f.aceita(vaga_es, c_es)
    assert Filtros.de_args({"local": "mg"}).aceita(vaga_mg, c_mg)            # UF
    assert Filtros.de_args({"local": "Minas Gerais"}).aceita(vaga_mg, c_mg)  # estado por extenso
    assert Filtros.de_args({"local": "uberlandia"}).aceita(vaga_mg, c_mg)    # cidade sem acento
    assert not Filtros.de_args({"local": "sp"}).aceita(vaga_mg, c_mg)
    assert Filtros.de_args({"local": "Espanha"}).aceita(vaga_es, c_es)       # país
    assert not Filtros.de_args({"email": "1"}).aceita(vaga_es, c_es)
    # Valor inválido vindo da URL é ignorado, não quebra.
    assert Filtros.de_args({"pais": "marte", "modalidade": "x,remoto"}) == Filtros(modalidades=frozenset({"remoto"}))


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    import yaml

    from tests.test_candidatura import PERFIL

    monkeypatch.setattr(config, "CANDIDATURAS_DB_PATH", tmp_path / "cand.db")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "saida")
    perfil = tmp_path / "c.yaml"
    perfil.write_text(yaml.safe_dump(PERFIL, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(config, "PERFIL_PATH", perfil)
    repositorio.iniciar()
    from web.app import criar_app

    return criar_app().test_client()


def test_api_proximas_e_contagem_respeitam_filtros(cliente):
    repositorio.inserir({"id": "br", "titulo": "Desenvolvedor Python", "local": "Recife - PE", "site": "Catho",
                         "modalidade": "Remoto", "score": 80})
    repositorio.inserir({"id": "es", "titulo": "Desarrollador Python", "local": "Madrid, Spain",
                         "site": "LinkedIn", "modalidade": "Remoto", "score": 90})
    todas = cliente.get("/api/proximas?n=10").get_json()
    assert [v["id"] for v in todas] == ["es", "br"]
    so_br = cliente.get("/api/proximas?n=10&pais=brasil&regiao=Nordeste").get_json()
    assert [v["id"] for v in so_br] == ["br"] and so_br[0]["classificacao"]["uf"] == "PE"
    info = cliente.get("/api/filtros?idioma=es").get_json()
    assert info["total"] == 1 and info["novas"] == 2 and info["contagem"]["pais"] == {"brasil": 1, "exterior": 1}


def test_check_de_candidatura_pelo_site(cliente):
    local = {"Origin": "http://localhost"}
    repositorio.inserir({"id": "m1", "titulo": "Dev", "empresa": "ACME", "status": "manual", "cv_path": "x.pdf"})
    r = cliente.post("/api/aplicada/m1", json={"feito": True}, headers=local)
    assert r.status_code == 200 and r.get_json()["contagem"]["aplicada"] == 1
    v = repositorio.obter("m1")
    assert v["status"] == "aplicada" and v["aplicada_em"] and not v.get("enviada_em")
    # Não conta como e-mail: limite diário e bloqueio de empresa ficam intactos.
    assert repositorio.enviadas_hoje() == 0
    assert not repositorio.ja_contatado("", "ACME", 30)
    assert "m1" in cliente.get("/fila?aba=enviada").get_data(as_text=True)
    # Desmarcar volta para "Sem e-mail".
    assert cliente.post("/api/aplicada/m1", json={"feito": False}, headers=local).status_code == 200
    assert repositorio.obter("m1")["status"] == "manual"
    # Vaga já enviada por e-mail não pode ser marcada.
    repositorio.inserir({"id": "e1", "titulo": "Dev", "status": "enviada"})
    assert cliente.post("/api/aplicada/e1", json={"feito": True}, headers=local).status_code == 400


def test_vaga_aplicada_nao_e_preparada_de_novo(cliente):
    from candidatura import servico

    repositorio.inserir({"id": "a1", "titulo": "Dev", "status": "aplicada"})
    with pytest.raises(ValueError):
        servico.preparar("a1")


# ------------------------------------------- localidades (IBGE + países)

@pytest.mark.parametrize("digitado, rotulo", [
    ("udia", "Uberlândia - MG"), ("Uberlandia", "Uberlândia - MG"), ("UBERLÂNDIA", "Uberlândia - MG"),
    ("uberlandai", "Uberlândia - MG"),            # erro de digitação
    ("Uberlândia - MG", "Uberlândia - MG"),       # rótulo que o próprio sistema sugere
    ("BH", "Belo Horizonte - MG"), ("floripa", "Florianópolis - SC"),
    ("mg", "Minas Gerais (MG)"), ("minas gerais", "Minas Gerais (MG)"), ("Minas Gerais (MG)", "Minas Gerais (MG)"),
    ("campo grande", "Campo Grande - MS"),        # repetido em 3 estados: fica a capital
    ("Campo Grande - RN", "Campo Grande - RN"),
    ("Spain", "Espanha"), ("espanha", "Espanha"), ("EUA", "Estados Unidos"),
])
def test_resolver_entende_variacoes(digitado, rotulo):
    from candidatura import localidades

    assert localidades.resolver(digitado).rotulo == rotulo


def test_resolver_nao_inventa_lugar():
    from candidatura import localidades

    assert localidades.resolver("xyzabc") is None and localidades.resolver("a") is None


@pytest.mark.parametrize("local, esperado", [
    ("Udia - MG", {"cidade": "Uberlândia", "uf": "MG", "pais": "Brasil"}),
    ("Ituiutaba - MG", {"cidade": "Ituiutaba", "uf": "MG", "pais": "Brasil"}),  # não é capital: vem do IBGE
    ("Grande São Paulo", {"cidade": "São Paulo", "uf": "SP", "pais": "Brasil"}),
    ("Greater Campinas", {"cidade": "Campinas", "uf": "SP", "pais": "Brasil"}),
    ("Campo Grande, Mato Grosso do Sul, Brazil", {"cidade": "Campo Grande", "uf": "MS", "pais": "Brasil"}),
    ("Huntsville, AL", {"cidade": "", "uf": "", "pais": ""}),                   # Alabama, não Alagoas
    ("Santiago, Santiago Metropolitan Region, Chile", {"cidade": "", "uf": "", "pais": "Chile"}),
    ("Sweden", {"cidade": "", "uf": "", "pais": "Suécia"}),
])
def test_extrair_local_da_vaga(local, esperado):
    from candidatura import localidades

    assert localidades.extrair(local) == esperado


def test_filtro_por_apelido_acha_vaga_escrita_de_outro_jeito():
    vaga = {"local": "Uberlandia - Minas Gerais", "site": "Gupy", "titulo": "Desenvolvedor"}
    c = classificar(vaga)
    assert c.cidade == "Uberlândia" and c.uf == "MG"
    for digitado in ("udia", "UBERLÂNDIA", "Uberlândia - MG", "mg"):
        assert Filtros.de_args({"local": digitado}).aceita(vaga, c), digitado
    assert not Filtros.de_args({"local": "Campinas"}).aceita(vaga, c)


def test_api_localidades(cliente):
    sugestoes = cliente.get("/api/localidades?q=udia").get_json()
    assert sugestoes[0]["rotulo"] == "Uberlândia - MG" and sugestoes[0]["tipo"] == "cidade"
    assert cliente.get("/api/filtros?local=udia").get_json()["lugar"]["rotulo"] == "Uberlândia - MG"
