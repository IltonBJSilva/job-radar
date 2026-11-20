"""Compatibilidade vaga x candidato, no estilo de um ATS — sem IA.

ATS (Gupy, Sólides, Greenhouse...) ranqueia currículo por presença das
palavras-chave da vaga. Aqui fazemos o mesmo ao contrário: extraímos as
tecnologias citadas na vaga, cruzamos com o perfil e devolvemos
- score 0-100,
- o que você tem e a vaga pede (vai para o topo do currículo),
- o que a vaga pede e você NÃO declarou (só informativo — nunca entra no CV).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from candidatura.perfil import Candidato


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


# Nome canônico -> variações como aparecem em anúncio. A comparação é feita
# com borda de palavra, então "Go" não casa com "Google" nem "MongoDB".
VOCABULARIO: dict[str, list[str]] = {
    "Python": ["python", "python3"],
    "JavaScript": ["javascript", "js", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "Node.js": ["node.js", "nodejs", "node js", "node"],
    "Java": ["java"],
    "Kotlin": ["kotlin"],
    "C#": ["c#", "csharp"],
    ".NET": [".net", "dotnet", "asp.net"],
    "Go": ["golang", "go lang"],
    "PHP": ["php"],
    "Laravel": ["laravel"],
    "Ruby": ["ruby"],
    "Rails": ["rails", "ruby on rails"],
    "Rust": ["rust"],
    "Elixir": ["elixir"],
    "Scala": ["scala"],
    "SQL": ["sql"],
    "Django": ["django", "django rest framework", "drf"],
    "FastAPI": ["fastapi", "fast api"],
    "Flask": ["flask"],
    "Express": ["express", "express.js", "expressjs"],
    "NestJS": ["nestjs", "nest.js", "nest"],
    "Spring": ["spring", "spring boot", "springboot"],
    "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs"],
    "Vue": ["vue", "vue.js", "vuejs"],
    "Angular": ["angular"],
    "REST": ["restful", "api rest", "apis rest", "rest api", "rest apis", "api restful", "apis restful"],
    "GraphQL": ["graphql"],
    "gRPC": ["grpc"],
    "Microsserviços": ["microsservicos", "microservicos", "microservices", "microsservico", "microservice"],
    "Mensageria": ["mensageria", "message broker"],
    "Kafka": ["kafka"],
    "RabbitMQ": ["rabbitmq", "rabbit mq"],
    "Celery": ["celery"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MySQL": ["mysql", "mariadb"],
    "SQL Server": ["sql server", "sqlserver", "mssql"],
    "Oracle": ["oracle", "pl/sql", "plsql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "DynamoDB": ["dynamodb"],
    "SQLite": ["sqlite"],
    "ORM": ["orm", "sqlalchemy", "prisma", "typeorm", "sequelize"],
    "Docker": ["docker", "containers", "conteineres", "container"],
    "Kubernetes": ["kubernetes", "k8s", "eks", "gke", "aks"],
    "Terraform": ["terraform", "iac", "infraestrutura como codigo"],
    "AWS": ["aws", "amazon web services", "lambda", "ec2", "s3"],
    "GCP": ["gcp", "google cloud", "cloud run", "bigquery"],
    "Azure": ["azure"],
    "Linux": ["linux", "bash", "shell script"],
    "Git": ["git", "github", "gitlab", "bitbucket"],
    "CI/CD": ["ci/cd", "ci cd", "pipelines", "github actions", "gitlab ci", "jenkins"],
    "Testes automatizados": ["testes automatizados", "testes unitarios", "unit tests", "testes de integracao",
                             "pytest", "jest", "junit", "tdd"],
    "Clean Architecture": ["clean architecture", "arquitetura limpa", "clean code", "solid", "ddd", "design patterns"],
    "Observabilidade": ["observabilidade", "observability", "prometheus", "grafana", "datadog", "new relic", "opentelemetry"],
    "Segurança": ["oauth", "jwt", "owasp", "seguranca da informacao"],
    "Scraping": ["scraping", "web scraping", "playwright", "selenium", "beautifulsoup"],
    "Pandas": ["pandas", "numpy"],
    "Airflow": ["airflow"],
    "Spark": ["spark", "pyspark", "databricks"],
    "Machine Learning": ["machine learning", "aprendizado de maquina", "scikit-learn", "sklearn"],
    "IA Generativa": ["llm", "llms", "ia generativa", "genai", "openai", "langchain", "rag"],
    "Scrum": ["scrum", "kanban", "agil", "agile", "metodologias ageis"],
    "Inglês": ["ingles", "english"],
    "Espanhol": ["espanhol", "spanish"],
}

# Canônicos que, sozinhos, são palavra comum ("go-live", "rest of the team"):
# só contam pelas variações explícitas.
_CANONICO_AMBIGUO = {"Go", "REST"}

_PADROES = {
    canonico: [
        re.compile(r"(?<![\w.#+-])" + re.escape(normalizar(v)) + r"(?![\w#+]|\.\w)")
        for v in variacoes + ([] if canonico in _CANONICO_AMBIGUO else [canonico])
    ]
    for canonico, variacoes in VOCABULARIO.items()
}


def extrair_tecnologias(texto: str) -> list[str]:
    """Tecnologias do VOCABULARIO citadas no texto, na ordem de primeira aparição."""
    alvo = normalizar(texto)
    achadas = []
    for canonico, padroes in _PADROES.items():
        posicoes = [m.start() for p in padroes for m in [p.search(alvo)] if m]
        if posicoes:
            achadas.append((min(posicoes), canonico))
    return [c for _, c in sorted(achadas)]


def canonizar(termo: str) -> str:
    """Mapeia um item do perfil ("node", "Postgres") para o nome canônico."""
    achados = extrair_tecnologias(termo)
    return achados[0] if achados else termo.strip()


def termos_declarados(habilidades: list[str]) -> dict[str, str]:
    """Nome canônico -> termo EXATAMENTE como você escreveu no perfil.

    O texto do currículo/carta usa sempre o termo declarado: se o perfil diz
    "MariaDB", a vaga que pede MySQL casa, mas o CV continua dizendo MariaDB.
    """
    mapa: dict[str, str] = {}
    for h in habilidades:
        for canonico in extrair_tecnologias(h) or [h.strip()]:
            mapa.setdefault(canonico, h.strip())
    return mapa


def contar_ocorrencias(texto: str, tecnologias: list[str]) -> int:
    alvo = normalizar(texto)
    return sum(1 for t in tecnologias for p in _PADROES.get(t, []) if p.search(alvo))


SENIORIDADES = [
    ("Estágio", ["estagio", "estagiario", "intern", "internship"]),
    ("Júnior", ["junior", "jr", "jr."]),
    ("Pleno", ["pleno", "pl", "mid-level", "mid level"]),
    ("Sênior", ["senior", "sr", "sr."]),
    ("Especialista", ["especialista", "staff", "principal", "lead", "tech lead", "lider"]),
]


def detectar_senioridade(titulo: str) -> str:
    alvo = normalizar(titulo).replace("pl/sql", " ").replace("pl sql", " ")
    for nome, termos in SENIORIDADES:
        if any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", alvo) for t in termos):
            return nome
    return ""


# Competências que quase toda vaga cita: contam, mas pouco.
GENERICAS = {"Inglês", "Espanhol", "Git", "Scrum", "Linux", "SQL", "REST"}


@dataclass
class Analise:
    score: int
    em_comum: list[str] = field(default_factory=list)
    faltando: list[str] = field(default_factory=list)
    pedidas: list[str] = field(default_factory=list)
    senioridade: str = ""

    @property
    def resumo(self) -> str:
        if not self.pedidas:
            return "A vaga não cita tecnologias conhecidas — score baseado no título."
        return f"Você tem {len(self.em_comum)} de {len(self.pedidas)} tecnologias citadas."


# Quem declara X também atende Y (Kafka -> Mensageria). Só vale para o
# SCORE: o texto do CV/carta continua usando apenas o que você escreveu.
IMPLICA = {
    "Kafka": {"Mensageria"}, "RabbitMQ": {"Mensageria"}, "Celery": {"Mensageria"},
    "Django": {"Python"}, "FastAPI": {"Python"}, "Flask": {"Python"}, "Pandas": {"Python"},
    "Express": {"Node.js"}, "NestJS": {"Node.js", "TypeScript"},
    "React": {"JavaScript"}, "Next.js": {"React", "JavaScript"}, "Vue": {"JavaScript"},
    "Spring": {"Java"}, "Laravel": {"PHP"}, "Rails": {"Ruby"},
    "Kubernetes": {"Docker"}, "PostgreSQL": {"SQL"}, "MySQL": {"SQL"}, "SQL Server": {"SQL"},
}

NIVEIS = ["Estágio", "Júnior", "Pleno", "Sênior", "Especialista"]

_NIVEL_IDIOMA_OK = ("intermedi", "avancad", "fluente", "fluent", "nativ", "b2", "c1", "c2", "proficien")


def _idioma_suficiente(idiomas: str, nome: tuple[str, ...]) -> bool:
    for linha in idiomas.split("|"):
        if any(n in linha for n in nome) and any(n in linha for n in _NIVEL_IDIOMA_OK):
            return True
    return False


def idioma_da_vaga(texto: str) -> str:
    """'en' quando a descrição está claramente em inglês, senão 'pt'."""
    palavras = re.findall(r"[a-z]+", normalizar(texto))
    if len(palavras) < 40:
        return "pt"
    en = sum(1 for p in palavras if p in {"the", "and", "you", "with", "our", "will", "for", "are", "your", "we"})
    pt = sum(1 for p in palavras if p in {"de", "e", "com", "para", "voce", "nossa", "nosso", "em", "da", "do", "que"})
    return "en" if en > pt * 1.5 else "pt"


def nivel_do_candidato(candidato: Candidato) -> str:
    return (candidato.preferencias or {}).get("senioridade") or detectar_senioridade(candidato.titulo)


def analisar(candidato: Candidato, titulo: str, descricao: str) -> Analise:
    texto_vaga = f"{titulo}\n{descricao}"
    pedidas = extrair_tecnologias(texto_vaga)
    perfil = {canonizar(h) for h in candidato.todas_habilidades}
    perfil |= set(extrair_tecnologias(" ".join(candidato.todas_habilidades)))
    for t in list(perfil):
        perfil |= IMPLICA.get(t, set())

    # Idioma só conta a partir de intermediário ("Inglês — básico" não atende B2).
    idiomas = "|".join(normalizar(i) for i in candidato.idiomas)
    if _idioma_suficiente(idiomas, ("ingles", "english")):
        perfil.add("Inglês")
    if _idioma_suficiente(idiomas, ("espanhol", "spanish")):
        perfil.add("Espanhol")

    em_comum = [t for t in pedidas if t in perfil]
    faltando = [t for t in pedidas if t not in perfil]

    # 1) Cobertura técnica. Tecnologia no título = requisito central (peso 2);
    #    competência genérica (inglês, git, scrum) pesa pouco. O "+1" no
    #    denominador evita que 1 de 1 tecnologia vire 100%.
    no_titulo = set(extrair_tecnologias(titulo))

    def peso(t: str) -> float:
        return 0.5 if t in GENERICAS else (2.0 if t in no_titulo else 1.0)

    peso_total = sum(peso(t) for t in pedidas)
    peso_ok = sum(peso(t) for t in em_comum)
    cobertura = 100 * peso_ok / (peso_total + 1) if pedidas else 40

    # 2) Aderência do cargo: o título da vaga bate com os cargos que você busca?
    alvo = normalizar(titulo)
    cargos = [normalizar(c) for c in candidato.preferencias.get("cargos_alvo", [])] or [w for w in re.findall(r"\w{4,}", normalizar(candidato.titulo.split("|")[0]))]
    if any(re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", alvo) for c in cargos if c):
        cargo = 100
    elif no_titulo & perfil:
        cargo = 60
    else:
        cargo = 15
    # "Desenvolvedor Backend (Java)" para quem não tem Java: o cargo bate,
    # mas a tecnologia central do título não.
    if no_titulo - perfil - GENERICAS:
        cargo = min(cargo, 30)

    score = 0.55 * cobertura + 0.45 * cargo

    # Pouca informação (vaga sem descrição) não pode virar score alto.
    if len(pedidas) < 3:
        score = min(score, 55)

    # Senioridade: júnior em vaga sênior (ou o contrário) perde pontos.
    senioridade = detectar_senioridade(titulo)
    meu = nivel_do_candidato(candidato)
    if senioridade in NIVEIS and meu in NIVEIS:
        distancia = abs(NIVEIS.index(senioridade) - NIVEIS.index(meu))
        score -= {0: 0, 1: 8}.get(distancia, 22)

    return Analise(
        score=max(0, min(100, round(score))),
        em_comum=em_comum,
        faltando=faltando,
        pedidas=pedidas,
        senioridade=senioridade,
    )
