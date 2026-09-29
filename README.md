<div align="center">

<!-- ![JobRadar](assets/cover.png) -->

# 📡 JobRadar
### Monitor Automatizado de Vagas de Dados & BI

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Scraping-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Banco%20versionado-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Cron-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)
![Tests](https://img.shields.io/badge/testes-73%20passing-success?style=for-the-badge)
![Status](https://img.shields.io/badge/status-em%20produção-success?style=for-the-badge)

**Autora:** Liliam Kezia Oliveira Souza

</div>

---

## 💎 Proposta de Valor

> Em cidade pequena, vaga boa de Dados/BI aparece pouco e some rápido — quem checa o board duas vezes por dia perde pra quem checou na primeira hora. **JobRadar** é um sistema de monitoramento contínuo que substitui essa checagem manual: varre **8 fontes** a cada **3 horas**, filtra por cargo/cidade/mercado/idioma com três níveis de confiança, pontua cada vaga por relevância e notifica no Telegram — rodando de graça, sem servidor próprio, 24 horas por dia.

---

## 🗂️ Sumário

- [Visão Geral e Resultados](#-visão-geral-e-resultados)
- [Como Funciona (Pipeline)](#-como-funciona-pipeline)
- [Arquitetura Técnica](#%EF%B8%8F-arquitetura-técnica)
- [Estrutura do Repositório](#-estrutura-do-repositório)
- [Como Executar Localmente](#-como-executar-localmente)
- [Testes Automatizados](#-testes-automatizados)

---

## 📄 Visão Geral e Resultados

O JobRadar é um sistema que opera **sem intervenção manual**, projetado para garantir máxima eficiência e custo zero de infraestrutura. 

Em testes reais (entre 07 e 15 de agosto), o sistema processou **1.052 vagas únicas**. Os dados expõem as características da arquitetura atual:

| Métrica / Achado | Valor |
|---|---|
| 📊 **Vagas processadas** (deduplicadas) | **1.052** |
| 🔗 **Concentração** (maior volume no LinkedIn) | **89,5%** |
| 🧪 **Testes automatizados** (CI a cada push) | **73** |
| 🌎 **Fontes monitoradas** (em paralelo) | **8** |
| ⏱️ **Frequência de checagem** | **a cada 3h** |
| 💰 **Custo de infraestrutura** | **R$ 0** |

> **Nota sobre o LinkedIn:** A concentração no LinkedIn é um risco medido. Como o endpoint utilizado não é oficial e há risco de bloqueio, a estratégia atual foca em otimizar o rendimento das fontes secundárias (paginação profunda) em vez de apenas adicionar novas fontes.

---

## 📸 Como a Notificação Chega pra Você

<!-- ![Notificação no Telegram](assets/screenshots/notificacao.png) -->

Vagas de **alta relevância** chegam em tempo real, informando o motivo da aprovação, o nível de senioridade e o link direto. Vagas regulares entram em um **resumo diário (digest)**, ranqueadas por relevância, evitando sobrecarregar seu Telegram com notificações não solicitadas.

---

## 🧭 Como Funciona (Pipeline)

| Etapa | Descrição |
|---|---|
| 🔍 **Busca** | Varre as fontes em paralelo, aplicando rodízio de termos para controlar o escopo e evitar limites de requisição. |
| 🎯 **Filtra** | Analisa cargo, qualificadores de dados, ferramentas, cidade, mercado (remoto/presencial) e idioma. |
| ⭐ **Pontua** | Atribui um score de 0 a 10 para cada vaga com base em sinais claros (cargo, ferramenta, senioridade), sem o uso de IA. |
| 🔄 **Deduplica** | Evita vagas repetidas cruzando link, empresa e título (útil para vagas publicadas em múltiplas fontes). |
| 📲 **Notifica** | Envia alertas imediatos para vagas *top-tier* e um resumo diário ranqueado para as demais. |
| 🧠 **Aprende** | Coleta feedback através de botões 👍/👎 no Telegram, utilizando os dados para mensurar precisão e refinar os filtros. |

---

## 🏗️ Arquitetura Técnica

- **Filtro Semântico (3 Níveis):** Um cargo inequívoco é aprovado de imediato. Cargos ambíguos (ex: "Business Analyst") exigem um qualificador da área de dados. Ferramentas (ex: "Power BI") necessitam estar acompanhadas de termos de cargo. Nenhuma vaga é aprovada por palavra-chave solta.
- **Score Algorítmico:** Baseado em 5 sinais conhecidos (cargo, ferramenta, senioridade, mercado, idioma). Os pesos foram calibrados contra um histórico real de banco de dados.
- **Zero Infraestrutura (Serverless):** Utiliza **GitHub Actions** como motor de Cron e **SQLite** (versionado no próprio Git) como banco de dados. O histórico de vagas é mantido nos commits do repositório.
- **Resiliência e Tolerância a Falhas:** Nenhuma vaga é marcada como "vista" sem a confirmação de envio da notificação. O sistema emite alertas automáticos caso 50% das fontes falhem e envia um *heartbeat* diário confirmando sua atividade.
- **CI / CD (Testes em Produção):** Com 73 testes em CI, cada cenário reflete um bug real corrigido no histórico do projeto, garantindo robustez contra regressões.

---

## 📁 Estrutura do Repositório

```text
job-radar/
├── README.md
├── requirements.txt
├── main.py                     # Motor principal: executa o ciclo de busca por perfil
├── core/
│   ├── perfis.py               # Configuração Brasil vs Internacional
│   ├── config.py / config_intl.py # Configurações, cargos, termos e pesos
│   └── job.py                  # Classe Job, regras de filtro e score
├── relatorio_precisao.py       # Estatísticas de vagas aprovadas/notificadas
├── database/
│   └── database.py             # SQLite: deduplicação, fila de digest e metadados
├── notifier/
│   └── telegram.py             # Integração Telegram (notificações, digest e botões)
├── scrapers/                   # Módulos de extração (LinkedIn, Gupy, Indeed, etc.)
├── utils/
│   └── filtro.py               # Funções de auxílio para filtragem
├── tests/                      # 73 casos de teste automatizados
├── data/
│   └── jobs.db                 # Banco SQLite versionado
└── .github/workflows/
    ├── jobradar.yml            # Workflow de cron job (execução a cada 3h)
    └── testes.yml              # CI para validação de PRs e pushes
```

---

## 💻 Como Executar Localmente

### Pré-requisitos
- Python 3.11+
- Git

### Passos de Instalação

1. Clone o repositório:
```bash
git clone https://github.com/IltonBJSilva/job-radar.git
cd job-radar
```

2. Crie e ative um ambiente virtual:
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python -m venv venv
source venv/bin/activate
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

4. Configure as Variáveis de Ambiente:
Crie um arquivo `.env` na raiz do projeto contendo as chaves do seu bot do Telegram (criado via [@BotFather](https://t.me/BotFather)):

```env
TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=seu_chat_id_aqui
```

5. Execute o projeto:
```bash
python main.py --perfil brasil internacional --once
```

---

## 🧪 Testes Automatizados

O sistema conta com uma suíte de 73 testes automatizados (parametrizados) que validam desde a camada de filtro e parsing de callbacks do Telegram até os relatórios de precisão.

Para executá-los localmente:
```bash
pytest tests/ -v
```
*Esses testes são executados automaticamente a cada push via GitHub Actions.*

---

<div align="center">

*Projeto portfólio de automação de dados utilizando Python, Playwright, SQLite, GitHub Actions e engenharia avançada de filtros (sem uso de Machine Learning).*

</div>
