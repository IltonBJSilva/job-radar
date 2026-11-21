"""Orquestra o fluxo: importar -> pontuar -> preparar -> enviar."""

from __future__ import annotations

import random
import re
import threading
import time
from contextlib import nullcontext
from datetime import datetime

from candidatura import config, repositorio
from candidatura.adaptador import montar_pacote
from candidatura.compatibilidade import analisar, idioma_da_vaga
from candidatura.contato import buscar_descricao, email_valido, emails_com_relevancia, extrair_emails
from candidatura.documentos import GeradorPDF, html_carta, pasta_da_vaga, slug
from candidatura.envio import ErroConexao, ErroEnvio, ErroFatalSMTP, enviar_smtp, montar_mensagem, salvar_eml
from candidatura.perfil import Candidato, carregar_candidato
from core.logger import get_logger

logger = get_logger()

DESCRICAO_MINIMA = 300  # menos que isso é só o card do anúncio, não a vaga

# Checagem de limite/repetição + reserva da vaga acontecem sob esta trava:
# duas threads (botão "Enviar" + lote) nunca passam juntas pela checagem.
_TRAVA_ENVIO = threading.Lock()


def ja_enviada_de_verdade(vaga: dict) -> bool:
    return vaga.get("status") in ("enviada", "enviando", "respondida", "aplicada") and not (
        vaga.get("status") == "enviada" and vaga.get("simulado")
    )


# ------------------------------------------------------------- pontuação

def pontuar_novas(candidato: Candidato | None = None) -> int:
    """Calcula score/tecnologias das vagas 'nova' (rápido, sem rede)."""
    candidato = candidato or carregar_candidato()
    n = 0
    for vaga in repositorio.listar("nova", limite=5000):
        a = analisar(candidato, vaga["titulo"], vaga.get("descricao") or "")
        repositorio.atualizar(vaga["id"], score=a.score, em_comum=a.em_comum, faltando=a.faltando)
        n += 1
    return n


def importar_tudo(github: bool = True, remotar_termos: list[str] | None = None,
                  fontes: list[str] | None = None, termos: list[str] | None = None,
                  preferencias: dict | None = None) -> dict:
    """Busca vagas nas fontes escolhidas. Sem `fontes`, mantém o comportamento
    antigo (radar + GitHub + Remotar/Gupy pelos `remotar_termos`)."""
    from candidatura import fontes as coletores

    repositorio.iniciar()
    if fontes is None:
        fontes = ["radar"] + (["github"] if github else []) + (["remotar", "gupy"] if remotar_termos else [])
        termos = remotar_termos
    termos = termos or []
    resultado: dict = {}
    if "radar" in fontes:
        resultado["radar"] = repositorio.importar_do_radar()
    if "github" in fontes:
        resultado["github"] = coletores.coletar_github()
    if termos:
        if "remotar" in fontes:
            resultado["remotar"] = coletores.coletar_remotar(termos)
        if "gupy" in fontes:  # maior ATS do Brasil, com descrição completa
            resultado["gupy"] = coletores.coletar_gupy(termos)
        locais = [f for f in ("linkedin", "catho", "indeed") if f in fontes]
        if locais:
            from candidatura import areas

            resultado.update(coletores.coletar_scrapers(locais, termos, foco=areas.foco_regional(preferencias or {})))
    if "posts" in fontes:  # posts públicos de recrutador com e-mail (Brave Search; sem chave, pula)
        from candidatura import busca_posts

        resultado["posts"] = busca_posts.coletar(preferencias or {"termos_busca": termos})
    if "empresas" in fontes:  # vagas abertas direto no site/portal das empresas da lista
        from candidatura import vagas_empresas

        resultado["empresas"] = vagas_empresas.coletar(preferencias or {"termos_busca": termos})
    resultado["pontuadas"] = pontuar_novas()
    if preferencias:  # vaga boa na cidade do foco -> aviso no Telegram (se ligado)
        from candidatura import alertas

        resultado["alertas"] = alertas.avisar_vagas_boas(preferencias)
    return resultado


def importar_do_perfil(candidato: Candidato | None = None) -> dict:
    """Busca vagas com as fontes e os termos que o perfil ativo escolheu."""
    from candidatura import areas

    candidato = candidato or carregar_candidato()
    prefs = candidato.preferencias or {}
    return importar_tudo(fontes=areas.fontes(prefs), termos=areas.termos_busca(prefs), preferencias=prefs)


# --------------------------------------------------------------- preparo

def preparar(id_: str, candidato: Candidato | None = None, gerador: GeradorPDF | None = None,
             usar_ia: bool = True) -> dict:
    """Gera CV + carta (HTML e PDF) + e-mail para a vaga. Não envia nada."""
    vaga = repositorio.obter(id_)
    if not vaga:
        raise KeyError(f"Vaga {id_} não encontrada")
    if ja_enviada_de_verdade(vaga):
        raise ValueError("Vaga já enviada — não é preparada de novo (protege o histórico de envio).")

    try:
        candidato = candidato or carregar_candidato()
        descricao = vaga.get("descricao") or ""
        espontanea = vaga.get("origem") == "espontanea"
        # Espontânea: o link é o site/portal da empresa, não um anúncio de vaga.
        if len(descricao) < DESCRICAO_MINIMA and vaga.get("link") and not espontanea:
            baixada = buscar_descricao(vaga["link"])
            if len(baixada) > len(descricao):
                descricao = baixada

        emails = list(dict.fromkeys((vaga.get("emails_encontrados") or []) + extrair_emails(descricao)))
        # Espontânea: só o e-mail de recrutamento escolhido na descoberta
        # (contato@/comercial@ do site não viram destino sozinhos).
        destino = vaga.get("email_destino") or (emails[0] if emails and not espontanea else None)

        analise = analisar(candidato, vaga["titulo"], descricao)
        pacote = montar_pacote(candidato, {**vaga, "descricao": descricao}, analise, usar_ia=usar_ia)

        pasta = pasta_da_vaga(vaga)
        partes_nome = candidato.nome.split()
        nome_arquivo = " ".join([partes_nome[0], partes_nome[-1]]) if len(partes_nome) > 2 else candidato.nome
        nome = slug(nome_arquivo, 40).replace("-", "_").title() or "Candidato"
        html_ct = html_carta(candidato, pacote.carta, vaga["titulo"], vaga.get("empresa") or "", espontanea=espontanea)
        (pasta / "carta.html").write_text(html_ct, encoding="utf-8")
        (pasta / "email.txt").write_text(f"Assunto: {pacote.assunto}\n\n{pacote.corpo_email}", encoding="utf-8")

        cv_pdf = pasta / f"Curriculo_{nome}.pdf"
        carta_pdf = pasta / f"Carta_Apresentacao_{nome}.pdf"
        with (nullcontext(gerador) if gerador else GeradorPDF()) as g:
            html_cv, paginas = g.gerar_curriculo(pacote.curriculo, cv_pdf)  # sempre 2 páginas (ajusta o layout)
            g.gerar(html_ct, carta_pdf)
        (pasta / "curriculo.html").write_text(html_cv, encoding="utf-8")
        if paginas != 2:
            logger.warning(f"[Candidatura] Currículo saiu com {paginas} página(s) (o alvo é 2): {vaga['titulo']}")

        status = "pronta" if destino and email_valido(destino) else "manual"
        aviso = None
        if not espontanea and idioma_da_vaga(descricao) == "en":
            # CV/carta saem em português: enviar sem revisão eliminaria a candidatura.
            status, aviso = "manual", "Vaga em inglês: revise e traduza CV/carta antes de enviar."
        # Você pode ter desfeito/descartado enquanto o PDF era gerado: nesse
        # caso os arquivos ficam salvos, mas a vaga NÃO entra na fila de envio.
        agora = repositorio.obter(id_) or {}
        atual = agora.get("status")
        if atual in ("nova", "descartada", "enviada", "enviando", "respondida", "aplicada"):
            status = atual
        # E-mail editado por você durante o preparo vence o encontrado.
        if agora.get("email_destino") and agora.get("email_destino") != vaga.get("email_destino"):
            destino = agora["email_destino"]
            if not aviso:
                status = "pronta" if status in ("pronta", "manual") and email_valido(destino) else status
        repositorio.atualizar(
            id_,
            descricao=descricao,
            emails_encontrados=emails,
            email_destino=destino,
            score=None if espontanea else analise.score,
            em_comum=analise.em_comum,
            faltando=analise.faltando,
            assunto=pacote.assunto,
            corpo=pacote.corpo_email,
            carta=pacote.carta,
            cv_path=str(cv_pdf),
            carta_path=str(carta_pdf),
            status=status,
            erro=aviso,
        )
        logger.info(f"[Candidatura] Preparada ({status}, {analise.score}%): {vaga['titulo']} — {vaga.get('empresa')}")
    except Exception as e:
        atual = (repositorio.obter(id_) or {}).get("status")
        if atual not in ("nova", "descartada", "enviada", "enviando", "respondida", "aplicada"):
            repositorio.atualizar(id_, status="erro", erro=f"preparo: {e}", cv_path=None, carta_path=None)
        logger.error(f"[Candidatura] Erro ao preparar {id_}: {e}")
        raise
    return repositorio.obter(id_)


def preparar_lote(ids: list[str], usar_ia: bool = True) -> dict:
    candidato = carregar_candidato()
    ok, falhas = 0, 0
    with GeradorPDF() as g:
        for id_ in ids:
            try:
                preparar(id_, candidato, g, usar_ia)
                ok += 1
            except Exception:
                falhas += 1
    return {"preparadas": ok, "falhas": falhas}


# ----------------------------------------------------------------- envio

def motivo_bloqueio(vaga: dict, real: bool) -> str | None:
    simulada = vaga["status"] == "enviada" and vaga.get("simulado")
    if vaga["status"] != "pronta" and not (real and simulada):
        return f"status '{vaga['status']}' (precisa estar 'pronta'; após erro, refaça o preparo)"
    destino = vaga.get("email_destino")
    if not destino or not email_valido(destino):
        return "sem e-mail de destino válido"
    if not vaga.get("cv_path"):
        return "currículo ainda não gerado"
    if real:
        if repositorio.enviadas_hoje() >= config.LIMITE_DIARIO:
            return f"limite diário atingido ({config.LIMITE_DIARIO})"
        if repositorio.ja_contatado(destino, vaga.get("empresa") or "", config.DIAS_SEM_REPETIR_EMPRESA, vaga["id"]):
            return f"já enviado para este e-mail/empresa nos últimos {config.DIAS_SEM_REPETIR_EMPRESA} dias"
    return None


def enviar(id_: str, real: bool | None = None, candidato: Candidato | None = None) -> dict:
    real = config.ENVIO_REAL if real is None else real
    vaga = repositorio.obter(id_)
    if not vaga:
        raise KeyError(id_)
    # Tudo que pode falhar ANTES da reserva — nada fica preso em 'enviando'.
    candidato = candidato or carregar_candidato()
    with _TRAVA_ENVIO:
        vaga = repositorio.obter(id_)
        bloqueio = motivo_bloqueio(vaga, real)
        if bloqueio:
            raise ErroEnvio(bloqueio)
        recusa = repositorio.reservar_para_envio(
            id_, real, vaga.get("email_destino") or "", vaga.get("empresa") or "",
            config.DIAS_SEM_REPETIR_EMPRESA, config.LIMITE_DIARIO,
        )
        if recusa:
            raise ErroEnvio(recusa)

    remetente = config.SMTP_USUARIO or candidato.email
    anexos = [p for p in (vaga.get("cv_path"), vaga.get("carta_path")) if p]
    try:
        if real and vaga_encerrada(vaga):
            repositorio.atualizar(id_, status="encerrada", erro="A vaga foi fechada antes do envio.")
            raise VagaEncerrada("a vaga foi encerrada na fonte (anúncio removido ou fechado) — não enviei")
        msg = montar_mensagem(candidato.nome, remetente, vaga["email_destino"], vaga["assunto"] or "",
                              vaga["corpo"] or "", anexos, responder_para=candidato.email)
        if real:
            enviar_smtp(msg)
        else:
            from pathlib import Path

            salvar_eml(msg, Path(vaga["cv_path"]).parent)
    except VagaEncerrada:
        raise
    except ErroEnvio as e:
        dica = " (pode ter saído antes da queda — confira sua caixa de Enviados antes de reenviar)" \
            if isinstance(e, ErroConexao) else ""
        repositorio.atualizar(id_, status="erro", erro=f"envio: {e}{dica}")
        raise
    except BaseException as e:  # inclui Ctrl+C: a vaga nunca fica presa em 'enviando'
        repositorio.atualizar(id_, status="erro", erro=f"envio: {e!r}")
        if isinstance(e, Exception):
            raise ErroEnvio(str(e)) from e
        raise

    repositorio.atualizar(id_, status="enviada", simulado=0 if real else 1, message_id=msg["Message-ID"],
                          enviada_em=datetime.now().isoformat(timespec="seconds"), erro=None)
    logger.info(f"[Candidatura] {'ENVIADA' if real else 'Simulada'}: {vaga['titulo']} -> {vaga['email_destino']}")
    return repositorio.obter(id_)


class VagaEncerrada(ErroEnvio):
    pass


def _esperar_intervalo_anti_spam(real: bool) -> None:
    """Garante um intervalo aleatório desde o último envio real (curtidas seguidas)."""
    if not real:
        return
    ultimas = repositorio.listar("enviada", limite=1, ordem="enviada_em DESC")
    ultimo = next((v.get("enviada_em") for v in ultimas if not v.get("simulado")), None)
    if not ultimo:
        return
    passado = (datetime.now() - datetime.fromisoformat(ultimo)).total_seconds()
    espera = random.uniform(config.INTERVALO_MIN_SEG, config.INTERVALO_MAX_SEG) - passado
    if espera > 0:
        logger.info(f"[Candidatura] Aguardando {espera:.0f}s antes do próximo envio (anti-spam)")
        time.sleep(espera)


def preparar_e_enviar(id_: str, real: bool | None = None) -> dict:
    """Coração com ENVIAR_AO_CURTIR: prepara e, se a vaga tiver e-mail, envia."""
    real = config.ENVIO_REAL if real is None else real
    vaga = preparar(id_)
    if not vaga or vaga["status"] != "pronta":
        logger.info(f"[Candidatura] Não enviada automaticamente ({(vaga or {}).get('status')}): {id_}")
        return vaga
    _esperar_intervalo_anti_spam(real)
    if (repositorio.obter(id_) or {}).get("status") != "pronta":  # desfeita durante a espera
        return repositorio.obter(id_)
    return enviar(id_, real=real)


_TEXTO_ENCERRADA = re.compile(
    r"vaga encerrada|inscri[cç][oõ]es encerradas|n[aã]o est[aá] mais dispon[ií]vel|vaga n[aã]o encontrada|"
    r"no longer accepting applications|n[aã]o aceita mais candidaturas|this job is no longer|job (?:is )?closed|"
    r"position has been filled|vaga (?:foi )?preenchida",
    re.I,
)


def _gupy_encerrada(r) -> bool:
    """Gupy: o texto "Inscrições encerradas" está em TODA página (traduções da interface), então
    olhamos os dados da vaga: status diferente de "published", prazo vencido, ou id inexistente
    (redireciona para o login)."""
    import json
    from datetime import datetime, timezone

    if r.status_code in (404, 410) or "/jobs/" not in (getattr(r, "url", "") or "/jobs/"):
        return True
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text or "", re.S)
    if r.status_code != 200 or not m:
        return False
    job = ((json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}).get("job") or {}
    if not job:
        return False
    if job.get("status") and job["status"] != "published":
        return True
    for campo in ("expiresAt", "registerEndDate"):
        try:
            if job.get(campo) and datetime.fromisoformat(job[campo].replace("Z", "+00:00")) < datetime.now(timezone.utc):
                return True
        except (ValueError, AttributeError):
            pass
    return False


def vaga_encerrada(vaga: dict, sessao=None) -> bool:
    """A vaga fechou? Confere na fonte antes de enviar: issue do GitHub fechada,
    vaga removida no Gupy/Greenhouse/Lever (404) ou anúncio dizendo "encerrada"
    (Gupy, LinkedIn). Erro de rede ou página diferente = considera ABERTA."""
    import requests

    http = sessao or requests
    link = vaga.get("link") or ""
    ua = {"User-Agent": "Mozilla/5.0 (job-radar)"}
    try:
        m = re.match(r"https://github\.com/([^/]+/[^/]+)/issues/(\d+)", link)
        if m:
            r = http.get(f"https://api.github.com/repos/{m.group(1)}/issues/{m.group(2)}",
                         headers={"User-Agent": "job-radar-candidatura"}, timeout=10)
            return r.status_code == 200 and r.json().get("state") == "closed"
        m = re.search(r"(?:boards|job-boards)\.greenhouse\.io/([\w-]+)/jobs/(\d+)", link)
        if m:
            r = http.get(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}", headers=ua, timeout=10)
            return r.status_code == 404
        m = re.search(r"jobs\.lever\.co/([\w-]+)/([0-9a-f-]{20,})", link)
        if m:
            r = http.get(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}", headers=ua, timeout=10)
            return r.status_code == 404
        m = re.search(r"linkedin\.com/jobs/view/(?:[\w-]*-)?(\d{6,})", link)
        if m:
            r = http.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}", headers=ua, timeout=10)
            return r.status_code == 200 and bool(_TEXTO_ENCERRADA.search(r.text))
        if re.search(r"\.gupy\.io/(?:jobs|job)/", link):
            return _gupy_encerrada(http.get(link, headers=ua, timeout=10))
    except Exception:  # noqa: BLE001 — na dúvida, a vaga está aberta
        return False
    return False


def enviar_lote(limite: int = 10, real: bool | None = None, ids: list[str] | None = None,
                ao_progredir=None) -> dict:
    real = config.ENVIO_REAL if real is None else real
    candidato = carregar_candidato()
    if ids is not None and not ids:
        raise ValueError("Lista de ids vazia — nada a enviar.")
    if ids:
        fila = [repositorio.obter(i) for i in ids]
    else:
        # Envio real também pega o que você revisou em modo simulação.
        fila = repositorio.listar("pronta") + (
            [v for v in repositorio.listar("enviada", limite=1000) if v.get("simulado")] if real else []
        )
    resultado = {"enviadas": 0, "puladas": [], "erros": [], "real": real}
    falhas_conexao_seguidas = 0
    houve_envio_real = False
    for vaga in (f for f in fila if f):
        if resultado["enviadas"] >= limite:
            break
        bloqueio = motivo_bloqueio(vaga, real)
        if bloqueio:
            resultado["puladas"].append((vaga["titulo"], bloqueio))
            if "limite diário" in bloqueio:
                break
            continue
        # Intervalo aleatório ANTES do próximo envio real (nunca depois do
        # último): e-mails em rajada parecem spam.
        if real and houve_envio_real:
            time.sleep(random.uniform(config.INTERVALO_MIN_SEG, config.INTERVALO_MAX_SEG))
        try:
            enviar(vaga["id"], real=real, candidato=candidato)
            resultado["enviadas"] += 1
            falhas_conexao_seguidas = 0
            if ao_progredir:
                ao_progredir(vaga, resultado)
        except ErroFatalSMTP as e:
            resultado["erros"].append((vaga["titulo"], str(e)))
            break
        except ErroConexao as e:
            resultado["erros"].append((vaga["titulo"], str(e)))
            falhas_conexao_seguidas += 1
            if falhas_conexao_seguidas >= 2:
                break
            continue
        except ErroEnvio as e:
            resultado["erros"].append((vaga["titulo"], str(e)))
            continue
        finally:
            houve_envio_real = houve_envio_real or real
    return resultado


# ----------------------------------------------------------- enriquecer

def enriquecer(score_minimo: int = 40, limite: int = 40, candidato: Candidato | None = None) -> int:
    """Baixa a descrição completa das vagas promissoras que só têm o card
    (típico do radar) para achar e-mail e recalcular o score com precisão."""
    candidato = candidato or carregar_candidato()
    alvo = [
        v for v in repositorio.listar("nova", limite=5000)
        if not v.get("email_destino") and len(v.get("descricao") or "") < DESCRICAO_MINIMA
        and (v.get("score") or 0) >= score_minimo and v.get("link")
    ][:limite]
    baixadas = 0
    for v in alvo:
        descricao = buscar_descricao(v["link"])
        if len(descricao) <= len(v.get("descricao") or ""):
            continue
        baixadas += 1
        emails = extrair_emails(descricao)
        a = analisar(candidato, v["titulo"], descricao)
        repositorio.atualizar(
            v["id"], descricao=descricao, emails_encontrados=emails,
            email_destino=emails[0] if emails else None,
            score=a.score, em_comum=a.em_comum, faltando=a.faltando,
        )
        time.sleep(random.uniform(1.0, 2.5))  # educado com os sites
    return baixadas


# ------------------------------------------------------- modo automático

def dominio_da_empresa(email: str, empresa: str) -> bool:
    """'jobs@milkboxmail.com' + 'MilkBox' -> True; 'fulano@gmail.com' -> False."""
    import re

    from candidatura.compatibilidade import normalizar

    dominio = normalizar(email.rsplit("@", 1)[-1]).replace("-", "")
    palavras = [p for p in re.findall(r"[a-z0-9]+", normalizar(empresa)) if len(p) >= 4]
    junto = "".join(re.findall(r"[a-z0-9]+", normalizar(empresa)))
    return bool(palavras or junto) and (
        (len(junto) >= 4 and junto in dominio) or any(p in dominio for p in palavras)
    )


def auto(score_minimo: int | None = None, limite: int = 10, real: bool | None = None,
         usar_ia: bool = True, remotar_termos: list[str] | None = None) -> dict:
    """Sem swipe: importa, escolhe as vagas mais compatíveis QUE TÊM e-mail,
    prepara e envia. Vagas sem e-mail ficam como estão para o swipe."""
    score_minimo = config.SCORE_MINIMO_AUTO if score_minimo is None else score_minimo
    importacao = importar_tudo(remotar_termos=remotar_termos) if remotar_termos else importar_do_perfil()
    enriquecer(score_minimo=max(0, score_minimo - 15))
    def email_de_recrutamento(v: dict) -> bool:
        # Sem revisão humana, só envia para e-mail que (1) aparece em contexto
        # de candidatura (currículo/vagas/rh...) e (2) é do domínio da empresa.
        # Qualquer um pode abrir uma issue de "vaga" com um e-mail pessoal: sem
        # a checagem de domínio, seu CV iria automaticamente para essa pessoa.
        email = (v.get("email_destino") or "").lower()
        relevante = emails_com_relevancia(v.get("descricao") or "").get(email, 0) > 0
        return relevante and dominio_da_empresa(email, v.get("empresa") or "")

    candidatas = [
        v for v in repositorio.listar("nova", limite=5000)
        if (v.get("score") or 0) >= score_minimo and v.get("email_destino") and email_de_recrutamento(v)
    ][: limite * 2]
    for v in candidatas:
        repositorio.atualizar(v["id"], status="curtida")
    if not candidatas:
        vazio = {"enviadas": 0, "puladas": [], "erros": [], "real": real}
        return {"importacao": importacao, "selecionadas": 0, "preparo": {"preparadas": 0, "falhas": 0}, "envio": vazio}
    preparo = preparar_lote([v["id"] for v in candidatas], usar_ia=usar_ia)
    envio = enviar_lote(limite=limite, real=real, ids=[v["id"] for v in candidatas])
    return {"importacao": importacao, "selecionadas": len(candidatas), "preparo": preparo, "envio": envio}
