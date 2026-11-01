@echo off
title DevLabs - HarnessAgents v2.0 Launcher
cd /d "C:\Users\Legion\.gemini\antigravity\scratch\harness-agents"

echo ========================================================
echo   Starting DevLabs - HarnessAgents Virtual AI Office...
echo ========================================================

REM Check if port 8420 is already listening; if not, start server in a minimized window
netstat -ano | findstr ":8420 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    start "HarnessAgents Server" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Legion\.gemini\antigravity\scratch\harness-agents\Start-HarnessOffice.ps1" -Port 8420
    timeout /t 3 /nobreak >nul
)

REM Open the Virtual AI Office in the default browser
start "" "http://127.0.0.1:8420"
exit
