$ErrorActionPreference = "Stop"
$projectRoot = "C:\AI Gold Trader"
$launcher = Join-Path $projectRoot "start-services.vbs"
$ecosystem = Join-Path $projectRoot "ecosystem.config.cjs"
$pm2 = (Get-Command "pm2.cmd" -ErrorAction Stop).Source
$startupFolder = [Environment]::GetFolderPath("Startup")
$legacyShortcut = Join-Path $startupFolder "AIGoldTrader.lnk"
$disabledShortcut = Join-Path $startupFolder "AIGoldTrader.lnk.disabled"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Missing startup launcher: $launcher"
}
if (-not (Test-Path -LiteralPath $ecosystem)) {
    throw "Missing PM2 ecosystem file: $ecosystem"
}

# Disable the legacy launcher that starts a second visible Node/Python pair.
if (Test-Path -LiteralPath $legacyShortcut) {
    if (Test-Path -LiteralPath $disabledShortcut) {
        Remove-Item -LiteralPath $disabledShortcut -Force
    }
    Move-Item -LiteralPath $legacyShortcut -Destination $disabledShortcut
}

Push-Location $projectRoot
try {
    # Stop managed children first, then clear only project-owned listeners left by
    # the legacy launcher. This prevents an EADDRINUSE restart loop.
    & $pm2 stop aigold-frontend 2>$null
    & $pm2 stop aigold-backend 2>$null
    foreach ($port in @(3001, 8000)) {
        foreach ($listener in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
            $candidate = $process
            $projectOwned = $false
            for ($depth = 0; $candidate -and $depth -lt 6; $depth++) {
                if ($candidate.CommandLine -like "*$projectRoot*") {
                    $projectOwned = $true
                    break
                }
                $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$($candidate.ParentProcessId)" -ErrorAction SilentlyContinue
            }
            if (-not $projectOwned) {
                throw "Port $port is owned by an unrelated process; refusing to terminate it"
            }
            Stop-Process -Id $process.ProcessId -Force
        }
    }
    Start-Sleep -Seconds 2
    & $pm2 delete aigold-frontend 2>$null
    & $pm2 delete aigold-backend 2>$null
    & $pm2 start $ecosystem
    if ($LASTEXITCODE -ne 0) { throw "PM2 failed to load services" }
    & $pm2 save
    if ($LASTEXITCODE -ne 0) { throw "PM2 failed to save the process list" }
}
finally {
    Pop-Location
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runValue = 'wscript.exe "' + $launcher + '"'
New-Item -Path $runKey -Force | Out-Null
New-ItemProperty -Path $runKey -Name "AIGoldTrader" -Value $runValue -PropertyType String -Force | Out-Null

$installed = Get-ItemPropertyValue -Path $runKey -Name "AIGoldTrader"
if ($installed -ne $runValue) {
    throw "Auto-start registry verification failed"
}

Write-Host "SUCCESS: PM2 services are saved and AI Gold Trader will start at user logon"
