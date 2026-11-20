<div align="center">

# 📡 Job Radar
### Encontra vagas, adapta seu currículo para cada uma e se candidata por e-mail — de graça

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Interface%20local-000000?style=for-the-badge&logo=flask&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Scraping%20%2B%20PDF-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Cron-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)
![Custo](https://img.shields.io/badge/custo-R%24%200-success?style=for-the-badge)

</div>

---

## O que é

Procurar emprego tem duas partes chatas: **achar** vaga boa antes de todo mundo e **se candidatar**
dezenas de vezes, ajustando currículo e carta para cada uma. O Job Radar automatiza as duas.

| | O que faz |
|---|---|
| 🔍 **Radar** | Varre 11 fontes (LinkedIn, Gupy, Indeed, Sólides, Catho, 99Jobs, GeekHunter, Trampos, Senior, WeWorkRemotely…) a cada 3h no GitHub Actions, filtra por cargo/cidade/idioma e avisa no Telegram. |
| 💌 **Fontes com e-mail** | Puxa vagas dos repositórios da comunidade (`backend-br`, `frontendbr`, `react-brasil`, `datascience-br`), do Remotar e da Gupy (com descrição completa). A mesma vaga em várias fontes entra uma vez só. |
| 🃏 **Swipe** | Interface estilo Tinder: cada vaga vira um cartão com **% de compatibilidade**, tecnologias que você tem ✓ e as que faltam. → quero, ← descarto. |
| 📄 **Currículo adaptado** | Para cada vaga curtida gera um PDF próprio: título, resumo e competências reordenados para o que a vaga pede, conquistas mais relevantes primeiro. **Nunca inventa nada.** |
| ✉️ **Carta + e-mail** | Carta de apresentação e corpo do e-mail personalizados (empresa, cargo, evidências reais do seu perfil, links de portfólio). |
| 🚀 **Envio em massa, com freio** | Envia por Gmail com limite diário, intervalo aleatório entre e-mails, sem repetir empresa — e começa em **modo simulação**. |
| 🔁 **Follow-up e respostas** | Lê sua caixa do Gmail (IMAP, só leitura), marca quem respondeu e e-mails que voltaram, e manda **1** follow-up educado após 7 dias sem resposta. |
| ⏰ **Todo dia sozinho** | `agendar` cria uma tarefa no Agendador do Windows para buscar (e, se quiser, enviar) todo dia. |
| 🤖 **IA opcional e gratuita** | Groq, Gemini ou Ollama (local) deixam resumo e carta mais naturais. Sem IA, tudo funciona com modelos de texto. |

---

## Começando (5 minutos)

```bash
git clone https://github.com/IltonBJSilva/job-radar.git
cd job-radar
python -m venv venv
venv\Scripts\activate            # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

copy .env.example .env           # Linux/macOS: cp .env.example .env
python candidatar.py iniciar     # cria config/candidato.yaml
```

1. **Preencha `config/candidato.yaml`** com seus dados reais: experiências, conquistas, projetos,
   habilidades, links (GitHub, LinkedIn, portfólio). Esse arquivo é a única fonte do currículo e
   fica fora do Git.
2. **Abra a interface:**
   ```bash
   python candidatar.py app       # abre http://127.0.0.1:5000
   ```
3. Clique em **Buscar vagas novas**, faça o swipe, confira os PDFs na aba **Prontas** e clique
   em **Enviar prontas**. No modo simulação, cada e-mail vira um arquivo `.eml` em `saida/` para você
   abrir e conferir.
4. Satisfeito? Configure o Gmail (abaixo) e troque `ENVIO_REAL=true` no `.env`.

### Configurar o Gmail (grátis)
1. Ative a [verificação em duas etapas](https://myaccount.google.com/security).
2. Crie uma **senha de app** em <https://myaccount.google.com/apppasswords>.
3. No `.env`: `SMTP_USUARIO=seu@gmail.com` e `SMTP_SENHA=<senha de app>`.

---

## Linha de comando

```bash
python candidatar.py importar --enriquecer 40   # radar + GitHub + Remotar; baixa descrições p/ achar e-mails
python candidatar.py listar --top 20            # melhores vagas por compatibilidade
python candidatar.py preparar --top 10 --score-min 60
python candidatar.py enviar --limite 10         # simulação (ou ENVIO_REAL=true / --real)
python candidatar.py auto --limite 10           # tudo de uma vez: importa, escolhe, prepara e envia
python candidatar.py respostas               # lê o Gmail: respondidas e bounces
python candidatar.py followup --limite 10      # 1 follow-up após 7 dias sem resposta
python candidatar.py agendar --hora 09:00      # tarefa diária (adicione --auto para também enviar)
python candidatar.py status
```

`auto` só escolhe vagas **com e-mail** e compatibilidade ≥ `SCORE_MINIMO_AUTO` (padrão 60%).
Vagas sem e-mail ficam com o currículo adaptado pronto na aba **Sem e-mail**, para você se candidatar
pelo site do anúncio anexando o PDF.

---

## Como a adaptação funciona (e por que ela é honesta)

1. **Extração**: identifica ~70 tecnologias/competências na vaga (com sinônimos: `Postgres` → PostgreSQL,
   `k8s` → Kubernetes) com borda de palavra — `Google` não vira `Go`, `JavaScript` não vira `Java`.
2. **Compatibilidade (0–100%)**: 55% cobertura técnica (tecnologia no título pesa em dobro; inglês/git
   pesam pouco) + 45% aderência do cargo aos seus `cargos_alvo`.
3. **Currículo**: suas habilidades que a vaga pede vão para o início do grupo, em **negrito**; o título
   ganha as 3 tecnologias centrais que você tem; as conquistas de cada experiência são reordenadas.
4. **O que falta** aparece só para você, na tela — nunca entra no currículo ou na carta. Há testes
   automatizados garantindo isso (`tests/test_candidatura.py`).

Recrutadores e ATS (Gupy, Sólides, Greenhouse) ranqueiam por palavra-chave: destacar o que você **já
tem** e a vaga pede é o maior ganho, sem o risco de inventar experiência.

---

## Segurança e o que o sistema NUNCA faz

- **Não envia nada sem você ligar:** o padrão é simulação (`.eml` em `saida/`). Envio real pede confirmação.
- **Não inventa experiência:** o CV usa só o seu perfil, com as palavras que você escreveu.
- **Não manda CV para qualquer um no modo `auto`:** só para e-mails em contexto de recrutamento **e** do domínio
  da empresa (`vagas@empresa.com.br` para "Empresa"). E-mail pessoal (gmail etc.) fica para você revisar no swipe.
- **Vaga em inglês não sai automaticamente:** fica em "Sem e-mail/revisar", porque CV e carta são em português.
- **Não envia duas vezes:** reserva atômica por vaga e trava entre envios; não repete empresa por 30 dias.
- **Interface só local:** aceita apenas `127.0.0.1`/`localhost` (bloqueia CSRF e DNS rebinding).
- **Links de vagas não acessam sua rede:** downloads recusam IPs internos e páginas acima de 2 MB.
- **IA (se ligada):** recebe nome, cidade, experiências e projetos (nunca telefone/e-mail). A descrição da vaga vai
  marcada como "dados"; resposta que cite link ou e-mail fora do seu perfil é descartada.
- **LGPD:** e-mails de recrutadores ficam só na sua máquina (`data/candidaturas.db`), usados apenas para a
  candidatura. Apague o banco quando encerrar a busca.

## Boas práticas de envio (para não cair em spam)

- Comece com **20–30 e-mails/dia** (contando follow-ups) (o Gmail grátis aceita ~500, mas volume alto queima sua reputação).
- O sistema espera **60–180 s aleatórios** entre envios e manda **um e-mail por destinatário**.
- Não repete a mesma empresa/e-mail por **30 dias** (`DIAS_SEM_REPETIR_EMPRESA`).
- Credencial inválida ou limite do provedor interrompem o lote na hora.
- Revise as primeiras candidaturas no modo simulação antes de ligar o envio real.

---

## Arquitetura

```text
job-radar/
├── candidatar.py            # CLI da candidatura (app, importar, preparar, enviar, auto)
├── main.py                  # Radar: ciclo de busca por perfil (roda no GitHub Actions)
├── candidatura/
│   ├── perfil.py            # Lê config/candidato.yaml
│   ├── compatibilidade.py   # Extração de tecnologias + score estilo ATS
│   ├── adaptador.py         # Currículo/carta/e-mail adaptados (sem inventar)
│   ├── ia.py                # IA opcional: Groq / Gemini / Ollama
│   ├── contato.py           # Baixa a descrição da vaga e acha e-mails
│   ├── fontes.py            # GitHub vagas + Remotar
│   ├── documentos.py        # HTML → PDF (Chromium do Playwright)
│   ├── envio.py             # SMTP com tratamento de erros
│   ├── repositorio.py       # Fila em data/candidaturas.db (fora do Git)
│   ├── servico.py           # Orquestração + limites anti-spam
│   └── templates/           # Modelos do currículo e da carta
├── web/                     # Interface Flask (swipe, fila, detalhe, vaga manual)
├── core/                    # Regras de filtro do radar (cargo, cidade, idioma, score)
├── scrapers/                # 11 fontes de vagas
├── database/                # SQLite do radar (data/jobs.db, versionado pelo robô)
├── notifier/                # Telegram: alertas, digest diário, 👍/👎
├── config/candidato.example.yaml
└── tests/                   # 569 testes (CI a cada push)
```

**Privacidade:** `config/candidato.yaml`, `data/candidaturas.db`, `saida/` e `.env` estão no
`.gitignore`. O `data/jobs.db` (só vagas públicas) é o único banco versionado, porque o radar roda no
GitHub Actions.

### Radar no GitHub Actions

> ⚠️ **Antes de dar push:** cadastre os segredos `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` em
> *Settings → Secrets and variables → Actions* (sem eles o robô roda, mas não avisa ninguém). Se o push
> conflitar em `data/jobs.db` (o robô commita esse arquivo a cada 3h), fique com a versão do remoto:
> `git checkout --theirs data/jobs.db`.

O workflow `.github/workflows/jobradar.yml` roda a cada 3h. Configure os segredos
`TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no repositório. Cargos, termos e cidades ficam em
`core/config.py` (Brasil) e `core/config_intl.py` (internacional).

---

## Inspirações e alternativas pesquisadas

| Projeto | O que faz | Por que não basta |
|---|---|---|
| [AIHawk](https://github.com/feder-cr/jobs_applier_ai_agent_aihawk) | Agente que aplica no LinkedIn e gera CV por vaga | Foco em LinkedIn Easy Apply; exige LLM pago/configurado |
| [ApplyPilot](https://github.com/ibarrajo/ApplyPilot) | Pipeline descoberta → score → CV → carta → auto-apply (usa JobSpy) | Mercado dos EUA; depende de Gemini + Claude Code + Chrome |
| [python-jobspy](https://pypi.org/project/python-jobspy/) | Scraper multi-site com coluna de e-mails | No Brasil traz e-mail raramente |
| [LoopCV](https://www.loopcv.pro/pt/) | SaaS que envia candidaturas automaticamente | Plano gratuito limitado |
| Simplify / Huntr | Extensões que preenchem formulários e organizam a busca | Auto-envio só no plano pago |

O Job Radar junta o que funciona nesses projetos (score, CV por vaga, envio automático) com fontes
brasileiras, envio por e-mail e custo zero.

---

## Testes

```bash
pytest tests/ -q
```

Os testes rodam sem rede, sem navegador e sem SMTP. O CI (`.github/workflows/testes.yml`) executa
a suíte a cada push.

---

<sub>O radar de vagas (scrapers, filtro, Telegram) nasceu do projeto JobRadar de Liliam Kezia Oliveira
Souza, adaptado aqui para vagas de desenvolvimento backend e estendido com o módulo de candidatura.</sub>
