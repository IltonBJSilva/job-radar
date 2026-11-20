"""Depois do envio: follow-up educado e leitura das respostas (IMAP).

Por que existe: a maioria das candidaturas não recebe resposta, e um único
follow-up alguns dias depois recupera parte delas. Mas follow-up para quem
já respondeu (ou para e-mail que voltou) é spam — por isso as duas coisas
andam juntas: `verificar_respostas()` roda antes de `enviar_followups()`.

Usa a MESMA senha de app do Gmail (IMAP precisa estar ativado nas
configurações do Gmail: Ver todas as configurações > Encaminhamento e POP/IMAP).
"""

from __future__ import annotations

import email
import imaplib
import random
import time
from datetime import datetime, timedelta
from email.header import decode_header, make_header

from candidatura import config, repositorio
from candidatura.envio import ErroEnvio, ErroFatalSMTP, enviar_smtp, montar_mensagem, salvar_eml
from candidatura.perfil import Candidato, carregar_candidato
from core.logger import get_logger

logger = get_logger()

IMAP_HOST = "imap.gmail.com"
DIAS_PARA_FOLLOWUP = 7
MAX_FOLLOWUPS = 1


# ------------------------------------------------------------- follow-up

def texto_followup(candidato: Candidato, vaga: dict) -> str:
    empresa = vaga.get("empresa") or "a equipe"
    data = "/".join(reversed((vaga.get("enviada_em") or "")[:10].split("-"))) if vaga.get("enviada_em") else ""
    return (
        "Olá, tudo bem?\n\n"
        f"Escrevo para reforçar meu interesse na vaga de {vaga['titulo']}, para a qual enviei meu currículo"
        + (f" em {data}" if data else "") + ". "
        f"Sigo disponível para conversar e mostrar como posso contribuir com {empresa}.\n\n"
        "Se a vaga já tiver sido preenchida, agradeço o retorno e não enviarei novas mensagens.\n\n"
        "Atenciosamente,\n"
        + (candidato.assinatura_email or f"{candidato.nome}\n{candidato.telefone}\n{candidato.email}")
        + "\n"
    )


def pendentes_de_followup(dias: int = DIAS_PARA_FOLLOWUP, maximo: int = MAX_FOLLOWUPS) -> list[dict]:
    limite = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    return [
        v for v in repositorio.listar("enviada", limite=2000, ordem="enviada_em ASC")
        if not v.get("simulado")
        and (v.get("followups") or 0) < maximo
        and (v.get("ultimo_followup_em") or v.get("enviada_em") or "9999") <= limite
        and v.get("email_destino")
    ]


def enviar_followups(limite: int = 10, real: bool | None = None, dias: int = DIAS_PARA_FOLLOWUP,
                     candidato: Candidato | None = None) -> dict:
    real = config.ENVIO_REAL if real is None else real
    candidato = candidato or carregar_candidato()
    resultado = {"enviados": 0, "erros": [], "real": real}
    for vaga in pendentes_de_followup(dias)[:limite]:
        if real and repositorio.enviadas_hoje() >= config.LIMITE_DIARIO:
            resultado["erros"].append((vaga["titulo"], "limite diário atingido"))
            break
        assunto = vaga.get("assunto") or f"Candidatura: {vaga['titulo']}"
        assunto = assunto if assunto.lower().startswith("re:") else f"Re: {assunto}"
        msg = montar_mensagem(candidato.nome, config.SMTP_USUARIO or candidato.email, vaga["email_destino"],
                              assunto, texto_followup(candidato, vaga), [], responder_para=candidato.email)
        if vaga.get("message_id"):
            # Mesmo fio da conversa: o recrutador vê o e-mail original logo abaixo.
            msg["In-Reply-To"] = vaga["message_id"]
            msg["References"] = vaga["message_id"]
        try:
            if real:
                enviar_smtp(msg)
            else:
                from pathlib import Path

                pasta = Path(vaga["cv_path"]).parent if vaga.get("cv_path") else config.SAIDA_DIR
                pasta.mkdir(parents=True, exist_ok=True)
                (pasta / "followup_simulado.eml").write_bytes(bytes(msg))
        except ErroFatalSMTP as e:
            resultado["erros"].append((vaga["titulo"], str(e)))
            break
        except ErroEnvio as e:
            resultado["erros"].append((vaga["titulo"], str(e)))
            continue
        if real:
            repositorio.atualizar(vaga["id"], followups=(vaga.get("followups") or 0) + 1,
                                  ultimo_followup_em=datetime.now().isoformat(timespec="seconds"))
        resultado["enviados"] += 1
        logger.info(f"[Follow-up] {'ENVIADO' if real else 'Simulado'}: {vaga['titulo']} -> {vaga['email_destino']}")
        if real:
            time.sleep(random.uniform(config.INTERVALO_MIN_SEG, config.INTERVALO_MAX_SEG))
    return resultado


# --------------------------------------------------------------- respostas

def _decodificar(valor: str | None) -> str:
    try:
        return str(make_header(decode_header(valor or "")))
    except Exception:
        return valor or ""


def _corpo_texto(msg: email.message.Message, limite: int = 4000) -> str:
    partes = msg.walk() if msg.is_multipart() else [msg]
    for parte in partes:
        if parte.get_content_type() == "text/plain":
            try:
                return parte.get_payload(decode=True).decode(parte.get_content_charset() or "utf-8", "replace")[:limite]
            except Exception:
                continue
    return ""


def classificar_mensagem(remetente: str, assunto: str, corpo: str, cabecalhos: dict, vagas: list[dict]) -> list[tuple[str, str, str]]:
    """Decide a que candidatura(s) uma mensagem recebida se refere.

    Devolve [(id_vaga, tipo, resumo)] com tipo 'resposta' ou 'bounce'.
    Função pura — testável sem servidor IMAP."""
    remetente_l = (remetente or "").lower()
    referencias = f"{cabecalhos.get('In-Reply-To', '')} {cabecalhos.get('References', '')}"
    eh_bounce = any(t in remetente_l for t in ("mailer-daemon", "postmaster")) or \
        any(t in (assunto or "").lower() for t in ("delivery status notification", "undeliverable", "não entregue", "falha na entrega"))
    achados = []
    for v in vagas:
        destino = (v.get("email_destino") or "").lower()
        mid = v.get("message_id") or ""
        if eh_bounce:
            if destino and destino in (corpo or "").lower():
                achados.append((v["id"], "bounce", f"E-mail não entregue para {destino}"))
        elif (mid and mid in referencias) or (destino and destino in remetente_l):
            achados.append((v["id"], "resposta", (assunto or "")[:200]))
    return achados


def verificar_respostas(dias: int = 45) -> dict:
    """Lê a caixa de entrada via IMAP e marca candidaturas respondidas ou que voltaram."""
    if not config.SMTP_USUARIO or not config.SMTP_SENHA:
        raise RuntimeError("Configure SMTP_USUARIO/SMTP_SENHA no .env (a mesma senha de app serve para IMAP).")
    vagas = [v for v in repositorio.listar("enviada", limite=5000) if not v.get("simulado")]
    resultado = {"respostas": 0, "bounces": 0, "lidas": 0}
    if not vagas:
        return resultado
    desde = (datetime.now() - timedelta(days=dias)).strftime("%d-%b-%Y")
    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(config.SMTP_USUARIO, config.SMTP_SENHA)
        imap.select("INBOX", readonly=True)  # só leitura: não marca nada como lido
        _, dados = imap.search(None, f'(SINCE "{desde}")')
        ids = (dados[0] or b"").split()[-1500:]
        for num in ids:
            _, bruto = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT IN-REPLY-TO REFERENCES)] BODY.PEEK[TEXT]<0.4000>)")
            pedacos = [p[1] for p in bruto if isinstance(p, tuple)]
            if not pedacos:
                continue
            cab = email.message_from_bytes(pedacos[0])
            corpo = pedacos[1].decode("utf-8", "replace") if len(pedacos) > 1 else ""
            resultado["lidas"] += 1
            for id_, tipo, resumo in classificar_mensagem(
                _decodificar(cab.get("From")), _decodificar(cab.get("Subject")), corpo,
                {"In-Reply-To": cab.get("In-Reply-To", ""), "References": cab.get("References", "")}, vagas,
            ):
                atual = repositorio.obter(id_)
                if not atual or atual["status"] != "enviada":
                    continue
                if tipo == "resposta":
                    repositorio.atualizar(id_, status="respondida", resposta_resumo=resumo,
                                          resposta_em=datetime.now().isoformat(timespec="seconds"))
                    resultado["respostas"] += 1
                else:
                    repositorio.atualizar(id_, status="erro", erro=resumo)
                    resultado["bounces"] += 1
    logger.info(f"[IMAP] {resultado}")
    return resultado
