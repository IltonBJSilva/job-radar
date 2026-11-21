"""Interface local estilo Tinder para decidir vagas e disparar candidaturas.

    python candidatar.py app      ->  http://127.0.0.1:5000

Roda só na sua máquina (127.0.0.1). Preparação de PDF e envio em lote
rodam numa thread de trabalho para a tela nunca travar.
"""

from __future__ import annotations

import queue
import threading
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

from candidatura import config, empresas, importar_perfil, localizacao, repositorio, servico
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

    def retomar_curtidas():
        """Vagas curtidas que não terminaram (app fechado ou perfil trocado no meio).
        Com o coração configurado para enviar, retomam o ENVIO — não só o preparo."""
        tarefa = servico.preparar_e_enviar if config.ENVIAR_AO_CURTIR else servico.preparar
        for pendente in repositorio.listar("curtida", limite=500):
            trabalhador.agendar(f"Preparando {pendente['titulo'][:40]}", tarefa, pendente["id"])

    retomar_curtidas()

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

    cache_classificacao: dict[tuple, localizacao.Classificacao] = {}

    def classificada(v: dict) -> localizacao.Classificacao:
        chave = (v["id"], v.get("atualizada_em"))
        if chave not in cache_classificacao:
            if len(cache_classificacao) > 50000:
                cache_classificacao.clear()
            cache_classificacao[chave] = localizacao.classificar(v)
        return cache_classificacao[chave]

    def foco_atual() -> dict | None:
        from candidatura import areas

        c = candidato_ou_none()
        return areas.foco_regional((c.preferencias or {}) if c else {})

    def no_foco(c: localizacao.Classificacao, foco: dict | None) -> bool:
        return bool(foco) and localizacao.normalizar(c.cidade) == localizacao.normalizar(foco["cidade"]) and (
            not foco.get("uf") or c.uf == foco["uf"])

    def filtradas(filtros: localizacao.Filtros) -> list[tuple[dict, localizacao.Classificacao]]:
        lista = [(v, c) for v in repositorio.listar("nova", limite=100000)
                 for c in [classificada(v)] if filtros.aceita(v, c)]
        foco = foco_atual()
        if foco:  # foco regional ligado: vagas da cidade primeiro (já vêm por nota dentro de cada grupo)
            lista.sort(key=lambda par: not no_foco(par[1], foco))
        return lista

    def proximas(n: int = 3, filtros: localizacao.Filtros | None = None) -> list[dict]:
        filtros = filtros or localizacao.Filtros()
        saida = []
        foco = foco_atual()
        for v, c in filtradas(filtros)[:n]:
            saida.append({**cartao(v), "classificacao": c.como_dict(), "foco": no_foco(c, foco)})
        return saida

    def inteiro(valor, padrao: int, minimo: int = 1, maximo: int = 500) -> int:
        try:
            return max(minimo, min(maximo, int(valor)))
        except (TypeError, ValueError):
            return padrao

    rotulos = {
        "nova": "Nova — ainda não avaliada", "descartada": "Descartada", "curtida": "Preparando currículo…",
        "pronta": "Pronta para enviar", "manual": "Sem e-mail — candidate-se pelo site com o PDF",
        "enviando": "Enviando…", "erro": "Erro — veja a mensagem abaixo", "respondida": "A empresa respondeu!",
        "aplicada": "Candidatura feita pelo site da empresa",
        "encerrada": "Vaga encerrada",
    }

    def rotulo_status(status: str, simulado: int = 0) -> str:
        if status == "enviada":
            return "Simulada (.eml gerado — pode ser enviada de verdade)" if simulado else "Enviada"
        return rotulos.get(status, status)

    @app.context_processor
    def globais():
        return {"envio_real": config.ENVIO_REAL, "contagem": repositorio.contagem_por_status(),
                "perfis": perfis_disponiveis(), "perfil_ativo": config.PERFIL_ATIVO,
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


    # ------------------------------------------------ perfis (várias pessoas)

    def perfis_disponiveis() -> list[dict]:
        from candidatura.perfil import nome_do_perfil

        saida = []
        for pid in config.listar_perfis():
            caminho = config.PERFIL_PATH if pid == config.PERFIL_ATIVO else (
                config._PADRAO_PRINCIPAL["PERFIL_PATH"] if pid == config.PERFIL_PRINCIPAL
                else config.pasta_do_perfil(pid) / "candidato.yaml")
            nome = nome_do_perfil(Path(caminho))
            if not nome or nome == "Seu Nome":
                nome = "Perfil principal" if pid == config.PERFIL_PRINCIPAL else pid
            saida.append({"id": pid, "nome": nome, "ativo": pid == config.PERFIL_ATIVO})
        return saida

    def trocar_para(perfil_id: str):
        config.ativar_perfil(perfil_id)
        repositorio.iniciar()
        repositorio.liberar_envios_interrompidos()
        cache_classificacao.clear()
        retomar_curtidas()

    @app.post("/api/perfil/ativar")
    def api_perfil_ativar():
        perfil_id = str((request.get_json(silent=True) or {}).get("id") or "")
        if perfil_id not in config.listar_perfis():
            return jsonify({"ok": False, "erro": "Perfil não encontrado."}), 404
        if trabalhador.estado["ocupado"] or not trabalhador.fila.empty():
            return jsonify({"ok": False, "erro": "Espere a tarefa atual terminar para trocar de perfil."}), 409
        trocar_para(perfil_id)
        return jsonify({"ok": True})

    @app.route("/perfis/novo", methods=["GET", "POST"])
    def novo_perfil():
        import re
        import unicodedata

        aviso = ""
        if request.method == "POST":
            nome = (request.form.get("nome") or "").strip()[:60]
            base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
            base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:30] or "perfil"
            if base == config.PERFIL_PRINCIPAL:
                base = "perfil-principal"
            if not nome:
                aviso = "Digite o nome da pessoa."
            elif trabalhador.estado["ocupado"] or not trabalhador.fila.empty():
                aviso = "Espere a tarefa atual terminar."
            else:
                perfil_id, n = base, 2
                while perfil_id in config.listar_perfis():
                    perfil_id, n = f"{base}-{n}", n + 1
                pasta = config.PERFIS_DIR / perfil_id
                pasta.mkdir(parents=True)
                (pasta / "config.env").write_text(
                    "# E-mail desta pessoa (preencha pela página Configurações)\nENVIO_REAL=false\n", encoding="utf-8")
                trocar_para(perfil_id)
                return redirect(url_for("perfil"))
        return render_template("novo_perfil.html", aviso=aviso)

    # ------------------------------------------------ configurações do perfil

    @app.route("/configuracoes", methods=["GET", "POST"])
    def configuracoes():
        from candidatura import areas
        from candidatura.perfil import salvar_preferencias

        c = candidato_ou_none()
        if not c:
            return redirect(url_for("perfil"))
        prefs = c.preferencias or {}
        aviso = ""
        if request.method == "POST":
            def foco_do_formulario() -> dict:
                from candidatura import localidades

                texto = (request.form.get("foco_cidade") or "").strip()
                lugar = localidades.resolver(texto) if texto else None
                cidade, uf = (lugar.nome, lugar.uf) if lugar and lugar.tipo == "cidade" else (texto, "")
                return {"ativo": bool(request.form.get("foco_ativo")) and bool(cidade), "cidade": cidade, "uf": uf,
                        "alerta_telegram": bool(request.form.get("alerta_telegram")),
                        "alerta_limiar": inteiro(request.form.get("alerta_limiar"), 75, minimo=0, maximo=100)}

            def lista(campo):
                return [x.strip() for x in (request.form.get(campo) or "").replace("\n", ",").split(",") if x.strip()]

            area = request.form.get("area") or "outra"
            novas = {
                "area": area if area in areas.AREAS else "outra",
                "cargos_alvo": lista("cargos_alvo"),
                "termos_busca": lista("termos_busca"),
                "termos_extras": lista("termos_extras"),
                "fontes": [f for f in request.form.getlist("fontes") if f in areas.FONTES],
                "senioridade": request.form.get("senioridade") or prefs.get("senioridade") or "",
                "modalidade": (request.form.get("modalidade") or "").strip(),
                "foco_regional": foco_do_formulario(),
            }
            email = (request.form.get("smtp_usuario") or "").strip()
            if email and not email_valido(email):
                aviso = f"E-mail inválido: {email}"
            elif not novas["termos_busca"]:
                aviso = "Informe pelo menos um termo de busca (ex.: o nome do cargo que você procura)."
            else:
                salvar_preferencias(novas)
                valores = {
                    "SMTP_USUARIO": email,
                    "ENVIO_REAL": "true" if request.form.get("envio_real") and email else "false",
                    "ENVIAR_AO_CURTIR": "true" if request.form.get("enviar_ao_curtir") else "false",
                    "EMAIL_COPIA_PARA_MIM": "true" if request.form.get("copia") else "false",
                }
                senha = (request.form.get("smtp_senha") or "").replace(" ", "")
                if senha:  # em branco = mantém a senha que já estava salva
                    valores["SMTP_SENHA"] = senha
                if email.lower().endswith(("@gmail.com", "@googlemail.com")):
                    valores.update(SMTP_HOST="smtp.gmail.com", SMTP_PORTA="587")
                config.gravar_config_perfil(config.PERFIL_ATIVO, valores)
                chaves = {"IA_NO_RESUMO": "true" if request.form.get("ia_no_resumo") else "false"}
                for campo, nome in (("ia_api_key", "IA_API_KEY"), ("tavily_api_key", "TAVILY_API_KEY"),
                                    ("brave_api_key", "BRAVE_API_KEY"),
                                    ("hunter_api_key", "HUNTER_API_KEY")):
                    valor = (request.form.get(campo) or "").strip()
                    if valor == "-":  # "-" apaga a chave
                        chaves[nome] = ""
                    elif valor:
                        chaves[nome] = valor
                if chaves.get("IA_API_KEY"):
                    chaves["IA_PROVEDOR"] = "groq"
                elif chaves.get("IA_API_KEY") == "":
                    chaves["IA_PROVEDOR"] = ""
                config.gravar_chaves(chaves)
                if request.form.get("buscar"):
                    trabalhador.agendar("Buscando vagas para o seu perfil", servico.importar_do_perfil)
                    return redirect(url_for("swipe"))
                trabalhador.agendar("Recalculando compatibilidade", servico.pontuar_novas)
                return redirect(url_for("configuracoes", salvo=1))
            prefs = {**prefs, **novas}
        area = prefs.get("area") or ("desenvolvimento" if prefs.get("termos_remotar") else "")
        return render_template(
            "configuracoes.html", c=c, prefs=prefs, area=area, areas=areas.AREAS, fontes=areas.FONTES,
            fontes_marcadas=areas.fontes(prefs), termos=areas.termos_busca(prefs), aviso=aviso,
            salvo=request.args.get("salvo"), primeira=request.args.get("primeira"),
            smtp_usuario=config.SMTP_USUARIO, tem_senha=bool(config.SMTP_SENHA),
            envio_real=config.ENVIO_REAL, enviar_ao_curtir=config.ENVIAR_AO_CURTIR,
            copia=config.EMAIL_COPIA_PARA_MIM, perfil_id=config.PERFIL_ATIVO,
            tem_ia=bool(config.IA_API_KEY) and config.IA_PROVEDOR == "groq", ia_no_resumo=config.IA_NO_RESUMO,
            tem_brave=bool(config.BRAVE_API_KEY), tem_hunter=bool(config.HUNTER_API_KEY),
            tem_tavily=bool(config.TAVILY_API_KEY),
            rotina=__import__("candidatura.rotina", fromlist=["situacao"]).situacao())

    @app.get("/funil")
    def pagina_funil():
        from candidatura import funil

        return render_template("funil.html", linhas=funil.calcular())

    @app.post("/api/etapa/<id_>")
    def api_etapa(id_):
        """Marca a etapa do processo (entrevista, teste, proposta...) — alimenta o funil."""
        from candidatura import funil

        repositorio.obter(id_) or abort(404)
        etapa = str((request.get_json(silent=True) or {}).get("etapa") or "")
        if etapa and etapa not in funil.ETAPAS:
            abort(400)
        repositorio.atualizar(id_, etapa=etapa or None)
        return jsonify({"ok": True})

    @app.post("/api/rotina")
    def api_rotina():
        from candidatura import rotina

        dados = request.get_json(silent=True) or {}
        try:
            if dados.get("ligar"):
                rotina.ativar(str(dados.get("hora") or "09:00"), auto=bool(dados.get("auto")))
            else:
                rotina.desativar()
        except (RuntimeError, ValueError) as e:
            return jsonify({"ok": False, "erro": str(e)}), 400
        return jsonify({"ok": True, **rotina.situacao()})

    @app.post("/api/testar-chave")
    def api_testar_chave():
        """Confere uma chave opcional sem gastar quase nada (Groq: 1 frase; Brave: 1 busca; Hunter: créditos)."""
        from candidatura import busca_posts, hunter, ia

        dados = request.get_json(silent=True) or {}
        tipo, chave = dados.get("tipo"), (dados.get("chave") or "").strip()
        antes = {k: getattr(config, k) for k in ("IA_PROVEDOR", "IA_API_KEY", "TAVILY_API_KEY", "BRAVE_API_KEY",
                                                  "HUNTER_API_KEY")}
        try:
            if tipo == "groq":
                config.IA_PROVEDOR, config.IA_API_KEY = "groq", chave or config.IA_API_KEY
                ok = bool(ia.completar("Responda só: ok", "ok?", max_tokens=60))
                modelo = config.IA_MODELO or ia._modelo_descoberto.get("groq") or ia.PROVEDORES["groq"][1]
                if ok:
                    msg = f"IA respondeu ✓ (modelo {modelo}). Clique em Salvar para usar."
                elif "401" in ia.ultimo_erro or "invalid api key" in ia.ultimo_erro.lower():
                    msg = "O Groq recusou a chave (inválida ou apagada). Gere outra em console.groq.com/keys."
                else:
                    msg = f"O Groq respondeu com erro: {ia.ultimo_erro or 'sem resposta'}"
            elif tipo in ("tavily", "brave"):
                if tipo == "tavily":
                    config.TAVILY_API_KEY = chave or config.TAVILY_API_KEY
                else:  # testa a Brave mesmo se houver Tavily salva
                    config.TAVILY_API_KEY, config.BRAVE_API_KEY = "", chave or config.BRAVE_API_KEY
                n = len(busca_posts.buscar('"envie seu currículo" vaga desenvolvedor'))
                ok, msg = True, f"Busca funcionou ✓ ({n} resultados, gastou 1 crédito). Clique em Salvar para usar."
            elif tipo == "hunter":
                config.HUNTER_API_KEY = chave or config.HUNTER_API_KEY
                c = hunter.creditos()
                ok = c is not None
                msg = f"Chave ok ✓ — {c['disponiveis'] - c['usadas']} buscas restantes no mês" if ok else "Chave do Hunter recusada."
            else:
                abort(400)
        except Exception as e:  # noqa: BLE001 — devolve o motivo para a tela
            ok, msg = False, str(e)[:200]
        finally:
            for k, v in antes.items():
                setattr(config, k, v)
        return jsonify({"ok": ok, "erro": "" if ok else msg, "msg": msg}), (200 if ok else 400)

    @app.post("/api/empresas/hunter")
    def api_empresas_hunter():
        from candidatura import hunter

        if not hunter.disponivel():
            return jsonify({"ok": False, "erro": "Configure a chave do Hunter em Configurações → Chaves."}), 400
        limite = inteiro((request.get_json(silent=True) or {}).get("limite"), 10, maximo=50)
        c = candidato_ou_none()
        trabalhador.agendar("Procurando e-mails de RH no Hunter", hunter.completar_empresas,
                            (c.preferencias or {}) if c else {}, limite)
        return jsonify({"ok": True})

    @app.post("/api/testar-email")
    def api_testar_email():
        """Só faz login no SMTP (não envia nada) para conferir e-mail + senha de app."""
        import smtplib
        import ssl

        dados = request.get_json(silent=True) or {}
        usuario = (dados.get("usuario") or config.SMTP_USUARIO or "").strip()
        senha = (dados.get("senha") or "").replace(" ", "") or config.SMTP_SENHA
        if not usuario or not senha:
            return jsonify({"ok": False, "erro": "Preencha o e-mail e a senha de app."}), 400
        host = "smtp.gmail.com" if usuario.lower().endswith("@gmail.com") else config.SMTP_HOST
        try:
            with smtplib.SMTP(host, config.SMTP_PORTA, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(usuario, senha)
        except smtplib.SMTPAuthenticationError:
            return jsonify({"ok": False, "erro": "O Gmail recusou o login. Use uma SENHA DE APP (16 letras), "
                                                 "não a senha normal — e confira o e-mail."}), 400
        except (smtplib.SMTPException, OSError) as e:
            return jsonify({"ok": False, "erro": f"Não consegui conectar: {e}"}), 400
        return jsonify({"ok": True})

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
            if not (c.preferencias or {}).get("area") and not (c.preferencias or {}).get("fontes"):
                return redirect(url_for("configuracoes", primeira=1))  # 1ª vez: escolher área, busca e e-mail
            trabalhador.agendar("Buscando vagas para o seu perfil", servico.importar_do_perfil)
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
        from candidatura import hunter

        return render_template("empresas.html", empresas=linhas, aviso=request.args.get("aviso", ""),
                               tem_hunter=hunter.disponivel(),
                               sem_email=sum(1 for e in linhas if not e.get("email") and (e.get("tipo") or "").lower() != "big tech"),
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
            "enviada": ["enviada", "aplicada"],
            "respondida": ["respondida"],
            "erro": ["erro"],
            "descartada": ["descartada"],
        }
        # "Prontas" tem duas listas: o que falta enviar e o que já saiu por e-mail.
        ver = request.args.get("ver", "falta") if aba == "pronta" else ""
        enviadas_email = [v for v in repositorio.listar("enviada", limite=2000, ordem="enviada_em DESC")
                          if v.get("email_destino")] if aba == "pronta" else []
        if ver == "enviadas":
            vagas = enviadas_email
        else:
            vagas = repositorio.listar(grupos.get(aba, ["pronta"]), limite=500,
                                       ordem="coalesce(enviada_em, aplicada_em) DESC, score DESC" if aba == "enviada"
                                       else "score DESC, criada_em DESC")
        if ver == "falta":  # avisa o que NÃO vai sair porque a empresa/e-mail já recebeu candidatura
            for v in vagas:
                v["ja_contatado"] = bool(v.get("email_destino")) and repositorio.ja_contatado(
                    v["email_destino"], v.get("empresa") or "", config.DIAS_SEM_REPETIR_EMPRESA, v["id"])
        contagem = repositorio.contagem_por_status()
        return render_template("fila.html", vagas=vagas, aba=aba, ver=ver, metricas=repositorio.metricas(),
                               limite=config.LIMITE_DIARIO, n_falta=contagem["pronta"] + contagem["curtida"],
                               n_enviadas_email=len(enviadas_email), dias_repetir=config.DIAS_SEM_REPETIR_EMPRESA)

    @app.get("/vaga/<id_>")
    def detalhe(id_):
        v = repositorio.obter(id_) or abort(404)
        from candidatura import funil

        return render_template("detalhe.html", v=v, aviso=request.args.get("aviso", ""), etapas=funil.ETAPAS)

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
            return render_template("nova.html", enviar_ao_curtir=config.ENVIAR_AO_CURTIR)
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
        tarefa = servico.preparar_e_enviar if f.get("enviar") else servico.preparar
        trabalhador.agendar(f"Preparando {vaga['titulo']}", tarefa, vaga["id"])
        return redirect(url_for("fila", aba="pronta"))

    @app.post("/api/ler-post")
    def api_ler_post():
        """Post colado (LinkedIn/WhatsApp...) -> cargo, empresa, e-mail, local. Não salva nada."""
        from candidatura import posts

        texto = str((request.get_json(silent=True) or {}).get("texto") or "")[:20000]
        return jsonify(posts.ler_post(texto))

    # ---------------------------------------------------------------- API

    @app.get("/api/proximas")
    def api_proximas():
        return jsonify(proximas(inteiro(request.args.get("n"), 3, maximo=50), localizacao.Filtros.de_args(request.args)))

    @app.get("/api/localidades")
    def api_localidades():
        """Sugestões para o campo de localização ("udia" -> Uberlândia - MG)."""
        from candidatura import localidades

        q = (request.args.get("q") or "")[:60]
        return jsonify([s.como_dict() for s in localidades.sugerir(q, limite=8)])

    @app.get("/api/filtros")
    def api_filtros():
        """Quantas vagas novas passam no filtro atual + contagem por opção (para os rótulos)."""
        filtros = localizacao.Filtros.de_args(request.args)
        passam = filtradas(filtros)
        todas = [(v, classificada(v)) for v in repositorio.listar("nova", limite=100000)]
        def contar(campo):
            contagem: dict[str, int] = {}
            for _, c in todas:
                valor = getattr(c, campo) or "indefinido"
                contagem[valor] = contagem.get(valor, 0) + 1
            return contagem
        return jsonify({"total": len(passam), "novas": len(todas),
                        "lugar": filtros.lugar.como_dict() if filtros.lugar else None,
                        "contagem": {campo: contar(campo) for campo in ("pais", "idioma", "modalidade", "regiao")}})

    @app.post("/api/aplicada/<id_>")
    def api_aplicada(id_):
        """Check de "já me candidatei pelo site" (vaga sem e-mail) — e o desfazer."""
        v = repositorio.obter(id_) or abort(404)
        feito = bool((request.get_json(silent=True) or {}).get("feito", True))
        if feito:
            if v["status"] not in ("manual", "pronta", "erro", "curtida", "nova"):
                return jsonify({"ok": False, "erro": f"Não dá para marcar uma vaga '{v['status']}'."}), 400
            repositorio.atualizar(id_, status="aplicada", aplicada_em=datetime.now().isoformat(timespec="seconds"))
        else:
            if v["status"] != "aplicada":
                return jsonify({"ok": False, "erro": "Essa vaga não está marcada."}), 400
            repositorio.atualizar(id_, status="manual" if v.get("cv_path") else "nova", aplicada_em=None)
        return jsonify({"ok": True, "contagem": repositorio.contagem_por_status()})

    @app.post("/api/decidir/<id_>")
    def api_decidir(id_):
        acao = (request.get_json(silent=True) or {}).get("acao")
        if acao in ("curtir", "descartar"):
            v = repositorio.obter(id_) or abort(404)
            if v["status"] not in ("nova", "descartada", "curtida", "manual", "pronta", "erro"):
                return jsonify({"ok": False, "erro": "Essa vaga já foi enviada."}), 400
        if acao == "curtir":
            repositorio.atualizar(id_, status="curtida")
            if config.ENVIAR_AO_CURTIR:
                trabalhador.agendar("Preparando e enviando candidatura", servico.preparar_e_enviar, id_)
            else:
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
        if not candidato_ou_none():
            return jsonify({"ok": False, "erro": "Monte seu perfil primeiro (aba Meu perfil)."}), 400
        trabalhador.agendar("Buscando vagas nas fontes do seu perfil", servico.importar_do_perfil)
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
