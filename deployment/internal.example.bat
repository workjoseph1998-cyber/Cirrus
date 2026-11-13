@echo off
rem Example only. Replace hostname/data/code paths with your actual internal settings.
rem IIS receives HTTPS; Waitress remains on localhost. Never add a public NAT/port forward.
set "CIRRUS_TIMEZONE=Asia/Beirut"
set "CIRRUS_BIND=127.0.0.1"
set "CIRRUS_PORT=8000"
set "CIRRUS_INTERNAL_ACCESS=1"
set "CIRRUS_HTTPS=1"
set "CIRRUS_TRUSTED_PROXY=127.0.0.1"
set "CIRRUS_ALLOWED_HOSTS=workplace.example.internal"
rem Keep the existing data directory. This is an example, not a migration destination.
set "CIRRUS_DATA_DIR=C:\CirrusWorkplaceData"
call "C:\Apps\CirrusWorkplace\start.bat"
