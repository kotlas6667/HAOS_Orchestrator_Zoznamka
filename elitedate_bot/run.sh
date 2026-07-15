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

# HA lokálne add-ony: DNS = local-{slug} ( _ → - ), nie samotný slug
ORCHESTRATOR_URL=http://local-haos-orchestrator:8000

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
    print(f"[elitedate_bot] Migrated .env DNS: {note}")

updates = {}
if options_path.is_file():
    opts = json.loads(options_path.read_text(encoding="utf-8"))
    mapping = {
        "elitedate_email": "ELITEDATE_EMAIL",
        "elitedate_password": "ELITEDATE_PASSWORD",
        "elitedate_login_url": "ELITEDATE_LOGIN_URL",
        "orchestrator_url": "ORCHESTRATOR_URL",
        "headless": "HEADLESS",
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
                print(f"[elitedate_bot] DNS fix {env_key}: {raw} → {fixed}")
            updates[env_key] = fixed
else:
    print("[elitedate_bot] No /data/options.json — keeping .env defaults")

# Guarantee reachable bind + valid orchestrator DNS
orch = updates.get("ORCHESTRATOR_URL")
if orch is None:
    m = re.search(r"(?m)^ORCHESTRATOR_URL=(.*)$", text)
    orch = m.group(1).strip() if m else ""
orch = fix_addon_dns(orch) if orch else "http://local-haos-orchestrator:8000"
for bad, good in _HOST_MAP.items():
    if bad in orch:
        orch = orch.replace(bad, good)
updates["ORCHESTRATOR_URL"] = orch or "http://local-haos-orchestrator:8000"
updates["BOT_HOST"] = "0.0.0.0"

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
