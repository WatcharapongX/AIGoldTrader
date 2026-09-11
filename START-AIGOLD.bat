@echo off
setlocal
cd /d "C:\AI Gold Trader"
call "%APPDATA%\npm\pm2.cmd" startOrReload ecosystem.config.cjs
if errorlevel 1 exit /b 1
call "%APPDATA%\npm\pm2.cmd" save
echo AI Gold Trader is managed by PM2.
echo Frontend: http://localhost:3001
echo Backend:  http://localhost:8000
