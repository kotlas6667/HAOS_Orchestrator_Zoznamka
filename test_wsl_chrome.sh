#!/usr/bin/env bash
# WSL: over ci Chrome vobec funguje pred Selenium (sede okno = WSLg problem).
set -euo pipefail

pick_executable() {
  for candidate in "$@"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

BROWSER=""
for candidate in \
  "$(command -v google-chrome-stable 2>/dev/null || true)" \
  "/usr/bin/google-chrome-stable" \
  "$(command -v google-chrome 2>/dev/null || true)" \
  "$(command -v chromium-browser 2>/dev/null || true)" \
  "/snap/bin/chromium"; do
  if picked="$(pick_executable "$candidate")"; then
    BROWSER="$picked"
    break
  fi
done

if [ -z "$BROWSER" ]; then
  echo "Nainstaluj google-chrome-stable:"
  echo "  sudo apt install -y wget gnupg"
  echo "  wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg"
  echo '  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list'
  echo "  sudo apt update && sudo apt install -y google-chrome-stable"
  exit 1
fi

echo "Testujem: $BROWSER"
echo "Ak sa neotvori normalne okno s google.com, WSL GUI nefunguje — pouzi Windows capture_tinder_session.ps1"
"$BROWSER" --no-sandbox --disable-gpu --disable-dev-shm-usage https://www.google.com &
PID=$!
sleep 8
kill "$PID" 2>/dev/null || true
echo "Ak si videl normalnu stranku, spusti: bash ./capture_tinder_session_wsl.sh"
