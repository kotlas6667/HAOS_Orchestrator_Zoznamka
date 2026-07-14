#!/usr/bin/env bash
# Zachyt Tinder session v WSL (Linux Chromium/Chrome) — profil je prenosny na HAOS.
#
# Spusti z WSL v koreni projektu:
#   bash ./capture_tinder_session_wsl.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PROFILE="$ROOT/tinder_bot/chrome-profile-linux"
VENV="$ROOT/.venv-wsl-tinder"
rm -rf "$PROFILE"
mkdir -p "$PROFILE"

pick_executable() {
  for candidate in "$@"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-venv python3-full chromium-chromedriver >/dev/null 2>&1 || true

BROWSER_BIN=""
for candidate in \
  "$(command -v google-chrome-stable 2>/dev/null || true)" \
  "$(command -v google-chrome 2>/dev/null || true)" \
  "/usr/bin/google-chrome-stable" \
  "/usr/bin/google-chrome" \
  "$(command -v chromium-browser 2>/dev/null || true)" \
  "$(command -v chromium 2>/dev/null || true)" \
  "/snap/bin/chromium" \
  "/usr/bin/chromium-browser" \
  "/usr/bin/chromium"; do
  if picked="$(pick_executable "$candidate")"; then
    BROWSER_BIN="$picked"
    break
  fi
done

if [ -z "$BROWSER_BIN" ]; then
  echo "Chrome/Chromium nenajdeny — instalujem google-chrome-stable..."
  sudo apt-get install -y wget gnupg ca-certificates
  wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y google-chrome-stable
  BROWSER_BIN="$(pick_executable "$(command -v google-chrome-stable 2>/dev/null || true)" /usr/bin/google-chrome-stable)" || true
fi

if [ -z "$BROWSER_BIN" ]; then
  echo "CHYBA: ziadny Chrome/Chromium. Skus:"
  echo "  which google-chrome-stable chromium-browser chromium chromedriver"
  echo "  ls -la /usr/bin/chromium* /snap/bin/chromium 2>/dev/null"
  exit 1
fi

DRIVER_BIN=""
for candidate in \
  "$(command -v chromedriver 2>/dev/null || true)" \
  "/usr/bin/chromedriver" \
  "/snap/bin/chromium.chromedriver"; do
  if picked="$(pick_executable "$candidate")"; then
    DRIVER_BIN="$picked"
    break
  fi
done

echo "Python venv: $VENV"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q -U pip
pip install -q -r tinder_bot/requirements.txt

export TINDER_HEADLESS=false
export TINDER_USER_DATA_DIR="$PROFILE"
export TINDER_BROWSER=chrome
export TINDER_BROWSER_BINARY="$BROWSER_BIN"
if [ -n "$DRIVER_BIN" ]; then
  export TINDER_WEBDRIVER_PATH="$DRIVER_BIN"
  echo "Chromedriver: $DRIVER_BIN"
else
  unset TINDER_WEBDRIVER_PATH || true
  echo "Chromedriver: (Selenium Manager auto)"
fi
export TINDER_BOT_HOST=127.0.0.1
export TINDER_BOT_PORT=8601
export ORCHESTRATOR_URL=http://127.0.0.1:8000
export TINDER_POLL_ENABLED=false
export TINDER_LOGIN_WAIT_SEC=600
export TINDER_CHROME_PASSWORD_STORE=basic

echo "============================================================"
echo " Browser: $BROWSER_BIN"
echo " Otvara sa okno. Prihlas sa TELEFONOM + OTP (nie Google)."
echo " Cakam az 10 min. Hladaj: Login detected, session saved..."
echo " Profil: $PROFILE"
echo "============================================================"

python -m tinder_bot.main

echo ""
echo "Hotovo. Skopiruj na Samba:"
echo "  $PROFILE  ->  \\\\192.168.1.109\\addons\\haos_tinder\\chrome-profile"
echo "Potom HAOS SSH:"
echo "  TD=/mnt/data/supervisor/addons/data/local_haos_tinder"
echo "  rm -rf \"\$TD/chrome-profile\"/*"
echo "  cp -a /addons/haos_tinder/chrome-profile/. \"\$TD/chrome-profile/\""
echo "  Restart HAOS Tinder Bot"
