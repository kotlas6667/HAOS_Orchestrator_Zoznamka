#!/usr/bin/env bash
# Zachyt Tinder session v WSL (Linux Chromium) — funguje na HAOS, na rozdiel
# od skopirovaneho Windows chrome-profile.
#
# Spusti z WSL v koreni projektu:
#   bash ./capture_tinder_session_wsl.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PROFILE="$ROOT/tinder_bot/chrome-profile-linux"
rm -rf "$PROFILE"
mkdir -p "$PROFILE"

# Chromium / chromedriver v WSL
if ! command -v chromium-browser >/dev/null 2>&1 && ! command -v chromium >/dev/null 2>&1; then
  echo "Instalujem chromium..."
  sudo apt-get update
  sudo apt-get install -y chromium-browser chromium-chromedriver || \
    sudo apt-get install -y chromium chromium-driver
fi

BROWSER_BIN="$(command -v chromium-browser || command -v chromium)"
DRIVER_BIN="$(command -v chromedriver || true)"

python3 -m pip install -q -r tinder_bot/requirements.txt

export TINDER_HEADLESS=false
export TINDER_USER_DATA_DIR="$PROFILE"
export TINDER_BROWSER=chrome
export TINDER_BROWSER_BINARY="$BROWSER_BIN"
if [ -n "$DRIVER_BIN" ]; then
  export TINDER_WEBDRIVER_PATH="$DRIVER_BIN"
fi
export TINDER_BOT_HOST=127.0.0.1
export TINDER_BOT_PORT=8601
export ORCHESTRATOR_URL=http://127.0.0.1:8000
export TINDER_POLL_ENABLED=false
export TINDER_LOGIN_WAIT_SEC=600
# Linux: plain password store so profile is portable to HAOS Chromium
export TINDER_CHROME_PASSWORD_STORE=basic

echo "============================================================"
echo " Otvara sa Chromium (WSL). Prihlas sa TELEFONOM + OTP."
echo " (Google OAuth v automate casto nefunguje.)"
echo " Cakam az 10 min. Hladaj: Login detected, session saved..."
echo " Profil: $PROFILE"
echo "============================================================"

python3 -m tinder_bot.main

echo ""
echo "Hotovo. Skopiruj na Samba:"
echo "  $PROFILE  ->  \\\\192.168.1.109\\addons\\haos_tinder\\chrome-profile"
echo "Potom HAOS SSH:"
echo "  TD=/mnt/data/supervisor/addons/data/local_haos_tinder"
echo "  rm -rf \"\$TD/chrome-profile\"/*"
echo "  cp -a /addons/haos_tinder/chrome-profile/. \"\$TD/chrome-profile/\""
echo "  Restart HAOS Tinder Bot"
