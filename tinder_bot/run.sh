#!/usr/bin/env bash
#
# HAOS Tinder Bot add-on entrypoint (samostatný kontajner, jeden Chromium).
#
set -e

echo "Starting HAOS Tinder Bot add-on..."

DATA=/data
mkdir -p "$DATA/chrome-profile"

# Persistent .env — seed empty template on first boot if missing.
if [ ! -f "$DATA/.env" ]; then
    cat > "$DATA/.env" <<'EOF'
TINDER_EMAIL=
TINDER_PASSWORD=
TINDER_PHONE=
TINDER_LOGIN_URL=https://tinder.com/app/login

TINDER_BOT_HOST=0.0.0.0
TINDER_BOT_PORT=8601

# Slug DNS name hlavného add-onu (alebo host IP / mapped port)
ORCHESTRATOR_URL=http://haos_orchestrator:8000

TINDER_POLL_ENABLED=true
TINDER_POLL_INTERVAL_MIN_SEC=90
TINDER_POLL_INTERVAL_MAX_SEC=180
TINDER_PAGE_SETTLE_SEC=4
TINDER_SPRAVY_SETTLE_SEC=10
TINDER_WAIT_TIMEOUT_SEC=10

TINDER_HEADLESS=true
TINDER_USER_DATA_DIR=/data/chrome-profile

TINDER_GEOLOCATION_ENABLED=true
TINDER_GEOLOCATION_LAT=48.1486
TINDER_GEOLOCATION_LON=17.1077
EOF
    echo "Seeded $DATA/.env — po prvom boote treba raz prihlásiť Tinder (TINDER_HEADLESS=false) a uložiť session."
fi

ln -sf "$DATA/.env" /app/.env

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
export SELENIUM_CHROME_LOCK="${SELENIUM_CHROME_LOCK:-/tmp/selenium_chrome.lock}"

# Startup diagnostics — helps spot missing profile / Windows cookie issues.
echo "[tinder_bot] TINDER_USER_DATA_DIR=$TINDER_USER_DATA_DIR"
echo "[tinder_bot] TINDER_HEADLESS=$TINDER_HEADLESS"
if [ -f "$TINDER_USER_DATA_DIR/Default/Network/Cookies" ]; then
    echo "[tinder_bot] Found Default/Network/Cookies ($(stat -c%s "$TINDER_USER_DATA_DIR/Default/Network/Cookies" 2>/dev/null || echo '?') bytes)"
elif [ -f "$TINDER_USER_DATA_DIR/Default/Cookies" ]; then
    echo "[tinder_bot] Found Default/Cookies"
else
    echo "[tinder_bot] WARNING: no Cookies file under $TINDER_USER_DATA_DIR/Default — session missing"
fi

_shutdown() {
    echo "Shutting down Tinder bot..."
    if [ -n "${BOT_PID:-}" ]; then
        kill -TERM "$BOT_PID" 2>/dev/null || true
        wait "$BOT_PID" 2>/dev/null || true
    fi
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
