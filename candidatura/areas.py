"""Áreas prontas para quem vai usar o sistema pela primeira vez.

Escolher a área preenche, no perfil, os cargos que contam como "cargo certo"
na compatibilidade, os termos usados para buscar vagas e as fontes. Tudo
continua editável na página de Configurações.

Fontes:
  radar   vagas do robô no GitHub Actions (termos de DESENVOLVIMENTO, fixos)
  github  repositórios de vagas da comunidade dev (backend-br, frontendbr...)
  gupy    API da Gupy, pelos seus termos
  remotar vagas remotas do Remotar, pelos seus termos
  linkedin, catho, indeed   busca local, na sua máquina, pelos seus termos
"""

from __future__ import annotations

FONTES = {
    "linkedin": "LinkedIn (busca pelos seus termos)",
    "gupy": "Gupy",
    "catho": "Catho",
    "indeed": "Indeed",
    "remotar": "Remotar (só remotas)",
    "empresas": "Sites das empresas (Gupy, Greenhouse, Lever)",
    "posts": "Posts públicos de recrutadores (precisa da chave grátis da Tavily)",
    "radar": "Radar automático (vagas de desenvolvimento)",
    "github": "Repositórios de vagas dev no GitHub",
}
FONTES_PADRAO_LEGADO = ["radar", "github", "gupy", "remotar"]  # perfis antigos, sem a chave "fontes"
_FONTES_GERAIS = ["linkedin", "gupy", "catho", "indeed", "remotar", "empresas", "posts"]

AREAS: dict[str, dict] = {
    "desenvolvimento": {
        "nome": "Desenvolvimento de software",
        "cargos_alvo": ["desenvolvedor", "developer", "engenheiro de software", "software engineer", "backend",
                        "back-end", "frontend", "front-end", "full stack", "programador"],
        "termos_busca": ["desenvolvedor", "backend", "frontend", "full stack"],
        "fontes": ["radar", "github", *_FONTES_GERAIS],
        "termos_extras": [],
    },
    "ciberseguranca": {
        "nome": "Cibersegurança / Segurança da Informação",
        "cargos_alvo": ["seguranca da informacao", "ciberseguranca", "cybersecurity", "security", "seguranca",
                        "soc", "pentest", "pentester", "red team", "blue team", "grc", "infosec", "appsec",
                        "devsecops", "analista de seguranca", "security analyst", "security engineer"],
        "termos_busca": ["segurança da informação", "cibersegurança", "analista SOC", "pentest"],
        "fontes": _FONTES_GERAIS,
        "termos_extras": [],
    },
    "dados": {
        "nome": "Dados / BI / Ciência de dados",
        "cargos_alvo": ["dados", "data", "bi", "business intelligence", "analytics", "cientista de dados",
                        "data scientist", "engenheiro de dados", "data engineer", "analista de dados", "data analyst"],
        "termos_busca": ["analista de dados", "engenheiro de dados", "cientista de dados", "BI"],
        "fontes": ["github", *_FONTES_GERAIS],
        "termos_extras": [],
    },
    "infraestrutura": {
        "nome": "Infraestrutura / Cloud / DevOps / Redes",
        "cargos_alvo": ["infraestrutura", "infra", "devops", "sre", "cloud", "redes", "network", "sysadmin",
                        "administrador de sistemas", "analista de infraestrutura", "platform engineer"],
        "termos_busca": ["analista de infraestrutura", "devops", "cloud", "analista de redes"],
        "fontes": _FONTES_GERAIS,
        "termos_extras": [],
    },
    "suporte": {
        "nome": "Suporte / Help desk / Service desk",
        "cargos_alvo": ["suporte", "help desk", "helpdesk", "service desk", "tecnico de informatica",
                        "analista de suporte", "atendimento", "ti"],
        "termos_busca": ["analista de suporte", "help desk", "técnico de suporte", "service desk"],
        "fontes": _FONTES_GERAIS,
        "termos_extras": [],
    },
    "qa": {
        "nome": "QA / Testes de software",
        "cargos_alvo": ["qa", "quality assurance", "teste", "testes", "tester", "analista de testes",
                        "automacao de testes", "sdet"],
        "termos_busca": ["analista de testes", "QA", "automação de testes"],
        "fontes": ["github", *_FONTES_GERAIS],
        "termos_extras": [],
    },
    "produto": {
        "nome": "Produto / Agilidade / Projetos",
        "cargos_alvo": ["produto", "product", "product owner", "product manager", "po", "pm", "scrum master",
                        "agile", "agilista", "projetos", "gerente de projetos", "analista de negocios"],
        "termos_busca": ["product owner", "product manager", "scrum master", "analista de negócios"],
        "fontes": _FONTES_GERAIS,
        "termos_extras": [],
    },
    "design": {
        "nome": "Design / UX / UI",
        "cargos_alvo": ["designer", "ux", "ui", "product designer", "ux designer", "ui designer", "design"],
        "termos_busca": ["UX designer", "UI designer", "product designer"],
        "fontes": _FONTES_GERAIS,
        "termos_extras": ["Adobe XD", "Design System", "Prototipação", "Pesquisa com usuários"],
    },
    "outra": {
        "nome": "Outra área (eu configuro)",
        "cargos_alvo": [],
        "termos_busca": [],
        "fontes": ["linkedin", "gupy", "catho", "indeed"],
        "termos_extras": [],
    },
}


def preferencias_da_area(area: str) -> dict:
    """Valores iniciais de `preferencias` para a área escolhida."""
    a = AREAS.get(area) or AREAS["outra"]
    return {"area": area if area in AREAS else "outra", "cargos_alvo": list(a["cargos_alvo"]),
            "termos_busca": list(a["termos_busca"]), "fontes": list(a["fontes"]),
            "termos_extras": list(a["termos_extras"])}


def termos_busca(preferencias: dict) -> list[str]:
    """Termos de busca do perfil (aceita o nome antigo `termos_remotar`)."""
    p = preferencias or {}
    termos = p.get("termos_busca") or p.get("termos_remotar") or []
    return [str(t).strip() for t in termos if str(t).strip()]


def foco_regional(preferencias: dict) -> dict | None:
    """{"cidade": "Uberlândia", "uf": "MG"} quando o foco está LIGADO; None quando desligado."""
    foco = (preferencias or {}).get("foco_regional") or {}
    if not foco.get("ativo") or not str(foco.get("cidade") or "").strip():
        return None
    return {"cidade": str(foco["cidade"]).strip(), "uf": str(foco.get("uf") or "").strip().upper()}


def fontes(preferencias: dict) -> list[str]:
    escolhidas = (preferencias or {}).get("fontes")
    if not escolhidas:
        return list(FONTES_PADRAO_LEGADO)
    return [f for f in escolhidas if f in FONTES]
