@echo off
cd /d "%~dp0"
echo Apagando gravacoes e memoria do teste (os clipes prontos ficam)...
if exist estado.json del /q estado.json
if exist gravacoes rmdir /s /q gravacoes
echo Pronto. Agora o clipador comeca "zerado" para a proxima live.
pause
