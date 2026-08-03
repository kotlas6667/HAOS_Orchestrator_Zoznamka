#!/usr/bin/env bash
# HAOS Badoo Bot add-on entrypoint (samostatný kontajner, jeden Chromium).
#
# Prvé prihlásenie (Google cez noVNC):
#   1) Nastavenia add-onu → badoo_headless = false → Uložiť
#   2) Spustiť add-on
#   3) Otvor http://<IP_HA>:6081/vnc.html — prihlás sa cez Google
#   4) Po "Login detected" v logu: Nastavenia → badoo_headless = true → Reštart
#
set -e

echo "Starting HAOS Badoo Bot add-on..."

DATA=/data

log_data_mount() {
    echo "[badoo_bot] --- /data mount ---"
    ls -la "$DATA/" 2>/dev/null | head -20 || echo "  (cannot list $DATA)"
    if [ -d "$DATA/chrome-profile" ]; then
        local n
        n=$(find "$DATA/chrome-profile" -maxdepth 3 -type f 2>/dev/null | wc -l)
        echo "[badoo_bot] chrome-profile: $n files under $DATA/chrome-profile"
        ls -la "$DATA/chrome-profile/Default/Network/Cookies" 2>/dev/null \
            || ls -la "$DATA/chrome-profile/Default/Cookies" 2>/dev/null \
            || echo "[badoo_bot]   (no Cookies file inside container yet)"
        rm -f "$DATA/chrome-profile/SingletonLock" \
              "$DATA/chrome-profile/SingletonCookie" \
              "$DATA/chrome-profile/SingletonSocket" 2>/dev/null || true
        chmod -R a+rX "$DATA/chrome-profile" 2>/dev/null || true
    else
        echo "[badoo_bot] chrome-profile dir missing in container — will create after mount check"
    fi
    echo "[badoo_bot] --- end /data ---"
}

log_data_mount
mkdir -p "$DATA/chrome-profile"

if [ ! -f "$DATA/.env" ]; then
    cat > "$DATA/.env" <<'EOF'
BADOO_LOGIN_URL=https://badoo.com/en/signin/
BADOO_HOME_URL=https://badoo.com/

BADOO_BOT_HOST=0.0.0.0
BADOO_BOT_PORT=8602
# GitHub-store DNS = {repo_hash}-haos-orchestrator (nie local- / haos_)
ORCHESTRATOR_URL=http://8c003d88-haos-orchestrator:8000

BADOO_POLL_ENABLED=false
BADOO_AUTO_SEND=false
BADOO_POLL_INTERVAL_MIN_SEC=90
BADOO_POLL_INTERVAL_MAX_SEC=180
BADOO_PAGE_SETTLE_SEC=3
BADOO_WAIT_TIMEOUT_SEC=30

# Prvé prihlásenie: false + noVNC http://<IP>:6081/vnc.html (Google), potom true
BADOO_HEADLESS=false
BADOO_USER_DATA_DIR=/data/chrome-profile
BADOO_LOGIN_WAIT_SEC=600

BADOO_GEOLOCATION_ENABLED=true
BADOO_GEOLOCATION_LAT=48.1486
BADOO_GEOLOCATION_LON=17.1077
EOF
    echo "Seeded $DATA/.env"
fi

ln -sf "$DATA/.env" /app/.env

apply_addon_options() {
    python3 - <<'PY'
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from addon_dns import persist_self_options, resolve_url  # noqa: E402

options_path = Path("/data/options.json")
env_path = Path("/data/.env")
text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""

updates = {}
opts = {}
if options_path.is_file():
    opts = json.loads(options_path.read_text(encoding="utf-8"))
    mapping = {
        "badoo_headless": "BADOO_HEADLESS",
        "orchestrator_url": "ORCHESTRATOR_URL",
        "poll_enabled": "BADOO_POLL_ENABLED",
        "login_wait_sec": "BADOO_LOGIN_WAIT_SEC",
        "geolocation_enabled": "BADOO_GEOLOCATION_ENABLED",
        "geolocation_lat": "BADOO_GEOLOCATION_LAT",
        "geolocation_lon": "BADOO_GEOLOCATION_LON",
        "auto_send": "BADOO_AUTO_SEND",
    }
    for opt_key, env_key in mapping.items():
        if opt_key not in opts:
            continue
        val = opts[opt_key]
        if val is None:
            continue
        if isinstance(val, bool):
            updates[env_key] = "true" if val else "false"
        else:
            updates[env_key] = str(val).strip()
else:
    print("[badoo_bot] No /data/options.json — keeping .env defaults")

orch = updates.get("ORCHESTRATOR_URL")
if orch is None:
    m = re.search(r"(?m)^ORCHESTRATOR_URL=(.*)$", text)
    orch = m.group(1).strip() if m else ""
orch = resolve_url(
    orch,
    slug_suffix="haos_orchestrator",
    port=8000,
    label="badoo/orch",
)
updates["ORCHESTRATOR_URL"] = orch
updates["BADOO_BOT_HOST"] = "0.0.0.0"

if opts and options_path.is_file() and str(opts.get("orchestrator_url") or "") != orch:
    opts["orchestrator_url"] = orch
    options_path.write_text(json.dumps(opts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[badoo_bot] Patch options.json orchestrator_url → {orch}")
    persist_self_options({"orchestrator_url": orch})

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
print("[badoo_bot] Applied HA Nastavenia → .env:")
for line in export_lines:
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

[ -e "$DATA/.seen_messages.json" ] || echo "[]" > "$DATA/.seen_messages.json"
[ -e "$DATA/.conversation_previews.json" ] || echo "{}" > "$DATA/.conversation_previews.json"
mkdir -p /app/badoo_bot
ln -sf "$DATA/.seen_messages.json" /app/badoo_bot/.seen_messages.json
ln -sf "$DATA/.conversation_previews.json" /app/badoo_bot/.conversation_previews.json

export BADOO_BROWSER=chrome
export BADOO_BROWSER_BINARY=/usr/bin/chromium
export BADOO_WEBDRIVER_PATH=/usr/bin/chromedriver
export BADOO_HEADLESS="${BADOO_HEADLESS:-true}"
export BADOO_BOT_HOST="${BADOO_BOT_HOST:-0.0.0.0}"
export BADOO_BOT_PORT="${BADOO_BOT_PORT:-8602}"
export BADOO_USER_DATA_DIR="${BADOO_USER_DATA_DIR:-$DATA/chrome-profile}"
export BADOO_CHROME_PASSWORD_STORE="${BADOO_CHROME_PASSWORD_STORE:-basic}"
export BADOO_LOGIN_WAIT_SEC="${BADOO_LOGIN_WAIT_SEC:-600}"
export SELENIUM_CHROME_LOCK="${SELENIUM_CHROME_LOCK:-/tmp/selenium_chrome.lock}"

start_novnc_if_needed() {
    if [ "$BADOO_HEADLESS" = "false" ] || [ "$BADOO_HEADLESS" = "0" ]; then
        export DISPLAY="${DISPLAY:-:99}"
        if ! pgrep -f "Xvfb $DISPLAY" >/dev/null 2>&1; then
            echo "[badoo_bot] Starting Xvfb on $DISPLAY..."
            Xvfb "$DISPLAY" -screen 0 1366x768x24 -ac +extension GLX +render -noreset &
            sleep 2
        fi
        if ! pgrep -x x11vnc >/dev/null 2>&1; then
            echo "[badoo_bot] Starting x11vnc..."
            x11vnc -display "$DISPLAY" -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared -bg -o /tmp/x11vnc.log
        fi
        if ! pgrep -f "websockify.*6081" >/dev/null 2>&1; then
            echo "[badoo_bot] Starting noVNC on port 6081..."
            websockify --web=/usr/share/novnc 6081 localhost:5900 &
        fi
        echo "[badoo_bot] =============================================="
        echo "[badoo_bot] PRIHLÁSENIE cez prehliadač na PC:"
        echo "[badoo_bot]   http://<IP_HA>:6081/vnc.html"
        echo "[badoo_bot] Prihlás sa cez Google (alebo telefón/email)."
        echo "[badoo_bot] Po login v logu: Login detected, session saved..."
        echo "[badoo_bot] Potom Nastavenia → badoo_headless=true → Reštart."
        echo "[badoo_bot] =============================================="
    fi
}

echo "[badoo_bot] BADOO_USER_DATA_DIR=$BADOO_USER_DATA_DIR"
echo "[badoo_bot] BADOO_HEADLESS=$BADOO_HEADLESS"
if [ -f "$BADOO_USER_DATA_DIR/Default/Network/Cookies" ] || [ -f "$BADOO_USER_DATA_DIR/Default/Cookies" ]; then
    COOKIE_PATH="$BADOO_USER_DATA_DIR/Default/Network/Cookies"
    [ -f "$COOKIE_PATH" ] || COOKIE_PATH="$BADOO_USER_DATA_DIR/Default/Cookies"
    echo "[badoo_bot] Found Cookies ($(stat -c%s "$COOKIE_PATH" 2>/dev/null || echo '?') bytes) at $COOKIE_PATH"
else
    echo "[badoo_bot] WARNING: no Cookies in container — prvé prihlásenie cez noVNC :6081"
fi

start_novnc_if_needed

_shutdown() {
    echo "Shutting down Badoo bot..."
    if [ -n "${BOT_PID:-}" ]; then
        kill -TERM "$BOT_PID" 2>/dev/null || true
        wait "$BOT_PID" 2>/dev/null || true
    fi
    pkill -x x11vnc 2>/dev/null || true
    pkill -f "websockify.*6081" 2>/dev/null || true
    pkill -f "Xvfb :99" 2>/dev/null || true
}
trap _shutdown SIGTERM SIGINT

max_restarts=8
window_sec=600
restart_times=()

set +e
while true; do
    cd /app
    python -m badoo_bot.main &
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

    echo "[badoo_bot] exited with code $code (${#restart_times[@]}/${max_restarts} restarts in last ${window_sec}s)"
    if [ "${#restart_times[@]}" -ge "$max_restarts" ]; then
        echo "[badoo_bot] too many restarts, giving up."
        exit "$code"
    fi
    sleep 5
done
