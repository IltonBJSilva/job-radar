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
| 🔎 **Filtros** | País (Brasil/exterior), idioma do anúncio (PT/EN/ES), modalidade (remoto/híbrido/presencial), região do Brasil e localização (cidade, UF ou país). Ficam salvos no navegador. |
| 🏢 **Sites das empresas** | Além dos sites de vaga, visita as empresas da aba Empresas, acha o portal de cada uma (Gupy, Greenhouse, Lever) e puxa as vagas abertas que combinam com você. |
| ⭐ **Foco regional** | Liga/desliga em Configurações: vagas da sua cidade (ex.: Uberlândia) primeiro no swipe, LinkedIn buscando também na cidade e empresas de lá visitadas primeiro. |
| 📋 **Colar post de recrutador** | Cole o post do LinkedIn/WhatsApp ("envie o CV para vagas@…"): o sistema acha cargo, empresa, e-mail, cidade e modalidade e prepara a candidatura. Sem entrar na sua conta. |
| 🔎 **Posts públicos e Hunter** | Com chaves grátis opcionais: busca posts públicos de recrutadores (Tavily, grátis) e e-mail de RH das empresas que não publicam (Hunter.io). |
| 📱 **Aviso no Telegram** | Vaga nova na sua cidade com compatibilidade ≥ 75% vira mensagem no celular. |
| 📊 **Funil por fonte** | Quantas você enviou, quantas responderam e quantas viraram entrevista, por fonte. |
| ✅ **Check do site** | Vaga sem e-mail: candidate-se pelo site com o PDF pronto e marque **✓ Candidatei** — ela vai para Enviadas. |
| 📄 **Currículo adaptado** | Para cada vaga curtida gera um PDF próprio no **visual do Overleaf** (`resume.cls`, fonte do LaTeX), **sempre com 2 páginas**: competências e conquistas reordenadas para o que a vaga pede, **IA / agentes / orquestração sempre em destaque**. **Nunca inventa nada.** |
| 🎓 **Modo estágio** | Em vaga de estágio, usa automaticamente uma versão "estudante" do seu perfil (resumo de graduando, competências enxutas), para não parecer sênior demais. |
| ❤️ **Coração que envia** | Com `ENVIAR_AO_CURTIR=true`, curtir uma vaga com e-mail já prepara o currículo e envia — respeitando os limites anti-spam. |
| ✉️ **Carta + e-mail** | Carta de apresentação e corpo do e-mail personalizados (empresa, cargo, evidências reais do seu perfil, links de portfólio). |
| 🚀 **Envio em massa, com freio** | Envia por Gmail com limite diário, intervalo aleatório entre e-mails, sem repetir empresa — e começa em **modo simulação**. |
| 🔁 **Follow-up e respostas** | Lê sua caixa do Gmail (IMAP, só leitura), marca quem respondeu e e-mails que voltaram, e manda **1** follow-up educado após 7 dias sem resposta. |
| ⏰ **Todo dia sozinho** | `agendar` cria uma tarefa no Agendador do Windows para buscar (e, se quiser, enviar) todo dia. |
| 🤖 **IA opcional e gratuita** | Groq, Gemini ou Ollama (local) deixam resumo e carta mais naturais. Sem IA, tudo funciona com modelos de texto. |

---

## Como iniciar (passo a passo)

### Jeito fácil (Windows, sem saber programar)

1. Baixe/extraia a pasta do Job Radar (ou receba o `.zip` de alguém — veja
   [Compartilhar com outra pessoa](#compartilhar-com-outra-pessoa)).
2. Dê **dois cliques em `Iniciar Job Radar.bat`**. Na primeira vez ele:
   instala o Python se faltar (via `winget`), cria o ambiente, instala as dependências e o
   navegador que gera os PDFs (uns 5 minutos, precisa de internet) e cria um atalho
   **Job Radar** na Área de Trabalho. Das próximas vezes, só abre.
3. O navegador abre sozinho em <http://127.0.0.1:5000>: envie o currículo, escolha a área e
   conecte o Gmail em **⚙️ Configurações**. Deixe a janela preta aberta enquanto usa.

> Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações →
> Executar assim mesmo** (o `.bat` só chama o `scripts\iniciar.ps1`, que você pode ler).

Nada é hospedado na internet: o sistema roda só no seu computador e seus dados ficam nele.

### Jeito manual (qualquer sistema)

Pré-requisitos: **Python 3.11+** e **Git**. Tudo é gratuito e roda na sua máquina.

### 1. Instalar (uma vez só)

```bash
git clone https://github.com/IltonBJSilva/job-radar.git
cd job-radar
python -m venv venv
venv\Scripts\activate            # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
playwright install chromium      # navegador usado para buscar vagas e gerar os PDFs

copy .env.example .env           # Linux/macOS: cp .env.example .env
```

### 2. Montar o seu perfil (`config/candidato.yaml`)

Esse arquivo é a **única fonte** do currículo, da carta e do e-mail — o sistema só reordena e
destaca o que está nele. Fica fora do Git. Três jeitos de criar:

```bash
# a) Cadastro único: lê seu currículo (PDF/DOCX), o PDF do LinkedIn e seus repositórios do GitHub
python candidatar.py perfil --cv meu_curriculo.pdf --linkedin-pdf Profile.pdf \
    --github seu-usuario --linkedin https://www.linkedin.com/in/voce/ --portfolio https://voce.github.io/

# b) Pela interface: aba "Perfil" (mesma coisa, com revisão antes de salvar)

# c) Do zero, copiando o exemplo comentado
python candidatar.py iniciar
```

**Confira o arquivo depois** — a leitura de PDF erra (colunas, acentos do LaTeX). O que estiver
errado ali sai errado no currículo. Veja [O perfil em detalhe](#o-perfil-em-detalhe) para os campos
de IA e de estágio.

### 3. Abrir o sistema

```bash
venv\Scripts\activate
python candidatar.py app         # abre http://127.0.0.1:5000
```

1. Clique em **Buscar vagas novas** (radar + GitHub + Remotar + Gupy).
2. Faça o **swipe**: ❤️ / → quero, ✕ / ← descarto. Cada cartão mostra a % de compatibilidade.
3. Ao curtir, o sistema gera `saida/<empresa>_<vaga>/Curriculo_*.pdf` (2 páginas), a carta e o e-mail.
4. Na aba **Prontas**, confira os PDFs e clique em **Enviar prontas** — ou ligue o envio direto
   pelo coração (passo 5). A aba tem duas listas: **📤 Falta enviar** e **✅ Já enviadas** (com ✅ em
   cada linha). Vaga cuja empresa/e-mail já recebeu sua candidatura nos últimos 30 dias aparece com
   aviso e botão **Descartar** — o sistema nunca manda de novo para o mesmo lugar.
5. Na aba **Sem e-mail**, abra o anúncio (↗), candidate-se pelo site anexando o PDF e clique em
   **✓ Candidatei**. A vaga vai para **Enviadas** (dá para desmarcar). Isso não conta no limite diário
   de e-mails nem gera follow-up.

**Filtros (botão ⚙️ Filtros na tela de swipe):** país, idioma do anúncio, modalidade, região e
localização (`Uberlândia`, `MG`, `Minas Gerais`, `Portugal`...). O painel mostra quantas vagas passam
e quantas há em cada opção; cada cartão ganha etiquetas (🇧🇷 Brasil · MG · Sudeste · Remoto · Idioma: PT).
Sem descrição, o idioma vem do título e do país — vaga brasileira com título em inglês conta como
português, a não ser que o título seja claramente internacional ("Senior Engineer - Remote Work").

No começo tudo roda em **modo simulação**: cada e-mail vira um arquivo `.eml` em `saida/` para você
abrir e conferir. Nada sai da sua máquina.

### 4. Conectar o Gmail (grátis)

1. Ative a [verificação em duas etapas](https://myaccount.google.com/security).
2. Crie uma **senha de app** em <https://myaccount.google.com/apppasswords> (16 letras).
3. No `.env`:
   ```ini
   SMTP_USUARIO=seu@gmail.com
   SMTP_SENHA=abcdefghijklmnop     # a senha de APP, nunca a senha normal
   ENVIO_REAL=true                 # false = simulação
   EMAIL_COPIA_PARA_MIM=true       # recebe cópia de cada candidatura
   ```
4. Reinicie o `python candidatar.py app`. O topo da página passa de **MODO SIMULAÇÃO** para **ENVIO REAL**.

### 5. (Opcional) Coração que já envia

```ini
ENVIAR_AO_CURTIR=true
```

Curtir uma vaga **com e-mail** prepara o currículo e envia na hora. Vaga sem e-mail vai para a aba
**Sem e-mail**, com o PDF pronto para você anexar no site da empresa. Se você curtir várias seguidas,
o sistema espera 60–180 s entre um envio e outro (sem travar a tela) e respeita o limite diário.

### 6. (Opcional) Chaves grátis, rotina e avisos — tudo em ⚙️ Configurações

- **IA (Groq):** crie a chave em <https://console.groq.com/keys> e cole em *Chaves opcionais*. A IA escreve
  a carta e o e-mail de cada vaga; o **resumo do currículo continua sendo o seu** (há uma opção para a IA
  reescrevê-lo, mantendo sempre a parte de IA/agentes). Resposta que cite número, link ou e-mail que não
  estejam no seu perfil é descartada e volta o texto padrão.
- **Posts públicos de recrutadores (Tavily):** chave grátis em <https://app.tavily.com> (1.000 créditos/mês, sem
  cartão; cada busca gasta 1 e o sistema usa no máximo 6 por rodada) e ligue a fonte "Posts públicos de
  recrutadores". Quem já paga a Brave Search pode usar a chave dela (a Brave não tem mais plano grátis). Busca, sem login, posts tipo `"envie seu currículo" python
  Uberlândia` e só aceita os que têm e-mail em contexto de recrutamento. As vagas vão para o swipe.
- **Hunter.io:** chave grátis em <https://hunter.io>. Na aba **Empresas**, "📇 Procurar no Hunter" busca o
  e-mail de RH das empresas sem e-mail publicado (genérico de RH primeiro; senão, pessoa de recrutamento,
  confiança ≥ 70%, do domínio da empresa). Cada empresa gasta 1 busca do plano.
- **Rotina diária:** "Ligar rotina diária" cria uma tarefa no Agendador do Windows: todo dia busca vagas,
  lê as respostas no Gmail e manda 1 follow-up para quem não respondeu em 7 dias (opcional: enviar sozinho
  as mais compatíveis). Log em `data/rotina_<perfil>.log`.
- **Aviso no Telegram:** dentro do Foco regional, marque "📱 Avisar no Telegram" e o limite (padrão 75%).
  Usa `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` do `.env`; cada vaga é avisada uma vez.
- **Funil:** aba **📊 Funil**. Marque a etapa (entrevista, teste, proposta…) na página de cada vaga enviada.

Antes de cada envio, o sistema confere se a vaga ainda está aberta (GitHub, Gupy, Greenhouse, Lever e
LinkedIn); vaga fechada não recebe currículo. Na dúvida (site fora do ar), considera aberta.

### Principais opções do `.env`

| Variável | Padrão | Para quê |
|---|---|---|
| `ENVIO_REAL` | `false` | `true` envia de verdade; `false` só gera `.eml` |
| `ENVIAR_AO_CURTIR` | `false` | o coração prepara **e** envia |
| `SMTP_USUARIO` / `SMTP_SENHA` | — | Gmail + senha de app |
| `EMAIL_COPIA_PARA_MIM` | `false` | cópia de cada envio para você |
| `LIMITE_DIARIO_ENVIOS` | `30` | teto de e-mails por dia (inclui follow-ups) |
| `INTERVALO_MIN_SEG` / `INTERVALO_MAX_SEG` | `60` / `180` | espera aleatória entre envios |
| `DIAS_SEM_REPETIR_EMPRESA` | `30` | não manda de novo para a mesma empresa |
| `SCORE_MINIMO_AUTO` | `60` | compatibilidade mínima do modo `auto` |
| `IA_PROVEDOR` / `IA_API_KEY` | vazio | IA opcional (groq, gemini, ollama) |

---

## Várias pessoas, qualquer área

O sistema não é só para dev. Cada pessoa tem um **perfil** próprio, com currículo, Gmail, fila de
vagas e PDFs separados, e você troca no seletor **👤** no topo da página.

- **Criar:** 👤 → **+ Novo perfil…** → nome da pessoa → envie o currículo dela (PDF/DOCX, PDF do
  LinkedIn, GitHub) → confira → **⚙️ Configurações**.
- **Área pronta:** em Configurações, escolha a área (Desenvolvimento, **Cibersegurança**, Dados/BI,
  Infraestrutura/Cloud/Redes, Suporte, QA, Produto/Agilidade, Design/UX ou Outra). Isso preenche
  os termos de busca, os cargos que contam pontos e as fontes. Tudo continua editável.
- **Pontuação para outras áreas:** além de linguagens e cloud, a compatibilidade reconhece
  segurança (SIEM, SOC, Splunk, QRadar, pentest, firewall, EDR, IAM, ISO 27001, LGPD, NIST,
  Security+, CEH, CISSP…), redes e infraestrutura, dados/BI e QA. O que faltar, a pessoa
  escreve em **"Competências que o sistema talvez não conheça"** (ex.: SAP, AutoCAD).
- **Sites das empresas:** a fonte "Sites das empresas" visita a lista da aba **Empresas**
  (`config/empresas.example.yaml` + as que você adicionar), descobre onde cada uma publica vagas
  (`<empresa>.gupy.io`, Greenhouse, Lever — APIs públicas) e guarda o portal achado para ir direto
  nas próximas vezes. Só entram vagas com cargo, termo ou tecnologia do seu perfil.
- **Foco regional (liga/desliga):** em Configurações, marque **⭐ Foco regional** e escolha a cidade
  (aceita "udia", "BH"...). Com ele ligado: vagas da cidade aparecem primeiro no swipe com o selo
  **⭐ Sua cidade**, o LinkedIn também busca na cidade e as empresas de lá são visitadas primeiro.
  Desligado, tudo volta a ser ordenado só pela compatibilidade.
- **Busca pelos termos da pessoa:** LinkedIn, Catho e Indeed rodam **no computador**, com os termos
  do perfil; Gupy e Remotar também. O "Radar automático" (GitHub Actions) só traz vagas de dev,
  então vem desligado nas outras áreas.
- **E-mail de cada um:** o Gmail e a senha de app ficam no perfil. Em Configurações, o botão
  **🔌 Testar conexão** só faz login, sem enviar nada. Perfil novo começa em simulação.

Onde fica cada coisa: o perfil **principal** usa os caminhos de sempre (`config/candidato.yaml`,
`.env`, `data/candidaturas.db`, `saida/`); os outros ficam em `perfis/<id>/` (`candidato.yaml`,
`config.env`, `candidaturas.db`, `saida/`). Tudo fora do Git. Na linha de comando:
`python candidatar.py --perfil carla-souza status`.

### Compartilhar com outra pessoa

Dê dois cliques em **`Compartilhar Job Radar.bat`**. Ele gera `dist\JobRadar-<data>.zip` com o
sistema e um `LEIA-ME PRIMEIRO.txt`, **sem nenhum dado seu**: currículo, `.env`, senha de app,
perfis, vagas, PDFs, `curriculos_certificados/` e `venv/` ficam de fora. O script confere o
pacote antes de terminar, aborta se achar arquivo pessoal e avisa se o seu e-mail aparecer em
algum arquivo. A pessoa extrai, dá dois cliques em `Iniciar Job Radar.bat` e monta o perfil dela.

---

## O currículo enviado

- **Visual do Overleaf** (`resume.cls`): nome centralizado em caixa alta, seções com filete,
  cargo em negrito com a empresa à direita, data em itálico, tópicos com "·", fonte **CMU Serif**
  (a do LaTeX) embutida no PDF — sai igual em qualquer computador. Modelo em
  `candidatura/templates/curriculo.html`.
- **Sempre 2 páginas.** O gerador renderiza o PDF, conta as páginas e ajusta sozinho
  (`candidatura/documentos.py`): primeiro a fonte e o espaçamento; se ainda passar, tira **um tópico
  por vez**, do menos importante para o mais importante (projetos extras → tópicos das experiências
  mais antigas → …). Os tópicos já chegam ordenados por aderência à vaga, então sai sempre o menos
  relevante. Fica a versão mais completa que cabe, com a 2ª página cheia.
- **IA sempre em destaque.** Resumo com parágrafo de IA Generativa/Agentic AI, grupos de competências
  de IA, agentes e orquestração, e a seção **Projetos e Aplicações em Inteligência Artificial** — que
  nunca é cortada por completo.
- **Ordem das seções:** Resumo · Formação · Habilidades · Experiência · Projetos de IA · Projetos
  Selecionados · Certificações.

## O perfil em detalhe

Trechos do `config/candidato.yaml` que controlam o currículo:

```yaml
resumo: |                         # parágrafos separados por linha em branco
  Engenheiro de Software com experiência em ...

  Atuação também em Engenharia de IA Generativa (GenAI) e Agentic AI ...

habilidades:                      # cada grupo vira uma linha da tabela, na ordem em que aparece
  Engenharia de IA: [Generative AI, Agentic AI, LLMs, Multi-Agent Systems]
  Frameworks de Agentes: [LangGraph, LangChain, CrewAI]

projetos:
  - nome: Engenharia de Agentes e Orquestração Multiagente
    organizacao: Projetos Independentes   # aparece à direita (estilo experiência)
    periodo: "2026"
    ia: true                              # vai para a seção de IA (sempre aparece)
    itens: [ "Experimentação ...", "Estruturação ..." ]
  - nome: Sistema de Transferência Financeira
    tecnologias: [Python, Flask, SQLAlchemy]   # vira "Nome | Python, Flask, SQLAlchemy  [GitHub]"
    link: https://github.com/...
    descricao: Desenvolvimento de API REST ...

formacao:
  - curso: Bacharelado em Sistemas de Informação
    instituicao: Universidade Federal de Uberlândia (UFU)
    periodo: 2024 – Atual
    detalhe: "6º período · Previsão de conclusão: dezembro de 2028"   # opcional

links:
  certificados: https://github.com/voce/Certificados   # vira o link "Formação Complementar"
```

### Versão para vagas de estágio

Quando o **título da vaga** diz estágio/estagiário/intern, o sistema usa `variantes.estagio` no
currículo, na carta, no e-mail **e** na compatibilidade (sem perder pontos por você estar como Pleno).
A variante troca só as seções que declarar; o resto vem do perfil principal:

```yaml
variantes:
  estagio:
    pessoal: { titulo: "Estudante de Sistemas de Informação | Desenvolvimento de Software e IA" }
    resumo: |
      Graduando em Sistemas de Informação pela UFU, com previsão de conclusão em dezembro de 2028 ...
    habilidades: { ... }      # lista mais enxuta, sem cara de sênior
    experiencias: [ ... ]     # tópicos mais curtos
    projetos: [ ... ]         # mantenha 1 projeto com ia: true para a IA continuar em destaque
    preferencias:
      senioridade: Estágio
      cargos_alvo: [desenvolvimento, software, backend, python, dados, ia]  # só vale se o título já diz "estágio"
```

Seções que podem ser trocadas: `resumo`, `habilidades`, `experiencias`, `projetos`, `formacao`,
`certificacoes`, `idiomas`, `assinatura_email` (e chaves de `pessoal`, `links`, `preferencias`).

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
2. **Compatibilidade (0–100%)** (em vaga de estágio, calculada com a variante `estagio`): 55% cobertura técnica (tecnologia no título pesa em dobro; inglês/git
   pesam pouco) + 45% aderência do cargo aos seus `cargos_alvo`.
3. **Currículo**: suas habilidades que a vaga pede ficam em **negrito** e no início do grupo; as conquistas
   de cada experiência e os projetos são reordenados pela aderência; o que menos importa é o primeiro a
   sair se não couber em 2 páginas.
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
- **IA (se ligada):** recebe nome, cidade, experiências e projetos (nunca telefone/e-mail). Por padrão só escreve
  carta e e-mail; número, link ou e-mail que não estejam no seu perfil fazem a resposta ser descartada.
- **LinkedIn:** o sistema nunca entra na sua conta nem raspa perfis. Posts entram colados por você ou pela busca
  pública (Tavily/Brave), e só com e-mail que o próprio recrutador publicou. A descrição da vaga vai
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
│   ├── perfil.py            # Lê config/candidato.yaml (+ variante de estágio)
│   ├── importar_perfil.py   # Cadastro único: currículo/LinkedIn/GitHub -> perfil
│   ├── compatibilidade.py   # Extração de tecnologias + score estilo ATS
│   ├── adaptador.py         # Currículo/carta/e-mail adaptados (sem inventar)
│   ├── ia.py                # IA opcional: Groq / Gemini / Ollama
│   ├── contato.py           # Baixa a descrição da vaga e acha e-mails
│   ├── localizacao.py       # País, idioma, modalidade, UF e região de cada vaga (filtros do swipe)
│   ├── localidades.py       # Municípios (IBGE) e países: entende "udia", "BH", "Spain"...
│   ├── areas.py             # Áreas prontas (dev, cibersegurança, dados...), fontes e foco regional
│   ├── vagas_empresas.py    # Vagas abertas no portal de cada empresa (Gupy, Greenhouse, Lever)
│   ├── posts.py             # Lê post de recrutador colado (cargo, empresa, e-mail, local)
│   ├── busca_posts.py       # Posts públicos de recrutadores via Tavily ou Brave (opcional)
│   ├── hunter.py            # E-mail de RH das empresas via Hunter.io (opcional)
│   ├── alertas.py           # Aviso no Telegram de vaga boa na sua cidade
│   ├── funil.py             # Funil por fonte (enviadas, respostas, entrevistas)
│   ├── rotina.py            # Rotina diária no Agendador do Windows
│   ├── fontes.py            # GitHub vagas + Remotar
│   ├── documentos.py        # HTML → PDF (Chromium) + ajuste automático para 2 páginas
│   ├── envio.py             # SMTP com tratamento de erros
│   ├── repositorio.py       # Fila em data/candidaturas.db (fora do Git)
│   ├── servico.py           # Orquestração + limites anti-spam
│   └── templates/           # Currículo (estilo Overleaf), carta e fontes CMU Serif (licença OFL)
├── web/                     # Interface Flask (swipe, fila, perfis, configurações)
├── scripts/                 # iniciar.ps1 e compartilhar.ps1 (chamados pelos .bat da raiz)
├── Iniciar Job Radar.bat    # dois cliques: instala na 1ª vez e abre
├── Compartilhar Job Radar.bat  # gera um .zip sem seus dados
├── core/                    # Regras de filtro do radar (cargo, cidade, idioma, score)
├── scrapers/                # 11 fontes de vagas
├── database/                # SQLite do radar (data/jobs.db, versionado pelo robô)
├── notifier/                # Telegram: alertas, digest diário, 👍/👎
├── config/candidato.example.yaml
└── tests/                   # 711 testes (CI a cada push)
```

**Privacidade:** `config/candidato.yaml`, `data/candidaturas.db`, `saida/`, `perfis/` e `.env` estão no
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
