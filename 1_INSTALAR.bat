@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   INSTALADOR DO MESTRE-CLIPADOR
echo ============================================
echo.

py -3.12 --version >nul 2>nul
if errorlevel 1 (
  echo Instalando Python...
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
  echo  rode o 1_INSTALAR.bat DE NOVO para terminar.
  echo ============================================
  pause
  exit /b
)

echo Instalando bibliotecas do Python...
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install --upgrade "yt-dlp[default]" numpy requests faster-whisper
if errorlevel 1 (
  echo.
  echo ERRO na instalacao das bibliotecas. Tire um print desta janela e abra uma "issue" no GitHub do projeto.
  pause
  exit /b
)

echo.
echo Baixando o modelo de legenda (uns 500 MB, so na primeira vez)...
py -3.12 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('Modelo OK')"
if errorlevel 1 (
  echo.
  echo ERRO ao baixar o modelo de legenda. Tire um print e abra uma "issue" no GitHub do projeto.
  pause
  exit /b
)

echo.
echo ============================================
echo  TUDO PRONTO! Agora configure o config.ini
echo  (veja o README.md, passo 3).
echo ============================================
pause
