@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title CLIPADOR by @kauan.ssw - VIDEO
echo Clipa um video comum do YouTube (nao precisa ser live).
echo Ele baixa o video, escolhe os melhores momentos e manda pro Telegram.
echo.
set /p LINK=Cole o link do video e aperte Enter:
echo.
py -3.12 clipador.py --video "%LINK%"
echo.
echo Os clipes tambem ficam na pasta clipes_prontos.
pause
