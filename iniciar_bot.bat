@echo off
echo ===================================================
echo   HallyuBot - Atualizador e Inicializador Automatico
echo ===================================================
echo.

echo [1/3] Navegando para a pasta do bot...
cd /d "%~dp0"

echo [2/3] Baixando atualizacoes do GitHub...
git pull

echo [3/3] Ativando ambiente virtual (venv) e ligando o bot...
call venv\Scripts\activate.bat
python main.py

pause
