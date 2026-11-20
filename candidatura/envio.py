"""Envio por e-mail (SMTP) com trava de segurança e limites anti-spam.

- ENVIO_REAL=false (padrão): grava um .eml na pasta da vaga — abra no
  Outlook/Thunderbird para ver exatamente o que seria enviado.
- ENVIO_REAL=true: envia de verdade via SMTP (Gmail com senha de app).
"""

from __future__ import annotations

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from candidatura import config


class ErroEnvio(RuntimeError):
    pass


class ErroFatalSMTP(ErroEnvio):
    """Credencial inválida ou conta bloqueada: parar o lote inteiro."""


def montar_mensagem(remetente_nome: str, remetente_email: str, destino: str, assunto: str,
                    corpo: str, anexos: list[Path], responder_para: str = "") -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((remetente_nome, remetente_email))
    msg["To"] = destino
    msg["Subject"] = assunto
    msg["Message-ID"] = make_msgid(domain=remetente_email.split("@")[-1] or "localhost")
    if responder_para and responder_para != remetente_email:
        msg["Reply-To"] = responder_para
    msg.set_content(corpo)
    for caminho in anexos:
        caminho = Path(caminho)
        if not caminho.exists():
            continue
        tipo, _ = mimetypes.guess_type(caminho.name)
        principal, sub = (tipo or "application/octet-stream").split("/", 1)
        msg.add_attachment(caminho.read_bytes(), maintype=principal, subtype=sub, filename=caminho.name)
    return msg


def salvar_eml(msg: EmailMessage, pasta: Path) -> Path:
    destino = Path(pasta) / "email_simulado.eml"
    destino.write_bytes(bytes(msg))
    return destino


def enviar_smtp(msg: EmailMessage):
    if not config.SMTP_USUARIO or not config.SMTP_SENHA:
        raise ErroFatalSMTP("SMTP_USUARIO/SMTP_SENHA não configurados no .env")
    contexto = ssl.create_default_context()
    try:
        if config.SMTP_PORTA == 465:
            servidor = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORTA, context=contexto, timeout=30)
        else:
            servidor = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORTA, timeout=30)
            servidor.starttls(context=contexto)
        with servidor:
            servidor.login(config.SMTP_USUARIO, config.SMTP_SENHA)
            destinos = [msg["To"]]
            if config.EMAIL_COPIA_PARA_MIM:
                destinos.append(config.SMTP_USUARIO)
            servidor.send_message(msg, to_addrs=destinos)
    except smtplib.SMTPAuthenticationError as e:
        raise ErroFatalSMTP(
            f"Login SMTP recusado ({e.smtp_code}). No Gmail, use uma SENHA DE APP "
            "(myaccount.google.com/apppasswords, exige verificação em 2 etapas)."
        ) from e
    except smtplib.SMTPRecipientsRefused as e:
        raise ErroEnvio(f"Destinatário recusado: {e.recipients}") from e
    except smtplib.SMTPResponseException as e:
        if e.smtp_code in (421, 450, 451, 452, 454, 550, 554) and b"limit" in (e.smtp_error or b"").lower():
            raise ErroFatalSMTP(f"Limite do provedor atingido ({e.smtp_code}). Pare por hoje.") from e
        raise ErroEnvio(f"SMTP {e.smtp_code}: {e.smtp_error!r}") from e
    except (smtplib.SMTPException, OSError) as e:
        raise ErroEnvio(f"Falha de conexão SMTP: {e}") from e
