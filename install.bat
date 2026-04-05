@echo off
title WillTechBH IA Offline - Instalador
color 0B

echo.
echo  ====================================================
echo      WILLTECHBH IA OFFLINE - INICIALIZACAO
echo  ====================================================
echo.
echo    O sistema vai analisar o hardware desta maquina
echo    e instalar a IA ideal automaticamente.
echo    Nada sera instalado no computador hospedeiro.
echo.
echo    Direitos Autorais (c) Willtechbh
echo.
echo    [!] Certifique-se de estar conectado a internet.
echo.
pause

powershell -ExecutionPolicy Bypass -File "%~dp0install-core.ps1"

echo.
echo  ====================================================
echo      INSTALACAO CONCLUIDA COM SUCESSO!
echo  ====================================================
echo.
echo    Feche esta janela e execute: start-windows.bat
echo.
pause
exit