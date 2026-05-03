"""
=============================================
HallyuBot V3 - Módulo de Scraping (Radar de Notícias)
=============================================
Script responsável por varrer as fontes de notícias mapeadas na
documentação e popular o banco de dados local.

Plano A: Leitura via RSS com feedparser (fontes com feed XML disponível).
Plano B: Scraping com BeautifulSoup (fontes sem RSS — será implementado depois).

Este script roda de forma independente por enquanto.
Não possui agendamento automático (apscheduler será ligado em fase futura).
"""

import feedparser
import sqlite3
import os
import sys
import time
import random
import requests
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Corrige encoding do terminal no Windows (suporte a emojis e acentos)
sys.stdout.reconfigure(encoding="utf-8")

# =============================================
# Importações futuras para o Plano B (BeautifulSoup)
# =============================================
# from bs4 import BeautifulSoup
# import requests
# As funções de scraping com BeautifulSoup serão implementadas
# na próxima fase para os sites que não oferecem RSS:
#   - Allkpop (https://www.allkpop.com)
#   - MyDramaList (https://mydramalist.com/articles)

# Caminho do banco de dados (mesmo usado no database.py)
CAMINHO_BD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hallyubot.db")

# =============================================
# Dicionário de Fontes RSS — Mapeadas na Documentação V3
# =============================================
# Cada fonte contém: nome legível, URL do feed, e pilar editorial.
# Os três pilares garantem o equilíbrio de cobertura exigido pela doc.
FONTES_RSS = [
    # --- PILAR 1: K-Pop ---
    {
        "nome": "Soompi (Música)",
        "url": "https://www.soompi.com/category/music/feed",
        "pilar": "K-Pop"
    },
    {
        "nome": "Koreaboo",
        "url": "https://www.koreaboo.com/feed/",
        "pilar": "K-Pop"
    },
    {
        "nome": "Reddit r/kpop",
        "url": "https://www.reddit.com/r/kpop/top.rss",
        "fallbacks": [
            "https://old.reddit.com/r/kpop/top/.rss?t=day",
            "https://www.reddit.com/r/kpop/new/.rss",
        ],
        "pilar": "K-Pop"
    },

    # --- PILAR 2: K-Dramas ---
    {
        "nome": "Soompi (TV/Filmes)",
        "url": "https://www.soompi.com/category/tvfilm/feed",
        "fallbacks": [
            "https://www.soompi.com/category/tv-film/feed",
            "https://www.soompi.com/feed",
        ],
        "pilar": "K-Drama"
    },
    {
        "nome": "Reddit r/KDRAMA",
        "url": "https://www.reddit.com/r/KDRAMA/top.rss",
        "fallbacks": [
            "https://old.reddit.com/r/KDRAMA/top/.rss?t=day",
            "https://www.reddit.com/r/KDRAMA/new/.rss",
        ],
        "pilar": "K-Drama"
    },

    # --- PILAR 3: Cultura Chinesa (C-Dramas/C-Pop) ---
    {
        "nome": "DramaPanda",
        "url": "https://dramapanda.com/feed",
        "fallbacks": [
            "https://dramapanda.com/feed/",
            "https://www.dramapanda.com/feed/",
        ],
        "html_fallback": "https://dramapanda.com/",
        "pilar": "Cultura Chinesa"
    },
    {
        "nome": "JayneStars",
        "url": "https://www.jaynestars.com/feed/",
        "pilar": "Cultura Chinesa"
    },
    {
        "nome": "Reddit r/CDrama",
        "url": "https://www.reddit.com/r/CDrama/top.rss",
        "fallbacks": [
            "https://old.reddit.com/r/CDrama/top/.rss?t=day",
            "https://www.reddit.com/r/CDrama/new/.rss",
        ],
        "pilar": "Cultura Chinesa"
    },
]

HEADERS_RSS = {
    "User-Agent": (
        "HallyuBot/3.0 (+https://github.com/) "
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
}


def baixar_e_parsear_feed(url_feed):
    """Baixa o RSS com headers completos e devolve o objeto parseado."""
    resposta = requests.get(url_feed, headers=HEADERS_RSS, timeout=20)
    resposta.raise_for_status()
    return feedparser.parse(resposta.content)


def coletar_home_html(url_home, nome_fonte, pilar, limite=20):
    """Extrai noticias da pagina inicial quando o RSS da fonte falha."""
    resposta = requests.get(url_home, headers=HEADERS_RSS, timeout=20)
    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")
    noticias = []
    vistos = set()

    for link_tag in soup.select("h1 a, h2 a, h3 a, article a"):
        titulo = link_tag.get_text(" ", strip=True)
        link = urljoin(url_home, link_tag.get("href", "").strip())

        if not titulo or not link.startswith("http"):
            continue
        if len(titulo) < 12 or link in vistos:
            continue

        vistos.add(link)
        noticias.append({
            "titulo": titulo,
            "url": link,
            "fonte": nome_fonte,
            "pilar": pilar,
            "data_publicacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        if len(noticias) >= limite:
            break

    return noticias

# =============================================
# Fontes para Plano B (BeautifulSoup) — Implementação futura
# =============================================
# FONTES_BS4 = [
#     {
#         "nome": "Allkpop",
#         "url": "https://www.allkpop.com",
#         "pilar": "K-Pop"
#     },
#     {
#         "nome": "MyDramaList",
#         "url": "https://mydramalist.com/articles",
#         "pilar": "K-Drama"
#     },
# ]


def extrair_data_publicacao(entrada):
    """
    Extrai e formata a data de publicação de uma entrada do feed RSS.
    Feedparser retorna a data em 'published_parsed' como struct_time.
    Caso não exista, retorna a data/hora atual como fallback.

    Args:
        entrada: Um objeto de entrada do feedparser.

    Returns:
        String formatada com a data (YYYY-MM-DD HH:MM:SS).
    """
    if hasattr(entrada, "published_parsed") and entrada.published_parsed:
        # Converte a struct_time do feedparser para string formatada
        return datetime(*entrada.published_parsed[:6]).strftime("%Y-%m-%d %H:%M:%S")
    elif hasattr(entrada, "updated_parsed") and entrada.updated_parsed:
        # Algumas fontes usam 'updated' ao invés de 'published'
        return datetime(*entrada.updated_parsed[:6]).strftime("%Y-%m-%d %H:%M:%S")
    else:
        # Fallback: usa a data/hora da coleta
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def coletar_feed_rss(fonte):
    """
    Lê um feed RSS usando o feedparser e retorna uma lista de notícias
    extraídas com titulo, link, data_publicacao, fonte e pilar.

    Args:
        fonte: Dicionário com 'nome', 'url' e 'pilar' da fonte.

    Returns:
        Lista de dicionários, cada um representando uma notícia.
    """
    noticias = []
    nome_fonte = fonte["nome"]
    pilar = fonte["pilar"]
    urls_para_tentar = [fonte["url"]] + fonte.get("fallbacks", [])

    print(f"  📡 Lendo feed: {nome_fonte}...", end=" ")

    try:
        feed = None
        ultimo_erro = None
        url_usada = None

        for tentativa, url_feed in enumerate(urls_para_tentar, 1):
            try:
                feed_tentativa = baixar_e_parsear_feed(url_feed)
                if feed_tentativa.entries:
                    feed = feed_tentativa
                    url_usada = url_feed
                    break
                ultimo_erro = getattr(feed_tentativa, "bozo_exception", "sem entradas")
            except Exception as e:
                ultimo_erro = e

            if tentativa < len(urls_para_tentar):
                time.sleep(1)

        # Verifica se o feed retornou entradas válidas
        if not feed:
            html_fallback = fonte.get("html_fallback")
            if html_fallback:
                try:
                    noticias_html = coletar_home_html(html_fallback, nome_fonte, pilar)
                    if noticias_html:
                        print(f"✅ {len(noticias_html)} entradas encontradas (HTML fallback).")
                        return noticias_html
                except Exception as e:
                    ultimo_erro = e

            detalhe = str(ultimo_erro)[:120] if ultimo_erro else "sem detalhe"
            print(f"⚠️  Feed com problemas ou inacessível ({detalhe}).")
            return noticias

        # Itera pelas entradas (artigos) do feed
        for entrada in feed.entries:
            # Extrai o título (limpa espaços extras)
            titulo = entrada.get("title", "Sem título").strip()

            # Extrai o link da notícia
            link = entrada.get("link", "").strip()

            # Ignora entradas sem link (não temos como fazer upsert sem URL)
            if not link:
                continue

            # Extrai a data de publicação formatada
            data_pub = extrair_data_publicacao(entrada)

            # Monta o dicionário da notícia
            noticias.append({
                "titulo": titulo,
                "url": link,
                "fonte": nome_fonte,
                "pilar": pilar,
                "data_publicacao": data_pub
            })

        sufixo = "" if url_usada == fonte["url"] else " (fallback)"
        print(f"✅ {len(noticias)} entradas encontradas{sufixo}.")

    except Exception as e:
        print(f"❌ Erro ao ler feed: {e}")

    return noticias


def salvar_no_banco(noticias):
    """
    Salva uma lista de notícias no banco de dados SQLite.
    Usa INSERT OR IGNORE para implementar a regra de upsert:
    se a URL já existe no banco, a notícia é ignorada silenciosamente.

    Args:
        noticias: Lista de dicionários com dados das notícias.

    Returns:
        Tupla (novas, ignoradas) com a contagem de cada operação.
    """
    novas = 0
    ignoradas = 0

    try:
        # Conecta no banco de dados
        conexao = sqlite3.connect(CAMINHO_BD)
        cursor = conexao.cursor()

        for noticia in noticias:
            # INSERT OR IGNORE: se a URL já existe (UNIQUE), o registro
            # é silenciosamente ignorado, sem gerar erro.
            # O status recebe 'pendente_avaliacao' pois a IA ainda não processou.
            cursor.execute("""
                INSERT OR IGNORE INTO noticias
                    (titulo, url, fonte, pilar, data_publicacao, status)
                VALUES
                    (?, ?, ?, ?, ?, 'pendente_avaliacao')
            """, (
                noticia["titulo"],
                noticia["url"],
                noticia["fonte"],
                noticia["pilar"],
                noticia["data_publicacao"]
            ))

            # rowcount == 1 significa que a linha foi inserida (nova)
            # rowcount == 0 significa que foi ignorada (já existia)
            if cursor.rowcount > 0:
                novas += 1
            else:
                ignoradas += 1

        # Salva todas as inserções no banco
        conexao.commit()
        conexao.close()

    except Exception as e:
        print(f"  ❌ Erro ao salvar no banco: {e}")

    return novas, ignoradas


def varrer_noticias():
    """
    Função principal do Radar de Notícias.
    Percorre todas as fontes RSS mapeadas, coleta as notícias
    e salva no banco de dados respeitando a regra de upsert.
    Exibe um relatório final no terminal.
    """
    print("=" * 60)
    print("🔍 HallyuBot V3 — Radar de Notícias (Varredura Manual)")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}")
    print("=" * 60)

    # Contadores globais da varredura
    total_novas = 0
    total_ignoradas = 0
    total_erros = 0

    # --- PLANO A: Fontes RSS ---
    print("\n📰 [PLANO A] Varrendo fontes RSS...\n")

    for indice, fonte in enumerate(FONTES_RSS):
        # Atraso aleatório entre requisições (1-3s) para evitar bloqueios
        if indice > 0:
            pausa = random.uniform(1.0, 3.0)
            print(f"     ⏳ Aguardando {pausa:.1f}s antes da próxima fonte...")
            time.sleep(pausa)

        # Coleta as notícias do feed atual
        noticias = coletar_feed_rss(fonte)

        if noticias:
            # Tenta salvar no banco de dados
            novas, ignoradas = salvar_no_banco(noticias)
            total_novas += novas
            total_ignoradas += ignoradas

            # Feedback individual por fonte
            print(f"     💾 {fonte['nome']}: {novas} novas | {ignoradas} já no banco")
        else:
            total_erros += 1

    # --- PLANO B: Fontes BeautifulSoup (futuro) ---
    # print("\n🔧 [PLANO B] Varrendo fontes com BeautifulSoup...")
    # Será implementado na próxima fase para Allkpop e MyDramaList.

    # -----------------------------------------------
    # Relatório final da varredura
    # -----------------------------------------------
    print("\n" + "=" * 60)
    print("📊 RELATÓRIO DA VARREDURA")
    print("=" * 60)
    print(f"  ✅ Notícias NOVAS salvas no banco:    {total_novas}")
    print(f"  ⏭️  Notícias IGNORADAS (duplicatas):   {total_ignoradas}")
    print(f"  ❌ Fontes com ERRO de leitura:         {total_erros}")
    print(f"  📁 Banco de dados: {CAMINHO_BD}")
    print("=" * 60)

    return total_novas, total_ignoradas


# =============================================
# Execução manual (sem apscheduler por enquanto)
# =============================================
# O agendamento automático será ligado em uma fase futura.
# Por enquanto, basta rodar: python scraper.py
if __name__ == "__main__":
    varrer_noticias()
