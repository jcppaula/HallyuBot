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
import urllib.request
from datetime import datetime
from html import unescape
from urllib.parse import urljoin
from html.parser import HTMLParser

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

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
        "nome": "Seoulbeats",
        # Seoulbeats: analise de K-pop e cultura coreana, cobre escândalos e tendencias.
        # Substitui o Dispatch, que renderiza via JavaScript e nao expoe RSS estatico.
        "url": "https://seoulbeats.com/feed/",
        "pilar": "K-Pop"
    },
    {
        "nome": "Hellokpop",
        # Hellokpop: noticias de K-pop e K-drama. Substitui Reddit r/kpop,
        # que bloqueia bots sem autenticacao OAuth desde 2023.
        "url": "https://www.hellokpop.com/feed/",
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
        "nome": "Dramabeans",
        # Dramabeans: site referencia em K-drama, com recaps e noticias detalhadas.
        # Substitui Reddit r/KDRAMA, bloqueado para bots sem OAuth.
        "url": "https://www.dramabeans.com/feed/",
        "pilar": "K-Drama"
    },

    # --- PILAR 3: Cultura Chinesa (C-Dramas/C-Pop) ---
    {
        "nome": "DramaPanda",
        "url": "https://dramapanda.com/?feed=rss2",
        "fallbacks": [
            "https://dramapanda.com/feed/?alt=rss",
            "https://dramapanda.com/?feed=atom",
        ],
        "wp_json_fallback": "https://dramapanda.com/wp-json/wp/v2/posts?per_page=20",
        "html_fallback": "https://dramapanda.com/",
        "pilar": "Cultura Chinesa"
    },
    {
        "nome": "JayneStars",
        "url": "https://www.jaynestars.com/feed/",
        "pilar": "Cultura Chinesa"
    },
    # Reddit r/CDrama removido: bloqueado para bots sem OAuth (HTTP 403).
    # Cobertura de C-Drama mantida pelo DramaPanda e JayneStars acima.
]

HEADERS_RSS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
}

HEADERS_MINIMOS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
}

# User-Agent no formato recomendado pelo Reddit para bots sem OAuth
HEADERS_REDDIT = {
    "User-Agent": "HallyuBot/3.0 K-Pop monitoring bot",
    "Accept": "application/json",
}


def baixar_e_parsear_feed(url_feed):
    """Baixa o RSS com headers completos e devolve o objeto parseado."""
    try:
        resposta = requests.get(url_feed, headers=HEADERS_RSS, timeout=20)
        resposta.raise_for_status()
        return feedparser.parse(resposta.content)
    except Exception:
        req = urllib.request.Request(url_feed, headers=HEADERS_MINIMOS)
        with urllib.request.urlopen(req, timeout=20) as resposta:
            return feedparser.parse(resposta.read())


class LinkHTMLParser(HTMLParser):
    """Parser simples para coletar links quando BeautifulSoup nao estiver instalado."""
    def __init__(self):
        super().__init__()
        self.links = []
        self._href_atual = None
        self._texto_atual = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href_atual = href
            self._texto_atual = []

    def handle_data(self, data):
        if self._href_atual:
            self._texto_atual.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href_atual:
            texto = " ".join(t.strip() for t in self._texto_atual if t.strip())
            self.links.append((texto, self._href_atual))
            self._href_atual = None
            self._texto_atual = []


def coletar_home_html(url_home, nome_fonte, pilar, limite=20):
    """Extrai noticias da pagina inicial quando o RSS da fonte falha."""
    resposta = requests.get(url_home, headers=HEADERS_RSS, timeout=20)
    resposta.raise_for_status()

    if BeautifulSoup:
        soup = BeautifulSoup(resposta.text, "html.parser")
        links = [
            (tag.get_text(" ", strip=True), tag.get("href", "").strip())
            for tag in soup.select(
                "h1 a, h2 a, h3 a, h4 a, article a, "
                ".article a, .post a, .news a, .entry a, "
                ".tit a, .title a, .headline a, "
                ".list_news a, .news_list a, .view_list a, "
                ".news_item a, .content_list a, .post-title a"
            )
        ]
        links.extend([
            (tag.get("data-title", "").strip(), tag.get("href", "").strip())
            for tag in soup.select("a[data-title]")
        ])
    else:
        parser = LinkHTMLParser()
        parser.feed(resposta.text)
        links = parser.links

    noticias = []
    vistos = set()

    for titulo, href in links:
        link = urljoin(url_home, href.strip())
        titulo, data_publicacao = limpar_titulo_html(titulo)

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
            "data_publicacao": data_publicacao or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        if len(noticias) >= limite:
            break

    return noticias


def limpar_titulo_html(titulo):
    """Remove datas grudadas no texto e tenta extrair data de publicacao."""
    import re
    titulo = unescape(" ".join((titulo or "").split())).strip()
    padrao = re.compile(r"\s*(\d{4})\.(\d{2})\.(\d{2})(?:\s+(오전|오후)\s+(\d{1,2}):(\d{2}))?\s*$")
    match = padrao.search(titulo)
    if not match:
        return titulo, None

    ano, mes, dia, periodo, hora, minuto = match.groups()
    data_publicacao = f"{ano}-{mes}-{dia} 00:00:00"
    if hora and minuto:
        h = int(hora)
        if periodo == "오후" and h < 12:
            h += 12
        elif periodo == "오전" and h == 12:
            h = 0
        data_publicacao = f"{ano}-{mes}-{dia} {h:02d}:{minuto}:00"

    return titulo[:match.start()].strip(), data_publicacao


def coletar_html_fallbacks(urls_html, nome_fonte, pilar, limite=20):
    """Tenta varias paginas HTML ate encontrar noticias."""
    ultimo_erro = None
    for url_home in urls_html:
        try:
            noticias = coletar_home_html(url_home, nome_fonte, pilar, limite)
            if noticias:
                sufixo = "HTML fallback" if len(urls_html) == 1 else f"HTML fallback: {url_home}"
                print(f"✅ {len(noticias)} entradas encontradas ({sufixo}).")
                return noticias
        except Exception as e:
            ultimo_erro = e
        time.sleep(1)

    if ultimo_erro:
        raise ultimo_erro
    return []


def limpar_html_simples(texto):
    """Remove tags simples de campos vindos do WordPress JSON."""
    import re
    return unescape(re.sub(r"<[^>]+>", "", texto or "")).strip()


def coletar_wp_json(url_api, nome_fonte, pilar, limite=20):
    """Extrai noticias de endpoints WordPress quando RSS/HTML falham."""
    resposta = requests.get(url_api, headers=HEADERS_RSS, timeout=20)
    resposta.raise_for_status()
    posts = resposta.json()

    noticias = []
    for post in posts[:limite]:
        titulo = limpar_html_simples(post.get("title", {}).get("rendered", ""))
        link = post.get("link", "").strip()
        data_pub = (post.get("date") or "")[:19].replace("T", " ")

        if not titulo or not link:
            continue

        noticias.append({
            "titulo": titulo,
            "url": link,
            "fonte": nome_fonte,
            "pilar": pilar,
            "data_publicacao": data_pub or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    return noticias


def coletar_reddit_json(subreddit, nome_fonte, pilar, limite=25):
    """Coleta posts do Reddit via JSON API publica (alternativa ao RSS bloqueado com 403).

    O Reddit bloqueia feeds RSS de forma agressiva desde 2023. A JSON API
    publica (/top.json, /new.json) funciona de forma mais confiavel com
    um User-Agent no formato de bot.
    """
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit={limite}"
    resposta = requests.get(url, headers=HEADERS_REDDIT, timeout=20)
    resposta.raise_for_status()
    dados = resposta.json()

    noticias = []
    for post in dados.get("data", {}).get("children", []):
        post_data = post.get("data", {})
        titulo = post_data.get("title", "").strip()
        permalink = post_data.get("permalink", "")

        if not titulo or not permalink:
            continue

        url_noticia = f"https://www.reddit.com{permalink}"

        created = post_data.get("created_utc", 0)
        data_pub = (
            datetime.utcfromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S")
            if created else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        noticias.append({
            "titulo": titulo,
            "url": url_noticia,
            "fonte": nome_fonte,
            "pilar": pilar,
            "data_publicacao": data_pub
        })

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
            wp_json_fallback = fonte.get("wp_json_fallback")
            if wp_json_fallback:
                try:
                    noticias_json = coletar_wp_json(wp_json_fallback, nome_fonte, pilar)
                    if noticias_json:
                        print(f"✅ {len(noticias_json)} entradas encontradas (WP JSON fallback).")
                        return noticias_json
                except Exception as e:
                    ultimo_erro = e

            html_fallbacks = fonte.get("html_fallbacks")
            if not html_fallbacks and fonte.get("html_fallback"):
                html_fallbacks = [fonte["html_fallback"]]
            if html_fallbacks:
                try:
                    noticias_html = coletar_html_fallbacks(html_fallbacks, nome_fonte, pilar)
                    if noticias_html:
                        return noticias_html
                except Exception as e:
                    ultimo_erro = e

            # Reddit JSON API — fallback quando RSS e demais URLs sao bloqueadas (403)
            reddit_sub = fonte.get("reddit_subreddit")
            if reddit_sub:
                try:
                    noticias_reddit = coletar_reddit_json(reddit_sub, nome_fonte, pilar)
                    if noticias_reddit:
                        print(f"✅ {len(noticias_reddit)} entradas encontradas (Reddit JSON API).")
                        return noticias_reddit
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
        try:
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
        finally:
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

    return total_novas, total_ignoradas, total_erros


# =============================================
# Execução manual (sem apscheduler por enquanto)
# =============================================
# O agendamento automático será ligado em uma fase futura.
# Por enquanto, basta rodar: python scraper.py
if __name__ == "__main__":
    varrer_noticias()
