@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
  echo Cannot access the extracted V21 application folder.
  pause
  exit /b 1
)
set "SETUP_LOG=%TEMP%\Cirrus-Workplace-V21-setup.log"
echo Cirrus Workplace V21 setup is running. Please wait...
echo Diagnostic log: "%SETUP_LOG%"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\install_v21.py" > "%SETUP_LOG%" 2>&1
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    python "scripts\install_v21.py" > "%SETUP_LOG%" 2>&1
  ) else (
    py -3 "scripts\install_v21.py" > "%SETUP_LOG%" 2>&1
  )
)
set "SETUP_RESULT=%ERRORLEVEL%"
type "%SETUP_LOG%"
echo.
if "%SETUP_RESULT%"=="0" (
  ".venv\Scripts\python.exe" "scripts\bootstrap_v21.py"
  if errorlevel 1 (
    echo V21 account or storage setup could not finish. Read the message above.
    set "SETUP_RESULT=1"
  ) else (
    echo Ready. Run start.bat while Version 20 is stopped.
  )
) else (
  echo Dependency setup failed. Read the diagnostic log shown above.
  echo Python 3.11 or newer must be installed on this server.
)
popd
pause
exit /b %SETUP_RESULT%
