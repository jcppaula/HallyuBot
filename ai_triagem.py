"""
=============================================
HallyuBot V3 - Módulo de Triagem com IA (Termômetro de Urgência)
=============================================
Este script é o "Editor-Chefe" automatizado do bot.
Ele pega as notícias pendentes no banco de dados, envia cada uma para
o GPT-4o-mini para avaliação de urgência (nota de 1 a 10), e salva
a temperatura e justificativa de volta no banco.

Notícias com nota >= 9 disparam um alerta de plantão urgente no terminal.

Fluxo:
  1. Busca notícias com status = 'pendente_avaliacao'
  2. Envia título + link para o GPT com prompt de editor-chefe
  3. Recebe JSON { "nota": int, "justificativa": str }
  4. Atualiza banco: coluna 'temperatura' + 'justificativa' + status → 'avaliada'
  5. Se nota >= 9 → alerta de plantão urgente no terminal
"""

import os
import sys
import json
import sqlite3
import time
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Corrige encoding do terminal no Windows (suporte a emojis e acentos)
sys.stdout.reconfigure(encoding="utf-8")

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Caminho do banco de dados (mesmo usado nos outros módulos)
CAMINHO_BD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hallyubot.db")

# =============================================
# Configuração do cliente OpenAI
# =============================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Modelo utilizado (GPT-4o-mini: rápido, barato e eficiente para triagem)
MODELO = "gpt-4o-mini"

# =============================================
# Prompt de Sistema — Engenharia de Prompt Modular
# =============================================
# Seguindo a documentação V3: o prompt é construído em blocos separados
# (REGRA_TOM_DE_VOZ, REGRA_FORMATACAO, BASE_DE_FATOS) para evitar
# confusão sistêmica.

REGRA_TOM_DE_VOZ = (
    "Você é um editor-chefe experiente de um portal de cultura asiática "
    "especializado em K-pop, K-dramas e C-dramas. "
    "Você avalia notícias com olhar crítico e pragmático."
)

REGRA_FORMATACAO = (
    "Retorne a resposta ESTRITAMENTE em formato JSON com as chaves: "
    '"nota" (int de 1 a 10), "justificativa" (string curta de até 80 caracteres) e "resumo" (string de 3 a 4 linhas resumindo a notícia). '
    "Não inclua nenhum texto fora do JSON. Não use markdown."
)

BASE_DE_FATOS = (
    "Critérios de avaliação de urgência:\n"
    "- Notas 1-3: Notícias rotineiras, fofocas leves, listas genéricas.\n"
    "- Notas 4-6: Notícias relevantes mas sem caráter de urgência (entrevistas, reviews, rankings).\n"
    "- Notas 7-8: Notícias importantes (anúncios de comeback de grupos médios, mudanças em elenco de doramas populares, premiações).\n"
    "- Notas 9-10: EXCLUSIVAS para eventos de altíssimo impacto:\n"
    "  * Escândalos de namoro de idols de primeira linha\n"
    "  * Disband (separação) de grupos estabelecidos\n"
    "  * Mortes ou acidentes graves de celebridades\n"
    "  * Anúncios de comeback de grupos gigantes (BTS, BLACKPINK, EXO, TWICE, etc.)\n"
    "  * Polêmicas que dominem trending topics globais\n"
)

REGRA_ZERO_VS_NULO = (
    "NUNCA invente ou presuma dados. Se a notícia não fornecer informações "
    "suficientes para avaliar, atribua nota 3 e justifique com "
    "'informação insuficiente para avaliar'."
)

REGRA_FILTRO_SOCIAL = (
    "REGRA ESPECIAL PARA POSTS DE REDES SOCIAIS (Instagram, TikTok, YouTube):\n"
    "Identifique se o conteúdo é ESTÉTICO ou INFORMATIVO:\n"
    "- ESTÉTICO: fotos de ensaio, selfies de idols, vídeos de dança sem contexto, "
    "fotos de aeroporto, posts promocionais genéricos sem novidade concreta.\n"
    "  → Nota OBRIGATORIAMENTE inferior a 4.\n"
    "- INFORMATIVO: anúncio de data de comeback, teaser de MV, renovação/saída de contrato, "
    "anúncio de turnê, trailer de dorama, mudança de elenco, colaboração confirmada.\n"
    "  → Avaliar normalmente conforme os critérios de urgência.\n"
    "Na justificativa, indique se classificou como 'estético' ou 'informativo'."
)

# Monta o System Prompt completo a partir dos blocos modulares
SYSTEM_PROMPT = f"{REGRA_TOM_DE_VOZ}\n\n{BASE_DE_FATOS}\n\n{REGRA_FILTRO_SOCIAL}\n\n{REGRA_FORMATACAO}\n\n{REGRA_ZERO_VS_NULO}"


def buscar_pendentes():
    """
    Conecta no banco de dados e retorna todas as notícias que ainda
    não foram avaliadas pela IA (status = 'pendente_avaliacao').

    Returns:
        Lista de tuplas (id, titulo, url, fonte, pilar).
    """
    try:
        conexao = sqlite3.connect(CAMINHO_BD)
        try:
            cursor = conexao.cursor()

            cursor.execute("""
                SELECT id, titulo, url, fonte, pilar
                FROM noticias
                WHERE status = 'pendente_avaliacao'
                ORDER BY data_coleta ASC
            """)

            pendentes = cursor.fetchall()
            return pendentes
        finally:
            conexao.close()
    except Exception as e:
        print(f"  ❌ Erro ao buscar notícias pendentes: {e}")
        return []


def avaliar_com_ia(cliente_openai, titulo, url):
    """
    Envia o título e link de uma notícia para o GPT-4o-mini
    e recebe a avaliação de urgência em formato JSON.

    Args:
        cliente_openai: Instância do cliente OpenAI.
        titulo: Título da notícia.
        url: Link da notícia.

    Returns:
        Dicionário com 'nota' (int) e 'justificativa' (str),
        ou None em caso de erro.
    """
    # Monta a mensagem do usuário com os dados da notícia
    mensagem_usuario = (
        f"Avalie a urgência desta notícia de cultura asiática:\n\n"
        f"Título: {titulo}\n"
        f"Link: {url}"
    )

    try:
        # Chama a API do GPT com response_format JSON obrigatório
        resposta = cliente_openai.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": mensagem_usuario}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,  # Baixa temperatura = respostas mais consistentes
            max_tokens=500     # JSON com nota, justificativa e resumo
        )

        # Extrai o conteúdo JSON da resposta
        conteudo = resposta.choices[0].message.content
        dados = json.loads(conteudo)

        # Valida se as chaves esperadas existem
        nota = int(dados.get("nota", 3))
        justificativa = str(dados.get("justificativa", "Sem justificativa"))
        resumo = str(dados.get("resumo", "Sem resumo disponível."))

        # Garante que a nota está no range válido (1-10)
        nota = max(1, min(10, nota))

        return {"nota": nota, "justificativa": justificativa, "resumo": resumo}

    except json.JSONDecodeError as e:
        print(f"    ⚠️  Erro ao decodificar JSON da IA: {e}")
        return None

    except Exception as e:
        print(f"    ⚠️  Erro na comunicação com a OpenAI: {e}")
        return None


def atualizar_noticia(noticia_id, nota, justificativa, resumo):
    """
    Atualiza uma notícia no banco de dados com a nota da IA e resumo.
    Muda o status de 'pendente_avaliacao' para 'avaliada'.

    Args:
        noticia_id: ID da notícia no banco.
        nota: Nota de temperatura (1-10) atribuída pela IA.
        justificativa: Texto curto explicando a nota.
        resumo: Pequeno resumo da notícia.
    """
    try:
        conexao = sqlite3.connect(CAMINHO_BD)
        try:
            cursor = conexao.cursor()

            cursor.execute("""
                UPDATE noticias
                SET temperatura = ?,
                    justificativa = ?,
                    resumo = ?,
                    status = 'avaliada'
                WHERE id = ?
            """, (nota, justificativa, resumo, noticia_id))

            conexao.commit()
        finally:
            conexao.close()
    except Exception as e:
        print(f"    ❌ Erro ao atualizar notícia ID {noticia_id} no banco: {e}")


def exibir_alerta_plantao(titulo, nota, justificativa):
    """
    Exibe um alerta visual chamativo no terminal quando uma notícia
    recebe nota >= 9 (plantão urgente).
    """
    print("\n" + "🚨" * 25)
    print("🚨🚨🚨  PLANTÃO URGENTE DETECTADO  🚨🚨🚨")
    print("🚨" * 25)
    print(f"  📰 Título: {titulo}")
    print(f"  🔥 Temperatura: {nota}/10")
    print(f"  💬 Justificativa: {justificativa}")
    print("🚨" * 25 + "\n")


def executar_triagem():
    """
    Função principal da triagem.
    Percorre todas as notícias pendentes, envia para o GPT avaliar,
    salva os resultados no banco e exibe alertas quando necessário.
    """
    print("=" * 60)
    print("🧠 HallyuBot V3 — Triagem com IA (Termômetro de Urgência)")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}")
    print(f"🤖 Modelo: {MODELO}")
    print("=" * 60)

    # Verifica se a chave da API está configurada
    if not OPENAI_API_KEY:
        print("\n❌ ERRO: OPENAI_API_KEY não encontrada no arquivo .env!")
        print("Adicione sua chave no .env e tente novamente.")
        return

    # Inicializa o cliente OpenAI
    cliente = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ Cliente OpenAI inicializado com sucesso.\n")

    # Busca as notícias pendentes de avaliação
    pendentes = buscar_pendentes()
    total = len(pendentes)

    if total == 0:
        print("📭 Nenhuma notícia pendente de avaliação encontrada.")
        print("   Execute o scraper.py primeiro para popular o banco.")
        return {"total": 0, "avaliadas": 0, "erros": 0, "urgentes": 0, "distribuicao": {}}

    print(f"📋 {total} notícias pendentes encontradas. Iniciando triagem...\n")

    # Contadores para o relatório final
    avaliadas = 0
    erros = 0
    alertas_urgentes = 0
    distribuicao = {i: 0 for i in range(1, 11)}  # Distribuição de notas 1-10

    # -----------------------------------------------
    # Loop principal de triagem
    # -----------------------------------------------
    for indice, (noticia_id, titulo, url, fonte, pilar) in enumerate(pendentes, 1):
        # Exibe progresso
        print(f"  [{indice}/{total}] 📰 {titulo[:70]}{'...' if len(titulo) > 70 else ''}")
        print(f"           Fonte: {fonte} | Pilar: {pilar}")

        # Envia para o GPT avaliar
        resultado = avaliar_com_ia(cliente, titulo, url)

        if resultado:
            nota = resultado["nota"]
            justificativa = resultado["justificativa"]
            resumo = resultado.get("resumo", "")

            # Salva a avaliação no banco de dados
            atualizar_noticia(noticia_id, nota, justificativa, resumo)

            # Exibe a nota atribuída
            # Emojis diferentes conforme a faixa de temperatura
            if nota >= 9:
                emoji = "🔴"
            elif nota >= 7:
                emoji = "🟠"
            elif nota >= 4:
                emoji = "🟡"
            else:
                emoji = "🟢"

            print(f"           {emoji} Temperatura: {nota}/10 — {justificativa}")

            # Verifica se é alerta de plantão urgente (nota >= 9)
            if nota >= 9:
                exibir_alerta_plantao(titulo, nota, justificativa)
                alertas_urgentes += 1

            # Atualiza contadores
            avaliadas += 1
            distribuicao[nota] += 1

        else:
            # A IA não conseguiu avaliar (erro de conexão, JSON inválido, etc.)
            print(f"           ⚠️  Falha na avaliação — notícia permanece como pendente.")
            erros += 1

        # Pequena pausa entre requisições para respeitar rate limits
        # GPT-4o-mini é generoso, mas é bom ser educado com a API
        if indice < total:
            time.sleep(0.5)

    # -----------------------------------------------
    # Relatório final da triagem
    # -----------------------------------------------
    print("\n" + "=" * 60)
    print("📊 RELATÓRIO DA TRIAGEM")
    print("=" * 60)
    print(f"  ✅ Notícias avaliadas com sucesso:  {avaliadas}/{total}")
    print(f"  ❌ Falhas de avaliação:              {erros}")
    print(f"  🚨 Alertas de plantão urgente:       {alertas_urgentes}")

    # Exibe a distribuição de temperaturas
    print("\n  📈 Distribuição de temperaturas:")
    for nota in range(10, 0, -1):
        quantidade = distribuicao[nota]
        if quantidade > 0:
            barra = "█" * quantidade
            if nota >= 9:
                label = "🔴"
            elif nota >= 7:
                label = "🟠"
            elif nota >= 4:
                label = "🟡"
            else:
                label = "🟢"
            print(f"     {label} Nota {nota:>2}: {barra} ({quantidade})")

    print("=" * 60)
    
    return {
        "total": total,
        "avaliadas": avaliadas,
        "erros": erros,
        "urgentes": alertas_urgentes,
        "distribuicao": distribuicao
    }


# =============================================
# Execução manual (sem apscheduler por enquanto)
# =============================================
if __name__ == "__main__":
    executar_triagem()
