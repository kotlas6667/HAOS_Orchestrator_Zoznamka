#!/usr/bin/env bash
# HAOS Tinder Bot add-on entrypoint (samostatný kontajner, jeden Chromium).
#
# Prvé prihlásenie (Linux session pre HAOS):
#   1) Nastavenia add-onu → tinder_headless = false → Uložiť
#   2) Spustiť add-on
#   3) Otvor http://<IP_HA>:6080/vnc.html — prihlás sa telefónom+OTP
#   4) Po "Login detected" v logu: Nastavenia → tinder_headless = true → Reštart
#
set -e

echo "Starting HAOS Tinder Bot add-on..."

DATA=/data

# Diagnostika /data mountu a Chrome profilu (host vs kontajner)
log_data_mount() {
    echo "[tinder_bot] --- /data mount ---"
    ls -la "$DATA/" 2>/dev/null | head -20 || echo "  (cannot list $DATA)"
    if [ -d "$DATA/chrome-profile" ]; then
        local n
        n=$(find "$DATA/chrome-profile" -maxdepth 3 -type f 2>/dev/null | wc -l)
        echo "[tinder_bot] chrome-profile: $n files under $DATA/chrome-profile"
        ls -la "$DATA/chrome-profile/Default/Network/Cookies" 2>/dev/null \
            || ls -la "$DATA/chrome-profile/Default/Cookies" 2>/dev/null \
            || echo "[tinder_bot]   (no Cookies file inside container yet)"
        # Zbytočné lock súbory po nečistom ukončení Chromium
        rm -f "$DATA/chrome-profile/SingletonLock" \
              "$DATA/chrome-profile/SingletonCookie" \
              "$DATA/chrome-profile/SingletonSocket" 2>/dev/null || true
        chmod -R a+rX "$DATA/chrome-profile" 2>/dev/null || true
    else
        echo "[tinder_bot] chrome-profile dir missing in container — will create after mount check"
    fi
    echo "[tinder_bot] --- end /data ---"
}

log_data_mount
mkdir -p "$DATA/chrome-profile"

if [ ! -f "$DATA/.env" ]; then
    cat > "$DATA/.env" <<'EOF'
TINDER_EMAIL=
TINDER_PASSWORD=
TINDER_PHONE=
TINDER_LOGIN_URL=https://tinder.com/app/login

TINDER_BOT_HOST=0.0.0.0
TINDER_BOT_PORT=8601
# HA lokálne add-ony: DNS = local-{slug} ( _ → - ), nie samotný slug
ORCHESTRATOR_URL=http://local-haos-orchestrator:8000

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

# Synchronizuj Možnosti z HA UI (/data/options.json) → .env + export
# (Nastavenia add-onu majú prednosť pred ručne editovaným .env)
apply_addon_options() {
    python3 - <<'PY'
import json
import os
import re
from pathlib import Path

_HOST_MAP = {
    "haos_orchestrator": "local-haos-orchestrator",
    "haos_tinder": "local-haos-tinder",
    "haos_elitedate": "local-haos-elitedate",
}

def fix_addon_dns(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return s

    def _repl(match: re.Match[str]) -> str:
        scheme, host, rest = match.group(1), match.group(2), match.group(3) or ""
        new_host = _HOST_MAP.get(host, host)
        return f"{scheme}{new_host}{rest}"

    return re.sub(r"(https?://)([^/\s:]+)(\S*)", _repl, s, count=1)

def migrate_env_hosts(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        raw = line.rstrip("\n")
        if "=" not in raw or raw.lstrip().startswith("#"):
            out_lines.append(line)
            continue
        key, _, val = raw.partition("=")
        fixed = fix_addon_dns(val)
        if fixed != val:
            notes.append(f"{key.strip()}: {val.strip()} → {fixed}")
            nl = "\n" if line.endswith("\n") else ""
            out_lines.append(f"{key}={fixed}{nl}")
        else:
            out_lines.append(line)
    return "".join(out_lines), notes

options_path = Path("/data/options.json")
env_path = Path("/data/.env")

text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
text, env_notes = migrate_env_hosts(text)
for note in env_notes:
    print(f"[tinder_bot] Migrated .env DNS: {note}")

updates = {}
if options_path.is_file():
    opts = json.loads(options_path.read_text(encoding="utf-8"))
    mapping = {
        "tinder_headless": "TINDER_HEADLESS",
        "orchestrator_url": "ORCHESTRATOR_URL",
        "poll_enabled": "TINDER_POLL_ENABLED",
        "login_wait_sec": "TINDER_LOGIN_WAIT_SEC",
        "tinder_phone": "TINDER_PHONE",
        "geolocation_enabled": "TINDER_GEOLOCATION_ENABLED",
        "geolocation_lat": "TINDER_GEOLOCATION_LAT",
        "geolocation_lon": "TINDER_GEOLOCATION_LON",
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
            raw = str(val)
            fixed = fix_addon_dns(raw)
            if fixed != raw:
                print(f"[tinder_bot] DNS fix {env_key}: {raw} → {fixed}")
            updates[env_key] = fixed
else:
    print("[tinder_bot] No /data/options.json — keeping .env defaults")

orch = updates.get("ORCHESTRATOR_URL")
if orch is None:
    m = re.search(r"(?m)^ORCHESTRATOR_URL=(.*)$", text)
    orch = m.group(1).strip() if m else ""
orch = fix_addon_dns(orch) if orch else "http://local-haos-orchestrator:8000"
for bad, good in _HOST_MAP.items():
    if bad in orch:
        orch = orch.replace(bad, good)
updates["ORCHESTRATOR_URL"] = orch or "http://local-haos-orchestrator:8000"
updates["TINDER_BOT_HOST"] = "0.0.0.0"

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
print("[tinder_bot] Applied HA Nastavenia → .env:")
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

# Najprv .env (seed / ručné hodnoty), potom HA Nastavenia majú prednosť
set -a
# shellcheck disable=SC1091
source "$DATA/.env"
set +a

apply_addon_options

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
        echo "[tinder_bot] Potom Nastavenia → tinder_headless=true → Reštart."
        echo "[tinder_bot] =============================================="
    fi
}

echo "[tinder_bot] TINDER_USER_DATA_DIR=$TINDER_USER_DATA_DIR"
echo "[tinder_bot] TINDER_HEADLESS=$TINDER_HEADLESS"
if [ -f "$TINDER_USER_DATA_DIR/Default/Network/Cookies" ] || [ -f "$TINDER_USER_DATA_DIR/Default/Cookies" ]; then
    COOKIE_PATH="$TINDER_USER_DATA_DIR/Default/Network/Cookies"
    [ -f "$COOKIE_PATH" ] || COOKIE_PATH="$TINDER_USER_DATA_DIR/Default/Cookies"
    echo "[tinder_bot] Found Cookies ($(stat -c%s "$COOKIE_PATH" 2>/dev/null || echo '?') bytes) at $COOKIE_PATH"
else
    echo "[tinder_bot] WARNING: no Cookies in container — profil na hoste nemusí byť namapovaný do /data"
    echo "[tinder_bot]   Host:  ls /mnt/data/supervisor/addons/data/local_haos_tinder/chrome-profile/"
    echo "[tinder_bot]   Vnútri: docker exec addon_local_haos_tinder ls -la /data/chrome-profile/Default/Network/"
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
