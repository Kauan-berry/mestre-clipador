@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title mestre-clipador
py -3.12 -m pip install --upgrade --quiet "yt-dlp[default]" >nul 2>nul
py -3.12 app\main.py
if errorlevel 1 (
  echo.
  echo O app fechou com erro. Tire um print desta janela.
  pause
)
