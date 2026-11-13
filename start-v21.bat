@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat in the separate V21 application folder first.
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\control-v21.ps1" -Action start
set "START_RESULT=%ERRORLEVEL%"
if not "%START_RESULT%"=="0" pause
exit /b %START_RESULT%
