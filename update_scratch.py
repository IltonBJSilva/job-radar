import re
import os

with open('core/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

def replace_list(var_name, new_list_str, content):
    pattern = r'^' + var_name + r'\s*=\s*\[.*?\]'
    return re.sub(pattern, var_name + ' = [\n' + new_list_str + '\n]', content, flags=re.DOTALL | re.MULTILINE)

replacements = {
    'KEYWORDS_CARGO_FORTE': '''    "Desenvolvedor Backend",
    "Desenvolvedor Back-end",
    "Desenvolvedor Backend Python",
    "Desenvolvedor Backend Node.js",
    "Desenvolvedor Python",
    "Desenvolvedor Node.js",
    "Engenheiro de Software",
    "Software Engineer",
    "Backend Engineer",
    "Back-end Engineer",
    "Software Backend Engineer",
    "Backend Developer",
    "Back-end Developer",
    "Desenvolvedor Full Stack",
    "Desenvolvedor Full-Stack",
    "Full Stack Developer",
    "Full Stack Engineer",
    "Python Developer",
    "Node.js Developer",
    "Cloud Engineer",
    "Desenvolvedor Cloud",
    "Data Engineer",
    "Engenheiro de Dados",''',
    
    'KEYWORDS_CARGO_AMBIGUO': '''    "Desenvolvedor",
    "Desenvolvedora",
    "Developer",
    "Programador",
    "Engenheiro",
    "Engineer",
    "Analista de Sistemas",
    "Systems Analyst",
    "Analista Desenvolvedor",
    "Especialista em Desenvolvimento",
    "Especialista em Software",''',

    'QUALIFICADORES_DADOS': '''    "backend",
    "back-end",
    "python",
    "node",
    "node.js",
    "nodejs",
    "typescript",
    "javascript",
    "gcp",
    "google cloud",
    "cloud",
    "api",
    "apis",
    "django",
    "fastapi",
    "graphql",
    "docker",
    "kubernetes",
    "ci/cd",
    "bigquery",
    "sql",
    "full stack",
    "fullstack",
    "full-stack",
    "software",
    "sistemas",''',

    'FERRAMENTAS_TITULO': '''    "Python",
    "Node.js",
    "NodeJS",
    "TypeScript",
    "Django",
    "FastAPI",
    "GraphQL",
    "Docker",
    "GCP",
    "Google Cloud",
    "BigQuery",
    "Kubernetes",''',

    'QUALIFICADORES_CARGO': '''    "desenvolvedor",
    "desenvolvedora",
    "developer",
    "engenheiro",
    "engenheira",
    "engineer",
    "programador",
    "programadora",
    "architect",
    "arquiteto",
    "analista",
    "especialista",
    "backend",
    "back-end",''',

    'TERMOS_CARGO_EXTRA': '''    "python",
    "node.js",
    "typescript",
    "backend",
    "back-end",
    "software engineer",
    "engenheiro de software",
    "desenvolvedor backend",
    "backend developer",
    "python developer",
    "node developer",
    "gcp",
    "google cloud",
    "graphql",
    "api",
    "django",
    "fastapi",
    "docker",
    "full stack",
    "data engineer",
    "engenheiro de dados",
    "cloud engineer",''',

    'TERMOS_FERRAMENTA': '''    "python",
    "node.js",
    "typescript",
    "django",
    "fastapi",
    "graphql",
    "docker",
    "gcp",
    "google cloud",
    "bigquery",
    "kubernetes",
    "ci/cd",''',

    'TERMOS_PRIORITARIOS': '''    "desenvolvedor backend",
    "backend developer",
    "software engineer",
    "engenheiro de software",
    "desenvolvedor python",
    "python developer",''',

    'CIDADES': '''    "Remoto",
    "Uberlândia",'''
}

for var, new_str in replacements.items():
    content = replace_list(var, new_str, content)

os.makedirs('C:/Users/ilton/.gemini/antigravity-ide/brain/8f8f1aaa-efd6-4855-8f4d-4c7f02c7f7f5/scratch', exist_ok=True)
with open('C:/Users/ilton/.gemini/antigravity-ide/brain/8f8f1aaa-efd6-4855-8f4d-4c7f02c7f7f5/scratch/config_new.py', 'w', encoding='utf-8') as f:
    f.write(content)

# Now do config_intl.py
with open('core/config_intl.py', 'r', encoding='utf-8') as f:
    content_intl = f.read()

replacements_intl = {
    'KEYWORDS_INTL': '''    "Backend Developer",
    "Software Engineer",
    "Python Developer",
    "Node.js Developer",
    "Full Stack Developer",
    "Cloud Engineer",
    "Data Engineer",
    "Desenvolvedor Backend",
    "Engenheiro de Software",
    "Desenvolvedor Python",
    "Backend Engineer",''',

    'TERMOS_BUSCA_INTL': '''    "backend developer portuguese",
    "backend developer spanish",
    "software engineer portuguese",
    "software engineer spanish",
    "python developer portuguese",
    "python developer spanish",
    "remote backend developer latam",
    "remote software engineer latam",
    "python developer latam",
    "node developer latam",
    "backend developer",
    "software engineer",
    "python developer",
    "node developer",''',
}

for var, new_str in replacements_intl.items():
    content_intl = replace_list(var, new_str, content_intl)

with open('C:/Users/ilton/.gemini/antigravity-ide/brain/8f8f1aaa-efd6-4855-8f4d-4c7f02c7f7f5/scratch/config_intl_new.py', 'w', encoding='utf-8') as f:
    f.write(content_intl)

print("Generated new configs in scratch")
