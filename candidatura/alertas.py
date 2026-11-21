"""Aviso no celular (Telegram) quando aparece vaga BOA na sua cidade.

Liga em Configurações → Foco regional → "Avisar no Telegram". Depois de cada
busca: vaga nova da cidade do foco com compatibilidade >= limite (padrão 75%)
vira uma mensagem, uma vez só por vaga. Usa o mesmo bot do radar
(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID no .env).
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from candidatura import areas, localizacao, repositorio
from core.logger import get_logger

logger = get_logger()

LIMIAR_PADRAO = 75
MAXIMO_POR_RODADA = 10  # não inunda o celular depois de uma busca grande


def configuracao(preferencias: dict) -> dict | None:
    """{"cidade", "uf", "limiar"} se o aviso está ligado (exige o foco regional ligado)."""
    foco = areas.foco_regional(preferencias or {})
    bruto = (preferencias or {}).get("foco_regional") or {}
    if not foco or not bruto.get("alerta_telegram"):
        return None
    try:
        limiar = int(bruto.get("alerta_limiar") or LIMIAR_PADRAO)
    except (TypeError, ValueError):
        limiar = LIMIAR_PADRAO
    return {**foco, "limiar": max(0, min(100, limiar))}


def mensagem(v: dict, cidade: str) -> str:
    partes = [f"⭐ <b>Vaga boa em {escape(cidade)}</b> — {int(v.get('score') or 0)}% compatível",
              f"<b>{escape(v.get('titulo') or '')}</b>"]
    if v.get("empresa"):
        partes.append(escape(v["empresa"]))
    if v.get("email_destino"):
        partes.append(f"✉ {escape(v['email_destino'])} — curta no Job Radar para enviar")
    if v.get("link"):
        partes.append(escape(v["link"]))
    return "\n".join(partes)


def avisar_vagas_boas(preferencias: dict, enviar=None) -> int:
    cfg = configuracao(preferencias)
    if not cfg:
        return 0
    if enviar is None:
        from notifier.telegram import enviar_mensagem as enviar
    alvo_cidade, alvo_uf = localizacao.normalizar(cfg["cidade"]), cfg["uf"]
    avisadas = 0
    for v in repositorio.listar("nova", limite=100000):
        if v.get("alertada_em") or (v.get("score") or 0) < cfg["limiar"]:
            continue
        c = localizacao.classificar(v)
        if localizacao.normalizar(c.cidade) != alvo_cidade or (alvo_uf and c.uf and c.uf != alvo_uf):
            continue
        if not enviar(mensagem(v, cfg["cidade"])):
            logger.warning("[Alertas] Telegram não respondeu — tento de novo na próxima busca.")
            break
        repositorio.atualizar(v["id"], alertada_em=datetime.now().isoformat(timespec="seconds"))
        avisadas += 1
        if avisadas >= MAXIMO_POR_RODADA:
            break
    if avisadas:
        logger.info(f"[Alertas] {avisadas} vaga(s) de {cfg['cidade']} avisada(s) no Telegram")
    return avisadas
