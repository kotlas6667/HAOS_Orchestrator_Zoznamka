# Zachyti novu Tinder session do projektoveho chrome-profile (NE z desktop Chrome).
#
# Preco nie desktop Chrome:
#   Selenium nesmie sahat na %LOCALAPPDATA%\Google\Chrome\User Data — zamkne/znici
#   tvoj normalny Chrome. Bot ma vlastny profil v tinder_bot\chrome-profile.
#
# Pouzitie (na Windows PC, v koreni projektu):
#   .\capture_tinder_session.ps1
#
# Co sa stane:
#   1) zastavi stary bot / chromedriver
#   2) volitelne zmaze stary profil (-Reset)
#   3) otvori viditelne Chrome okno
#   4) caka az 10 min kym sa rucne prihlasis
#   5) session sa ulozi do tinder_bot\chrome-profile
# Potom skopiruj ten priecinok na HAOS (local_haos_tinder/chrome-profile).

param(
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ProfileDir = Join-Path $Root "tinder_bot\chrome-profile"

Write-Host "[1/4] Ukoncujem stare tinder/chrome procesy..."
Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'tinder_bot\.main' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
# Nezabijaj cely chrome.exe — user moze mat otvoreny bezny Chrome.
# Zabijame len lock subory v nasom profile.
Remove-Item "$ProfileDir\SingletonLock" -Force -ErrorAction SilentlyContinue
Remove-Item "$ProfileDir\SingletonCookie" -Force -ErrorAction SilentlyContinue
Remove-Item "$ProfileDir\SingletonSocket" -Force -ErrorAction SilentlyContinue
Remove-Item "$ProfileDir\DevToolsActivePort" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

if ($Reset) {
    Write-Host "[2/4] -Reset: mazem stary profil $ProfileDir ..."
    if (Test-Path $ProfileDir) {
        Remove-Item $ProfileDir -Recurse -Force
    }
} else {
    Write-Host "[2/4] Ponechavam existujuci profil (ak chces cisty start: .\capture_tinder_session.ps1 -Reset)"
}

New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null

Write-Host "[3/4] Nastavujem env pre rucne prihlasenie..."
$env:TINDER_HEADLESS = "false"
$env:TINDER_USER_DATA_DIR = $ProfileDir
$env:TINDER_BOT_HOST = "127.0.0.1"
$env:TINDER_BOT_PORT = "8601"
$env:ORCHESTRATOR_URL = "http://127.0.0.1:8000"
$env:TINDER_POLL_ENABLED = "false"
$env:TINDER_LOGIN_WAIT_SEC = "600"
# Desktop Chrome (nie Chromium z Dockeru)
if (-not $env:TINDER_BROWSER_BINARY) {
    $chrome = "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"
    if (Test-Path $chrome) { $env:TINDER_BROWSER_BINARY = $chrome }
}

Write-Host ""
Write-Host "============================================================"
Write-Host " Otvara sa Chrome. Prihlas sa do Tinderu (OTP / Google / FB)."
Write-Host " Cakam az 10 minut. Po uspechu uvidis:"
Write-Host "   [tinder_bot] Login detected, session saved..."
Write-Host " Potom Ctrl+C."
Write-Host " Profil: $ProfileDir"
Write-Host "============================================================"
Write-Host ""

Write-Host "[4/4] Spustam python -m tinder_bot.main ..."
python -m tinder_bot.main
