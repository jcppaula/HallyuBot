@echo off
echo ===================================================
echo   HallyuBot - Atualizador e Inicializador Automatico
echo ===================================================
echo.

echo [1/3] Navegando para a pasta do bot...
cd /d "%~dp0"

echo [2/3] Baixando atualizacoes do GitHub...
git pull

echo [3/4] Ativando ambiente virtual e instalando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo [4/4] Ligando o bot...
python main.py

pause
