@echo off
echo ===================================================
echo   HallyuBot - Atualizador e Inicializador Automatico
echo ===================================================
echo.

echo [1/4] Navegando para a pasta do bot...
cd /d "%~dp0"

echo [2/4] Baixando atualizacoes do GitHub...
git pull

echo [3/4] Preparando ambiente virtual...
if not exist "venv\Scripts\activate.bat" (
    echo Ambiente virtual nao encontrado. Criando venv...
    python -m venv venv
)

echo Ativando ambiente virtual e instalando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo [4/4] Ligando o bot...
python main.py

pause
