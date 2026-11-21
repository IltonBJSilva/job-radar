"""Posts PÚBLICOS de recrutadores ("envie seu currículo para vagas@...") achados
por um buscador com API, sem login no LinkedIn: Tavily (grátis, 1.000
créditos/mês, sem cartão) ou Brave Search (pago desde fev/2026).

Para cada resultado: lê o texto do post (o trecho do buscador e, se preciso, a
página pública), extrai cargo/empresa/e-mail com posts.ler_post e só aceita
quando há e-mail de recrutamento. As vagas entram no swipe para você revisar;
nada é enviado sozinho por aqui.
"""

from __future__ import annotations

import time

import requests

from candidatura import areas, config, repositorio
from candidatura.contato import buscar_descricao, emails_com_relevancia
from candidatura.posts import ler_post
from core.logger import get_logger

logger = get_logger()

URL_BRAVE = "https://api.search.brave.com/res/v1/web/search"
URL_TAVILY = "https://api.tavily.com/search"
MAX_CONSULTAS = 6  # por busca: cada uma gasta 1 crédito da cota mensal


def disponivel() -> bool:
    return bool(config.TAVILY_API_KEY or config.BRAVE_API_KEY)


def provedor() -> str:
    return "tavily" if config.TAVILY_API_KEY else ("brave" if config.BRAVE_API_KEY else "")


def consultas(preferencias: dict) -> list[str]:
    """Ex.: site:linkedin.com/posts "python" ("envie" OR "mande") (currículo OR CV) Uberlândia"""
    termos = areas.termos_busca(preferencias)[:3]
    foco = areas.foco_regional(preferencias)
    cidade = f' "{foco["cidade"]}"' if foco else ""
    saida = []
    for termo in termos:
        base = f'"{termo}" ("envie" OR "enviar" OR "mande") ("currículo" OR "CV")'
        if foco:
            saida.append(f"site:linkedin.com/posts {base}{cidade}")
        saida.append(f"site:linkedin.com/posts {base} vaga")
    return list(dict.fromkeys(saida))[:MAX_CONSULTAS]


def buscar(consulta: str, sessao=None) -> list[dict]:
    if provedor() == "tavily":
        return _buscar_tavily(consulta, sessao)
    return _buscar_brave(consulta, sessao)


def _buscar_tavily(consulta: str, sessao=None) -> list[dict]:
    # A Tavily filtra o domínio por parâmetro: tira o "site:" da consulta.
    dominios = ["linkedin.com"] if "site:linkedin.com" in consulta else None
    corpo = {"query": consulta.replace("site:linkedin.com/posts", "").strip(), "max_results": 20,
             "search_depth": "basic", "time_range": "month"}
    if dominios:
        corpo["include_domains"] = dominios
    r = (sessao or requests).post(URL_TAVILY, json=corpo, timeout=30,
                                  headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"})
    if r.status_code in (401, 403):
        raise PermissionError("chave da Tavily inválida")
    if r.status_code in (429, 432, 433):
        raise RuntimeError("acabaram os créditos do mês na Tavily")
    r.raise_for_status()
    return [{"titulo": x.get("title") or "", "link": x.get("url") or "", "trecho": x.get("content") or ""}
            for x in r.json().get("results") or []]


def _buscar_brave(consulta: str, sessao=None) -> list[dict]:
    r = (sessao or requests).get(
        URL_BRAVE, params={"q": consulta, "count": 20, "country": "BR", "search_lang": "pt-br", "freshness": "pm"},
        headers={"Accept": "application/json", "X-Subscription-Token": config.BRAVE_API_KEY}, timeout=20)
    if r.status_code == 401:
        raise PermissionError("chave da Brave Search inválida")
    if r.status_code == 429:
        raise RuntimeError("limite da Brave Search atingido")
    r.raise_for_status()
    return [{"titulo": x.get("title") or "", "link": x.get("url") or "",
             "trecho": " ".join([x.get("description") or "", *(x.get("extra_snippets") or [])])}
            for x in (r.json().get("web") or {}).get("results") or []]


def coletar(preferencias: dict, sessao=None, baixar=buscar_descricao) -> int:
    if not disponivel():
        logger.info("[Posts] Sem chave da Tavily/Brave — fonte ignorada (configure em Configurações → Chaves).")
        return 0
    novas = 0
    for consulta in consultas(preferencias):
        try:
            resultados = buscar(consulta, sessao)
        except (PermissionError, RuntimeError) as e:
            logger.warning(f"[Posts] {e}")
            break
        except requests.RequestException as e:
            logger.warning(f"[Posts] '{consulta}': {e}")
            continue
        for res in resultados:
            if not res["link"] or repositorio.obter(repositorio.gerar_id(res["link"])):
                continue
            texto = f"{res['titulo']}\n{res['trecho']}"
            if not any(emails_com_relevancia(texto).values()):
                texto = (texto + "\n" + (baixar(res["link"]) or ""))[:20000]  # post público, sem login
            lido = ler_post(texto)
            relevancia = emails_com_relevancia(texto)
            if not lido["email"] or relevancia.get(lido["email"], 0) <= 0:
                continue  # só e-mail em contexto de recrutamento ("envie o CV para...")
            vaga = {"id": repositorio.gerar_id(res["link"]), "titulo": lido["titulo"] or res["titulo"][:90],
                    "empresa": lido["empresa"], "local": lido["local"], "modalidade": lido["modalidade"],
                    "link": res["link"], "site": "Post de recrutador", "origem": "post",
                    "descricao": texto, "email_destino": lido["email"], "emails_encontrados": lido["emails"]}
            if repositorio.existe_semelhante(vaga["titulo"], vaga["email_destino"], vaga["empresa"]):
                continue
            if repositorio.inserir(vaga):
                novas += 1
        time.sleep(1.1)  # sem rajada: respeita o limite por segundo dos planos
    logger.info(f"[Posts] {novas} post(s) de recrutador com e-mail na fila")
    return novas
