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
    "IA Generativa": ["llm", "llms", "ia generativa", "genai", "generative ai", "openai", "langchain", "rag"],
    "Agentes de IA": ["agentes de ia", "agente de ia", "ai agents", "ai agent", "agentic", "agentic ai",
                      "multiagente", "multiagentes", "multi-agent", "langgraph", "crewai", "agents sdk"],
    "Scrum": ["scrum", "kanban", "agil", "agile", "metodologias ageis"],
    "Inglês": ["ingles", "english"],
    "Espanhol": ["espanhol", "spanish"],
    # --- Cibersegurança ---------------------------------------------------
    "SIEM": ["siem"],
    "SOC": ["soc", "security operations center", "centro de operacoes de seguranca"],
    "Splunk": ["splunk"],
    "QRadar": ["qradar"],
    "Microsoft Sentinel": ["microsoft sentinel", "azure sentinel"],
    "Wazuh": ["wazuh"],
    "ELK": ["elk", "kibana", "logstash"],
    "Pentest": ["pentest", "pen test", "penetration testing", "teste de invasao", "testes de invasao",
                "teste de intrusao", "testes de intrusao", "red team"],
    "Burp Suite": ["burp", "burp suite"],
    "Nmap": ["nmap"],
    "Metasploit": ["metasploit"],
    "Kali Linux": ["kali", "kali linux"],
    "Wireshark": ["wireshark"],
    "Resposta a Incidentes": ["resposta a incidentes", "incident response", "csirt", "tratamento de incidentes"],
    "Gestão de Vulnerabilidades": ["gestao de vulnerabilidades", "vulnerability management", "analise de vulnerabilidades",
                                   "tenable", "nessus", "qualys"],
    "Threat Intelligence": ["threat intelligence", "inteligencia de ameacas", "threat hunting"],
    "Firewall": ["firewall", "fortinet", "fortigate", "palo alto", "checkpoint", "pfsense"],
    "IDS/IPS": ["ids/ips", "ips/ids", "snort", "suricata", "intrusion detection"],
    "EDR/XDR": ["edr", "xdr", "crowdstrike", "sentinelone", "defender for endpoint"],
    "IAM": ["iam", "gestao de identidades", "gestao de acessos", "identity and access", "okta", "sailpoint", "cyberark"],
    "Active Directory": ["active directory", "entra id", "azure ad"],
    "ISO 27001": ["iso 27001", "iso/iec 27001", "27001", "iso 27002"],
    "NIST": ["nist", "nist csf"],
    "LGPD": ["lgpd", "gdpr", "protecao de dados"],
    "PCI DSS": ["pci dss", "pci-dss"],
    "GRC": ["grc", "governanca de ti", "gestao de riscos", "riscos e compliance"],
    "Forense Digital": ["forense", "forensics", "pericia digital"],
    "Hardening": ["hardening"],
    "DLP": ["dlp", "data loss prevention"],
    "Zero Trust": ["zero trust"],
    "Cloud Security": ["cloud security", "seguranca em nuvem", "cspm"],
    "Criptografia": ["criptografia", "cryptography", "pki"],
    "CompTIA Security+": ["security+", "comptia security", "security plus"],
    "CEH": ["ceh", "certified ethical hacker"],
    "CISSP": ["cissp"],
    "OSCP": ["oscp"],
    # --- Infraestrutura, redes e suporte ----------------------------------
    "Redes": ["redes de computadores", "tcp/ip", "tcp ip", "networking", "roteamento", "switching", "vlan"],
    "Windows Server": ["windows server"],
    "VMware": ["vmware", "vsphere", "esxi"],
    "Zabbix": ["zabbix"],
    "Ansible": ["ansible"],
    "Cisco": ["cisco", "ccna", "ccnp"],
    "ITIL": ["itil"],
    "PowerShell": ["powershell"],
    "Suporte Técnico": ["suporte tecnico", "help desk", "helpdesk", "service desk"],
    "Microsoft 365": ["office 365", "microsoft 365", "m365"],
    # --- Dados e BI ---------------------------------------------------------
    "Power BI": ["power bi", "powerbi"],
    "Excel": ["excel"],
    "Tableau": ["tableau"],
    "Looker": ["looker"],
    "ETL": ["etl", "elt"],
    "Data Warehouse": ["data warehouse", "data lake", "lakehouse"],
    "dbt": ["dbt"],
    "Estatística": ["estatistica", "statistics"],
    # --- QA, produto e design ----------------------------------------------
    "Cypress": ["cypress"],
    "Postman": ["postman"],
    "JMeter": ["jmeter"],
    "Testes Manuais": ["testes manuais", "manual testing", "qa manual"],
    "Jira": ["jira"],
    "Figma": ["figma"],
    "UX": ["ux", "user experience", "experiencia do usuario"],
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


_VOCABULARIO_BASE = {k: list(v) for k, v in VOCABULARIO.items()}
_extras_ativos: tuple[str, ...] = ()


def _compilar(vocabulario: dict[str, list[str]]) -> dict[str, list[re.Pattern]]:
    return {
        canonico: [
            re.compile(r"(?<![\w.#+-])" + re.escape(normalizar(v)) + r"(?![\w#+]|\.\w)")
            for v in variacoes + ([] if canonico in _CANONICO_AMBIGUO else [canonico])
        ]
        for canonico, variacoes in vocabulario.items()
    }


def usar_termos_extras(termos: list[str]) -> None:
    """Termos da área da pessoa que o vocabulário não conhece (ex.: "SAP", "AutoCAD",
    "Marketing Digital"), declarados em preferencias.termos_extras do perfil.
    Viram competências reconhecidas na vaga e no currículo, como as embutidas."""
    global _PADROES, _extras_ativos
    chave = tuple(sorted({str(t).strip() for t in termos or [] if str(t).strip()}))
    if chave == _extras_ativos:
        return
    vocabulario = {k: list(v) for k, v in _VOCABULARIO_BASE.items()}
    conhecidos = {normalizar(v) for vs in vocabulario.values() for v in vs} | {normalizar(k) for k in vocabulario}
    for termo in chave:
        if normalizar(termo) not in conhecidos:
            vocabulario[termo] = [termo.lower()]
    VOCABULARIO.clear()
    VOCABULARIO.update(vocabulario)
    _PADROES = _compilar(vocabulario)
    _extras_ativos = chave


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
    ("Especialista", ["especialista", "staff", "principal", "lead", "tech lead", "lider", "manager", "gerente",
                      "head", "coordenador", "coordenadora", "arquiteto", "architect", "diretor", "diretora",
                      "director", "ciso", "cto", "cio", "vp"]),
]


def detectar_senioridade(titulo: str) -> str:
    alvo = normalizar(titulo).replace("pl/sql", " ").replace("pl sql", " ")
    for nome, termos in SENIORIDADES:
        if any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", alvo) for t in termos):
            return nome
    return ""


# Competências que quase toda vaga cita: contam, mas pouco.
GENERICAS = {"Inglês", "Espanhol", "Git", "Scrum", "Linux", "SQL", "REST", "Excel", "Jira", "Microsoft 365"}


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
    # Quem trabalha com SIEM, pentest, firewall... trabalha com segurança.
    **{t: {"Segurança"} for t in ("SIEM", "SOC", "Splunk", "QRadar", "Microsoft Sentinel", "Wazuh", "Pentest",
                                  "Burp Suite", "Metasploit", "Resposta a Incidentes", "Gestão de Vulnerabilidades",
                                  "Threat Intelligence", "Firewall", "IDS/IPS", "EDR/XDR", "IAM", "ISO 27001",
                                  "NIST", "PCI DSS", "Forense Digital", "Hardening", "DLP", "Zero Trust",
                                  "Cloud Security", "CompTIA Security+", "CEH", "CISSP", "OSCP")},
    "Power BI": {"Excel"}, "Cisco": {"Redes"},
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


def variante_para_vaga(candidato: Candidato, titulo: str) -> Candidato:
    """Vaga de estágio usa o perfil "estagio" (resumo de estudante, sem cara de
    sênior), se você tiver declarado um em `variantes:`; senão, o perfil base."""
    if detectar_senioridade(titulo) == "Estágio" and "estagio" in candidato.variantes:
        return candidato.variantes["estagio"]
    return candidato


def analisar(candidato: Candidato, titulo: str, descricao: str) -> Analise:
    candidato = variante_para_vaga(candidato, titulo)
    usar_termos_extras((candidato.preferencias or {}).get("termos_extras") or [])
    texto_vaga = f"{titulo}\n{descricao}"
    pedidas = extrair_tecnologias(texto_vaga)
    perfil = {canonizar(h) for h in candidato.todas_habilidades}
    # O título do perfil também é competência: "Analista de Segurança da Informação" tem Segurança.
    perfil |= set(extrair_tecnologias(candidato.titulo))
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
