"""
HallyuBot V3 - Modulo de Sensores Sociais (Instagram, TikTok, YouTube)
Integra Apify API (IG/TikTok) e YouTube Data API v3 para monitorar
contas oficiais de entretenimento asiatico.
"""
import os, sys, sqlite3, time, random, json
from datetime import datetime
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()

CAMINHO_BD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hallyubot.db")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# === Contas monitoradas ===
CONTAS_INSTAGRAM = ["soompi", "netflixkcontent", "smtown", "hybe.labels.official", "yg_ent_official"]
CONTAS_TIKTOK = ["koreaboo", "allkpop"]
CANAIS_YOUTUBE = ["@HYBELABELS", "@SMTOWN", "@NetflixKContent"]

# Controle de varredura diaria automatica
_ultima_varredura_auto = None

def salvar_post_no_banco(titulo, url, fonte, pilar, data_pub=None):
    """Salva um post social no banco com INSERT OR IGNORE (upsert)."""
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        data = data_pub or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT OR IGNORE INTO noticias (titulo, url, fonte, pilar, data_publicacao, status)
            VALUES (?, ?, ?, ?, ?, 'pendente_avaliacao')
        """, (titulo[:500], url, fonte, pilar, data))
        inserido = cur.rowcount > 0
        con.commit(); con.close()
        return inserido
    except Exception as e:
        print(f"  [ERRO BD] {e}"); return False

# =============================================
# INSTAGRAM via Apify
# =============================================

def varrer_instagram():
    """Busca o post mais recente de cada conta do Instagram via Apify."""
    if not APIFY_API_TOKEN:
        print("  [AVISO] APIFY_API_TOKEN nao configurado."); return 0, 0

    from apify_client import ApifyClient
    client = ApifyClient(APIFY_API_TOKEN)
    novas = 0; ignoradas = 0

    for conta in CONTAS_INSTAGRAM:
        print(f"  [IG] @{conta}...", end=" ")
        try:
            # Actor: apify/instagram-post-scraper (busca posts de perfil)
            run_input = {
                "username": [conta],
                "resultsLimit": 1,
            }
            run = client.actor("apify/instagram-post-scraper").call(run_input=run_input, timeout_secs=120)
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            if items:
                post = items[0]
                caption = post.get("caption", "")[:200] or "Post sem legenda"
                url = post.get("url", f"https://www.instagram.com/p/{post.get('shortCode', '')}/")
                titulo = f"[Instagram] @{conta}: {caption}"
                data_pub = post.get("timestamp", "")[:19].replace("T", " ") if post.get("timestamp") else None

                if salvar_post_no_banco(titulo, url, f"Instagram @{conta}", "K-Pop", data_pub):
                    novas += 1; print("NOVO!")
                else:
                    ignoradas += 1; print("ja no banco.")
            else:
                print("sem posts.")

        except Exception as e:
            print(f"ERRO: {str(e)[:80]}")

        # Pausa entre contas (2-4s)
        time.sleep(random.uniform(2.0, 4.0))

    return novas, ignoradas

# =============================================
# TIKTOK via Apify
# =============================================

def varrer_tiktok():
    """Busca o video mais recente de cada conta do TikTok via Apify."""
    if not APIFY_API_TOKEN:
        print("  [AVISO] APIFY_API_TOKEN nao configurado."); return 0, 0

    from apify_client import ApifyClient
    client = ApifyClient(APIFY_API_TOKEN)
    novas = 0; ignoradas = 0

    for conta in CONTAS_TIKTOK:
        print(f"  [TT] @{conta}...", end=" ")
        try:
            run_input = {
                "profiles": [conta],
                "resultsPerPage": 1,
                "shouldDownloadVideos": False,
            }
            run = client.actor("clockworks/free-tiktok-scraper").call(run_input=run_input, timeout_secs=120)
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            if items:
                video = items[0]
                desc = video.get("text", "")[:200] or "Video sem descricao"
                url = video.get("webVideoUrl", "") or f"https://www.tiktok.com/@{conta}"
                titulo = f"[TikTok] @{conta}: {desc}"
                data_pub = video.get("createTimeISO", "")[:19].replace("T", " ") if video.get("createTimeISO") else None

                if salvar_post_no_banco(titulo, url, f"TikTok @{conta}", "K-Pop", data_pub):
                    novas += 1; print("NOVO!")
                else:
                    ignoradas += 1; print("ja no banco.")
            else:
                print("sem videos.")

        except Exception as e:
            print(f"ERRO: {str(e)[:80]}")

        time.sleep(random.uniform(2.0, 4.0))

    return novas, ignoradas

# =============================================
# YOUTUBE via YouTube Data API v3
# =============================================

def varrer_youtube():
    """Busca o video mais recente de cada canal do YouTube via API oficial."""
    if not YOUTUBE_API_KEY:
        print("  [AVISO] YOUTUBE_API_KEY nao configurado."); return 0, 0

    from googleapiclient.discovery import build
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    novas = 0; ignoradas = 0

    for handle in CANAIS_YOUTUBE:
        print(f"  [YT] {handle}...", end=" ")
        try:
            # Primeiro: resolver handle para channel ID
            ch_resp = youtube.channels().list(part="contentDetails,snippet", forHandle=handle.lstrip("@")).execute()
            if not ch_resp.get("items"):
                # Fallback: buscar por username
                ch_resp = youtube.channels().list(part="contentDetails,snippet", forUsername=handle.lstrip("@")).execute()
            if not ch_resp.get("items"):
                print("canal nao encontrado."); continue

            canal_info = ch_resp["items"][0]
            canal_nome = canal_info["snippet"]["title"]
            uploads_playlist = canal_info["contentDetails"]["relatedPlaylists"]["uploads"]

            # Busca o video mais recente da playlist de uploads
            pl_resp = youtube.playlistItems().list(
                part="snippet", playlistId=uploads_playlist, maxResults=1
            ).execute()

            if pl_resp.get("items"):
                video = pl_resp["items"][0]["snippet"]
                titulo_video = video.get("title", "Video sem titulo")
                video_id = video.get("resourceId", {}).get("videoId", "")
                url = f"https://www.youtube.com/watch?v={video_id}"
                data_pub = video.get("publishedAt", "")[:19].replace("T", " ") if video.get("publishedAt") else None

                titulo = f"[YouTube] {canal_nome}: {titulo_video}"
                pilar = "K-Pop" if "HYBE" in handle.upper() or "SM" in handle.upper() else "K-Drama"

                if salvar_post_no_banco(titulo, url, f"YouTube {handle}", pilar, data_pub):
                    novas += 1; print("NOVO!")
                else:
                    ignoradas += 1; print("ja no banco.")
            else:
                print("sem videos recentes.")

        except Exception as e:
            print(f"ERRO: {str(e)[:80]}")

        time.sleep(random.uniform(1.0, 2.0))

    return novas, ignoradas

# =============================================
# Funcao principal: varredura completa
# =============================================

def varrer_social(forcar=False):
    """
    Executa a varredura completa nas 3 plataformas.
    Args:
        forcar: Se True, ignora trava diaria (uso via comando /social).
    Returns:
        Dict com resultados por plataforma.
    """
    global _ultima_varredura_auto

    # Trava: varredura automatica 1x por dia (manual via /social e ilimitado)
    if not forcar and _ultima_varredura_auto:
        hoje = datetime.now().strftime("%Y-%m-%d")
        if _ultima_varredura_auto == hoje:
            print("[SOCIAL] Varredura automatica ja executada hoje. Pulando."); return None

    print("=" * 60)
    print("HALLYUBOT V3 — Sensores Sociais (Varredura)")
    print(f"{datetime.now().strftime('%d/%m/%Y as %H:%M:%S')}")
    print("=" * 60)

    resultados = {"instagram": {}, "tiktok": {}, "youtube": {}, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # Instagram
    print("\n[INSTAGRAM]")
    ig_novas, ig_ign = varrer_instagram()
    resultados["instagram"] = {"novas": ig_novas, "ignoradas": ig_ign}

    # TikTok
    print("\n[TIKTOK]")
    tt_novas, tt_ign = varrer_tiktok()
    resultados["tiktok"] = {"novas": tt_novas, "ignoradas": tt_ign}

    # YouTube
    print("\n[YOUTUBE]")
    yt_novas, yt_ign = varrer_youtube()
    resultados["youtube"] = {"novas": yt_novas, "ignoradas": yt_ign}

    # Salva timestamp da varredura
    salvar_timestamp_varredura()
    if not forcar:
        _ultima_varredura_auto = datetime.now().strftime("%Y-%m-%d")

    total_novas = ig_novas + tt_novas + yt_novas
    total_ign = ig_ign + tt_ign + yt_ign
    print(f"\n{'='*60}")
    print(f"TOTAL: {total_novas} novos | {total_ign} duplicados")
    print(f"{'='*60}\n")

    return resultados

def salvar_timestamp_varredura():
    """Salva o timestamp da ultima varredura social em um arquivo de controle."""
    try:
        caminho = os.path.join(os.path.dirname(CAMINHO_BD), "social_last_run.txt")
        with open(caminho, "w") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass

def ler_timestamp_varredura():
    """Le o timestamp da ultima varredura social."""
    try:
        caminho = os.path.join(os.path.dirname(CAMINHO_BD), "social_last_run.txt")
        with open(caminho, "r") as f:
            return f.read().strip()
    except Exception:
        return "Nunca executada"

def contar_posts_sociais_hoje():
    """Conta posts sociais capturados hoje no banco."""
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        hoje = datetime.now().strftime("%Y-%m-%d")
        cur.execute("SELECT COUNT(*) FROM noticias WHERE fonte LIKE 'Instagram%' OR fonte LIKE 'TikTok%' OR fonte LIKE 'YouTube%'")
        total = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM noticias WHERE (fonte LIKE 'Instagram%' OR fonte LIKE 'TikTok%' OR fonte LIKE 'YouTube%') AND data_coleta >= '{hoje}'")
        hoje_count = cur.fetchone()[0]
        con.close()
        return {"total": total, "hoje": hoje_count}
    except Exception:
        return {"total": 0, "hoje": 0}

if __name__ == "__main__":
    varrer_social(forcar=True)
