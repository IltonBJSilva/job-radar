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

from candidatura import config, empresas, importar_perfil, repositorio, servico
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


def config_github_token() -> str:
    import os

    return os.getenv("GITHUB_TOKEN", "")


def link_seguro(url: str | None) -> str:
    """Só http(s): bloqueia `javascript:` vindo de fonte externa."""
    url = (url or "").strip()
    return url if urlparse(url).scheme in ("http", "https") else ""


def criar_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # upload do currículo
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
        if filtro == "email":
            vagas = [v for v in repositorio.listar("nova", limite=10000) if v.get("email_destino")]
        else:
            vagas = repositorio.listar("nova", limite=max(n, 1))
        return [cartao(v) for v in vagas[:n]]

    def inteiro(valor, padrao: int, minimo: int = 1, maximo: int = 500) -> int:
        try:
            return max(minimo, min(maximo, int(valor)))
        except (TypeError, ValueError):
            return padrao

    rotulos = {
        "nova": "Nova — ainda não avaliada", "descartada": "Descartada", "curtida": "Preparando currículo…",
        "pronta": "Pronta para enviar", "manual": "Sem e-mail — candidate-se pelo site com o PDF",
        "enviando": "Enviando…", "erro": "Erro — veja a mensagem abaixo", "respondida": "A empresa respondeu!",
        "encerrada": "Vaga encerrada",
    }

    def rotulo_status(status: str, simulado: int = 0) -> str:
        if status == "enviada":
            return "Simulada (.eml gerado — pode ser enviada de verdade)" if simulado else "Enviada"
        return rotulos.get(status, status)

    @app.context_processor
    def globais():
        return {"envio_real": config.ENVIO_REAL, "contagem": repositorio.contagem_por_status(),
                "rotulo_status": rotulo_status}

    # ------------------------------------------------------------ páginas

    @app.get("/")
    def swipe():
        c = candidato_ou_none()
        if not c and erro_perfil["msg"]:
            return render_template("configurar.html", exemplo=config.PERFIL_EXEMPLO_PATH, destino=config.PERFIL_PATH,
                                   erro=erro_perfil["msg"])
        if not c or c.email == importar_perfil.EXEMPLO_EMAIL:
            return redirect(url_for("perfil"))  # cadastro único antes de tudo
        return render_template("swipe.html")

    # ------------------------------------------------ cadastro único

    def _yaml_atual() -> str:
        try:
            return config.PERFIL_PATH.read_text(encoding="utf-8")
        except OSError:
            return ""

    @app.route("/perfil", methods=["GET", "POST"])
    def perfil():
        import yaml

        aviso, avisos, texto_yaml = "", [], _yaml_atual()
        if request.method == "POST" and request.form.get("acao") == "salvar":
            texto_yaml = request.form.get("yaml", "")
            try:
                dados = yaml.safe_load(texto_yaml) or {}
                if not isinstance(dados, dict):
                    raise ValueError("o perfil precisa ser um mapa (pessoal:, habilidades:, ...)")
                from candidatura.perfil import candidato_de_dict

                c = candidato_de_dict(dados)
                if not c.nome or not c.email or not email_valido(c.email) or c.email == importar_perfil.EXEMPLO_EMAIL:
                    raise ValueError("preencha seu nome e seu e-mail real em pessoal:")
            except (yaml.YAMLError, ValueError) as e:
                return render_template("perfil.html", yaml=texto_yaml, aviso=f"Não salvei: {e}", avisos=[], gerado=True)
            config.PERFIL_PATH.parent.mkdir(parents=True, exist_ok=True)
            if config.PERFIL_PATH.exists():
                config.PERFIL_PATH.with_suffix(".yaml.bak").write_text(_yaml_atual(), encoding="utf-8")
            config.PERFIL_PATH.write_text(texto_yaml, encoding="utf-8")
            termos = (c.preferencias or {}).get("termos_remotar") or ["python", "backend", "node"]
            trabalhador.agendar("Buscando vagas para o seu perfil", servico.importar_tudo, remotar_termos=termos)
            trabalhador.agendar("Recalculando compatibilidade", servico.pontuar_novas)
            return redirect(url_for("swipe"))

        if request.method == "POST":  # acao == gerar
            arquivos = [f for f in (request.files.get("cv"), request.files.get("linkedin_pdf")) if f and f.filename]
            textos = [request.form.get("texto", "")]
            try:
                for f in arquivos:
                    textos.append(importar_perfil.texto_de_arquivo(f.filename, f.read()))
                base = yaml.safe_load(_yaml_atual()) if _yaml_atual() else {}
                gerado = importar_perfil.montar_perfil(
                    texto_cv="\n\n".join(t for t in textos if t.strip()),
                    github=request.form.get("github", ""), linkedin_url=request.form.get("linkedin", ""),
                    portfolio_url=request.form.get("portfolio", ""),
                    base=base if isinstance(base, dict) else {}, token_github=config_github_token(),
                )
            except (importar_perfil.ErroImportacao, yaml.YAMLError) as e:
                return render_template("perfil.html", yaml=texto_yaml, aviso=str(e), avisos=[], gerado=False)
            avisos = importar_perfil.faltando_no_perfil(gerado)
            return render_template("perfil.html", yaml=importar_perfil.perfil_para_yaml(gerado), gerado=True,
                                   aviso="Confira e corrija abaixo antes de salvar.", avisos=avisos)
        exemplo = (c := candidato_ou_none()) is None or c.email == importar_perfil.EXEMPLO_EMAIL
        return render_template("perfil.html", yaml=texto_yaml, aviso=aviso, avisos=avisos, gerado=False,
                               primeira_vez=exemplo)

    # ------------------------------------------- candidatura espontânea

    @app.get("/empresas")
    def pagina_empresas():
        empresas.sincronizar_lista()
        linhas = empresas.listar()
        return render_template("empresas.html", empresas=linhas, aviso=request.args.get("aviso", ""),
                               com_email=sum(1 for e in linhas if e.get("email")),
                               limite=config.LIMITE_DIARIO)

    @app.post("/empresas")
    def adicionar_empresa():
        try:
            empresas.adicionar(request.form.get("nome", ""), request.form.get("site", ""),
                               request.form.get("email", ""), request.form.get("tipo", ""))
        except ValueError as e:
            return redirect(url_for("pagina_empresas", aviso=str(e)))
        return redirect(url_for("pagina_empresas", aviso="Empresa adicionada."))

    @app.post("/api/empresas/descobrir")
    def api_descobrir():
        todas = bool((request.get_json(silent=True) or {}).get("todas"))
        trabalhador.agendar("Procurando e-mails de RH nos sites das empresas", empresas.descobrir_todas,
                            apenas_pendentes=not todas)
        return jsonify({"ok": True})

    @app.post("/api/empresas/preparar")
    def api_preparar_empresas():
        dominios = (request.get_json(silent=True) or {}).get("dominios")
        if dominios is not None and not isinstance(dominios, list):
            abort(400)

        def tarefa():
            ids = empresas.criar_candidaturas(dominios)
            if ids:
                servico.preparar_lote(ids)

        trabalhador.agendar("Preparando candidaturas espontâneas", tarefa)
        return jsonify({"ok": True})

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
        return render_template("detalhe.html", v=v, aviso=request.args.get("aviso", ""))

    @app.post("/vaga/<id_>")
    def salvar_detalhe(id_):
        v = repositorio.obter(id_) or abort(404)
        email = (request.form.get("email_destino") or "").strip() or None
        campos = {
            "email_destino": email,
            "assunto": request.form.get("assunto", v.get("assunto")),
            "corpo": request.form.get("corpo", v.get("corpo")),
        }
        if email and not email_valido(email):
            # Não grava e-mail inválido (a vaga sumiria das "Prontas" em silêncio).
            return redirect(url_for("detalhe", id_=id_, aviso=f"E-mail inválido ou não aceito: {email}"))
        if v["status"] in ("manual", "pronta") and v.get("cv_path"):
            campos["status"] = "pronta" if email and not (v.get("erro") or "").startswith("Vaga em inglês") else "manual"
        repositorio.atualizar(id_, **campos)
        return redirect(url_for("detalhe", id_=id_, aviso="Salvo."))

    @app.get("/arquivo/<id_>/<tipo>")
    def arquivo(id_, tipo):
        if tipo not in ("cv", "carta"):
            abort(404)
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
        return jsonify(proximas(inteiro(request.args.get("n"), 3, maximo=50), request.args.get("filtro", "")))

    @app.post("/api/decidir/<id_>")
    def api_decidir(id_):
        acao = (request.get_json(silent=True) or {}).get("acao")
        if acao in ("curtir", "descartar"):
            v = repositorio.obter(id_) or abort(404)
            if v["status"] not in ("nova", "descartada", "curtida", "manual", "pronta", "erro"):
                return jsonify({"ok": False, "erro": "Essa vaga já foi enviada."}), 400
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
        limite = inteiro((request.get_json(silent=True) or {}).get("limite"), 10, maximo=config.LIMITE_DIARIO)
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
