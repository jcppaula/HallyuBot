# Documentação do Projeto: HallyuBot - Automação Editorial de Cultura Asiática (V3)

Este documento detalha a estrutura, tecnologias e lógica do bot para Discord desenvolvido para automação de scraping de notícias, gestão de calendário e descoberta de novos criadores no nicho Hallyu (K-pop, K-dramas e Cultura Chinesa).

## 1. Visão Geral e Infraestrutura
* **Propósito:** Bot de Discord atuando como "sala de redação automatizada".
* **Hardware de Desenvolvimento:** AMD Ryzen 3, 8GB RAM, 1TB SSD M.2 (Operação 24/7 Local).
* **Stack Base:** Python 3.10+, VS Code (Extensão Antigravity para IA em código, SQLite Viewer).

## 2. Bibliotecas Principais e APIs
* **Bibliotecas Python:** `discord.py` (Interface), `BeautifulSoup4` e `requests` (Extração Plano B), `feedparser` (Leitura RSS Plano A), `apscheduler` (Agendamento de tarefas), `sqlite3` (Banco de Dados Local).
* **APIs Integradas:**
    1. **Discord API:** Token de comunicação para o bot.
    2. **Google Gemini API (1.5 Flash) ou OpenAI (GPT-4o mini):** Cérebro de processamento, resumo e roteirização.
    3. **YouTube Data API v3:** Monitoramento semanal de novos canais e trends.
    4. **Apify API:** Scraping focado em hashtags do Instagram e TikTok.

## 3. Fontes de Dados Mapeadas (Target URLs)
A coleta primária é dividida em três pilares para garantir o equilíbrio de cobertura:

**Pilar 1: K-Pop**
* Soompi (Música): `https://www.soompi.com/category/music/feed` (RSS)
* Allkpop: `https://www.allkpop.com` (Plano B - BeautifulSoup)
* Koreaboo: `https://www.koreaboo.com/feed/` (RSS)
* Reddit: `https://www.reddit.com/r/kpop/top.rss` (RSS)

**Pilar 2: K-Dramas**
* MyDramaList: `https://mydramalist.com/articles` (Plano B - BeautifulSoup)
* Soompi (TV/Filmes): `https://www.soompi.com/category/tv-film/feed` (RSS)
* Reddit: `https://www.reddit.com/r/KDRAMA/top.rss` (RSS)

**Pilar 3: Cultura Chinesa (C-Dramas/C-Pop)**
* DramaPanda: `https://dramapanda.com/feed` (RSS)
* JayneStars: `https://www.jaynestars.com/feed/` (RSS)
* Reddit: `https://www.reddit.com/r/CDrama/top.rss` (RSS)

## 4. Arquitetura de Dados e Resiliência (Boas Práticas Implementadas)
Para garantir que o bot seja à prova de falhas:
* **Upsert de Banco de Dados:** Uso de restrição `UNIQUE` na coluna de URLs da tabela SQLite. Inserções usam `INSERT OR IGNORE` para evitar envio de notícias duplicadas caso o sistema seja reiniciado.
* **Engenharia de Prompt Modular (Snippets):** O código constrói os prompts em blocos separados (`REGRA_TOM_DE_VOZ`, `REGRA_FORMATACAO`, `BASE_DE_FATOS`) antes de enviar para a IA, evitando confusão sistêmica.
* **A Regra "Zero vs. Nulo":** Instrução expressa no System Prompt da IA: *"NUNCA invente ou presuma dados. Se a notícia original não mencionar uma data, nome ou quantidade, responda com 'informação não disponível'."*

## 5. Módulos de Operação

### Módulo 1: Funil de Notícias Diário
* **Radar (1h/1h):** Lê novos links. A IA atribui um "Score de Temperatura" (1 a 10). Notas 9 e 10 geram alerta de emergência taggeando a usuária no `#plantao-urgente`.
* **Resumo Balanceado (08h, 14h, 20h):** Envia ao canal `#resumo-diario` um roteiro pronto de K-pop, um de K-Drama e um de Cultura Chinesa.

### Módulo 2: O Oráculo (Monitor de Eventos)
* **Objetivo:** Rastrear datas (Comebacks, Enlistments militares, Estreias de Doramas).
* **Ação:** A IA detecta anúncios de datas nas notícias e alimenta a tabela `calendario_hallyu`. Alertas prioritários são emitidos caso uma data já mapeada seja alterada ou cancelada.

### Módulo 3: Discovery Pipeline (Caçador de Tendências)
* **Objetivo:** Descobrir novos criadores ou tendências asiáticas no YouTube, IG e TikTok.
* **Rotina:** Execução semanal de madrugada (Domingos).
* **Mecanismo:** Utiliza a YouTube API (ordenando por vídeos recém-publicados mais vistos do nicho) e a Apify API (varrendo hashtags como #dorameiras, #kpopbrasil). Perfis em ascensão que não estão no banco de dados geram um relatório de recomendação para a criadora.
