"""Configuração do módulo de candidatura (tudo via .env, com padrões seguros).

Padrão SEGURO: ENVIO_REAL=false. Nesse modo nada sai da sua máquina — cada
e-mail vira um arquivo .eml em saida/ para você abrir e conferir.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RAIZ = Path(__file__).resolve().parent.parent


def _bool(nome: str, padrao: bool = False) -> bool:
    return os.getenv(nome, str(padrao)).strip().lower() in {"1", "true", "sim", "yes", "on"}


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, padrao))
    except ValueError:
        return padrao


# --- Perfil do candidato -------------------------------------------------
PERFIL_PATH = Path(os.getenv("PERFIL_CANDIDATO", RAIZ / "config" / "candidato.yaml"))
PERFIL_EXEMPLO_PATH = RAIZ / "config" / "candidato.example.yaml"

# --- Banco da fila de candidaturas (fora do Git) ------------------------
CANDIDATURAS_DB_PATH = Path(os.getenv("CANDIDATURAS_DB_PATH", RAIZ / "data" / "candidaturas.db"))

# --- Saída (PDFs, cartas, .eml do modo simulação) ------------------------
SAIDA_DIR = Path(os.getenv("SAIDA_CANDIDATURAS", RAIZ / "saida"))

# --- SMTP ----------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORTA = _int("SMTP_PORTA", 587)
SMTP_USUARIO = os.getenv("SMTP_USUARIO", "")
SMTP_SENHA = os.getenv("SMTP_SENHA", "")  # Gmail: "senha de app", nunca a senha normal
EMAIL_COPIA_PARA_MIM = _bool("EMAIL_COPIA_PARA_MIM", False)

ENVIO_REAL = _bool("ENVIO_REAL", False)

# --- Limites anti-spam ---------------------------------------------------
# Gmail gratuito aceita ~500/dia, mas volume alto de e-mails parecidos para
# desconhecidos derruba sua reputação de remetente. 30/dia é um teto sensato.
LIMITE_DIARIO = _int("LIMITE_DIARIO_ENVIOS", 30)
INTERVALO_MIN_SEG = _int("INTERVALO_MIN_SEG", 60)
INTERVALO_MAX_SEG = _int("INTERVALO_MAX_SEG", 180)
# Não manda de novo para a mesma empresa/e-mail dentro desta janela.
DIAS_SEM_REPETIR_EMPRESA = _int("DIAS_SEM_REPETIR_EMPRESA", 30)

# --- Modo automático -----------------------------------------------------
# Compatibilidade mínima (0-100) para o modo `auto` mandar sem você revisar.
SCORE_MINIMO_AUTO = _int("SCORE_MINIMO_AUTO", 60)

# --- IA opcional (gratuita) ----------------------------------------------
# Sem IA o sistema funciona 100% (adaptação por palavras-chave + modelos).
# Com IA, o resumo e a carta ficam mais naturais. Provedores com camada
# gratuita: groq, gemini, ollama (local, sem chave).
IA_PROVEDOR = os.getenv("IA_PROVEDOR", "").strip().lower()
IA_API_KEY = os.getenv("IA_API_KEY", "")
IA_MODELO = os.getenv("IA_MODELO", "")
IA_URL_BASE = os.getenv("IA_URL_BASE", "")
