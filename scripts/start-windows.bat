@echo off
setlocal
cd /d "%~dp0.."
set "NEXUS3_ROOT=%CD%"

where python >nul 2>nul
if %errorlevel%==0 (
  python nexus3.py start %*
  goto :end
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 nexus3.py start %*
  goto :end
)
if exist "%NEXUS3_ROOT%\runtime\python\python.exe" (
  "%NEXUS3_ROOT%\runtime\python\python.exe" nexus3.py start %*
  goto :end
)
echo [NEXUS 3] Python 3.10+ not found. Install Python or place a portable Python in runtime\python.
pause

:end
endlocal
