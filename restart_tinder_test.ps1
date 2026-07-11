# Vždy najprv zabije staré procesy, potom spustí orchestrátor + Tinder bota.
# Použitie:
#   .\restart_tinder_test.ps1           # len reštart služieb (~10 s čakanie)
#   .\restart_tinder_test.ps1 -Push Barbora
#   .\restart_tinder_test.ps1 -Push latest

param(
    [string]$Push = ""
)

$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Stop-PortListeners {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        $pids = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pids) {
            if ($procId -gt 0) {
                taskkill /F /PID $procId /T 2>$null | Out-Null
                Write-Host "  killed PID $procId (port $port)"
            }
        }
    }
}

function Stop-ProjectPython {
    Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'uvicorn app\.main|tinder_bot\.main' } |
        ForEach-Object {
            taskkill /F /PID $_.ProcessId /T 2>$null | Out-Null
            Write-Host "  killed python PID $($_.ProcessId)"
        }
}

Write-Host "[1/4] Ukoncujem Chrome, chromedriver, project python a porty 8000/8601..."
Stop-ProjectPython
taskkill /F /IM chrome.exe /T 2>$null | Out-Null
taskkill /F /IM chromedriver.exe /T 2>$null | Out-Null
Stop-PortListeners -Ports @(8000, 8601)
Remove-Item "$Root\.discord_bot.lock" -Force -ErrorAction SilentlyContinue
Remove-Item "$Root\tinder_bot\chrome-profile\DevToolsActivePort" -Force -ErrorAction SilentlyContinue
Remove-Item "$Root\tinder_bot\chrome-profile\SingletonLock" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$stillBusy = Get-NetTCPConnection -LocalPort 8000,8601 -State Listen -ErrorAction SilentlyContinue
if ($stillBusy) {
    Write-Host "  VAROVANIE: porty este obsadene, druhy kill..."
    Stop-PortListeners -Ports @(8000, 8601)
    Start-Sleep -Seconds 2
}

Write-Host "[2/4] Spustam orchestrator (8000)..."
$orchJob = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $Root -PassThru -WindowStyle Minimized

Write-Host "[3/4] Spustam Tinder bota (8601)..."
$env:TINDER_HEADLESS = "false"
$env:TINDER_POLL_ENABLED = "false"
$env:TINDER_GEOLOCATION_ENABLED = "true"
$env:TINDER_PAGE_SETTLE_SEC = "4"
$env:TINDER_SPRAVY_SETTLE_SEC = "10"
$env:TINDER_WAIT_TIMEOUT_SEC = "10"
$env:TINDER_USER_DATA_DIR = "$Root\tinder_bot\chrome-profile"
$botJob = Start-Process -FilePath "python" `
    -ArgumentList "-m", "tinder_bot.main" `
    -WorkingDirectory $Root -PassThru -WindowStyle Normal

Write-Host "[4/4] Cakam max 10 s na orchestrator, potom dalsich 10 s na bota..."
$orchOk = $false
$botOk = $false
$orchDeadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $orchDeadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $orchOk = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if ($orchOk) {
    $botDeadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $botDeadline) {
        try {
            $h = Invoke-RestMethod -Uri "http://127.0.0.1:8601/health" -TimeoutSec 2
            if ($h.logged_in -and $h.session_alive) { $botOk = $true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
}

Write-Host "  orchestrator: $(if ($orchOk) { 'OK' } else { 'FAIL' }) (PID $($orchJob.Id))"
Write-Host "  tinder bot:   $(if ($botOk) { 'OK' } else { 'FAIL - Chrome este nacitava' }) (PID $($botJob.Id))"

if (-not $orchOk) { exit 1 }

if ($Push) {
    if (-not $botOk) {
        Write-Host "Bot este nie je ready - push preskakujem. Skus: python push_tinder_discord.py $Push"
        exit 1
    }
    Write-Host "Push do Discordu: $Push"
    python push_tinder_discord.py $Push
}
