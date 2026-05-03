"""
=============================================
HallyuBot V3 - Módulo de Banco de Dados
=============================================
Script responsável por criar e inicializar o banco de dados SQLite local.
Cria três tabelas principais:
  - noticias: Armazena as notícias coletadas (com URL UNIQUE para upsert).
  - calendario_hallyu: Armazena eventos do Oráculo (comebacks, enlistments, estreias).
  - trending_topics: Armazena tendências descobertas pelo Discovery Pipeline.
"""

import sqlite3
import os

# Caminho do banco de dados na pasta 'data/' do projeto
CAMINHO_BD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hallyubot.db")


def criar_conexao():
    """
    Cria e retorna uma conexão com o banco de dados SQLite.
    Também garante que a pasta 'data/' exista antes de criar o arquivo.
    """
    # Garante que a pasta 'data/' exista
    os.makedirs(os.path.dirname(CAMINHO_BD), exist_ok=True)

    # Cria a conexão com o banco de dados
    conexao = sqlite3.connect(CAMINHO_BD)
    print(f"[BD] Conexão estabelecida com: {CAMINHO_BD}")
    return conexao


def criar_tabelas(conexao):
    """
    Cria as três tabelas principais do HallyuBot no banco de dados.
    Usa IF NOT EXISTS para evitar erros em execuções repetidas.
    """
    cursor = conexao.cursor()

    # -----------------------------------------------
    # TABELA 1: noticias
    # -----------------------------------------------
    # A coluna 'url' possui restrição UNIQUE para implementar a lógica
    # de "upsert" descrita na documentação. Usamos INSERT OR IGNORE
    # nas inserções futuras para evitar duplicatas caso o bot reinicie.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS noticias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            fonte TEXT NOT NULL,
            pilar TEXT NOT NULL,
            resumo TEXT,
            temperatura INTEGER DEFAULT 0,
            justificativa TEXT,
            status TEXT DEFAULT 'pendente_avaliacao',
            data_publicacao TEXT,
            data_coleta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            enviada_discord INTEGER DEFAULT 0
        )
    """)
    print("[BD] Tabela 'noticias' criada/verificada com sucesso.")

    # -----------------------------------------------
    # TABELA 2: calendario_hallyu
    # -----------------------------------------------
    # Módulo "O Oráculo": rastreia datas de comebacks, enlistments
    # militares e estreias de doramas. Inclui campo 'status' para
    # controlar alertas de alteração ou cancelamento.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calendario_hallyu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_evento TEXT NOT NULL,
            titulo_evento TEXT NOT NULL,
            artista_ou_titulo TEXT,
            data_evento TEXT,
            status TEXT DEFAULT 'confirmado',
            fonte_url TEXT,
            notas TEXT,
            data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[BD] Tabela 'calendario_hallyu' criada/verificada com sucesso.")

    # -----------------------------------------------
    # TABELA 3: trending_topics
    # -----------------------------------------------
    # Módulo "Discovery Pipeline": armazena criadores e tendências
    # descobertos via YouTube API e Apify (Instagram/TikTok).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trending_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plataforma TEXT NOT NULL,
            nome_perfil TEXT NOT NULL,
            url_perfil TEXT UNIQUE,
            hashtag_origem TEXT,
            seguidores INTEGER DEFAULT 0,
            visualizacoes INTEGER DEFAULT 0,
            categoria TEXT,
            recomendado INTEGER DEFAULT 0,
            data_descoberta TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[BD] Tabela 'trending_topics' criada/verificada com sucesso.")

    # Salva todas as alterações no banco
    conexao.commit()
    print("[BD] Todas as tabelas foram criadas com sucesso!")


def inicializar_banco():
    """
    Função principal que orquestra a criação do banco de dados.
    Pode ser chamada de qualquer lugar do projeto.
    """
    conexao = criar_conexao()
    criar_tabelas(conexao)
    conexao.close()
    print("[BD] Banco de dados inicializado e conexão encerrada.")


# Executa a inicialização quando o script é rodado diretamente
if __name__ == "__main__":
    print("=" * 50)
    print("HallyuBot V3 - Inicializando Banco de Dados...")
    print("=" * 50)
    inicializar_banco()
