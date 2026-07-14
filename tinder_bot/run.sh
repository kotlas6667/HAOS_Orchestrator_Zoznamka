#!/usr/bin/env bash
# HAOS Tinder Bot add-on entrypoint (samostatný kontajner, jeden Chromium).
#
# Prvé prihlásenie (Linux session pre HAOS):
#   1) v /data/.env nastav TINDER_HEADLESS=false
#   2) Rebuild + Start add-onu
#   3) Otvor http://<IP_HA>:6080/vnc.html — prihlás sa telefónom+OTP
#   4) Po "Login detected" v logu nastav TINDER_HEADLESS=true a reštartuj
#
set -e

echo "Starting HAOS Tinder Bot add-on..."

DATA=/data
mkdir -p "$DATA/chrome-profile"

if [ ! -f "$DATA/.env" ]; then
    cat > "$DATA/.env" <<'EOF'
TINDER_EMAIL=
TINDER_PASSWORD=
TINDER_PHONE=
TINDER_LOGIN_URL=https://tinder.com/app/login

TINDER_BOT_HOST=0.0.0.0
TINDER_BOT_PORT=8601
ORCHESTRATOR_URL=http://haos_orchestrator:8000

TINDER_POLL_ENABLED=true
TINDER_POLL_INTERVAL_MIN_SEC=90
TINDER_POLL_INTERVAL_MAX_SEC=180
TINDER_PAGE_SETTLE_SEC=4
TINDER_SPRAVY_SETTLE_SEC=10
TINDER_WAIT_TIMEOUT_SEC=10

# Prvé prihlásenie: false + noVNC http://<IP>:6080/vnc.html , potom true
TINDER_HEADLESS=false
TINDER_USER_DATA_DIR=/data/chrome-profile
TINDER_LOGIN_WAIT_SEC=600

TINDER_GEOLOCATION_ENABLED=true
TINDER_GEOLOCATION_LAT=48.1486
TINDER_GEOLOCATION_LON=17.1077
EOF
    echo "Seeded $DATA/.env"
fi

ln -sf "$DATA/.env" /app/.env

# Načítaj .env do shellu (inak run.sh nevidí TINDER_HEADLESS=false)
set -a
# shellcheck disable=SC1091
source "$DATA/.env"
set +a

[ -e "$DATA/.seen_messages.json" ] || echo "[]" > "$DATA/.seen_messages.json"
mkdir -p /app/tinder_bot
ln -sf "$DATA/.seen_messages.json" /app/tinder_bot/.seen_messages.json

export TINDER_BROWSER=chrome
export TINDER_BROWSER_BINARY=/usr/bin/chromium
export TINDER_WEBDRIVER_PATH=/usr/bin/chromedriver
export TINDER_HEADLESS="${TINDER_HEADLESS:-true}"
export TINDER_BOT_HOST="${TINDER_BOT_HOST:-0.0.0.0}"
export TINDER_BOT_PORT="${TINDER_BOT_PORT:-8601}"
export TINDER_USER_DATA_DIR="${TINDER_USER_DATA_DIR:-$DATA/chrome-profile}"
export TINDER_CHROME_PASSWORD_STORE="${TINDER_CHROME_PASSWORD_STORE:-basic}"
export TINDER_LOGIN_WAIT_SEC="${TINDER_LOGIN_WAIT_SEC:-600}"
export SELENIUM_CHROME_LOCK="${SELENIUM_CHROME_LOCK:-/tmp/selenium_chrome.lock}"

start_novnc_if_needed() {
    if [ "$TINDER_HEADLESS" = "false" ] || [ "$TINDER_HEADLESS" = "0" ]; then
        export DISPLAY="${DISPLAY:-:99}"
        if ! pgrep -f "Xvfb $DISPLAY" >/dev/null 2>&1; then
            echo "[tinder_bot] Starting Xvfb on $DISPLAY..."
            Xvfb "$DISPLAY" -screen 0 1366x768x24 -ac +extension GLX +render -noreset &
            sleep 2
        fi
        if ! pgrep -x x11vnc >/dev/null 2>&1; then
            echo "[tinder_bot] Starting x11vnc..."
            x11vnc -display "$DISPLAY" -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared -bg -o /tmp/x11vnc.log
        fi
        if ! pgrep -f "websockify.*6080" >/dev/null 2>&1; then
            echo "[tinder_bot] Starting noVNC on port 6080..."
            websockify --web=/usr/share/novnc 6080 localhost:5900 &
        fi
        echo "[tinder_bot] =============================================="
        echo "[tinder_bot] PRIHLÁSENIE cez prehliadač na PC:"
        echo "[tinder_bot]   http://<IP_HA>:6080/vnc.html"
        echo "[tinder_bot]   (Tailscale napr. http://100.82.143.35:6080/vnc.html)"
        echo "[tinder_bot] Telefón + OTP (NIE Google). Po login v logu:"
        echo "[tinder_bot]   Login detected, session saved..."
        echo "[tinder_bot] Potom TINDER_HEADLESS=true v .env a reštart."
        echo "[tinder_bot] =============================================="
    fi
}

echo "[tinder_bot] TINDER_USER_DATA_DIR=$TINDER_USER_DATA_DIR"
echo "[tinder_bot] TINDER_HEADLESS=$TINDER_HEADLESS"
if [ -f "$TINDER_USER_DATA_DIR/Default/Network/Cookies" ]; then
    echo "[tinder_bot] Found Default/Network/Cookies ($(stat -c%s "$TINDER_USER_DATA_DIR/Default/Network/Cookies" 2>/dev/null || echo '?') bytes)"
else
    echo "[tinder_bot] WARNING: no Cookies yet — use noVNC login if TINDER_HEADLESS=false"
fi

start_novnc_if_needed

_shutdown() {
    echo "Shutting down Tinder bot..."
    if [ -n "${BOT_PID:-}" ]; then
        kill -TERM "$BOT_PID" 2>/dev/null || true
        wait "$BOT_PID" 2>/dev/null || true
    fi
    pkill -x x11vnc 2>/dev/null || true
    pkill -f "websockify.*6080" 2>/dev/null || true
    pkill -f "Xvfb :99" 2>/dev/null || true
}
trap _shutdown SIGTERM SIGINT

max_restarts=8
window_sec=600
restart_times=()

set +e
while true; do
    cd /app
    python -m tinder_bot.main &
    BOT_PID=$!
    wait "$BOT_PID"
    code=$?
    BOT_PID=""

    now=$(date +%s)
    pruned=()
    for t in "${restart_times[@]+"${restart_times[@]}"}"; do
        if [ $((now - t)) -lt "$window_sec" ]; then
            pruned+=("$t")
        fi
    done
    restart_times=("${pruned[@]}")
    restart_times+=("$now")

    echo "[tinder_bot] exited with code $code (${#restart_times[@]}/${max_restarts} restarts in last ${window_sec}s)"
    if [ "${#restart_times[@]}" -ge "$max_restarts" ]; then
        echo "[tinder_bot] too many restarts, giving up."
        exit "$code"
    fi
    sleep 5
done
