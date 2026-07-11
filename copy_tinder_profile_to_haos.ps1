# Zmensi Windows Chrome profil (bez cache) a skopiruj ho na HAOS Samba add-on.
# Pri dalsom build/restarte add-onu run.sh profil nasadi do /data (perzistentne).
#
# Pouzitie:
#   .\copy_tinder_profile_to_haos.ps1
#   .\copy_tinder_profile_to_haos.ps1 -HaosHost 192.168.1.111
#
# Pred kopirovanim zatvor Tinder Chrome okno / tinder bota na PC.

param(
    [string]$HaosHost = "192.168.1.111",
    [string]$AddonSlug = "HAOS_Orchestrator_Zoznamka"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcProfile = Join-Path $Root "tinder_bot\chrome-profile"
$TempSlim = Join-Path $env:TEMP "tinder-chrome-profile-slim"
$DestOnShare = "\\$HaosHost\addons\$AddonSlug\data\orchestrator\config\tinder\chrome-profile"

if (-not (Test-Path $SrcProfile)) {
    throw "Chrome profil neexistuje: $SrcProfile. Najprv sa prihlas do Tinderu na PC."
}

Write-Host "[1/4] Zatvaram lokalny Chrome / tinder bota..."
Get-Process chrome, chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'tinder_bot\.main' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Write-Host "[2/4] Pripravujem slim profil (bez cache)..."
if (Test-Path $TempSlim) {
    Remove-Item $TempSlim -Recurse -Force
}
New-Item -ItemType Directory -Path $TempSlim -Force | Out-Null

$null = & robocopy $SrcProfile $TempSlim /E `
    /XD "Cache" "Code Cache" "GPUCache" "Service Worker" "Crashpad" `
    "BrowserMetrics" "component_crx_cache" "optimization_guide_model_store" `
    "hyphen-data" "GrShaderCache" "ShaderCache" "blob_storage" `
    /XF "SingletonLock" "SingletonCookie" "SingletonSocket" "DevToolsActivePort" "lockfile" `
    /R:2 /W:2 /NFL /NDL /NJH /NJS

if (-not (Test-Path (Join-Path $TempSlim "Default"))) {
    throw "Slim profil nema priecinok Default - skontroluj zdrojovy profil."
}

$slimMb = [math]::Round((Get-ChildItem $TempSlim -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "  slim profil: $slimMb MB"

Write-Host "[3/4] Kontrolujem Samba: $DestOnShare"
if (-not (Test-Path "\\$HaosHost\addons")) {
    throw "Samba share \\$HaosHost\addons nie je dostupny."
}
New-Item -ItemType Directory -Path $DestOnShare -Force | Out-Null

Write-Host "[4/4] Kopirujem na HAOS add-on..."
$null = & robocopy $TempSlim $DestOnShare /E /R:2 /W:3 /NFL /NDL
$rc = $LASTEXITCODE
if ($rc -ge 8) {
    throw "robocopy zlyhal s exit code $rc"
}

Write-Host ""
Write-Host "Hotovo: $DestOnShare"
Write-Host "Dalsi krok: rebuild / restart add-onu HAOS Orchestrator"
Write-Host "V logu hladaj: Seeding Tinder chrome profile"
Write-Host "Potom: [tinder_bot] Logged in, starting poll loop."
