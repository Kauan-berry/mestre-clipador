@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title CLIPADOR by @kauan.ssw - TESTE
echo Abra o YouTube, ache QUALQUER live de jogo que esteja no ar agora
echo e copie o link dela.
echo.
set /p LINK=Cole o link aqui e aperte Enter:
echo.
echo Deixe rodando uns 25 minutos. Deve chegar pelo menos 1 clipe no Telegram.
echo Depois feche esta janela e rode o LIMPAR_TESTE.bat
echo.
py -3.12 clipador.py --url "%LINK%"
pause
