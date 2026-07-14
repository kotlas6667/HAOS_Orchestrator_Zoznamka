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
    echo "Seeded $DATA/.env — vyplň Nastavenia add-onu (email/heslo) a reštartuj."
fi

ln -sf "$DATA/.env" /app/.env

# Synchronizuj Možnosti z HA UI (/data/options.json) → .env + export
# (Nastavenia add-onu majú prednosť pred ručne editovaným .env)
apply_addon_options() {
    python3 - <<'PY'
import json
import os
import re
from pathlib import Path

options_path = Path("/data/options.json")
env_path = Path("/data/.env")
if not options_path.is_file():
    print("[elitedate_bot] No /data/options.json — skipping HA options sync")
    raise SystemExit(0)

opts = json.loads(options_path.read_text(encoding="utf-8"))
# HA option key → ENV key
mapping = {
    "elitedate_email": "ELITEDATE_EMAIL",
    "elitedate_password": "ELITEDATE_PASSWORD",
    "elitedate_login_url": "ELITEDATE_LOGIN_URL",
    "orchestrator_url": "ORCHESTRATOR_URL",
    "headless": "HEADLESS",
}

updates = {}
for opt_key, env_key in mapping.items():
    if opt_key not in opts:
        continue
    val = opts[opt_key]
    if val is None:
        continue
    if isinstance(val, bool):
        updates[env_key] = "true" if val else "false"
    else:
        updates[env_key] = str(val)

if not updates:
    print("[elitedate_bot] HA options: nothing to apply")
    raise SystemExit(0)

text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
for env_key, env_val in updates.items():
    pattern = re.compile(rf"(?m)^{re.escape(env_key)}=.*$")
    line = f"{env_key}={env_val}"
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
env_path.write_text(text, encoding="utf-8")

export_lines = []
for env_key, env_val in updates.items():
    os.environ[env_key] = env_val
    export_lines.append(f"{env_key}={env_val}")
print("[elitedate_bot] Applied HA Nastavenia → .env:")
for line in export_lines:
    if line.startswith("ELITEDATE_PASSWORD="):
        print("  ELITEDATE_PASSWORD=***")
    else:
        print(f"  {line}")

Path("/tmp/ha_options_export.env").write_text(
    "\n".join(export_lines) + "\n", encoding="utf-8"
)
PY
    if [ -f /tmp/ha_options_export.env ]; then
        set -a
        # shellcheck disable=SC1091
        source /tmp/ha_options_export.env
        set +a
    fi
}

set -a
# shellcheck disable=SC1091
source "$DATA/.env"
set +a

apply_addon_options

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

if [ -z "${ELITEDATE_EMAIL:-}" ] || [ -z "${ELITEDATE_PASSWORD:-}" ]; then
    echo "[elitedate_bot] ELITEDATE_EMAIL / ELITEDATE_PASSWORD not set — vyplň Nastavenia add-onu a reštartuj."
    exit 77
fi

echo "[elitedate_bot] ORCHESTRATOR_URL=${ORCHESTRATOR_URL:-<unset>}"
echo "[elitedate_bot] HEADLESS=${HEADLESS:-true}"

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

    if [ "$code" -eq 77 ]; then
        echo "[elitedate_bot] configuration error (exit 77), not restarting."
        exit 77
    fi

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
