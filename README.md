# 🤖 HallyuBot V3 — Redação Automatizada com IA

O **HallyuBot** é um bot de Discord autônomo que atua como um **Editor-Chefe impulsionado por IA** para portais e comunidades de cultura asiática (K-Pop, K-Drama, C-Drama). Ele varre automaticamente sites de notícias e redes sociais, tria as informações usando o GPT-4o-mini (atribuindo uma "nota de temperatura" de 1 a 10), envia alertas urgentes no Discord e até redige o roteiro para vídeos curtos com 1 clique.

---

## ✨ Features Principais

- **📡 Radar de Notícias (RSS & Scraping):** Varre automaticamente (a cada 2h) sites como Soompi, Koreaboo e Reddit.
- **📱 Sensores Sociais:** Integração com Apify e YouTube Data API v3 para monitorar Instagram, TikTok e YouTube (1x ao dia).
- **🧠 Triagem Inteligente:** Toda nova postagem passa pela OpenAI (GPT-4o-mini) para avaliar a relevância (1 a 10) com base no potencial de viralização.
- **🚨 Plantão Urgente Automático:** Notícias nota 9-10 (escândalos, disbands, mortes) disparam um alerta imediato com `@everyone` ou `@here`.
- **📋 Digest Interativo:** Notícias nota 5-8 são agrupadas num resumo periódico no Discord.
- **📝 Geração de Roteiros (1 Clique):** Todas as notificações possuem um botão interativo do Discord. Basta clicar em "📝 Fazer Roteiro" e a IA redige um texto pronto (com Call To Action e ganchos) baseado em templates validados.
- **💡 Motor de Ideias:** Comando `/ideia` para gerar ganchos virais para o TikTok/Reels quando o noticiário estiver calmo.

---

## 🚀 Quick Start (Como rodar localmente)

### 1. Clonar e Instalar Dependências
```bash
git clone https://github.com/SEU-USUARIO/HallyuBot.git
cd HallyuBot

# Crie um ambiente virtual (opcional, mas recomendado)
python -m venv venv
# No Windows:
venv\Scripts\activate
# No Mac/Linux:
source venv/bin/activate

# Instale os requisitos
pip install -r requirements.txt
```

### 2. Configurar Variáveis de Ambiente
Renomeie o arquivo `.env.example` para `.env` e preencha com suas chaves:
```bash
cp .env.example .env
```

No arquivo `.env`, você precisará das seguintes credenciais:
- `DISCORD_TOKEN`: O token do seu bot criado no Discord Developer Portal.
- `CANAL_URGENTE_ID` / `CANAL_RESUMO_ID`: IDs dos canais de texto do seu servidor.
- `OPENAI_API_KEY`: Para o cérebro do Editor-Chefe e Roteirista (GPT-4o-mini).
- `APIFY_API_TOKEN`: Para capturar o TikTok e Instagram (plano gratuito da Apify serve).
- `YOUTUBE_API_KEY`: API Oficial do Google (YouTube Data API v3).

### 3. Iniciar o Bot
```bash
python main.py
```
Se for a primeira vez, ele criará o banco de dados `hallyubot.db` automaticamente dentro da pasta `data/`.

---

## 💻 Comandos (Slash Commands do Discord)

Embora o bot opere com laços 100% autônomos de varredura e triagem em background, você pode invocar ações manualmente no Discord:

| Comando | Descrição |
|---------|-----------|
| `/status` | Exibe o painel de saúde (quantas notícias na base, taxa de aproveitamento, sensores sociais). |
| `/varrer` | Força uma varredura manual de todos os feeds RSS cadastrados. |
| `/social` | Força uma varredura manual dos perfis (IG, TT, YT) ignorando a trava de 1x/dia. |
| `/triar` | Passa todas as notícias pendentes pela avaliação da IA. |
| `/roteiro`| Pega as 3 melhores notícias (nota 5+) não utilizadas nas últimas 48h e gera roteiros. |
| `/ideia` | Gera 3 ideias/formatos de vídeos virais baseados em tendências do nicho. |
| `/analisar`| (Requer Link/Texto) Analisa manualmente qualquer fofoca avulsa que você enviar. |

---

## ⚙️ Configuração das Fontes de Dados

Se você quiser adicionar ou remover sites e contas monitoradas, o projeto é altamente modular:

**Para sites de notícias (RSS):**
Edite a variável `FONTES_RSS` no arquivo `scraper.py`.

**Para perfis em redes sociais:**
Edite as listas no começo do arquivo `social_scraper.py`:
- `CONTAS_INSTAGRAM = ["soompi", "yg_ent_official", ...]`
- `CONTAS_TIKTOK = ["koreaboo", "allkpop", ...]`
- `CANAIS_YOUTUBE = ["@HYBELABELS", "@SMTOWN", ...]`

---

## 🌡️ Termômetro da IA (Critérios de Triagem)

A IA está calibrada para classificar a urgência e relevância de conteúdos da cultura Hallyu. Veja como ela pensa:

- 🟢 **Notas 1-3 (Descartadas):** Rotina, selfies em aeroportos, listas de beleza. Posts estéticos de redes sociais morrem aqui.
- 🟡 **Notas 4-6 (Relevante):** Teasers de MV, fotos de revistas, atualizações de agenda. Vão pro Digest Interativo no Discord.
- 🟠 **Notas 7-8 (Importante):** Datas de comeback de grupos fortes, escândalos menores, encerramento de contrato de atores conhecidos.
- 🔴 **Notas 9-10 (Plantão Urgente):** Namoro confirmado (Idols A-List), disbands, saída de membros de grupos ativos, crimes, ou anúncios do nível "BTS/BLACKPINK voltou".

---

## 📂 Estrutura do Projeto

```text
HallyuBot/
├── main.py             # Orquestrador do bot, slash commands e auto-loops
├── ai_triagem.py       # Lógica do "Editor-chefe" comunicando com OpenAI
├── scraper.py          # Coletor de dados dos feeds RSS (Plano A)
├── social_scraper.py   # Coletor de redes via Apify e YouTube Data API
├── database.py         # Configuração de tabelas SQLite (notícias, tags, tracking)
├── .env                # Variáveis de ambiente (Chaves de APIs)
├── data/               # (Gerado auto) Armazena o banco de dados hallyubot.db
└── templates/          # Arquivos .md usados como prompt para geração de roteiros
```

---
*Projeto arquitetado e desenvolvido em 2026. Pensado para simplificar e dar previsibilidade ao fluxo incessante de notícias de K-Pop e K-Drama.*
