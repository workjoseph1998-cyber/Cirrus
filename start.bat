@echo off
rem V21 always uses its isolated launcher; never V20 shared deployment defaults.
call "%~dp0start-v21.bat"
exit /b %ERRORLEVEL%
