"""Interface local estilo Tinder para decidir vagas e disparar candidaturas.

    python candidatar.py app      ->  http://127.0.0.1:5000

Roda só na sua máquina (127.0.0.1). Preparação de PDF e envio em lote
rodam numa thread de trabalho para a tela nunca travar.
"""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

from candidatura import config, repositorio, servico
from candidatura.contato import email_valido, extrair_emails
from candidatura.compatibilidade import analisar
from candidatura.perfil import PerfilInvalido, PerfilNaoEncontrado, carregar_candidato
from core.logger import get_logger

logger = get_logger()


# ------------------------------------------------------------ trabalhador

class Trabalhador:
    """Fila única de tarefas pesadas (PDF via Chromium, envio SMTP)."""

    def __init__(self):
        self.fila: queue.Queue = queue.Queue()
        self.estado = {"ocupado": False, "mensagem": "", "ultimo_erro": ""}
        threading.Thread(target=self._loop, daemon=True).start()

    def agendar(self, descricao: str, funcao, *args, **kwargs):
        self.fila.put((descricao, funcao, args, kwargs))

    def _loop(self):
        while True:
            descricao, funcao, args, kwargs = self.fila.get()
            self.estado.update(ocupado=True, mensagem=descricao)
            try:
                funcao(*args, **kwargs)
                self.estado["ultimo_erro"] = ""
            except Exception as e:
                self.estado["ultimo_erro"] = f"{descricao}: {e}"
                logger.error(traceback.format_exc())
            finally:
                self.estado.update(ocupado=not self.fila.empty(), mensagem="")


HOSTS_LOCAIS = {"127.0.0.1", "localhost"}


def link_seguro(url: str | None) -> str:
    """Só http(s): bloqueia `javascript:` vindo de fonte externa."""
    url = (url or "").strip()
    return url if urlparse(url).scheme in ("http", "https") else ""


def criar_app() -> Flask:
    app = Flask(__name__)
    app.jinja_env.filters["link_seguro"] = link_seguro
    repositorio.iniciar()
    repositorio.liberar_envios_interrompidos()

    @app.before_request
    def bloquear_outros_sites():
        """Proteção contra outros sites abertos no navegador.

        1. DNS rebinding: um domínio do atacante pode apontar para 127.0.0.1;
           o navegador então manda `Host: atacante.com`. Por isso TODA
           requisição (inclusive GET, que lê seu CV) exige Host local.
        2. CSRF: POST só vale se Origin/Referer for este próprio app."""
        if (urlparse(f"//{request.host}").hostname or "") not in HOSTS_LOCAIS:
            abort(403)
        if request.method != "POST":
            return None
        origem = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if not origem or urlparse(origem).netloc != request.host:
            abort(403)
        if request.path.startswith("/api/") and not request.is_json:
            abort(415)
        return None
    trabalhador = Trabalhador()

    # Vagas curtidas que não terminaram de preparar (app fechado no meio).
    for pendente in repositorio.listar("curtida", limite=500):
        trabalhador.agendar(f"Preparando {pendente['titulo'][:40]}", servico.preparar, pendente["id"])

    erro_perfil = {"msg": ""}

    def candidato_ou_none():
        try:
            erro_perfil["msg"] = ""
            return carregar_candidato()
        except PerfilNaoEncontrado:
            return None
        except PerfilInvalido as e:
            erro_perfil["msg"] = str(e)
            return None

    def cartao(v: dict | None) -> dict | None:
        if not v:
            return None
        desc = (v.get("descricao") or "").strip()
        return {
            "id": v["id"], "titulo": v["titulo"], "empresa": v.get("empresa") or "",
            "local": v.get("local") or "", "modalidade": v.get("modalidade") or "",
            "site": v.get("site") or "", "link": link_seguro(v.get("link")),
            "publicado_em": v.get("publicado_em") or "", "score": v.get("score") or 0,
            "em_comum": v.get("em_comum") or [], "faltando": v.get("faltando") or [],
            "email": v.get("email_destino") or "",
            "descricao": desc[:1800] + ("…" if len(desc) > 1800 else ""),
        }

    def proximas(n: int = 3, filtro: str = "") -> list[dict]:
        vagas = repositorio.listar("nova", limite=400)
        if filtro == "email":
            vagas = [v for v in vagas if v.get("email_destino")]
        return [cartao(v) for v in vagas[:n]]

    @app.context_processor
    def globais():
        return {"envio_real": config.ENVIO_REAL, "contagem": repositorio.contagem_por_status()}

    # ------------------------------------------------------------ páginas

    @app.get("/")
    def swipe():
        if not candidato_ou_none():
            return render_template("configurar.html", exemplo=config.PERFIL_EXEMPLO_PATH, destino=config.PERFIL_PATH,
                                   erro=erro_perfil["msg"])
        return render_template("swipe.html")

    @app.get("/fila")
    def fila():
        aba = request.args.get("aba", "pronta")
        grupos = {
            "pronta": ["pronta", "curtida"],
            "manual": ["manual"],
            "enviada": ["enviada"],
            "respondida": ["respondida"],
            "erro": ["erro"],
            "descartada": ["descartada"],
        }
        vagas = repositorio.listar(grupos.get(aba, ["pronta"]), limite=500,
                                   ordem="enviada_em DESC, score DESC" if aba == "enviada" else "score DESC, criada_em DESC")
        return render_template("fila.html", vagas=vagas, aba=aba, metricas=repositorio.metricas(),
                               limite=config.LIMITE_DIARIO)

    @app.get("/vaga/<id_>")
    def detalhe(id_):
        v = repositorio.obter(id_) or abort(404)
        return render_template("detalhe.html", v=v)

    @app.post("/vaga/<id_>")
    def salvar_detalhe(id_):
        v = repositorio.obter(id_) or abort(404)
        email = (request.form.get("email_destino") or "").strip() or None
        campos = {
            "email_destino": email,
            "assunto": request.form.get("assunto", v.get("assunto")),
            "corpo": request.form.get("corpo", v.get("corpo")),
        }
        if v["status"] in ("manual", "pronta") and v.get("cv_path"):
            campos["status"] = "pronta" if email and email_valido(email) else "manual"
        repositorio.atualizar(id_, **campos)
        return redirect(url_for("detalhe", id_=id_))

    @app.get("/arquivo/<id_>/<tipo>")
    def arquivo(id_, tipo):
        v = repositorio.obter(id_) or abort(404)
        caminho = v.get("cv_path") if tipo == "cv" else v.get("carta_path")
        if not caminho or not Path(caminho).exists():
            abort(404)
        return send_file(caminho, mimetype="application/pdf")

    @app.route("/nova", methods=["GET", "POST"])
    def nova():
        if request.method == "GET":
            return render_template("nova.html")
        f = request.form
        descricao = f.get("descricao", "")
        emails = extrair_emails(descricao)
        email = (f.get("email") or "").strip() or (emails[0] if emails else None)
        vaga = {
            "id": repositorio.gerar_id(f.get("link", ""), f.get("titulo", ""), f.get("empresa", "")),
            "titulo": f.get("titulo", "").strip() or "Vaga sem título",
            "empresa": f.get("empresa", "").strip(),
            "link": f.get("link", "").strip(),
            "local": f.get("local", "").strip(),
            "site": "Manual",
            "origem": "manual",
            "descricao": descricao,
            "email_destino": email,
            "emails_encontrados": emails,
            "status": "curtida",
        }
        if not repositorio.inserir(vaga):
            # Já estava na fila (ex.: veio do radar): completa com o que você colou.
            existente = repositorio.obter(vaga["id"])
            if servico.ja_enviada_de_verdade(existente):
                return redirect(url_for("detalhe", id_=vaga["id"]))
            repositorio.atualizar(vaga["id"], **{k: v for k, v in vaga.items()
                                                 if k not in ("id", "site", "origem") and v})
        trabalhador.agendar(f"Preparando {vaga['titulo']}", servico.preparar, vaga["id"])
        return redirect(url_for("fila", aba="pronta"))

    # ---------------------------------------------------------------- API

    @app.get("/api/proximas")
    def api_proximas():
        return jsonify(proximas(int(request.args.get("n", 3)), request.args.get("filtro", "")))

    @app.post("/api/decidir/<id_>")
    def api_decidir(id_):
        acao = (request.get_json(silent=True) or {}).get("acao")
        if acao == "curtir":
            repositorio.atualizar(id_, status="curtida")
            trabalhador.agendar("Preparando currículo", servico.preparar, id_)
        elif acao == "descartar":
            repositorio.atualizar(id_, status="descartada")
        elif acao == "desfazer":
            v = repositorio.obter(id_) or abort(404)
            if v["status"] not in ("descartada", "curtida", "pronta", "manual", "erro"):
                return jsonify({"ok": False, "erro": "Essa vaga já foi enviada."}), 400
            repositorio.atualizar(id_, status="nova")
        else:
            abort(400)
        return jsonify({"ok": True, "contagem": repositorio.contagem_por_status()})

    @app.post("/api/preparar/<id_>")
    def api_preparar(id_):
        v = repositorio.obter(id_) or abort(404)
        if v["status"] == "enviada":
            return jsonify({"ok": False, "erro": "Vaga já enviada."}), 400
        repositorio.atualizar(id_, status="curtida")
        trabalhador.agendar("Preparando currículo", servico.preparar, id_)
        return jsonify({"ok": True})

    @app.post("/api/enviar/<id_>")
    def api_enviar(id_):
        try:
            v = servico.enviar(id_)
            return jsonify({"ok": True, "simulado": bool(v["simulado"])})
        except Exception as e:
            return jsonify({"ok": False, "erro": str(e)}), 400

    @app.post("/api/enviar-lote")
    def api_enviar_lote():
        limite = int((request.get_json(silent=True) or {}).get("limite", 10))
        trabalhador.agendar(f"Enviando até {limite} candidaturas", servico.enviar_lote, limite)
        return jsonify({"ok": True})

    @app.post("/api/importar")
    def api_importar():
        prefs = (candidato_ou_none().preferencias if candidato_ou_none() else {}) or {}
        termos = prefs.get("termos_remotar") or ["python", "backend", "node"]
        trabalhador.agendar("Buscando vagas (radar + GitHub + Remotar)", servico.importar_tudo, remotar_termos=termos)
        return jsonify({"ok": True})

    @app.post("/api/enriquecer")
    def api_enriquecer():
        trabalhador.agendar("Baixando descrições e procurando e-mails", servico.enriquecer)
        return jsonify({"ok": True})

    @app.get("/api/estado")
    def api_estado():
        return jsonify({**trabalhador.estado, "pendentes": trabalhador.fila.qsize(),
                        "contagem": repositorio.contagem_por_status()})

    @app.post("/api/reanalisar/<id_>")
    def api_reanalisar(id_):
        v = repositorio.obter(id_) or abort(404)
        a = analisar(carregar_candidato(), v["titulo"], v.get("descricao") or "")
        repositorio.atualizar(id_, score=a.score, em_comum=a.em_comum, faltando=a.faltando)
        return jsonify({"score": a.score})

    return app
