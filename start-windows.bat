@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

title WillTechBH IA Offline - Nucleo Portatil
color 0b
mode con: cols=82 lines=32

:: ------------------------------------------------------------------
:: ZERO FOOTPRINT — tudo fica no drive, nada no PC hospedeiro
:: ------------------------------------------------------------------
set "OLLAMA_MODELS=%~dp0ollama\data"
set "APPDATA=%~dp0data\anythingllm"
set "STORAGE_DIR=%~dp0data\anythingllm"
set "OLLAMA_KEEP_ALIVE=-1"
set "userprofile=%~dp0data\ollama-profile"
set "localappdata=%~dp0data\ollama-local"

echo.
echo   [INICIANDO WILLTECHBH IA OFFLINE...]
echo   Analisando hardware e conectividade...
echo.

:: ======================================================
:: 1. DETECCAO DE INTERNET — bonus, nunca obrigacao
:: ======================================================
set "WEB_MODE=OFFLINE"
set "WEB_MSG=Air-Gap Total - 100pct Local"
set "WEB_BONUS=0"

ping -n 1 -w 1500 8.8.8.8 >nul 2>&1
if %errorlevel%==0 (
    set "WEB_MODE=ONLINE"
    set "WEB_MSG=Web Bonus ATIVO - Contexto em tempo real"
    set "WEB_BONUS=1"
)

:: ======================================================
:: 2. DETECCAO DE GPU
:: ======================================================
set "OLLAMA_NUM_THREADS=%NUMBER_OF_PROCESSORS%"
set "ACCEL_MSG=CPU %NUMBER_OF_PROCESSORS% threads"

wmic path win32_VideoController get name 2>nul | findstr /i "NVIDIA" >nul
if %errorlevel%==0 (
    set "OLLAMA_GPU_LAYERS=99"
    set "ACCEL_MSG=NVIDIA GPU - CUDA ativado"
    goto DETECT_RAM
)

wmic path win32_VideoController get name 2>nul | findstr /i "RX 7900\|RX 7800\|RX 7700" >nul
if %errorlevel%==0 (
    set "OLLAMA_GPU_LAYERS=99"
    set "ACCEL_MSG=AMD RX7000 - ROCm ativado"
    goto DETECT_RAM
)

wmic path win32_VideoController get name 2>nul | findstr /i "AMD\|Radeon\|Intel Arc" >nul
if %errorlevel%==0 (
    set "OLLAMA_VULKAN=1"
    set "ACCEL_MSG=GPU Vulkan - Aceleracao parcial"
    goto DETECT_RAM
)

:DETECT_RAM
:: ======================================================
:: 3. DETECCAO DE RAM E SELECAO DO MODELO
:: ======================================================
for /f "tokens=2 delims==" %%A in ('wmic computersystem get TotalPhysicalMemory /value 2^>nul') do set "RAM_BYTES=%%A"
powershell -NoProfile -Command "[Math]::Round(%RAM_BYTES% / 1GB)" > "%temp%\wtbh_ram.txt" 2>nul
set /p RAM_GB=<"%temp%\wtbh_ram.txt"
del "%temp%\wtbh_ram.txt" >nul 2>&1

if !RAM_GB! LEQ 6 (
    set "TARGET_MODEL=nano-1b"
    set "PROFILE=NANO"
    set "FEATURES=Juridico + Programacao Local"
) else if !RAM_GB! LEQ 10 (
    set "TARGET_MODEL=fast-8b"
    set "PROFILE=FAST"
    set "FEATURES=Juridico + Programacao Local"
) else if !RAM_GB! LEQ 16 (
    set "TARGET_MODEL=smart-12b"
    set "PROFILE=SMART"
    set "FEATURES=Juridico + Programacao + Visao Local"
) else if !RAM_GB! LEQ 28 (
    set "TARGET_MODEL=premium-24b"
    set "PROFILE=PREMIUM"
    set "FEATURES=Juridico + Programacao + Visao Local"
) else (
    set "TARGET_MODEL=ultra-32b"
    set "PROFILE=ULTRA"
    set "FEATURES=Juridico + Programacao + Visao Local"
)

if "!WEB_BONUS!"=="1" set "FEATURES=!FEATURES! + Web Tempo Real"

cls
echo.
echo   +--------------------------------------------------------------+
echo   ¦          WILLTECHBH IA OFFLINE  -  AUTO-MODULACAO            ¦
echo   ¦--------------------------------------------------------------¦
echo   ¦                                                              ¦
echo   ¦  RAM Detectada.....: !RAM_GB! GB
echo   ¦  Acelerador........: !ACCEL_MSG!
echo   ¦  Conectividade.....: !WEB_MSG!
echo   ¦  Perfil Ativo......: !PROFILE!
echo   ¦  Modelo............: !TARGET_MODEL!
echo   ¦  Funcionalidades...: !FEATURES!
echo   ¦                                                              ¦
echo   ¦  Processamento.....: 100pct LOCAL no seu drive               ¦
echo   ¦  Privacidade.......: Zero dados enviados para nuvem          ¦
echo   ¦                                                              ¦
echo   +--------------------------------------------------------------+
echo.

:: ======================================================
:: 4. VERIFICAR SE MODELO ESTA INSTALADO
:: ======================================================
"%~dp0ollama\ollama.exe" list 2>nul | findstr /i "!TARGET_MODEL!" >nul
if %errorlevel% NEQ 0 (
    echo   [ERRO] Modelo !TARGET_MODEL! nao encontrado neste drive.
    echo   Execute install.bat primeiro para instalar a IA.
    echo.
    pause
    exit /b
)

:: ======================================================
:: 5. INICIAR SERVIDOR OLLAMA
:: ======================================================
netstat -ano 2>nul | findstr :11434 >nul
if %errorlevel% NEQ 0 (
    echo   [+] Iniciando servidor Ollama...
    start "" /B "%~dp0ollama\ollama.exe" serve >nul 2>&1
    timeout /t 5 /nobreak >nul
)

:: ======================================================
:: 6. RAM-SHIFT — modelo na memoria antes de abrir chat
:: ======================================================
echo   [+] RAM-Shift - carregando !TARGET_MODEL! na memoria...
curl -s --max-time 15 -X POST http://localhost:11434/api/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"!TARGET_MODEL!\",\"prompt\":\"init\",\"stream\":false}" >nul 2>&1

:: ======================================================
:: 7. WEB BONUS — silencioso, nunca bloqueia o sistema
:: ======================================================
if "!WEB_BONUS!"=="1" (
    echo   [+] Ativando Web Bonus silenciosamente...
    timeout /t 2 /nobreak >nul

    :: Configura DuckDuckGo como provedor de busca no AnythingLLM
    curl -s --max-time 5 -X POST http://localhost:3001/api/v1/system/update-env ^
      -H "Content-Type: application/json" ^
      -d "{\"AgentSearchProvider\":\"duckduckgo\",\"AgentWebscrapeProvider\":\"native\"}" >nul 2>&1

    :: Se falhar — ignora silenciosamente, sistema continua 100% funcional
)

:: ======================================================
:: 8. LOCALIZAR E ABRIR ANYTHINGLLM
:: ======================================================
echo   [+] Abrindo interface de chat...
set "ANYLLM_EXE="

if exist "%~dp0anythingllm_app\app_path.txt" (
    set /p ANYLLM_EXE=<"%~dp0anythingllm_app\app_path.txt"
)

if not defined ANYLLM_EXE (
    for /r "%~dp0anythingllm_app" %%f in (*.exe) do (
        if not defined ANYLLM_EXE (
            for %%s in ("%%f") do (
                if %%~zs GTR 52428800 set "ANYLLM_EXE=%%f"
            )
        )
    )
)

if defined ANYLLM_EXE (
    start "" "!ANYLLM_EXE!"
) else (
    echo   [ERRO] Interface nao encontrada. Execute install.bat primeiro.
    echo.
    pause
    exit /b
)

:: ======================================================
:: 9. TELA DE STATUS — mantem o servidor ativo
:: ======================================================
:RUNNING_LOOP
cls
echo.
echo   +--------------------------------------------------------------+
echo   ¦       WILLTECHBH IA OFFLINE  -  SISTEMA ATIVO               ¦
echo   ¦--------------------------------------------------------------¦
echo   ¦                                                              ¦
echo   ¦  Perfil...: !PROFILE!
echo   ¦  Modelo...: !TARGET_MODEL!
echo   ¦  GPU......: !ACCEL_MSG!
echo   ¦  Rede.....: !WEB_MSG!
echo   ¦  Recursos.: !FEATURES!
echo   ¦                                                              ¦
echo   ¦  Processamento: 100pct LOCAL no seu drive                    ¦
echo   ¦  Privacidade..: Zero dados enviados para nuvem               ¦
echo   ¦                                                              ¦
echo   ¦  Use a janela de chat livremente.                            ¦
echo   ¦  MANTENHA ESTA JANELA PRETA ABERTA.                          ¦
echo   ¦                                                              ¦
echo   +--------------------------------------------------------------+
echo.
echo   Pressione qualquer tecla para desligar com seguranca...
pause >nul

:: ======================================================
:: 10. DESLIGAMENTO SEGURO
:: ======================================================
cls
echo.
echo   Desligando WillTechBH IA Offline com seguranca...
taskkill /F /IM "ollama.exe"             >nul 2>&1
taskkill /F /IM "AnythingLLM.exe"        >nul 2>&1
taskkill /F /IM "AnythingLLMDesktop.exe" >nul 2>&1
echo   Concluido. Pode ejetar o drive com seguranca.
timeout /t 3 /nobreak >nul
exit