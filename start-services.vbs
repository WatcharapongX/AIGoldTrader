Dim objShell
Set objShell = CreateObject("WScript.Shell")

' Restore the PM2 process list in the background at user logon.
objShell.Run "cmd /c cd /d ""C:\AI Gold Trader"" && call ""%APPDATA%\npm\pm2.cmd"" resurrect >> ""C:\AI Gold Trader\logs\startup.log"" 2>&1", 0, False
