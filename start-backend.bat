@echo off
setlocal
cd /d "C:\AI Gold Trader"
call "%APPDATA%\npm\pm2.cmd" startOrReload ecosystem.config.cjs --only aigold-backend
if errorlevel 1 exit /b 1
call "%APPDATA%\npm\pm2.cmd" save
