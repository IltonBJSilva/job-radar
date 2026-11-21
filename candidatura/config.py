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
# true = curtir (coração) prepara e já envia; vagas sem e-mail ficam em "manual".
ENVIAR_AO_CURTIR = _bool("ENVIAR_AO_CURTIR", False)

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
# false (padrão): o resumo do currículo é SEMPRE o seu (texto do perfil); a IA escreve carta e e-mail.
IA_NO_RESUMO = _bool("IA_NO_RESUMO", False)

# --- Chaves opcionais (Configurações -> Chaves) ----------------------------
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")    # busca de posts públicos (grátis: 1.000 créditos/mês)
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")      # alternativa paga à Tavily
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")    # e-mail de RH das empresas (hunter.io)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CHAVES_GLOBAIS = ("IA_PROVEDOR", "IA_API_KEY", "IA_MODELO", "IA_NO_RESUMO", "TAVILY_API_KEY", "BRAVE_API_KEY",
                  "HUNTER_API_KEY")

# --- Vários perfis na mesma instalação -------------------------------------
# "principal" = os caminhos acima (config/candidato.yaml, data/candidaturas.db,
# saida/ e o .env) — quem já usava o sistema não precisa mover nada. Cada
# perfil novo mora em perfis/<id>/ com o próprio currículo, fila, PDFs e
# config.env (e-mail/senha de app daquela pessoa). Tudo fora do Git.
PERFIS_DIR = RAIZ / "perfis"
ENV_PATH = RAIZ / ".env"  # config do perfil principal (os testes apontam para uma pasta temporária)
PERFIL_ATIVO_PATH = RAIZ / "data" / "perfil_ativo.txt"
PERFIL_PRINCIPAL = "principal"
# Configurações que são DA PESSOA (cada perfil tem as suas).
CHAVES_DO_PERFIL = ("SMTP_HOST", "SMTP_PORTA", "SMTP_USUARIO", "SMTP_SENHA", "EMAIL_COPIA_PARA_MIM",
                    "ENVIO_REAL", "ENVIAR_AO_CURTIR")
_PADRAO_PRINCIPAL = {
    "PERFIL_PATH": PERFIL_PATH, "CANDIDATURAS_DB_PATH": CANDIDATURAS_DB_PATH, "SAIDA_DIR": SAIDA_DIR,
    "SMTP_HOST": SMTP_HOST, "SMTP_PORTA": SMTP_PORTA, "SMTP_USUARIO": SMTP_USUARIO, "SMTP_SENHA": SMTP_SENHA,
    "EMAIL_COPIA_PARA_MIM": EMAIL_COPIA_PARA_MIM, "ENVIO_REAL": ENVIO_REAL, "ENVIAR_AO_CURTIR": ENVIAR_AO_CURTIR,
}
PERFIL_ATIVO = PERFIL_PRINCIPAL


def _id_valido(perfil_id: str) -> bool:
    import re

    return perfil_id == PERFIL_PRINCIPAL or bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", perfil_id or ""))


def pasta_do_perfil(perfil_id: str) -> Path:
    if not _id_valido(perfil_id) or perfil_id == PERFIL_PRINCIPAL:
        raise ValueError(f"perfil inválido: {perfil_id!r}")
    return PERFIS_DIR / perfil_id


def arquivo_config(perfil_id: str) -> Path:
    """Onde ficam e-mail/senha de app do perfil: o .env (principal) ou perfis/<id>/config.env."""
    return ENV_PATH if perfil_id == PERFIL_PRINCIPAL else pasta_do_perfil(perfil_id) / "config.env"


def _converter(chave: str, valor: str):
    if chave == "SMTP_PORTA":
        try:
            return int(valor)
        except ValueError:
            return 587
    if chave in ("EMAIL_COPIA_PARA_MIM", "ENVIO_REAL", "ENVIAR_AO_CURTIR"):
        return str(valor).strip().lower() in {"1", "true", "sim", "yes", "on"}
    return valor


def ativar_perfil(perfil_id: str, lembrar: bool = True) -> None:
    """Troca caminhos e e-mail para os do perfil. Os módulos leem `config.X`
    na hora de usar, então a troca vale imediatamente (sem reiniciar)."""
    global PERFIL_ATIVO
    from dotenv import dotenv_values

    if not _id_valido(perfil_id):
        raise ValueError(f"perfil inválido: {perfil_id!r}")
    valores = dict(_PADRAO_PRINCIPAL)
    if perfil_id != PERFIL_PRINCIPAL:
        pasta = pasta_do_perfil(perfil_id)
        if not pasta.is_dir():
            raise ValueError(f"perfil não encontrado: {perfil_id}")
        valores.update(PERFIL_PATH=pasta / "candidato.yaml", CANDIDATURAS_DB_PATH=pasta / "candidaturas.db",
                       SAIDA_DIR=pasta / "saida")
        # Perfil novo NÃO herda o e-mail/senha do principal: começa em simulação, sem SMTP.
        valores.update(SMTP_USUARIO="", SMTP_SENHA="", ENVIO_REAL=False, ENVIAR_AO_CURTIR=False,
                       EMAIL_COPIA_PARA_MIM=False)
        for chave, valor in dotenv_values(arquivo_config(perfil_id)).items():
            if chave in CHAVES_DO_PERFIL and valor is not None:
                valores[chave] = _converter(chave, valor)
    globals().update(valores)
    PERFIL_ATIVO = perfil_id
    if lembrar:
        PERFIL_ATIVO_PATH.parent.mkdir(parents=True, exist_ok=True)
        PERFIL_ATIVO_PATH.write_text(perfil_id, encoding="utf-8")


def gravar_config_perfil(perfil_id: str, novos: dict) -> None:
    """Atualiza só as chaves informadas no .env/config.env do perfil, mantendo o resto do arquivo."""
    caminho = arquivo_config(perfil_id)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    faltando = dict(novos)
    for i, linha in enumerate(linhas):
        chave = linha.split("=", 1)[0].strip()
        if chave in faltando and not linha.lstrip().startswith("#"):
            linhas[i] = f"{chave}={faltando.pop(chave)}"
    linhas += [f"{k}={v}" for k, v in faltando.items()]
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    if perfil_id == PERFIL_PRINCIPAL:  # o principal também vale como padrão até reiniciar
        for chave, valor in novos.items():
            if chave in _PADRAO_PRINCIPAL:
                _PADRAO_PRINCIPAL[chave] = _converter(chave, str(valor))
    if perfil_id == PERFIL_ATIVO:  # só as chaves de e-mail mudam; caminhos do perfil ficam como estão
        globals().update({k: _converter(k, str(v)) for k, v in novos.items() if k in CHAVES_DO_PERFIL})


def gravar_chaves(novos: dict) -> None:
    """Chaves de serviços (IA, busca, Hunter) ficam no .env e valem para todos os perfis."""
    novos = {k: str(v).strip() for k, v in novos.items() if k in CHAVES_GLOBAIS}
    caminho = ENV_PATH
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    faltando = dict(novos)
    for i, linha in enumerate(linhas):
        chave = linha.split("=", 1)[0].strip()
        if chave in faltando and not linha.lstrip().startswith("#"):
            linhas[i] = f"{chave}={faltando.pop(chave)}"
    linhas += [f"{k}={v}" for k, v in faltando.items()]
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    for chave, valor in novos.items():
        globals()[chave] = (valor.lower() in {"1", "true", "sim", "yes", "on"} if chave == "IA_NO_RESUMO"
                            else valor.lower() if chave == "IA_PROVEDOR" else valor)


def listar_perfis() -> list[str]:
    ids = [PERFIL_PRINCIPAL]
    if PERFIS_DIR.is_dir():
        ids += sorted(p.name for p in PERFIS_DIR.iterdir() if p.is_dir() and _id_valido(p.name))
    return ids


def _perfil_inicial() -> str:
    escolhido = os.getenv("JOBRADAR_PERFIL", "").strip()
    if not escolhido:
        try:
            escolhido = PERFIL_ATIVO_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            escolhido = ""
    return escolhido or PERFIL_PRINCIPAL


try:
    ativar_perfil(_perfil_inicial(), lembrar=False)
except ValueError:  # perfil apagado à mão: volta para o principal
    ativar_perfil(PERFIL_PRINCIPAL, lembrar=False)
