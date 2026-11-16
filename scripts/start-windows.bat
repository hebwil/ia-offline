@echo off
setlocal EnableExtensions
rem Launcher Windows - Nexus Portable 3.0
rem Caminhos relativos ao proprio script; nenhuma dependencia de diretorio atual.
cd /d "%~dp0.."
set "NEXUS3_ROOT=%CD%"

if not exist "%NEXUS3_ROOT%\nexus3.py" (
  echo [NEXUS 3] nexus3.py nao encontrado em %NEXUS3_ROOT% ^(instalacao incompleta^).
  exit /b 2
)

rem Testa se o interpretador e Python 3.10+ (requisito do nucleo).
:try_python
where python >nul 2>nul
if %errorlevel%==0 (
  python -c "import sys; sys.exit(0 if sys.version_info ^>= (3,10) else 1)" >nul 2>nul
  if %errorlevel%==0 (
    python nexus3.py start %*
    goto :end
  )
)

:try_py
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -c "import sys; sys.exit(0 if sys.version_info ^>= (3,10) else 1)" >nul 2>nul
  if %errorlevel%==0 (
    py -3 nexus3.py start %*
    goto :end
  )
)

:try_portable
if exist "%NEXUS3_ROOT%\runtime\python\python.exe" (
  "%NEXUS3_ROOT%\runtime\python\python.exe" -c "import sys; sys.exit(0 if sys.version_info ^>= (3,10) else 1)" >nul 2>nul
  if %errorlevel%==0 (
    "%NEXUS3_ROOT%\runtime\python\python.exe" nexus3.py start %*
    goto :end
  )
)

echo [NEXUS 3] Python 3.10+ nao encontrado. Instale o Python ou coloque um runtime portatil em runtime\python.
echo [NEXUS 3] Download: https://www.python.org/downloads/
exit /b 1

:end
endlocal
