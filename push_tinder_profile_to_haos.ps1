# Skopiruj Tinder chrome-profile z PC na HAOS (samostatny add-on haos_tinder).
#
# Samba (ak bezi):
#   .\push_tinder_profile_to_haos.ps1 -HaosHost 192.168.1.109
#
# SCP cez SSH (odporucane, ked Samba nejde):
#   .\push_tinder_profile_to_haos.ps1 -Method scp -HaosHost 192.168.1.109 -SshUser root
#   .\push_tinder_profile_to_haos.ps1 -Method scp -HaosHost 100.82.143.35 -SshUser root
#
# Potom na HAOS SSH:
#   bash /root/tinder-chrome-profile/deploy_on_haos.sh
#   # alebo: bash /share/tinder-chrome-profile/deploy_on_haos.sh

param(
    [ValidateSet("auto", "samba", "scp")]
    [string]$Method = "auto",
    [string]$HaosHost = "192.168.1.109",
    [string]$ShareName = "share",
    [string]$StagingFolder = "tinder-chrome-profile",
    [string]$SshUser = "root",
    [string]$SshPort = "22",
    [string]$ScpRemoteDir = "/root/tinder-chrome-profile"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcProfile = Join-Path $Root "tinder_bot\chrome-profile"

if (-not (Test-Path (Join-Path $SrcProfile "Default"))) {
    throw "Profil nenajdeny: $SrcProfile\Default. Najprv spusti .\capture_tinder_session.ps1"
}

function New-SlimProfile {
    param([string]$Dest)
    if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    $null = & robocopy $SrcProfile $Dest /E `
        /XD "Cache" "Code Cache" "GPUCache" "Service Worker" "Crashpad" `
        "BrowserMetrics" "component_crx_cache" "optimization_guide_model_store" `
        "hyphen-data" "GrShaderCache" "ShaderCache" "blob_storage" `
        /XF "SingletonLock" "SingletonCookie" "SingletonSocket" "DevToolsActivePort" "lockfile" `
        /R:2 /W:2 /NFL /NDL /NJH /NJS
    if (-not (Test-Path (Join-Path $Dest "Default"))) {
        throw "Slim profil sa nevytvoril."
    }
}

function Write-HaosHelper {
    param([string]$LocalPath, [string]$SrcHint)
    $haosHelper = @"
#!/usr/bin/env bash
set -e
TD=/mnt/data/supervisor/addons/data/local_haos_tinder
for SRC in "$SrcHint" /root/$StagingFolder /share/$StagingFolder /mnt/data/$StagingFolder; do
  if [ -d "`$SRC/Default" ]; then
    mkdir -p "`$TD/chrome-profile"
    rm -rf "`$TD/chrome-profile"/* 2>/dev/null || true
    cp -a "`$SRC/." "`$TD/chrome-profile/"
    rm -f "`$TD/chrome-profile/deploy_on_haos.sh"
    echo "Hotovo -> `$TD/chrome-profile"
    ls "`$TD/chrome-profile/Default" | head
    echo "UI: Restart HAOS Tinder Bot"
    exit 0
  fi
done
echo "Profil nenajdeny. Hladam..."
find /root /share /mnt/data -maxdepth 3 -type d -name '$StagingFolder' 2>/dev/null
exit 1
"@
    Set-Content -Path $LocalPath -Value $haosHelper -Encoding Ascii
}

Write-Host "[1/4] Uvolnujem profile lock..."
Get-Process chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Remove-Item "$SrcProfile\SingletonLock","$SrcProfile\SingletonCookie","$SrcProfile\SingletonSocket","$SrcProfile\DevToolsActivePort" -Force -ErrorAction SilentlyContinue

$TempSlim = Join-Path $env:TEMP "tinder-chrome-profile-slim"
Write-Host "[2/4] Pripravujem slim profil..."
New-SlimProfile -Dest $TempSlim
Write-HaosHelper -LocalPath (Join-Path $TempSlim "deploy_on_haos.sh") -SrcHint $ScpRemoteDir

function Try-Samba {
    $shareRoot = "\\$HaosHost\$ShareName"
    if (-not (Test-Path $shareRoot)) {
        foreach ($name in @("share", "addons", "config", "media")) {
            if (Test-Path "\\$HaosHost\$name") {
                $script:ShareName = $name
                $shareRoot = "\\$HaosHost\$ShareName"
                break
            }
        }
    }
    if (-not (Test-Path $shareRoot)) { return $false }

    $DestOnShare = "$shareRoot\$StagingFolder"
    Write-Host "[3/4] Samba OK -> $DestOnShare"
    New-Item -ItemType Directory -Path $DestOnShare -Force | Out-Null
    $null = & robocopy $TempSlim $DestOnShare /MIR /R:2 /W:3 /NFL /NDL
    if ($LASTEXITCODE -ge 8) { throw "robocopy zlyhal: $LASTEXITCODE" }

    Write-Host "[4/4] Hotovo cez Samba."
    Write-Host "NA HAOS SSH:  bash /share/$StagingFolder/deploy_on_haos.sh"
    return $true
}

function Push-Scp {
    Write-Host "[3/4] SCP $SshUser@${HaosHost}:$ScpRemoteDir (port $SshPort)..."
    $scp = Get-Command scp -ErrorAction SilentlyContinue
    if (-not $scp) {
        throw "scp nie je v PATH. Nainstaluj OpenSSH Client (Optional Features) alebo pouzi WSL."
    }
    # vytvor remote dir
    & ssh -p $SshPort "$SshUser@$HaosHost" "rm -rf '$ScpRemoteDir' && mkdir -p '$ScpRemoteDir'"
    if ($LASTEXITCODE -ne 0) { throw "ssh mkdir zlyhal (exit $LASTEXITCODE). Skontroluj SSH user/port/heslo." }

    & scp -P $SshPort -r "$TempSlim\*" "${SshUser}@${HaosHost}:${ScpRemoteDir}/"
    if ($LASTEXITCODE -ne 0) { throw "scp zlyhal (exit $LASTEXITCODE)." }

    Write-Host "[4/4] Hotovo cez SCP."
    Write-Host "NA HAOS SSH:  bash $ScpRemoteDir/deploy_on_haos.sh"
}

$used = $Method
if ($Method -eq "auto") {
    Write-Host "Skusam Samba, potom SCP..."
    if (Try-Samba) { exit 0 }
    Write-Host "Samba nedostupna, prepinam na SCP."
    $used = "scp"
}

if ($used -eq "samba") {
    if (-not (Try-Samba)) { throw "Samba nie je dostupna." }
    exit 0
}

if ($used -eq "scp") {
    Push-Scp
    exit 0
}
