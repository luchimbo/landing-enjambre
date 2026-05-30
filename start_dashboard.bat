@echo off
title Panel de Agentes PC MIDI
color 0A

echo.
echo  ================================================
echo   PC MIDI - Panel de Agentes
echo  ================================================
echo.

REM Verificar que Python esté disponible
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no encontrado en el PATH.
    pause
    exit /b 1
)

REM Verificar que cloudflared esté disponible
where cloudflared >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] cloudflared no encontrado. Instalar con:
    echo    winget install Cloudflare.cloudflared
    pause
    exit /b 1
)

echo  [1/2] Iniciando servidor Flask en puerto 5000...
start "API Server - PC MIDI" cmd /k "cd /d %~dp0 && python api_server.py"

echo  Esperando que el servidor arranque...
timeout /t 3 /nobreak >nul

echo  [2/2] Iniciando tunel cloudflared...
echo.
echo  La URL publica aparecera en unos segundos:
echo  Buscá la linea que dice "trycloudflare.com"
echo.
echo  ------------------------------------------------
echo   Para detener: Ctrl+C en esta ventana
echo  ------------------------------------------------
echo.

cloudflared tunnel --url http://localhost:5000 2>&1
