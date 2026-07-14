# Skopiruj Tinder chrome-profile z PC na HAOS (samostatny add-on haos_tinder).
#
# 1) Na Windows (po uspesnom capture_tinder_session.ps1):
#      .\push_tinder_profile_to_haos.ps1
#      .\push_tinder_profile_to_haos.ps1 -HaosHost 192.168.1.109
#      .\push_tinder_profile_to_haos.ps1 -HaosHost 192.168.1.109 -ShareName share
#
# 2) Na HAOS SSH:
#      bash /share/tinder-chrome-profile/deploy_on_haos.sh
#    (alebo prikazy vypisane na konci tohto skriptu)

param(
    [string]$HaosHost = "192.168.1.109",
    [string]$ShareName = "share",
    [string]$StagingFolder = "tinder-chrome-profile"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcProfile = Join-Path $Root "tinder_bot\chrome-profile"
$DestOnShare = "\\$HaosHost\$ShareName\$StagingFolder"

if (-not (Test-Path (Join-Path $SrcProfile "Default\Cookies")) -and
    -not (Test-Path (Join-Path $SrcProfile "Default"))) {
    throw "Profil nenajdeny: $SrcProfile\Default. Najprv spusti .\capture_tinder_session.ps1"
}

Write-Host "[1/4] Uvolnujem profile lock..."
Get-Process chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Remove-Item "$SrcProfile\SingletonLock","$SrcProfile\SingletonCookie","$SrcProfile\SingletonSocket","$SrcProfile\DevToolsActivePort" -Force -ErrorAction SilentlyContinue

$shareRoot = "\\$HaosHost\$ShareName"
Write-Host "[2/4] Kontrolujem Samba $shareRoot ..."
if (-not (Test-Path $shareRoot)) {
    Write-Host "Nedostupne. Skusam bezne share mena: share, addons, config..."
    $found = $null
    foreach ($name in @("share", "addons", "config", "media")) {
        if (Test-Path "\\$HaosHost\$name") {
            $ShareName = $name
            $shareRoot = "\\$HaosHost\$ShareName"
            $DestOnShare = "$shareRoot\$StagingFolder"
            $found = $name
            break
        }
    }
    if (-not $found) {
        throw "Ziadny Samba share na \\$HaosHost nie je dostupny. Zapni Samba add-on / uprav -HaosHost."
    }
    Write-Host "  pouzivam share: $ShareName"
}

Write-Host "[3/4] Kopirujem slim profil -> $DestOnShare"
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

# HAOS helper script next to the profile on the share
$haosHelper = @"
#!/usr/bin/env bash
set -e
TD=/mnt/data/supervisor/addons/data/local_haos_tinder
SRC=/share/$StagingFolder
# ak Samba mapuje inak:
[ -d "`$SRC/Default" ] || SRC=/mnt/data/$StagingFolder
[ -d "`$SRC/Default" ] || SRC=/share/$StagingFolder

if [ ! -d "`$SRC/Default" ]; then
  echo "Nenasiel som profil. Hladam..."
  find /share /mnt/data -maxdepth 3 -type d -name 'tinder-chrome-profile' 2>/dev/null
  exit 1
fi

mkdir -p "`$TD/chrome-profile"
rm -rf "`$TD/chrome-profile"/* "`$TD/chrome-profile"/.[!.]* 2>/dev/null || true
cp -a "`$SRC/." "`$TD/chrome-profile/"
# zbav sa helper skriptu v profile ak sa skopiroval
rm -f "`$TD/chrome-profile/deploy_on_haos.sh"
echo "Hotovo. Cookies?"
ls "`$TD/chrome-profile/Default" | head
echo "Teraz v UI: Restart HAOS Tinder Bot"
"@
Set-Content -Path (Join-Path $DestOnShare "deploy_on_haos.sh") -Value $haosHelper -Encoding Ascii

$cookies = Join-Path $DestOnShare "Default\Cookies"
$ok = Test-Path $cookies
Write-Host "[4/4] Samba OK. Cookies present: $ok"
Write-Host ""
Write-Host "====== NA HAOS SSH SPUSTI ======"
Write-Host "bash /share/$StagingFolder/deploy_on_haos.sh"
Write-Host "================================"
Write-Host "Potom v UI: Stop + Start HAOS Tinder Bot"
Write-Host "V logu hladaj: Logged in, starting poll loop"
