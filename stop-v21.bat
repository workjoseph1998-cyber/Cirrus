@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\control-v21.ps1" -Action stop
exit /b %ERRORLEVEL%
