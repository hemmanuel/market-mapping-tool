@echo off
setlocal EnableExtensions
cd /d "%SystemRoot%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_bespoke_servers.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %EXIT_CODE%
