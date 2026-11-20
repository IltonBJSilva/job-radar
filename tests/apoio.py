"""Dados de apoio compartilhados pelos testes.

Os testes de filtro validam o MOTOR (core/job.py), não a configuração pessoal
de quem usa o projeto. Por isso usam uma lista de cidades de referência fixa
(ver conftest.py) e uma descrição em português — o filtro exige descrição em
PT (ver heurística de idioma em Job._avaliar).
"""

TEXTO_PT = "Vaga com experiência em desenvolvimento de sistemas, requisitos e trabalho em equipe."

CIDADES_REFERENCIA = [
    "Remoto",
    "Campina Grande",
    "João Pessoa",
    "Recife",
    "Natal",
    "Caruaru",
    "Manaus",
    "Maceió",
    "Aracaju",
    "Fortaleza",
]
