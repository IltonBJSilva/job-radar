"""IA opcional para deixar resumo e carta mais naturais.

Totalmente opcional: sem configurar, `disponivel()` é False e o sistema usa
os modelos de texto determinísticos. Todos os provedores abaixo têm uso
gratuito e falam o mesmo protocolo (chat/completions estilo OpenAI):

  IA_PROVEDOR=groq    IA_API_KEY=...   (console.groq.com — camada gratuita)
  IA_PROVEDOR=gemini  IA_API_KEY=...   (aistudio.google.com — camada gratuita)
  IA_PROVEDOR=ollama                   (roda local, sem chave: ollama.com)

Qualquer falha (rede, cota, chave inválida) devolve None e o chamador cai no
texto padrão — a IA nunca impede uma candidatura de ser preparada.
"""

from __future__ import annotations

import json

import requests

from candidatura import config
from core.logger import get_logger

logger = get_logger()

PROVEDORES = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "ollama": ("http://localhost:11434/v1", "llama3.1"),
}

REGRAS_DE_HONESTIDADE = (
    "Regras obrigatórias: use SOMENTE fatos presentes no PERFIL do candidato. "
    "Não invente empresas, cargos, números, prazos, certificações ou tecnologias. "
    "Se a vaga pede algo que o perfil não tem, não afirme que o candidato tem. "
    "Escreva em português do Brasil, tom profissional e direto, sem clichês "
    "como 'sou apaixonado' ou 'vim por meio desta'. Não use markdown."
)


def disponivel() -> bool:
    if config.IA_PROVEDOR not in PROVEDORES:
        return False
    return config.IA_PROVEDOR == "ollama" or bool(config.IA_API_KEY)


def completar(sistema: str, usuario: str, max_tokens: int = 700, temperatura: float = 0.4) -> str | None:
    if not disponivel():
        return None
    url_base, modelo_padrao = PROVEDORES[config.IA_PROVEDOR]
    url = (config.IA_URL_BASE or url_base).rstrip("/") + "/chat/completions"
    cabecalhos = {"Content-Type": "application/json"}
    if config.IA_API_KEY:
        cabecalhos["Authorization"] = f"Bearer {config.IA_API_KEY}"
    corpo = {
        "model": config.IA_MODELO or modelo_padrao,
        "messages": [
            {"role": "system", "content": sistema + "\n\n" + REGRAS_DE_HONESTIDADE},
            {"role": "user", "content": usuario},
        ],
        "max_tokens": max_tokens,
        "temperature": temperatura,
    }
    try:
        r = requests.post(url, headers=cabecalhos, data=json.dumps(corpo), timeout=60)
        if r.status_code != 200:
            logger.warning(f"[IA] {config.IA_PROVEDOR} respondeu HTTP {r.status_code}: {r.text[:200]}")
            return None
        texto = r.json()["choices"][0]["message"]["content"]
        return (texto or "").strip() or None
    except Exception as e:
        logger.warning(f"[IA] Falha ao chamar {config.IA_PROVEDOR}: {e}")
        return None


def perfil_em_texto(candidato) -> str:
    linhas = [
        f"Nome: {candidato.nome}",
        f"Título: {candidato.titulo}",
        f"Cidade: {candidato.cidade}",
        f"Resumo: {candidato.resumo}",
        "Habilidades: " + ", ".join(candidato.todas_habilidades),
    ]
    for e in candidato.experiencias:
        linhas.append(f"Experiência: {e.cargo} na {e.empresa} ({e.periodo}). " + " ".join(e.conquistas))
    for p in candidato.projetos:
        linhas.append(f"Projeto: {p.nome} — {p.descricao} [{', '.join(p.tecnologias)}]")
    for f in candidato.formacao:
        linhas.append(f"Formação: {f.curso}, {f.instituicao} {f.periodo}")
    if candidato.idiomas:
        linhas.append("Idiomas: " + "; ".join(candidato.idiomas))
    return "\n".join(linhas)


def resumo_adaptado(candidato, titulo: str, empresa: str, descricao: str, em_comum: list[str]) -> str | None:
    return completar(
        "Você reescreve o resumo profissional de um currículo para uma vaga específica, "
        "em 3 a 4 frases (máximo 420 caracteres), em terceira pessoa implícita "
        "(sem 'eu'), destacando as competências do perfil que a vaga pede.",
        f"PERFIL:\n{perfil_em_texto(candidato)}\n\nVAGA: {titulo} na {empresa}\n"
        f"Tecnologias em comum: {', '.join(em_comum) or 'nenhuma identificada'}\n"
        f"DESCRIÇÃO DA VAGA:\n{descricao[:3500]}\n\nDevolva só o resumo.",
        max_tokens=250,
    )


def carta_adaptada(candidato, titulo: str, empresa: str, descricao: str, em_comum: list[str]) -> str | None:
    return completar(
        "Você escreve cartas de apresentação curtas para candidaturas por e-mail: "
        "3 parágrafos curtos (máximo 1100 caracteres no total). 1) interesse na vaga "
        "e na empresa; 2) 2 ou 3 evidências concretas do perfil ligadas ao que a vaga "
        "pede; 3) fechamento convidando para conversa. Sem saudação e sem assinatura "
        "(elas são adicionadas depois).",
        f"PERFIL:\n{perfil_em_texto(candidato)}\n\nVAGA: {titulo} na {empresa}\n"
        f"Tecnologias em comum: {', '.join(em_comum) or 'nenhuma identificada'}\n"
        f"DESCRIÇÃO DA VAGA:\n{descricao[:3500]}\n\nDevolva só os 3 parágrafos.",
        max_tokens=500,
    )
