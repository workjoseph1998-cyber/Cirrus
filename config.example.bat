@echo off
rem Example only: point to V21's external profile; never use V20 deployment.json.
set "CIRRUS_V21_PROFILE=C:\CirrusConfigV21\profile.json"
call "%~dp0start-v21.bat"
