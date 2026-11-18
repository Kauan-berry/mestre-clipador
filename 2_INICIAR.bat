@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title mestre-clipador - nao feche esta janela
echo Atualizando o yt-dlp (o YouTube muda direto)...
py -3.12 -m pip install --upgrade --quiet "yt-dlp[default]"
:loop
py -3.12 clipador.py
echo.
echo O clipador parou. Reiniciando em 10 segundos... (feche a janela para desligar)
timeout /t 10 >nul
goto loop
