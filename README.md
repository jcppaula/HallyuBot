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

## 🚀 Como Rodar o HallyuBot (3 Opções)

Você pode rodar este bot no seu próprio computador ou deixá-lo 24/7 na nuvem. Siga o guia que melhor se adapta à sua necessidade:

### Opção 1: Rodar Localmente (No seu PC para testes)
Ideal para desenvolver, testar ou deixar rodando num computador que não desliga na sua casa.

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/SEU-USUARIO/HallyuBot.git
   cd HallyuBot
   ```
2. **Crie o ambiente e instale as dependências:**
   ```bash
   python -m venv venv
   # No Windows:
   venv\Scripts\activate
   # No Mac/Linux:
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Configure as senhas:**
   Copie o arquivo `.env.example` para `.env` e preencha suas chaves (Discord, OpenAI, Apify, YouTube).
4. **Ligue o Bot:**
   ```bash
   python main.py
   ```

---

### Opção 2: Rodar na Railway (Nuvem "Mágica" / Fácil)
A [Railway](https://railway.com/) é a plataforma mais fácil para hospedar bots. Ela custa ~$5/mês e o deploy é automático via GitHub.

1. Faça login na Railway com seu GitHub.
2. Clique em **New Project** > **Deploy from GitHub repo** e selecione o `HallyuBot`.
3. Na aba **Variables**, adicione todas as chaves que estariam no seu `.env` (`DISCORD_TOKEN`, `OPENAI_API_KEY`, etc).
4. **⚠️ CRÍTICO:** Para não perder o banco de dados quando o bot reiniciar, vá na aba **Volumes**, crie um "Persistent Volume" e monte ele no caminho `/app/data` (ou a pasta local onde o `hallyubot.db` é criado).
5. O bot vai subir sozinho e atualizar automaticamente sempre que você fizer um `git push` no GitHub.

---

### Opção 3: Rodar numa VPS Clássica (ex: Hostinger / Ubuntu)
A [Hostinger KVM](https://www.hostinger.com/br/servidor-vps) oferece servidores Linux raiz a partir de ~R$ 30/mês. É a melhor opção se você quiser ter os arquivos físicos na sua máquina sem risco de exclusão por restarts.

1. Acesse sua VPS via SSH:
   ```bash
   ssh root@IP_DA_SUA_VPS
   ```
2. Instale o Python e baixe o seu código:
   ```bash
   sudo apt update && sudo apt install python3 python3-venv git npm -y
   git clone https://github.com/SEU-USUARIO/HallyuBot.git
   cd HallyuBot
   ```
3. Configure o bot:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   nano .env  # Preencha suas senhas e salve (Ctrl+X, Y, Enter)
   ```
4. Mantenha o bot vivo para sempre com o **PM2**:
   ```bash
   sudo npm install pm2 -g
   pm2 start main.py --name "HallyuBot" --interpreter ./venv/bin/python
   pm2 save
   pm2 startup
   ```

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
