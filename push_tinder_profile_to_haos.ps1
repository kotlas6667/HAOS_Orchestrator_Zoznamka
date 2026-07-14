# Skopiruj Tinder chrome-profile z PC na HAOS cez Samba addons share.
#
# Tvoj share:
#   \\192.168.1.109\addons\...
#
# Pouzitie:
#   .\push_tinder_profile_to_haos.ps1
#   .\push_tinder_profile_to_haos.ps1 -HaosHost 192.168.1.109
#
# Potom na HAOS SSH:
#   bash /addons/tinder-chrome-profile/deploy_on_haos.sh

param(
    [string]$HaosHost = "192.168.1.109",
    [string]$ShareName = "addons",
    [string]$StagingFolder = "tinder-chrome-profile"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcProfile = Join-Path $Root "tinder_bot\chrome-profile"
$DestOnShare = "\\$HaosHost\$ShareName\$StagingFolder"

if (-not (Test-Path (Join-Path $SrcProfile "Default"))) {
    throw "Profil nenajdeny: $SrcProfile\Default. Najprv spusti .\capture_tinder_session.ps1"
}

Write-Host "[1/3] Uvolnujem profile lock..."
Get-Process chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Remove-Item "$SrcProfile\SingletonLock","$SrcProfile\SingletonCookie","$SrcProfile\SingletonSocket","$SrcProfile\DevToolsActivePort" -Force -ErrorAction SilentlyContinue

$shareRoot = "\\$HaosHost\$ShareName"
Write-Host "[2/3] Samba: $shareRoot"
if (-not (Test-Path $shareRoot)) {
    throw "Samba $shareRoot nie je dostupna. Over v prieskumnikovi: \\$HaosHost\$ShareName"
}

Write-Host " ciel: $DestOnShare"
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

$null = & robocopy $TempSlim $DestOnShare /MIR /R:2 /W:3 /NFL /NDL `
    /XF "deploy_on_haos.sh"
if ($LASTEXITCODE -ge 8) { throw "robocopy zlyhal: $LASTEXITCODE" }

# Samba "addons" = /addons na HAOS (zdroj add-onov), NIE /data.
# Helper skopiruje profil do perzistentneho data dir Tinder add-onu.
$haosHelper = @'
#!/usr/bin/env bash
set -e
TD=/mnt/data/supervisor/addons/data/local_haos_tinder
SRC=/addons/tinder-chrome-profile
if [ ! -d "$SRC/Default" ]; then
  echo "Nenasiel som $SRC/Default"
  ls -la /addons/ | head
  exit 1
fi
mkdir -p "$TD/chrome-profile"
rm -rf "$TD/chrome-profile"/* 2>/dev/null || true
cp -a "$SRC/." "$TD/chrome-profile/"
rm -f "$TD/chrome-profile/deploy_on_haos.sh"
echo "Hotovo -> $TD/chrome-profile"
ls "$TD/chrome-profile/Default" | head
echo "UI: Restart HAOS Tinder Bot"
'@
Set-Content -Path (Join-Path $DestOnShare "deploy_on_haos.sh") -Value $haosHelper -Encoding Ascii

$ok = Test-Path (Join-Path $DestOnShare "Default")
Write-Host "[3/3] Hotovo. Default present: $ok"
Write-Host ""
Write-Host "====== NA HAOS SSH ======"
Write-Host "bash /addons/tinder-chrome-profile/deploy_on_haos.sh"
Write-Host "========================="
Write-Host "Potom UI: Restart HAOS Tinder Bot"
