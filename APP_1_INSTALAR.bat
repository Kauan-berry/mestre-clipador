@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Instalador do mestre-clipador (app)
echo ============================================
echo   INSTALADOR DO MESTRE-CLIPADOR (APP)
echo ============================================
echo.

py -3.12 --version >nul 2>nul
if errorlevel 1 (
  echo Instalando Python 3.12...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  set FALTOU=1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo Instalando FFmpeg...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
  set FALTOU=1
)
where deno >nul 2>nul
if errorlevel 1 (
  echo Instalando Deno - o yt-dlp precisa dele para o YouTube...
  winget install -e --id DenoLand.Deno --accept-source-agreements --accept-package-agreements
  set FALTOU=1
)
if defined FALTOU (
  echo.
  echo ============================================
  echo  Programas instalados. FECHE esta janela e
  echo  rode o APP_1_INSTALAR.bat DE NOVO.
  echo ============================================
  pause
  exit /b
)

echo Instalando bibliotecas...
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install --upgrade "yt-dlp[default]" numpy requests faster-whisper pywebview
if errorlevel 1 (
  echo.
  echo ERRO na instalacao das bibliotecas. Tire um print e abra uma "issue" no GitHub.
  pause
  exit /b
)

echo.
echo Baixando o modelo de legenda (uns 500 MB, so na primeira vez)...
py -3.12 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('Modelo OK')"
if errorlevel 1 (
  echo ERRO ao baixar o modelo de legenda.
  pause
  exit /b
)

echo.
echo Criando atalho na Area de Trabalho...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\mestre-clipador.lnk'); $s.TargetPath='%~dp0APP_ABRIR.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"

echo.
echo ============================================
echo  TUDO PRONTO! Abra pelo atalho "mestre-clipador"
echo  na Area de Trabalho (ou pelo APP_ABRIR.bat).
echo ============================================
pause
