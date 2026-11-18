@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo (Antes, mande um "oi" para o seu bot no Telegram.)
echo.
py -3.12 clipador.py --descobrir-chat
echo.
echo Cole esse numero no config.ini (telegram_chat_id), SALVE o arquivo
echo e depois aperte qualquer tecla aqui para testar o envio.
pause
py -3.12 clipador.py --testar-telegram
pause
