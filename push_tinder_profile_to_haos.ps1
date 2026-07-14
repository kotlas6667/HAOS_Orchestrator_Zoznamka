# Po capture_tinder_session.ps1 skopiruj profil na HAOS Tinder add-on.
#
# Pouzitie:
#   .\push_tinder_profile_to_haos.ps1
#   .\push_tinder_profile_to_haos.ps1 -HaosHost 192.168.1.109
#   .\push_tinder_profile_to_haos.ps1 -HaosHost 100.82.143.35 -ShareName share

param(
    [string]$HaosHost = "192.168.1.109",
    [string]$ShareName = "share",
    [string]$StagingFolder = "tinder-chrome-profile"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcProfile = Join-Path $Root "tinder_bot\chrome-profile"
$DestOnShare = "\\$HaosHost\$ShareName\$StagingFolder"

if (-not (Test-Path (Join-Path $SrcProfile "Default"))) {
    throw "Profil nenajdeny / prazdny: $SrcProfile\Default. Najprv spusti .\capture_tinder_session.ps1"
}

Write-Host "[1/3] Zastav chromedriver (Chrome na PC mozes nechat)..."
Get-Process chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Remove-Item "$SrcProfile\SingletonLock","$SrcProfile\SingletonCookie","$SrcProfile\SingletonSocket","$SrcProfile\DevToolsActivePort" -Force -ErrorAction SilentlyContinue

Write-Host "[2/3] Kopirujem slim profil na Samba: $DestOnShare"
if (-not (Test-Path "\\$HaosHost\$ShareName")) {
    throw "Samba \\$HaosHost\$ShareName nie je dostupna. Uprav -HaosHost / -ShareName."
}
New-Item -ItemType Directory -Path $DestOnShare -Force | Out-Null

$TempSlim = Join-Path $env:TEMP "tinder-chrome-profile-slim"
if (Test-Path $TempSlim) { Remove-Item $TempSlim -Recurse -Force }
New-Item -ItemType Directory -Path $TempSlim -Force | Out-Null

$null = & robocopy $SrcProfile $TempSlim /E `
    /XD "Cache" "Code Cache" "GPUCache" "Service Worker" "Crashpad" `
    "BrowserMetrics" "component_crx_cache" "optimization_guide_model_store" `
    "hyphen-data" "GrShaderCache" "ShaderCache" "blob_storage" `
    /XF "SingletonLock" "SingletonCookie" "SingletonSocket" "DevToolsActivePort" "lockfile" `
    /R:2 /W:2 /NFL /NDL /NJH /NJS

$null = & robocopy $TempSlim $DestOnShare /MIR /R:2 /W:3 /NFL /NDL
if ($LASTEXITCODE -ge 8) { throw "robocopy zlyhal: $LASTEXITCODE" }

Write-Host "[3/3] Hotovo na Samba. Na HAOS SSH teraz spusti:"
Write-Host @"

TD=/mnt/data/supervisor/addons/data/local_haos_tinder
mkdir -p "`$TD/chrome-profile"
rm -rf "`$TD/chrome-profile"/*
cp -a /share/$StagingFolder/. "`$TD/chrome-profile/"
ls "`$TD/chrome-profile/Default" | head

# potom v UI: Restart HAOS Tinder Bot
"@
