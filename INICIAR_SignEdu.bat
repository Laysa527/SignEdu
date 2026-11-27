@echo off
chcp 65001 >nul
title SignEdu
rem ============================================================================
rem  Inicia o SignEdu. Fica DENTRO da pasta do projeto (ao lado de backend\ e frontend\).
rem  Um servidor so, com dois enderecos:
rem    - neste computador: http://localhost:5000 (sem aviso de seguranca)
rem    - celular ou outro computador na mesma rede: https://IP-DESTE-PC:5443
rem ============================================================================
set PROJETO=%~dp0
cd /d "%PROJETO%"
echo === SignEdu ===

rem ---- 1. Python com as bibliotecas (o primeiro que existir) ----
rem    a) venv dentro do projeto (pasta venv\)
rem    b) venv que ja esta ativado no terminal (ex.: terminal do VS Code)
rem    c) venv antigo do 2.2 guardado em Backup - antigos\codigo\SignEdu_2.2\venv, no PC da Laysa
rem    d) nenhum: cria o venv\ agora (precisa de internet na primeira vez)
set PY=
if exist "%PROJETO%venv\Scripts\python.exe" set PY=%PROJETO%venv\Scripts\python.exe
if not defined PY if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set PY=%VIRTUAL_ENV%\Scripts\python.exe
if not defined PY for %%N in (".." "..\.." "..\..\.." "..\..\..\..") do (
  for /d %%D in ("%PROJETO%%%~N\Backup - antigos\c*digo") do (
    if exist "%%~fD\SignEdu_2.2\venv\Scripts\python.exe" set PY=%%~fD\SignEdu_2.2\venv\Scripts\python.exe
  )
)
if not defined PY (
  echo Primeira vez neste computador: criando o ambiente do Python.
  where py >nul 2>&1 && (py -3 -m venv venv) || (python -m venv venv)
  if not exist "%PROJETO%venv\Scripts\python.exe" (
    echo Nao consegui criar o ambiente. Instale o Python 3 em python.org, marcando "Add to PATH", e tente de novo.
    pause
    exit /b
  )
  set PY=%PROJETO%venv\Scripts\python.exe
)
echo Python: %PY%
"%PY%" -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
if errorlevel 1 (
  echo Este Python e muito antigo. O SignEdu precisa do Python 3.11 ou mais novo, de python.org.
  pause
  exit /b
)

rem ---- 1b. Confere as bibliotecas; se faltar alguma (ou versao diferente), instala ----
"%PY%" -c "import flask, flask_sqlalchemy, pymysql, cv2, mediapipe, sklearn, joblib, dotenv, cryptography; assert sklearn.__version__ == '1.9.1'" >nul 2>&1
if errorlevel 1 (
  echo Instalando as bibliotecas do backend\requirements.txt. Pode levar alguns minutos e precisa de internet.
  "%PY%" -m pip install -r backend\requirements.txt
  "%PY%" -c "import flask, flask_sqlalchemy, pymysql, cv2, mediapipe, sklearn, joblib, dotenv" >nul 2>&1
  if errorlevel 1 (
    echo Nao consegui instalar as bibliotecas. Confira a internet e tente de novo.
    pause
    exit /b
  )
)

rem ---- 2. Arquivos que nao vao no GitHub ----
if not exist "backend\.env" (
  copy "backend\.env.example" "backend\.env" >nul
  echo.
  echo Criei o arquivo backend\.env. Coloque nele a senha do SEU MySQL na linha DB_PASSWORD=,
  echo salve, feche o Bloco de Notas e abra este arquivo de novo.
  notepad "backend\.env"
  pause
  exit /b
)
for %%F in (hand_landmarker.task pose_landmarker.task face_landmarker.task) do (
  if not exist "backend\%%F" (
    echo Falta o arquivo backend\%%F, modelo do MediaPipe. Veja o README, secao de instalacao.
    pause
    exit /b
  )
)

rem ---- 3. Liga o servidor ----
set HOST=127.0.0.1
set PORT=5000
set HTTPS=0
set PORTA_REDE=5443
echo.
echo Deixe esta janela aberta enquanto usa (pode minimizar).
echo NAO aperte Ctrl + C aqui e evite clicar dentro dela. Para parar, feche a janela.
echo Se o Windows perguntar sobre o firewall, clique em "Permitir acesso".
echo No celular/outro PC: abra o endereco https que aparece abaixo e, no aviso de
echo conexao nao particular, toque em "Avancado" e "Continuar".
echo.
start "" cmd /c "timeout /t 40 >nul & start http://localhost:5000"

rem ---- 4. Endereco pela internet (opcional) ----
rem Se o cloudflared.exe estiver nesta pasta, abre uma segunda janela com um endereco
rem https://....trycloudflare.com que funciona de QUALQUER lugar (ex.: a feira acessando
rem o servidor que esta em casa). O endereco muda a cada vez; a mensagem pronta para mandar
rem fica no arquivo ENDERECO_PARA_ENVIAR.txt, que abre sozinho no Bloco de Notas.
if exist "%PROJETO%cloudflared.exe" (
  echo Abrindo tambem o endereco pela internet: o link aparece na janela "SignEdu - internet"
  echo e no arquivo ENDERECO_PARA_ENVIAR.txt, que abre sozinho no Bloco de Notas.
  start "SignEdu - internet" cmd /k ""%PY%" -u "%PROJETO%backend\tunel_internet.py""
)
"%PY%" -u backend\app.py
echo.
echo O servidor parou. Feche esta janela e abra o INICIAR_SignEdu.bat de novo.
pause
