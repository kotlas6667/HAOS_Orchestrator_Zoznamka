#!/usr/bin/env bash
#
# HAOS Elite Date Bot add-on entrypoint (samostatný kontajner, jeden Chromium).
#
set -e

echo "Starting HAOS Elite Date Bot add-on..."

DATA=/data
mkdir -p "$DATA"

# Persistent .env — seed empty template on first boot if missing.
if [ ! -f "$DATA/.env" ]; then
    cat > "$DATA/.env" <<'EOF'
ELITEDATE_EMAIL=
ELITEDATE_PASSWORD=
ELITEDATE_LOGIN_URL=https://www.elitedate.sk/prihlaseni

# 0.0.0.0 so orchestrator add-on can reach us over the Docker network
BOT_HOST=0.0.0.0
BOT_PORT=8600

# Slug DNS name hlavného add-onu (alebo host IP / mapped port)
ORCHESTRATOR_URL=http://haos_orchestrator:8000

POLL_INTERVAL_MIN_SEC=90
POLL_INTERVAL_MAX_SEC=180

HEADLESS=true
EOF
    echo "Seeded $DATA/.env — vyplň ELITEDATE_EMAIL/PASSWORD a reštartuj add-on."
fi

ln -sf "$DATA/.env" /app/.env

# Seen-messages cache survives rebuilds.
[ -e "$DATA/.seen_messages.json" ] || echo "[]" > "$DATA/.seen_messages.json"
mkdir -p /app/elitedate_bot
ln -sf "$DATA/.seen_messages.json" /app/elitedate_bot/.seen_messages.json

# Force in-image Chromium (ignore Windows paths that may leak from a shared .env).
export BROWSER=chrome
export BROWSER_BINARY=/usr/bin/chromium
export WEBDRIVER_PATH=/usr/bin/chromedriver
export HEADLESS="${HEADLESS:-true}"
export BOT_HOST="${BOT_HOST:-0.0.0.0}"
export BOT_PORT="${BOT_PORT:-8600}"
export SELENIUM_CHROME_LOCK="${SELENIUM_CHROME_LOCK:-/tmp/selenium_chrome.lock}"

_shutdown() {
    echo "Shutting down Elite Date bot..."
    if [ -n "${BOT_PID:-}" ]; then
        kill -TERM "$BOT_PID" 2>/dev/null || true
        wait "$BOT_PID" 2>/dev/null || true
    fi
}
trap _shutdown SIGTERM SIGINT

# Poor-man's supervisor — Chrome/Selenium occasionally dies on Pi.
max_restarts=8
window_sec=600
restart_times=()

set +e
while true; do
    cd /app
    python -m elitedate_bot.main &
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

    echo "[elitedate_bot] exited with code $code (${#restart_times[@]}/${max_restarts} restarts in last ${window_sec}s)"
    if [ "${#restart_times[@]}" -ge "$max_restarts" ]; then
        echo "[elitedate_bot] too many restarts, giving up."
        exit "$code"
    fi
    sleep 5
done
