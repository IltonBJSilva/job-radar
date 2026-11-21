"""Rotina diária no Agendador de Tarefas do Windows (uma por perfil).

Todo dia, no horário escolhido: busca vagas nas fontes do perfil, lê as
respostas no Gmail, manda os follow-ups de quem não respondeu em 7 dias e,
se você ligar, envia sozinho as vagas mais compatíveis (modo auto).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from candidatura import config


def nome_tarefa(perfil_id: str | None = None) -> str:
    perfil_id = perfil_id or config.PERFIL_ATIVO
    return "JobRadarCandidaturas" if perfil_id == config.PERFIL_PRINCIPAL else f"JobRadar-{perfil_id}"


def script(perfil_id: str | None = None) -> Path:
    perfil_id = perfil_id or config.PERFIL_ATIVO
    return config.RAIZ / "data" / f"rotina_{perfil_id}.cmd"


def conteudo(perfil_id: str, auto: bool = False, limite_auto: int = 10) -> str:
    raiz = config.RAIZ
    python = raiz / "venv" / "Scripts" / "python.exe"
    py = f'"{python if python.exists() else sys.executable}" candidatar.py --perfil {perfil_id}'
    log = raiz / "data" / f"rotina_{perfil_id}.log"
    linhas = ["@echo off", f'cd /d "{raiz}"', f'echo ==== %date% %time% >> "{log}"',
              f'{py} importar --enriquecer 40 >> "{log}" 2>&1']
    if config.SMTP_SENHA:
        linhas.append(f'{py} respostas >> "{log}" 2>&1')
        if config.ENVIO_REAL:
            linhas.append(f'{py} followup --limite 5 >> "{log}" 2>&1')
    if auto:
        linhas.append(f'{py} auto --limite {int(limite_auto)} >> "{log}" 2>&1')
    return "\r\n".join(linhas) + "\r\n"


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, encoding="cp850", errors="replace")


def ativar(hora: str = "09:00", auto: bool = False, limite_auto: int = 10, perfil_id: str | None = None) -> str:
    if os.name != "nt":
        raise RuntimeError("A rotina automática usa o Agendador do Windows. No Linux/macOS, use o cron "
                           "com: python candidatar.py --perfil <id> importar")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora or ""):
        raise ValueError("Horário inválido (use HH:MM, ex.: 09:00).")
    perfil_id = perfil_id or config.PERFIL_ATIVO
    caminho = script(perfil_id)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo(perfil_id, auto, limite_auto), encoding="utf-8", newline="")  # o texto já vem com CRLF
    r = _schtasks("/Create", "/F", "/SC", "DAILY", "/ST", hora, "/TN", nome_tarefa(perfil_id), "/TR", f'"{caminho}"')
    if r.returncode != 0:
        raise RuntimeError(f"O Windows recusou criar a tarefa: {(r.stderr or r.stdout).strip()[:200]}")
    return nome_tarefa(perfil_id)


def desativar(perfil_id: str | None = None) -> bool:
    if os.name != "nt":
        return False
    return _schtasks("/Delete", "/F", "/TN", nome_tarefa(perfil_id)).returncode == 0


def situacao(perfil_id: str | None = None) -> dict:
    """{"ativa": bool, "hora": "09:00", "auto": bool, "proxima": "..."}"""
    if os.name != "nt":
        return {"ativa": False, "hora": "", "auto": False, "proxima": ""}
    r = _schtasks("/Query", "/TN", nome_tarefa(perfil_id), "/V", "/FO", "LIST")
    if r.returncode != 0:
        return {"ativa": False, "hora": "", "auto": False, "proxima": ""}
    texto = r.stdout
    hora = re.search(r"(?:Hora de in[ií]cio|Start Time):\s*(\d{1,2}:\d{2})", texto)
    proxima = re.search(r"(?:Hora da pr[oó]xima execu[cç][aã]o|Pr[oó]xima execu[cç][aã]o|Next Run Time):\s*(.+)", texto)
    try:
        auto = " auto " in script(perfil_id).read_text(encoding="utf-8")
    except OSError:
        auto = False
    return {"ativa": True, "hora": hora.group(1).zfill(5) if hora else "", "auto": auto,
            "proxima": proxima.group(1).strip() if proxima else ""}
