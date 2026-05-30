@echo off
title PC MIDI Agent Watch
color 0A

cd /d %~dp0

if not exist logs mkdir logs

echo.
echo  ================================================
echo   PC MIDI - Supervisor permanente de agentes
echo  ================================================
echo.
echo  Iniciando swarm.py watch en modo permanente...
echo  Logs:
echo    logs\watch.out.log
echo    logs\watch.err.log
echo.

start "PC MIDI Watch" /min cmd /c "python swarm.py watch >> logs\watch.out.log 2>> logs\watch.err.log"

echo  Listo. El supervisor queda en segundo plano.
echo  Ver estado en http://localhost:5000/dashboard
echo.
pause
