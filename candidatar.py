"""Candidatura automática — linha de comando.

    python candidatar.py iniciar               cria config/candidato.yaml a partir do exemplo
    python candidatar.py app                   abre a interface (swipe) em http://127.0.0.1:5000
    python candidatar.py importar              puxa vagas do radar + GitHub + Remotar e pontua
    python candidatar.py listar [--top 20]     mostra as vagas mais compatíveis
    python candidatar.py preparar --top 10     gera CV + carta para as 10 melhores com e-mail
    python candidatar.py enviar --limite 10    envia as 'prontas' (simulação se ENVIO_REAL=false)
    python candidatar.py auto --limite 10      tudo acima de uma vez, sem revisão manual
    python candidatar.py respostas             lê o Gmail (IMAP) e marca respondidas/bounces
    python candidatar.py followup --limite 10  1 follow-up educado após 7 dias sem resposta
    python candidatar.py agendar --hora 09:00  roda tudo todo dia (Agendador de Tarefas do Windows)
    python candidatar.py status                resumo da fila

Envio real exige ENVIO_REAL=true no .env OU a flag --real (que pede confirmação).
"""

from __future__ import annotations

import argparse
import shutil
import sys

# Windows: garante acentos no terminal.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from candidatura import config, repositorio  # noqa: E402


def _termos_remotar() -> list[str]:
    from candidatura.perfil import carregar_candidato

    prefs = carregar_candidato().preferencias or {}
    return prefs.get("termos_remotar") or ["python", "backend", "node"]


def _confirmar_real(args) -> bool:
    real = config.ENVIO_REAL or getattr(args, "real", False)
    if real and getattr(args, "real", False) and not getattr(args, "sem_confirmar", False):
        resp = input(f"ENVIO REAL de até {args.limite} e-mail(s) a partir de {config.SMTP_USUARIO}. Confirmar? [s/N] ")
        if resp.strip().lower() not in {"s", "sim", "y", "yes"}:
            print("Cancelado.")
            sys.exit(1)
    return real


def cmd_iniciar(args):
    if config.PERFIL_PATH.exists():
        print(f"Já existe: {config.PERFIL_PATH}")
        return
    config.PERFIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(config.PERFIL_EXEMPLO_PATH, config.PERFIL_PATH)
    print(f"Criado {config.PERFIL_PATH}. Edite com seus dados reais e rode: python candidatar.py app")


def cmd_app(args):
    from web.app import criar_app

    app = criar_app()
    print(f"\n  Job Radar — abra http://127.0.0.1:{args.porta}  ({'ENVIO REAL' if config.ENVIO_REAL else 'modo simulação'})\n")
    if not args.sem_navegador:
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{args.porta}")).start()
    app.run(host="127.0.0.1", port=args.porta, debug=False, threaded=True)


def cmd_importar(args):
    from candidatura import servico

    r = servico.importar_tudo(github=not args.sem_github, remotar_termos=None if args.sem_remotar else _termos_remotar())
    print("Importação:", r)
    if args.enriquecer:
        print("Descrições baixadas:", servico.enriquecer(limite=args.enriquecer))


def cmd_listar(args):
    repositorio.iniciar()
    vagas = repositorio.listar(args.status, limite=args.top)
    for v in vagas:
        email = v.get("email_destino") or "-"
        print(f"{v.get('score') or 0:>3}%  {v['titulo'][:60]:<60}  {(v.get('empresa') or '')[:24]:<24}  {email}")
    if not vagas:
        print("Nada encontrado. Rode: python candidatar.py importar")


def cmd_preparar(args):
    from candidatura import servico

    repositorio.iniciar()
    if args.id is not None:
        if not args.id:
            sys.exit("--id sem valores: informe ao menos um id.")
        ids = []
        for i in args.id:
            v = repositorio.obter(i)
            if not v:
                print(f"  ignorado: {i} não existe")
            elif servico.ja_enviada_de_verdade(v):
                print(f"  ignorado: {v['titulo'][:50]} já foi enviada")
            else:
                ids.append(i)
    else:
        vagas = [v for v in repositorio.listar(["nova", "curtida"], limite=5000)
                 if (v.get("score") or 0) >= args.score_min and (v.get("email_destino") or args.incluir_sem_email)]
        ids = [v["id"] for v in vagas[: args.top]]
    for i in ids:
        repositorio.atualizar(i, status="curtida")
    print(servico.preparar_lote(ids, usar_ia=not args.sem_ia))


def cmd_enviar(args):
    from candidatura import servico

    real = _confirmar_real(args)

    def progresso(v, r):
        print(f"  {'✅ enviada' if real else '📝 simulada'}: {v['titulo'][:60]} -> {v['email_destino']}")

    if args.id is not None and not args.id:
        sys.exit("--id sem valores: informe ao menos um id (nada foi enviado).")
    r = servico.enviar_lote(limite=args.limite, real=real, ids=args.id, ao_progredir=progresso)
    print(f"\n{r['enviadas']} {'enviada(s)' if real else 'simulada(s) (.eml em saida/)'}")
    for t, motivo in r["puladas"]:
        print(f"  pulada: {t[:60]} — {motivo}")
    for t, erro in r["erros"]:
        print(f"  ERRO: {t[:60]} — {erro}")


def cmd_auto(args):
    from candidatura import servico

    real = _confirmar_real(args)
    r = servico.auto(score_minimo=args.score_min, limite=args.limite, real=real,
                     usar_ia=not args.sem_ia, remotar_termos=_termos_remotar())
    print("Importação:", r["importacao"])
    print("Selecionadas:", r["selecionadas"], "| Preparo:", r["preparo"])
    e = r["envio"]
    print(f"{e['enviadas']} {'enviada(s)' if real else 'simulada(s)'}; puladas: {len(e['puladas'])}; erros: {len(e['erros'])}")
    for t, erro in e["erros"]:
        print(f"  ERRO: {t[:60]} — {erro}")


def cmd_respostas(args):
    from candidatura import acompanhamento

    print(acompanhamento.verificar_respostas(dias=args.dias))


def cmd_followup(args):
    from candidatura import acompanhamento

    real = _confirmar_real(args)
    try:
        acompanhamento.verificar_respostas()
    except Exception as e:
        print(f"(aviso) não consegui ler respostas antes do follow-up: {e}")
        if real:
            print("Por segurança, follow-up real só roda depois de checar respostas. Abortando.")
            sys.exit(1)
    r = acompanhamento.enviar_followups(limite=args.limite, real=real, dias=args.dias)
    if not r["enviados"] and not r["erros"]:
        print(f"Nenhuma candidatura REAL enviada há {args.dias}+ dias sem resposta (envios simulados não recebem follow-up).")
    print(f"{r['enviados']} follow-up(s) {'enviado(s)' if real else 'simulado(s)'}; erros: {r['erros']}")


def cmd_agendar(args):
    """Cria uma tarefa diária no Agendador de Tarefas do Windows."""
    import os
    import subprocess

    raiz = os.path.dirname(os.path.abspath(__file__))
    python = os.path.join(raiz, "venv", "Scripts", "python.exe")
    if not os.path.exists(python):
        python = sys.executable
    script = os.path.join(raiz, "rodar_diario.cmd")
    conteudo = (
        "@echo off\r\n"
        f'cd /d "{raiz}"\r\n'
        f'"{python}" candidatar.py importar --enriquecer 40\r\n'
        + (f'"{python}" candidatar.py respostas\r\n' if config.SMTP_SENHA else "")
        + (f'"{python}" candidatar.py auto --limite {args.limite}\r\n' if args.auto else "")
        + (f'"{python}" candidatar.py followup --limite 5\r\n' if args.auto and config.SMTP_SENHA else "")
    )
    comando = ["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", args.hora, "/TN", "JobRadarCandidaturas",
               "/TR", f'"{script}"']
    if args.mostrar:
        print(f"Conteúdo de {script}:\n{conteudo}\nComando: {' '.join(comando)}\n(nada foi criado)")
        return
    with open(script, "w", encoding="utf-8") as f:
        f.write(conteudo)
    print("Criando tarefa:", " ".join(comando))
    subprocess.run(comando, check=True)
    print(f"Pronto: todo dia às {args.hora} o Windows roda {script}. Remover: schtasks /Delete /TN JobRadarCandidaturas /F")


def cmd_status(args):
    repositorio.iniciar()
    m = repositorio.metricas()
    print("Fila:", ", ".join(f"{k}={v}" for k, v in m["por_status"].items()))
    print(f"Enviadas hoje: {m['enviadas_hoje']}/{config.LIMITE_DIARIO} | total real: {m['enviadas_reais']} | simuladas: {m['simuladas']}")
    print(f"Modo: {'ENVIO REAL' if config.ENVIO_REAL else 'simulação'} | SMTP: {config.SMTP_USUARIO or '(não configurado)'}")
    from candidatura import ia

    print(f"IA: {config.IA_PROVEDOR if ia.disponivel() else 'desligada (usa modelos de texto)'}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Candidatura automática com currículo adaptado por vaga.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("iniciar", help="cria config/candidato.yaml a partir do exemplo").set_defaults(f=cmd_iniciar)

    a = sub.add_parser("app", help="abre a interface (swipe) no navegador")
    a.add_argument("--porta", type=int, default=5000)
    a.add_argument("--sem-navegador", action="store_true")
    a.set_defaults(f=cmd_app)

    a = sub.add_parser("importar", help="busca vagas (radar, GitHub, Remotar, Gupy) e calcula a compatibilidade")
    a.add_argument("--sem-github", action="store_true")
    a.add_argument("--sem-remotar", action="store_true")
    a.add_argument("--enriquecer", type=int, default=0, metavar="N", help="baixa a descrição de até N vagas para achar e-mail")
    a.set_defaults(f=cmd_importar)

    a = sub.add_parser("listar", help="mostra as vagas mais compatíveis")
    a.add_argument("--top", type=int, default=20, help="quantas mostrar")
    a.add_argument("--status", default="nova", help="nova, pronta, manual, enviada, respondida, erro...")
    a.set_defaults(f=cmd_listar)

    a = sub.add_parser("preparar", help="gera CV + carta adaptados (não envia)")
    a.add_argument("--top", type=int, default=10, help="quantas vagas preparar")
    a.add_argument("--score-min", type=int, default=0, help="compatibilidade mínima (0-100)")
    a.add_argument("--incluir-sem-email", action="store_true", help="prepara também vagas sem e-mail")
    a.add_argument("--id", nargs="*", help="ids específicos (veja na interface)")
    a.add_argument("--sem-ia", action="store_true", help="não usa IA mesmo se configurada")
    a.set_defaults(f=cmd_preparar)

    for nome, func in (("enviar", cmd_enviar), ("auto", cmd_auto)):
        a = sub.add_parser(nome, help="envia as candidaturas prontas" if nome == "enviar"
                           else "importa, escolhe as melhores com e-mail, prepara e envia")
        a.add_argument("--limite", type=int, default=10, help="máximo de e-mails nesta execução")
        a.add_argument("--real", action="store_true", help="envia de verdade (pede confirmação)")
        a.add_argument("--sem-confirmar", action="store_true", help="com --real: não pedir confirmação (para agendador)")
        if nome == "enviar":
            a.add_argument("--id", nargs="*")
        else:
            a.add_argument("--score-min", type=int, default=None)
            a.add_argument("--sem-ia", action="store_true")
        a.set_defaults(f=func)

    a = sub.add_parser("respostas", help="lê o Gmail (IMAP) e marca respondidas e e-mails que voltaram")
    a.add_argument("--dias", type=int, default=45, help="quantos dias da caixa de entrada ler")
    a.set_defaults(f=cmd_respostas)

    a = sub.add_parser("followup", help="1 follow-up educado após N dias sem resposta (só envios reais)")
    a.add_argument("--limite", type=int, default=10)
    a.add_argument("--dias", type=int, default=7, help="dias sem resposta antes do follow-up")
    a.add_argument("--real", action="store_true")
    a.add_argument("--sem-confirmar", action="store_true")
    a.set_defaults(f=cmd_followup)

    a = sub.add_parser("agendar", help="cria tarefa diária no Agendador de Tarefas do Windows")
    a.add_argument("--hora", default="09:00")
    a.add_argument("--auto", action="store_true", help="além de buscar, também envia (modo auto) todo dia")
    a.add_argument("--limite", type=int, default=10)
    a.add_argument("--mostrar", action="store_true", help="só mostra o comando, não cria a tarefa")
    a.set_defaults(f=cmd_agendar)

    sub.add_parser("status", help="resumo da fila e da configuração").set_defaults(f=cmd_status)

    args = p.parse_args(argv)
    from candidatura.perfil import PerfilInvalido, PerfilNaoEncontrado

    try:
        args.f(args)
    except (PerfilNaoEncontrado, PerfilInvalido, RuntimeError, ValueError) as e:
        # Erro esperado (configuração faltando etc.): mensagem clara, sem traceback.
        print(f"Erro: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
