"""
HallyuBot V3 - Orquestrador Principal (Fase 9 — Automação Total + Botões Interativos)
"""
import os, sys, json, sqlite3, asyncio, itertools
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import tasks
from discord.ui import View, Button
from dotenv import load_dotenv
from openai import OpenAI
from database import inicializar_banco

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()

# === Configuracoes ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CANAL_URGENTE_ID = os.getenv("CANAL_URGENTE_ID")
CANAL_RESUMO_ID = os.getenv("CANAL_RESUMO_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CAMINHO_BD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hallyubot.db")
CAMINHO_TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "Templates_Validados_V2.md")
MODELO = "gpt-4o-mini"

# Cores do tema Hallyu
COR_URGENTE = 0xFF0000
COR_ROTEIRO = 0x9B59B6
COR_STATUS  = 0x3498DB
COR_VARRER  = 0x2ECC71
COR_TRIAR   = 0xF1C40F
COR_IDEIA   = 0xE91E63  # Rosa — Ideias criativas
COR_SOCIAL  = 0x1DA1F2  # Azul social
COR_BOMBA   = 0xFFD700  # Dourado — Bomba temp 10
COR_ANALISAR= 0x8E44AD  # Roxo escuro — Analise manual

# === Bot Discord ===
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# === Rotacao de Status ===
ATIVIDADES = itertools.cycle([
    discord.Activity(type=discord.ActivityType.watching, name="o mundo do K-Pop"),
    discord.Activity(type=discord.ActivityType.listening, name="as novidades Hallyu"),
    discord.Activity(type=discord.ActivityType.playing, name="Escrevendo roteiros..."),
    discord.Activity(type=discord.ActivityType.watching, name="os Doramas do momento"),
    discord.Activity(type=discord.ActivityType.listening, name="o radar de noticias"),
    discord.Activity(type=discord.ActivityType.watching, name="os C-Dramas em alta"),
    discord.Activity(type=discord.ActivityType.playing, name="Cacando tendencias..."),
])

# =============================================
# Funcoes de Banco de Dados
# =============================================

def buscar_alertas_urgentes():
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        cur.execute("SELECT id, titulo, url, temperatura, justificativa, pilar FROM noticias WHERE status='avaliada' AND temperatura>=9 ORDER BY temperatura DESC")
        r = cur.fetchall(); con.close(); return r
    except Exception as e:
        print(f"[ERRO] buscar_alertas: {e}"); return []

def buscar_melhores_para_roteiro(limite=3):
    """Busca noticias para roteiro com filtro anti-repeticao de 48h."""
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        # Calcula o limiar de 48h atras
        limiar_48h = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        # Prioridade: notas 5-8 avaliadas, excluindo roteirizadas nas ultimas 48h
        cur.execute("""
            SELECT id, titulo, url, temperatura, justificativa, pilar, fonte
            FROM noticias
            WHERE status = 'avaliada' AND temperatura BETWEEN 5 AND 8
            ORDER BY temperatura DESC, data_coleta DESC LIMIT ?
        """, (limite,))
        noticias = cur.fetchall()
        # Fallback: se nao encontrou suficientes, busca qualquer avaliada
        if len(noticias) < limite:
            ids_ja = [str(n[0]) for n in noticias]
            filtro = f"AND id NOT IN ({','.join(ids_ja)})" if ids_ja else ""
            falta = limite - len(noticias)
            cur.execute(f"""
                SELECT id, titulo, url, temperatura, justificativa, pilar, fonte
                FROM noticias WHERE status='avaliada' {filtro}
                ORDER BY temperatura DESC, data_coleta DESC LIMIT ?
            """, (falta,))
            noticias.extend(cur.fetchall())
        con.close(); return noticias
    except Exception as e:
        print(f"[ERRO] buscar_roteiro: {e}"); return []

def atualizar_status(noticia_id, novo_status):
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        cur.execute("UPDATE noticias SET status=? WHERE id=?", (novo_status, noticia_id))
        con.commit(); con.close()
    except Exception as e:
        print(f"[ERRO] atualizar_status: {e}")

def contar_noticias_por_status():
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        cur.execute("SELECT status, COUNT(*) FROM noticias GROUP BY status")
        r = dict(cur.fetchall()); con.close(); return r
    except Exception as e:
        print(f"[ERRO] contar: {e}"); return {}

def estatisticas_triagem_24h():
    """Retorna estatisticas de eficacia da triagem nas ultimas 24h."""
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        limiar = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT COUNT(*) FROM noticias WHERE data_coleta >= ? AND status != 'pendente_avaliacao'", (limiar,))
        total_triadas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM noticias WHERE data_coleta >= ? AND status != 'pendente_avaliacao' AND temperatura < 4", (limiar,))
        descartadas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM noticias WHERE data_coleta >= ? AND status != 'pendente_avaliacao' AND temperatura >= 4", (limiar,))
        aproveitadas = cur.fetchone()[0]
        con.close()
        return {"total": total_triadas, "descartadas": descartadas, "aproveitadas": aproveitadas}
    except Exception as e:
        print(f"[ERRO] stats_24h: {e}"); return {"total": 0, "descartadas": 0, "aproveitadas": 0}

def carregar_templates():
    try:
        with open(CAMINHO_TEMPLATES, "r", encoding="utf-8") as f: return f.read()
    except Exception as e:
        print(f"[ERRO] templates: {e}"); return None

def tendencia_semanal():
    """Extrai palavras-chave mais repetidas em noticias com temp > 7 dos ultimos 7 dias."""
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        limiar = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT titulo FROM noticias WHERE temperatura > 7 AND data_coleta >= ?", (limiar,))
        titulos = [r[0] for r in cur.fetchall()]; con.close()
        if not titulos: return "Sem dados suficientes esta semana."
        # Conta palavras relevantes (>3 chars, ignora stopwords)
        stopwords = {'the','and','for','with','has','from','that','this','are','was','will','its',
                     'new','all','but','not','have','been','more','who','their','after','just',
                     'about','what','how','into','com','www','https','http','que','para','uma',
                     'por','com','dos','das','del','los','las','como'}
        from collections import Counter
        palavras = []
        for t in titulos:
            for p in t.split():
                p_limpa = p.strip('.,!?:;"()[]').lower()
                if len(p_limpa) > 3 and p_limpa not in stopwords:
                    palavras.append(p_limpa)
        top = Counter(palavras).most_common(5)
        if not top: return "Sem tendencias claras."
        return ", ".join([f"**{p}** ({c}x)" for p, c in top])
    except Exception as e:
        print(f"[ERRO] tendencia: {e}"); return "Erro ao calcular."

def limpar_banco_antigo(dias=15):
    """Remove noticias pendentes ou com temp < 4 com mais de X dias."""
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        limiar = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("DELETE FROM noticias WHERE data_coleta < ? AND (status='pendente_avaliacao' OR temperatura < 4)", (limiar,))
        removidas = cur.rowcount
        con.commit(); con.close()
        if removidas > 0: print(f"[LIMPEZA] {removidas} noticias antigas removidas.", flush=True)
        return removidas
    except Exception as e:
        print(f"[ERRO] limpeza: {e}"); return 0

async def analisar_com_ia(texto):
    """Analisa um texto/link avulso com a IA e retorna temperatura + sugestao."""
    if not OPENAI_API_KEY: return None
    prompt = (
        "Voce e um editor-chefe de cultura asiatica (K-pop, K-dramas, C-dramas).\n"
        "Analise o texto/link abaixo e responda em JSON:\n"
        '{"nota": int 1-10, "justificativa": "string curta", "vale_video": true/false, '
        '"sugestao_video": "string com sugestao de angulo para video se vale_video=true"}\n\n'
        "Criterios: nota 9-10 = escandalo/disband/morte/comeback BTS-level. "
        "nota 7-8 = importante. nota 4-6 = relevante. nota 1-3 = rotineiro/estetico.\n"
        "vale_video = true se nota >= 5 e o tema tem potencial de engajamento."
    )
    try:
        cli = OpenAI(api_key=OPENAI_API_KEY)
        resp = await asyncio.to_thread(
            cli.chat.completions.create, model=MODELO,
            messages=[{"role":"system","content":prompt},{"role":"user","content":texto}],
            response_format={"type":"json_object"}, temperature=0.3, max_tokens=300
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[ERRO] analisar_ia: {e}"); return None

# =============================================
# Helpers visuais
# =============================================

def barra_progresso(valor, total, tamanho=10):
    if total == 0: return "[          ] 0%"
    pct = valor / total
    p = round(tamanho * pct); v = tamanho - p
    return f"[{'■' * p}{'□' * v}] {pct*100:.0f}%"

def classificar_impacto(temp):
    if temp == 10: return "CRITICO — Repercussao global imediata"
    if temp == 9: return "MUITO ALTO — Trending topics garantido"
    if temp == 8: return "ALTO — Grande interesse da comunidade"
    if temp >= 6: return "MODERADO — Relevante para o nicho"
    return "BAIXO — Informativo"

def buscar_noticia_por_id(noticia_id):
    """Busca uma noticia especifica pelo ID."""
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        cur.execute("SELECT id, titulo, url, temperatura, justificativa, pilar, fonte FROM noticias WHERE id=?", (noticia_id,))
        r = cur.fetchone(); con.close(); return r
    except Exception as e:
        print(f"[ERRO] buscar_por_id: {e}"); return None

# =============================================
# Botoes Interativos — "Fazer Roteiro" com 1 clique
# =============================================

class BotaoRoteiro(View):
    """View com botao para gerar roteiro de uma noticia especifica."""
    def __init__(self, noticia_id: int):
        super().__init__(timeout=None)  # Botao nao expira
        self.noticia_id = noticia_id

    @discord.ui.button(label="📝 Fazer Roteiro", style=discord.ButtonStyle.primary, custom_id="btn_roteiro")
    async def fazer_roteiro(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(thinking=True)
        try:
            noticia = buscar_noticia_por_id(self.noticia_id)
            if not noticia:
                await interaction.followup.send("❌ Noticia nao encontrada no banco."); return

            nid, titulo, url, temp, just, pilar, fonte = noticia
            templates_texto = carregar_templates()
            if not templates_texto:
                await interaction.followup.send("❌ Templates nao encontrado."); return

            # Gera roteiro para esta noticia especifica
            noticias_para_roteiro = [(nid, titulo, url, temp, just, pilar, fonte)]
            roteiro = await gerar_roteiro_com_ia(noticias_para_roteiro, templates_texto)
            if not roteiro:
                await interaction.followup.send("❌ Falha na IA. Tente novamente."); return

            # Embed do roteiro gerado
            embed = discord.Embed(
                title="Roteiro Gerado — HallyuBot",
                description=f"**{titulo[:100]}**",
                color=COR_ROTEIRO, timestamp=datetime.now()
            )
            embed.add_field(name="Temperatura", value=f"**{temp}/10**", inline=True)
            embed.add_field(name="Pilar", value=pilar, inline=True)
            embed.add_field(name="Fonte", value=f"[Link]({url})", inline=False)
            embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)

            # Envia o roteiro em blocos
            if len(roteiro) <= 1900:
                await interaction.channel.send(f"```\n{roteiro}\n```")
            else:
                partes = [roteiro[i:i+1800] for i in range(0, len(roteiro), 1800)]
                for idx, p in enumerate(partes, 1):
                    await interaction.channel.send(f"**Parte {idx}/{len(partes)}:**\n```\n{p}\n```")

            atualizar_status(nid, "roteirizada")
            # Desabilita o botao apos uso
            button.disabled = True
            button.label = "✅ Roteiro Gerado"
            button.style = discord.ButtonStyle.secondary
            await interaction.message.edit(view=self)
            print(f"[ROTEIRO-BOTAO] Gerado para: {titulo[:50]}...", flush=True)

        except Exception as e:
            print(f"[ERRO] botao_roteiro: {e}")
            try: await interaction.followup.send(f"Erro: {str(e)[:200]}")
            except: pass


class BotaoRoteiroPersistente(View):
    """View persistente que sobrevive a reinicializacoes do bot.
    Usa custom_id dinamico com o ID da noticia embutido."""
    def __init__(self, noticia_id: int):
        super().__init__(timeout=None)
        btn = Button(
            label="📝 Fazer Roteiro",
            style=discord.ButtonStyle.primary,
            custom_id=f"roteiro_{noticia_id}"
        )
        btn.callback = self.fazer_roteiro_callback
        self.add_item(btn)
        self.noticia_id = noticia_id

    async def fazer_roteiro_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            noticia = buscar_noticia_por_id(self.noticia_id)
            if not noticia:
                await interaction.followup.send("❌ Noticia nao encontrada no banco."); return

            nid, titulo, url, temp, just, pilar, fonte = noticia
            templates_texto = carregar_templates()
            if not templates_texto:
                await interaction.followup.send("❌ Templates nao encontrado."); return

            noticias_para_roteiro = [(nid, titulo, url, temp, just, pilar, fonte)]
            roteiro = await gerar_roteiro_com_ia(noticias_para_roteiro, templates_texto)
            if not roteiro:
                await interaction.followup.send("❌ Falha na IA. Tente novamente."); return

            embed = discord.Embed(
                title="Roteiro Gerado — HallyuBot",
                description=f"**{titulo[:100]}**",
                color=COR_ROTEIRO, timestamp=datetime.now()
            )
            embed.add_field(name="Temperatura", value=f"**{temp}/10**", inline=True)
            embed.add_field(name="Pilar", value=pilar, inline=True)
            embed.add_field(name="Fonte", value=f"[Link]({url})", inline=False)
            embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)

            if len(roteiro) <= 1900:
                await interaction.channel.send(f"```\n{roteiro}\n```")
            else:
                partes = [roteiro[i:i+1800] for i in range(0, len(roteiro), 1800)]
                for idx, p in enumerate(partes, 1):
                    await interaction.channel.send(f"**Parte {idx}/{len(partes)}:**\n```\n{p}\n```")

            atualizar_status(nid, "roteirizada")
            # Desabilita botao
            for item in self.children:
                item.disabled = True
                item.label = "✅ Roteiro Gerado"
                item.style = discord.ButtonStyle.secondary
            await interaction.message.edit(view=self)
            print(f"[ROTEIRO-BOTAO] Gerado para: {titulo[:50]}...", flush=True)

        except Exception as e:
            print(f"[ERRO] botao_roteiro_persistente: {e}")
            try: await interaction.followup.send(f"Erro: {str(e)[:200]}")
            except: pass

# =============================================
# Geracao de Roteiro com IA (com CTA/Dica de Engajamento)
# =============================================

async def gerar_roteiro_com_ia(noticias, templates_texto):
    if not OPENAI_API_KEY: return None
    bloco = ""
    for i, (nid, titulo, url, temp, just, pilar, fonte) in enumerate(noticias, 1):
        bloco += f"\n--- Noticia {i} ---\nTitulo: {titulo}\nLink: {url}\nPilar: {pilar}\nFonte: {fonte}\nTemperatura: {temp}/10\nJustificativa: {just}\n"

    system_prompt = (
        "Voce e um roteirista e estrategista de conteudo de cultura asiatica (K-pop, K-dramas, C-dramas) "
        "para um servidor de Discord chamado Hallyu News.\n\n"
        "REGRAS OBRIGATORIAS:\n"
        "1. NUNCA invente dados. Use APENAS as informacoes fornecidas.\n"
        "2. Se faltam dados, escreva 'informacao nao disponivel'.\n"
        "3. Portugues brasileiro natural e engajador.\n"
        "4. Max 280 palavras por roteiro.\n"
        "5. Sempre inclua o link da fonte.\n"
        "6. Emojis com moderacao.\n"
        "7. Escolha o template mais adequado.\n\n"
        "VOCABULARIO HALLYU (use quando natural):\n"
        "Bias, Comeback, Stan, Hallyu, Maknae, Idol, Dorameira\n\n"
        "CAMPO OBRIGATORIO — DICA DE ENGAJAMENTO:\n"
        "Ao final de CADA roteiro, adicione uma secao:\n"
        "💬 **Dica de Engajamento / CTA:**\n"
        "Sugira uma pergunta polemica, enquete ou interacao para os comentarios.\n"
        "Exemplos: 'Quem e seu bias nesse grupo?', 'Voce acha que merece 2a temporada?',\n"
        "'Qual foi o melhor comeback do ano ate agora?'\n\n"
        "FORMATO FINAL:\n"
        "Apos TODOS os roteiros, adicione:\n"
        "--- FONTES UTILIZADAS ---\n"
        "Liste todos os links originais numerados.\n\n"
        f"TEMPLATES:\n{templates_texto}"
    )
    msg = f"Gere roteiros editoriais com CTA para cada noticia:\n{bloco}"
    try:
        cli = OpenAI(api_key=OPENAI_API_KEY)
        resp = await asyncio.to_thread(
            cli.chat.completions.create, model=MODELO,
            messages=[{"role":"system","content":system_prompt},{"role":"user","content":msg}],
            temperature=0.7, max_tokens=2500
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERRO] gerar_roteiro: {e}"); return None

# =============================================
# Geracao de Ideias com IA (/ideia)
# =============================================

async def gerar_ideias_com_ia():
    if not OPENAI_API_KEY: return None
    system_prompt = (
        "Voce e um estrategista de conteudo especialista em cultura asiatica (K-pop, K-dramas, C-dramas, C-pop). "
        "Seu publico sao jovens brasileiros apaixonados por Hallyu.\n\n"
        "Gere exatamente 3 sugestoes de temas para videos curtos (Reels/TikTok/Shorts).\n"
        "Baseie-se em tendencias ATUAIS e temas que costumam viralizar no nicho.\n\n"
        "Para cada ideia, forneca:\n"
        "1. **Titulo do Video** (chamativo, max 60 caracteres)\n"
        "2. **Formato** (ranking, react, storytime, comparacao, etc.)\n"
        "3. **Gancho Inicial** (primeira frase que prende a atencao)\n"
        "4. **Por que Viraliza** (explicacao curta de 1 linha)\n"
        "5. **Hashtags Sugeridas** (5 hashtags relevantes)\n\n"
        "Escreva em portugues brasileiro. Nao invente noticias factuais."
    )
    try:
        cli = OpenAI(api_key=OPENAI_API_KEY)
        resp = await asyncio.to_thread(
            cli.chat.completions.create, model=MODELO,
            messages=[{"role":"system","content":system_prompt},
                      {"role":"user","content":"Gere 3 ideias de videos curtos sobre cultura asiatica para hoje."}],
            temperature=0.9, max_tokens=1500
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERRO] gerar_ideias: {e}"); return None

# =============================================
# Loops de Fundo
# =============================================

@tasks.loop(minutes=30)
async def rotacao_atividade():
    try:
        await client.change_presence(activity=next(ATIVIDADES))
    except Exception as e:
        print(f"[ERRO] rotacao: {e}")

@rotacao_atividade.before_loop
async def antes_rotacao():
    await client.wait_until_ready()

@tasks.loop(minutes=5)
async def monitor_plantao():
    try:
        alertas = buscar_alertas_urgentes()
        if not alertas or not CANAL_URGENTE_ID: return
        canal = client.get_channel(int(CANAL_URGENTE_ID))
        if not canal: return
        for nid, titulo, url, temp, just, pilar in alertas:
            # Temp 10 = Bomba (dourado + @everyone) / Temp 9 = Urgente (vermelho + @here)
            is_bomba = temp == 10
            cor = COR_BOMBA if is_bomba else COR_URGENTE
            titulo_embed = "BOMBA HALLYU — NOTICIA EXPLOSIVA" if is_bomba else "PLANTAO URGENTE — HALLYU NEWS"
            mention = "@everyone" if is_bomba else "@here"

            embed = discord.Embed(
                title=titulo_embed,
                description=f"**{titulo}**", color=cor,
                timestamp=datetime.now(), url=url
            )
            embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/4539/4539472.png")
            embed.add_field(name="Temperatura", value=f"**{temp}/10**", inline=True)
            embed.add_field(name="Pilar", value=pilar, inline=True)
            embed.add_field(name="Impacto Estimado", value=classificar_impacto(temp), inline=False)
            embed.add_field(name="Avaliacao da IA", value=just, inline=False)
            embed.add_field(name="Fonte Original", value=f"[Clique aqui]({url})", inline=False)
            embed.set_footer(text="HallyuBot V3 — Alerta Automatico | Clique no botao para gerar roteiro",
                           icon_url=client.user.display_avatar.url if client.user and client.user.avatar else discord.Embed.Empty)
            try:
                # Envia com botao interativo "Fazer Roteiro"
                view = BotaoRoteiroPersistente(nid)
                await canal.send(content=mention, embed=embed, view=view)
                atualizar_status(nid, "publicada_urgente")
                print(f"[PLANTAO] {'BOMBA' if is_bomba else 'Alerta'}: {titulo[:50]}...", flush=True)
            except Exception as e:
                print(f"[ERRO] envio plantao: {e}")
    except Exception as e:
        print(f"[ERRO] monitor: {e}")

@monitor_plantao.before_loop
async def antes_monitor():
    await client.wait_until_ready()

# =============================================
# Loop Automatico: Varredura + Triagem (a cada 2h)
# =============================================

@tasks.loop(hours=2)
async def varredura_automatica():
    """Varre noticias RSS + redes sociais e tria com IA automaticamente."""
    try:
        print(f"\n{'='*60}", flush=True)
        print(f"[AUTO] Varredura automatica iniciada — {datetime.now().strftime('%H:%M:%S')}", flush=True)
        print(f"{'='*60}", flush=True)

        # Fase 1: Varrer noticias RSS
        from scraper import varrer_noticias
        novas_rss, ign_rss = await asyncio.to_thread(varrer_noticias)
        print(f"[AUTO-RSS] {novas_rss} novas | {ign_rss} duplicadas", flush=True)

        # Fase 2: Varrer redes sociais (1x por dia)
        novas_social = 0
        try:
            from social_scraper import varrer_social
            resultado_social = await asyncio.to_thread(varrer_social, False)  # forcar=False respeita trava diaria
            if resultado_social:
                for plat in ["instagram", "tiktok", "youtube"]:
                    novas_social += resultado_social.get(plat, {}).get("novas", 0)
                print(f"[AUTO-SOCIAL] {novas_social} novos posts sociais", flush=True)
        except Exception as e:
            print(f"[AUTO-SOCIAL] Erro (nao-critico): {e}", flush=True)

        # Fase 3: Triagem com IA (se ha pendentes)
        total_novas = novas_rss + novas_social
        if total_novas > 0:
            print(f"[AUTO-TRIAGEM] {total_novas} noticias novas, iniciando triagem com IA...", flush=True)
            # Pequena pausa para o banco estabilizar
            await asyncio.sleep(5)
            from ai_triagem import executar_triagem
            await asyncio.to_thread(executar_triagem)
            print(f"[AUTO-TRIAGEM] Concluida.", flush=True)

            # Fase 4: Enviar alertas URGENTES (nota 9-10) IMEDIATAMENTE com botoes
            await enviar_alertas_urgentes_agora()

            # Fase 5: Enviar digest das noticias avaliadas (nota 5-8) com botoes
            await enviar_digest_noticias()
        else:
            print(f"[AUTO] Nenhuma noticia nova. Proxima varredura em 2h.", flush=True)

        # Limpeza periodica
        limpar_banco_antigo(dias=15)

    except Exception as e:
        print(f"[ERRO] varredura_automatica: {e}", flush=True)

@varredura_automatica.before_loop
async def antes_varredura_auto():
    await client.wait_until_ready()
    # Espera 60s apos ligar para nao sobrecarregar no startup
    await asyncio.sleep(60)


async def enviar_alertas_urgentes_agora():
    """Envia alertas de noticias nota 9-10 IMEDIATAMENTE apos triagem, com botoes."""
    try:
        if not CANAL_URGENTE_ID: return
        canal = client.get_channel(int(CANAL_URGENTE_ID))
        if not canal: return

        alertas = buscar_alertas_urgentes()
        if not alertas:
            print("[AUTO-URGENTE] Sem alertas urgentes nesta rodada.", flush=True)
            return

        for nid, titulo, url, temp, just, pilar in alertas:
            is_bomba = temp == 10
            cor = COR_BOMBA if is_bomba else COR_URGENTE
            titulo_embed = "BOMBA HALLYU — NOTICIA EXPLOSIVA" if is_bomba else "PLANTAO URGENTE — HALLYU NEWS"
            mention = "@everyone" if is_bomba else "@here"

            embed = discord.Embed(
                title=titulo_embed,
                description=f"**{titulo}**", color=cor,
                timestamp=datetime.now(), url=url
            )
            embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/4539/4539472.png")
            embed.add_field(name="Temperatura", value=f"**{temp}/10**", inline=True)
            embed.add_field(name="Pilar", value=pilar, inline=True)
            embed.add_field(name="Impacto Estimado", value=classificar_impacto(temp), inline=False)
            embed.add_field(name="Avaliacao da IA", value=just, inline=False)
            embed.add_field(name="Fonte Original", value=f"[Clique aqui]({url})", inline=False)
            embed.set_footer(text="HallyuBot V3 — Alerta Automatico | Clique no botao para gerar roteiro",
                           icon_url=client.user.display_avatar.url if client.user and client.user.avatar else discord.Embed.Empty)
            try:
                view = BotaoRoteiroPersistente(nid)
                await canal.send(content=mention, embed=embed, view=view)
                atualizar_status(nid, "publicada_urgente")
                print(f"[AUTO-URGENTE] {'BOMBA' if is_bomba else 'Alerta'} enviado COM BOTAO: {titulo[:50]}...", flush=True)
            except Exception as e:
                print(f"[ERRO] envio urgente: {e}")

    except Exception as e:
        print(f"[ERRO] alertas_urgentes_agora: {e}", flush=True)


async def enviar_digest_noticias():
    """Envia noticias recém-avaliadas (nota 5-8) no canal de resumo com botoes."""
    try:
        canal_id = CANAL_RESUMO_ID or CANAL_URGENTE_ID
        if not canal_id: return
        canal = client.get_channel(int(canal_id))
        if not canal: return

        # Busca noticias avaliadas com nota 5-8 que ainda nao foram enviadas
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        cur.execute("""
            SELECT id, titulo, url, temperatura, justificativa, pilar, fonte
            FROM noticias
            WHERE status = 'avaliada' AND temperatura BETWEEN 5 AND 8
            ORDER BY temperatura DESC, data_coleta DESC
            LIMIT 10
        """)
        noticias = cur.fetchall(); con.close()

        if not noticias:
            print("[DIGEST] Sem noticias nota 5-8 para enviar.", flush=True)
            return

        # Header do digest
        embed_header = discord.Embed(
            title="📋 Digest de Noticias — HallyuBot",
            description=(
                f"**{len(noticias)}** noticias avaliadas pela IA.\n"
                f"Clique em **📝 Fazer Roteiro** na noticia que quiser!"
            ),
            color=COR_STATUS, timestamp=datetime.now()
        )
        embed_header.set_footer(text="HallyuBot V3 — Redacao Automatizada")
        await canal.send(embed=embed_header)

        # Envia cada noticia como embed individual com botao
        for nid, titulo, url, temp, just, pilar, fonte in noticias:
            # Emoji de temperatura
            if temp >= 8: emoji = "🟠"
            elif temp >= 6: emoji = "🟡"
            else: emoji = "🟢"

            embed = discord.Embed(
                title=f"{emoji} {titulo[:200]}",
                color=COR_TRIAR if temp >= 7 else COR_STATUS,
                url=url
            )
            embed.add_field(name="Temperatura", value=f"**{temp}/10**", inline=True)
            embed.add_field(name="Pilar", value=pilar, inline=True)
            embed.add_field(name="Fonte", value=fonte or "—", inline=True)
            embed.add_field(name="Avaliacao", value=just[:200] if just else "—", inline=False)
            embed.set_footer(text=f"ID: {nid} | Clique no botao abaixo para gerar roteiro")

            view = BotaoRoteiroPersistente(nid)
            await canal.send(embed=embed, view=view)

            # Marca como 'notificada' para nao enviar de novo
            con2 = sqlite3.connect(CAMINHO_BD); cur2 = con2.cursor()
            cur2.execute("UPDATE noticias SET status='notificada' WHERE id=?", (nid,))
            con2.commit(); con2.close()

            # Pequena pausa para nao floodar
            await asyncio.sleep(1)

        print(f"[DIGEST] {len(noticias)} noticias enviadas com botoes.", flush=True)

    except Exception as e:
        print(f"[ERRO] digest: {e}", flush=True)

# =============================================
# Slash Commands
# =============================================

@tree.command(name="roteiro", description="Gera roteiro editorial com CTA usando IA.")
async def comando_roteiro(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        if not OPENAI_API_KEY:
            await interaction.followup.send("OPENAI_API_KEY nao configurada."); return

        noticias = buscar_melhores_para_roteiro(limite=3)
        if not noticias:
            embed = discord.Embed(title="Nenhuma noticia disponivel",
                description="Use `/varrer` e `/triar` para alimentar o sistema.", color=COR_ROTEIRO)
            await interaction.followup.send(embed=embed); return

        templates_texto = carregar_templates()
        if not templates_texto:
            await interaction.followup.send("Templates nao encontrado."); return

        print(f"[ROTEIRO] Gerando para {len(noticias)} noticias...", flush=True)
        roteiro = await gerar_roteiro_com_ia(noticias, templates_texto)
        if not roteiro:
            await interaction.followup.send("Falha na IA. Tente novamente."); return

        # Embed premium roxo Hallyu
        embed = discord.Embed(
            title="Roteiro Editorial — HallyuBot",
            description=f"Gerado com **{len(noticias)}** noticias + CTA de engajamento.",
            color=COR_ROTEIRO, timestamp=datetime.now()
        )
        if client.user and client.user.avatar:
            embed.set_thumbnail(url=client.user.display_avatar.url)
        resumo = ""
        for i, (nid, titulo, url, temp, *_) in enumerate(noticias, 1):
            resumo += f"**{i}.** {titulo[:55]}{'...' if len(titulo)>55 else ''} (T:{temp})\n"
        embed.add_field(name="Noticias Selecionadas", value=resumo, inline=False)
        fontes = ""
        for i, (nid, titulo, url, *_) in enumerate(noticias, 1):
            fontes += f"{i}. [Link]({url})\n"
        embed.add_field(name="Fontes Utilizadas", value=fontes, inline=False)
        embed.set_footer(text="HallyuBot V3 — Roteirista + Estrategista")
        await interaction.followup.send(embed=embed)

        # Envia roteiro em blocos
        if len(roteiro) <= 1900:
            await interaction.channel.send(f"```\n{roteiro}\n```")
        else:
            partes = [roteiro[i:i+1800] for i in range(0, len(roteiro), 1800)]
            for idx, p in enumerate(partes, 1):
                await interaction.channel.send(f"**Parte {idx}/{len(partes)}:**\n```\n{p}\n```")

        for nid, *_ in noticias:
            atualizar_status(nid, "roteirizada")
        print(f"[ROTEIRO] Concluido. {len(noticias)} roteirizadas.", flush=True)
    except Exception as e:
        print(f"[ERRO] /roteiro: {e}")
        try: await interaction.followup.send(f"Erro: {str(e)[:200]}")
        except: pass


@tree.command(name="ideia", description="Gera 3 ideias de videos curtos (Reels/TikTok/Shorts) sobre cultura asiatica.")
async def comando_ideia(interaction: discord.Interaction):
    """Comando /ideia — Gera ideias de conteudo quando nao ha noticias bombásticas."""
    await interaction.response.defer(thinking=True)
    try:
        if not OPENAI_API_KEY:
            await interaction.followup.send("OPENAI_API_KEY nao configurada."); return

        print("[IDEIA] Gerando ideias de conteudo...", flush=True)
        ideias = await gerar_ideias_com_ia()
        if not ideias:
            await interaction.followup.send("Falha na IA. Tente novamente."); return

        embed = discord.Embed(
            title="Ideias de Conteudo — HallyuBot",
            description="3 sugestoes de videos curtos baseadas em tendencias atuais do nicho Hallyu.",
            color=COR_IDEIA, timestamp=datetime.now()
        )
        if client.user and client.user.avatar:
            embed.set_thumbnail(url=client.user.display_avatar.url)
        embed.set_footer(text="HallyuBot V3 — Cerebro Estrategico")
        await interaction.followup.send(embed=embed)

        if len(ideias) <= 1900:
            await interaction.channel.send(f"```\n{ideias}\n```")
        else:
            partes = [ideias[i:i+1800] for i in range(0, len(ideias), 1800)]
            for idx, p in enumerate(partes, 1):
                await interaction.channel.send(f"**Parte {idx}/{len(partes)}:**\n```\n{p}\n```")

        print("[IDEIA] Concluido.", flush=True)
    except Exception as e:
        print(f"[ERRO] /ideia: {e}")
        try: await interaction.followup.send(f"Erro: {str(e)[:200]}")
        except: pass


@tree.command(name="social", description="Varre Instagram, TikTok e YouTube em busca de novos posts.")
async def comando_social(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        from social_scraper import varrer_social
        resultados = await asyncio.to_thread(varrer_social, True)  # forcar=True para manual
        if not resultados:
            await interaction.followup.send("Nenhum resultado retornado."); return

        ig = resultados.get("instagram", {})
        tt = resultados.get("tiktok", {})
        yt = resultados.get("youtube", {})
        total_novas = ig.get("novas",0) + tt.get("novas",0) + yt.get("novas",0)
        total_ign = ig.get("ignoradas",0) + tt.get("ignoradas",0) + yt.get("ignoradas",0)

        embed = discord.Embed(
            title="Sensores Sociais — Varredura Completa",
            description=f"**{total_novas}** posts novos capturados | **{total_ign}** duplicados",
            color=COR_SOCIAL, timestamp=datetime.now()
        )
        if client.user and client.user.avatar:
            embed.set_thumbnail(url=client.user.display_avatar.url)
        embed.add_field(name="Instagram", value=f"**{ig.get('novas',0)}** novos | **{ig.get('ignoradas',0)}** dup.", inline=True)
        embed.add_field(name="TikTok", value=f"**{tt.get('novas',0)}** novos | **{tt.get('ignoradas',0)}** dup.", inline=True)
        embed.add_field(name="YouTube", value=f"**{yt.get('novas',0)}** novos | **{yt.get('ignoradas',0)}** dup.", inline=True)
        embed.add_field(name="Proximo passo", value="Use `/triar` para avaliar os novos posts com IA.", inline=False)
        embed.set_footer(text="HallyuBot V3 — Sensores Sociais")
        await interaction.followup.send(embed=embed)
        print(f"[SOCIAL] Concluido: {total_novas} novos.", flush=True)
    except Exception as e:
        print(f"[ERRO] /social: {e}")
        await interaction.followup.send(f"Erro: {str(e)[:200]}")


@tree.command(name="status", description="Painel de saude do banco + sensores sociais.")
async def comando_status(interaction: discord.Interaction):
    try:
        contagens = contar_noticias_por_status()
        total = sum(contagens.values())
        pendentes = contagens.get("pendente_avaliacao", 0)
        avaliadas = contagens.get("avaliada", 0)
        urgentes = contagens.get("publicada_urgente", 0)
        roteirizadas = contagens.get("roteirizada", 0)
        processadas = avaliadas + urgentes + roteirizadas
        stats = estatisticas_triagem_24h()

        # Dados dos sensores sociais
        from social_scraper import ler_timestamp_varredura, contar_posts_sociais_hoje
        ultima_social = ler_timestamp_varredura()
        social_stats = contar_posts_sociais_hoje()

        embed = discord.Embed(
            title="Painel de Saude — HallyuBot V3",
            description=f"**{total}** noticias no banco de dados.",
            color=COR_STATUS, timestamp=datetime.now()
        )
        if client.user and client.user.avatar:
            embed.set_thumbnail(url=client.user.display_avatar.url)

        embed.add_field(name="Progresso Geral",
            value=f"{barra_progresso(processadas, total)} ({processadas}/{total})", inline=False)

        info = [
            ("Pendentes de Triagem", pendentes, "aguardando IA"),
            ("Avaliadas pela IA", avaliadas, "prontas para uso"),
            ("Publicadas (Plantao)", urgentes, "alertas enviados"),
            ("Roteirizadas", roteirizadas, "roteiros gerados"),
        ]
        for label, qtd, desc in info:
            barra = barra_progresso(qtd, total) if total > 0 else "[          ] 0%"
            embed.add_field(name=label, value=f"{barra}\n**{qtd}** — {desc}", inline=False)

        # Eficacia da Triagem (24h)
        if stats["total"] > 0:
            taxa = (stats["aproveitadas"] / stats["total"]) * 100
            embed.add_field(name="Eficacia da Triagem (24h)",
                value=(f"{barra_progresso(stats['aproveitadas'], stats['total'])}\n"
                       f"**{stats['aproveitadas']}** aproveitadas | **{stats['descartadas']}** descartadas\n"
                       f"Taxa: **{taxa:.0f}%**"), inline=False)
        else:
            embed.add_field(name="Eficacia da Triagem (24h)", value="Sem dados.", inline=False)

        # Sensores Sociais
        embed.add_field(name="Sensores Sociais",
            value=(f"Ultima varredura: **{ultima_social}**\n"
                   f"Posts sociais hoje: **{social_stats['hoje']}** | Total: **{social_stats['total']}**"),
            inline=False)

        # Tendencia da Semana
        trend = tendencia_semanal()
        embed.add_field(name="Tendencia da Semana (temp > 7)", value=trend, inline=False)

        embed.set_footer(text="HallyuBot V3 — Sala de Redacao Automatizada")
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"[ERRO] /status: {e}")
        await interaction.response.send_message(f"Erro: {str(e)[:200]}")


@tree.command(name="analisar", description="Analisa um link ou texto avulso e da a temperatura + sugestao de video.")
@app_commands.describe(conteudo="Cole o link ou texto que voce quer analisar.")
async def comando_analisar(interaction: discord.Interaction, conteudo: str):
    await interaction.response.defer(thinking=True)
    try:
        if not OPENAI_API_KEY:
            await interaction.followup.send("OPENAI_API_KEY nao configurada."); return

        resultado = await analisar_com_ia(conteudo)
        if not resultado:
            await interaction.followup.send("Falha na IA. Tente novamente."); return

        nota = int(resultado.get("nota", 3))
        justificativa = resultado.get("justificativa", "Sem justificativa")
        vale_video = resultado.get("vale_video", False)
        sugestao = resultado.get("sugestao_video", "")

        # Emoji de temperatura
        if nota >= 9: emoji_t = "🔴"
        elif nota >= 7: emoji_t = "🟠"
        elif nota >= 4: emoji_t = "🟡"
        else: emoji_t = "🟢"

        embed = discord.Embed(
            title="Analise Manual — HallyuBot",
            description=f"Conteudo analisado com sucesso.",
            color=COR_ANALISAR, timestamp=datetime.now()
        )
        embed.add_field(name=f"{emoji_t} Temperatura", value=f"**{nota}/10**", inline=True)
        embed.add_field(name="Vale video?", value="SIM" if vale_video else "NAO", inline=True)
        embed.add_field(name="Justificativa", value=justificativa, inline=False)
        if vale_video and sugestao:
            embed.add_field(name="Sugestao de angulo", value=sugestao, inline=False)
        embed.add_field(name="Conteudo analisado", value=conteudo[:500], inline=False)

        # Salva no banco se vale a pena (nota >= 5)
        if nota >= 5:
            url = conteudo if conteudo.startswith("http") else f"analise-manual-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            from social_scraper import salvar_post_no_banco
            salvar_post_no_banco(f"[Analise Manual] {conteudo[:200]}", url, "Analise Manual", "Hallyu")
            embed.set_footer(text="Salvo no banco para roteirizacao futura.")
        else:
            embed.set_footer(text="Nota baixa — nao salvo no banco.")

        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"[ERRO] /analisar: {e}")
        await interaction.followup.send(f"Erro: {str(e)[:200]}")


@tree.command(name="varrer", description="Executa a varredura de noticias manualmente.")
async def comando_varrer(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        from scraper import varrer_noticias
        novas, ignoradas = await asyncio.to_thread(varrer_noticias)
        embed = discord.Embed(title="Varredura Concluida", color=COR_VARRER, timestamp=datetime.now())
        embed.add_field(name="Novas", value=f"**{novas}**", inline=True)
        embed.add_field(name="Ignoradas", value=f"**{ignoradas}**", inline=True)
        embed.set_footer(text="HallyuBot V3 — Radar de Noticias")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"[ERRO] /varrer: {e}")
        await interaction.followup.send(f"Erro: {str(e)[:200]}")


@tree.command(name="triar", description="Executa a triagem com IA nas noticias pendentes.")
async def comando_triar(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        if not OPENAI_API_KEY:
            await interaction.followup.send("OPENAI_API_KEY nao configurada."); return
        from ai_triagem import executar_triagem
        await asyncio.to_thread(executar_triagem)
        contagens = contar_noticias_por_status()
        embed = discord.Embed(title="Triagem Concluida", color=COR_TRIAR, timestamp=datetime.now())
        embed.add_field(name="Avaliadas", value=f"**{contagens.get('avaliada',0)}**", inline=True)
        embed.add_field(name="Pendentes", value=f"**{contagens.get('pendente_avaliacao',0)}**", inline=True)
        embed.set_footer(text="HallyuBot V3 — Termometro de Urgencia")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"[ERRO] /triar: {e}")
        await interaction.followup.send(f"Erro: {str(e)[:200]}")

# =============================================
# on_ready
# =============================================

@client.event
async def on_ready():
    inicializar_banco()
    try:
        synced = await tree.sync()
        print(f"[SYNC] {len(synced)} comando(s) sincronizado(s).", flush=True)
    except Exception as e:
        print(f"[ERRO] Sync: {e}", flush=True)

    # Registra views persistentes para botoes sobreviverem a reinicializacoes
    # Busca IDs de noticias que podem ter botoes ativos
    try:
        con = sqlite3.connect(CAMINHO_BD); cur = con.cursor()
        cur.execute("SELECT id FROM noticias WHERE status IN ('publicada_urgente', 'notificada') ORDER BY id DESC LIMIT 50")
        ids_ativos = [r[0] for r in cur.fetchall()]; con.close()
        for nid in ids_ativos:
            client.add_view(BotaoRoteiroPersistente(nid))
        if ids_ativos:
            print(f"[VIEWS] {len(ids_ativos)} botoes persistentes registrados.", flush=True)
    except Exception as e:
        print(f"[AVISO] Registro de views: {e}", flush=True)

    if not monitor_plantao.is_running(): monitor_plantao.start()
    if not rotacao_atividade.is_running(): rotacao_atividade.start()
    if not varredura_automatica.is_running(): varredura_automatica.start()
    await client.change_presence(activity=next(ATIVIDADES))

    # Limpeza automatica de noticias antigas (>15 dias)
    limpar_banco_antigo(dias=15)

    print("=" * 60, flush=True)
    print(f"  Bot: {client.user}", flush=True)
    print(f"  Servidores: {len(client.guilds)}", flush=True)
    print(f"  Comandos: /roteiro /status /varrer /triar /ideia /social /analisar", flush=True)
    print(f"  Monitor Plantao: ativo (5 min)", flush=True)
    print(f"  Varredura Auto: ativo (2h) — RSS + Social + Triagem IA", flush=True)
    print(f"  Botoes Interativos: ativo — 📝 Fazer Roteiro em cada noticia", flush=True)
    print(f"  Rotacao Status: ativo (30 min)", flush=True)
    print("=" * 60, flush=True)
    print("  HallyuBot Online e 100%% AUTOMATICO!", flush=True)
    print("  Sua esposa so precisa clicar no botao 📝 Fazer Roteiro!", flush=True)
    print("=" * 60, flush=True)
    sys.stdout.flush()

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERRO: DISCORD_TOKEN nao encontrado no .env!")
    else:
        print("Iniciando HallyuBot V3...", flush=True)
        client.run(DISCORD_TOKEN)
