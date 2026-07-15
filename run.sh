#!/usr/bin/env bash
#
# HAOS Orchestrator Add-on Entry Point
#
# Elite Date a Tinder bežia ako SAMOSTATNÉ add-ony — tento kontajner ich nespúšťa.
#
set -e

echo "Starting HAOS Orchestrator Add-on..."

# Visible version marker — if this line is missing in logs, the image is STILL OLD.
ORCH_VERSION="$(python3 -c "import json; print(json.load(open('/app/config.json')).get('version','?'))" 2>/dev/null || echo "?")"
echo "[orchestrator] image version=${ORCH_VERSION}"

CFG=/data/orchestrator/config
mkdir -p /data/orchestrator/logs "$CFG" /data/orchestrator/tokens

# ---------------------------------------------------------------------------
# Configuration (.env)
# ---------------------------------------------------------------------------
if [ ! -f "$CFG/.env" ]; then
    cat > "$CFG/.env" <<'EOF'
APP_NAME=HAOS Orchestrator
APP_ENV=prod
LOG_LEVEL=info

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

HA_PROVIDER=real
HA_URL=http://supervisor/core:8123
HA_TOKEN=

WEATHER_PROVIDER=mock
WEATHER_DEFAULT_CITY=Senica
OPENWEATHER_API_KEY=

DISCORD_PROVIDER=mock
DISCORD_BOT_ENABLED=false
DISCORD_BOT_TOKEN=
DISCORD_WEBHOOK_URL=
DISCORD_BOT_CHANNEL_ID=

ELITEDATE_BOT_URL=http://local-haos-elitedate:8600
ELITEDATE_AUTO_SEND=false
TINDER_BOT_URL=http://local-haos-tinder:8601
TINDER_AUTO_SEND=false
EOF
    echo "Seeded $CFG/.env — vyplň Nastavenia add-onu a reštartuj."
fi

# HA lokálne add-ony: DNS hostname = local-{slug} (podčiarkovníky → pomlčky).
# Staré defaulty typu http://haos_tinder:8601 sa v DNS neriešia.
apply_addon_options() {
    python3 - <<'PY'
import json
import os
import re
from pathlib import Path

# Bare slug host → HA DNS local-{slug with dashes}
_HOST_MAP = (
    ("haos_orchestrator", "local-haos-orchestrator"),
    ("haos_tinder", "local-haos-tinder"),
    ("haos_elitedate", "local-haos-elitedate"),
)

def fix_addon_dns(value):
    """Rewrite broken HA addon hostnames (simple replace — no regex edge cases)."""
    s = (value or "").strip()
    if not s:
        return s
    for bad, good in _HOST_MAP:
        s = s.replace("://" + bad, "://" + good)
    return s

def migrate_env_hosts(text):
    notes = []
    out_lines = []
    for line in text.splitlines(keepends=True):
        raw = line.rstrip("\n")
        if "=" not in raw or raw.lstrip().startswith("#"):
            out_lines.append(line)
            continue
        key, _, val = raw.partition("=")
        fixed = fix_addon_dns(val)
        if fixed != val:
            notes.append("%s: %s → %s" % (key.strip(), val.strip(), fixed))
            nl = "\n" if line.endswith("\n") else ""
            out_lines.append("%s=%s%s" % (key, fixed, nl))
        else:
            out_lines.append(line)
    return "".join(out_lines), notes

options_path = Path("/data/options.json")
env_path = Path("/data/orchestrator/config/.env")

text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
text, env_notes = migrate_env_hosts(text)
for note in env_notes:
    print("[orchestrator] Migrated .env DNS: %s" % note)

updates = {}
opts = {}
if options_path.is_file():
    opts = json.loads(options_path.read_text(encoding="utf-8"))
    mapping = {
        "log_level": "LOG_LEVEL",
        "openai_api_key": "OPENAI_API_KEY",
        "openai_model": "OPENAI_MODEL",
        "ha_url": "HA_URL",
        "ha_token": "HA_TOKEN",
        "weather_default_city": "WEATHER_DEFAULT_CITY",
        "openweather_api_key": "OPENWEATHER_API_KEY",
        "discord_bot_enabled": "DISCORD_BOT_ENABLED",
        "discord_bot_token": "DISCORD_BOT_TOKEN",
        "discord_webhook_url": "DISCORD_WEBHOOK_URL",
        "discord_bot_channel_id": "DISCORD_BOT_CHANNEL_ID",
        "elitedate_bot_url": "ELITEDATE_BOT_URL",
        "tinder_bot_url": "TINDER_BOT_URL",
        "elitedate_auto_send": "ELITEDATE_AUTO_SEND",
        "tinder_auto_send": "TINDER_AUTO_SEND",
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
                print("[orchestrator] DNS fix %s: %s → %s" % (env_key, raw, fixed))
            updates[env_key] = fixed
else:
    print("[orchestrator] No /data/options.json — keeping .env defaults")

# HARD guarantee: dating-bot URLs must be local-haos-*
defaults = {
    "ELITEDATE_BOT_URL": "http://local-haos-elitedate:8600",
    "TINDER_BOT_URL": "http://local-haos-tinder:8601",
}
for key, default in defaults.items():
    current = updates.get(key)
    if current is None:
        m = re.search(r"(?m)^%s=(.*)$" % re.escape(key), text)
        current = m.group(1).strip() if m else ""
    fixed = fix_addon_dns(current) if current else default
    # If anything still looks like bare slug host, force default
    if ("haos_elitedate" in fixed and "local-haos-elitedate" not in fixed) or \
       ("haos_tinder" in fixed and "local-haos-tinder" not in fixed) or \
       ("haos_orchestrator" in fixed and "local-haos-orchestrator" not in fixed) or \
       not fixed:
        print("[orchestrator] FORCE %s → %s (was %r)" % (key, default, current))
        fixed = default
    updates[key] = fixed

# Write corrected URLs back into options.json so HA UI Nastavenia stop showing broken hosts
if opts and options_path.is_file():
    ui_changed = False
    for opt_key, env_key in (
        ("elitedate_bot_url", "ELITEDATE_BOT_URL"),
        ("tinder_bot_url", "TINDER_BOT_URL"),
    ):
        if env_key in updates and opt_key in opts:
            new_val = updates[env_key]
            if str(opts.get(opt_key) or "") != new_val:
                print("[orchestrator] Patch options.json %s → %s" % (opt_key, new_val))
                opts[opt_key] = new_val
                ui_changed = True
    if ui_changed:
        options_path.write_text(json.dumps(opts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for env_key, env_val in updates.items():
    pattern = re.compile(r"(?m)^%s=.*$" % re.escape(env_key))
    line = "%s=%s" % (env_key, env_val)
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
env_path.parent.mkdir(parents=True, exist_ok=True)
env_path.write_text(text, encoding="utf-8")

secret_keys = {
    "OPENAI_API_KEY",
    "HA_TOKEN",
    "OPENWEATHER_API_KEY",
    "DISCORD_BOT_TOKEN",
}
export_lines = []
for env_key, env_val in updates.items():
    os.environ[env_key] = env_val
    export_lines.append("%s=%s" % (env_key, env_val))
print("[orchestrator] Applied HA Nastavenia → .env:")
for line in export_lines:
    key = line.split("=", 1)[0]
    if key in secret_keys:
        print("  %s=***" % key)
    else:
        print("  %s" % line)

# Final sanity line for logs
print(
    "[orchestrator] dating URLs: ELITEDATE_BOT_URL=%s TINDER_BOT_URL=%s"
    % (updates.get("ELITEDATE_BOT_URL"), updates.get("TINDER_BOT_URL"))
)
for key in ("ELITEDATE_BOT_URL", "TINDER_BOT_URL"):
    val = updates.get(key, "")
    if "://" in val and "local-haos-" not in val and ("haos_elitedate" in val or "haos_tinder" in val):
        raise SystemExit("[orchestrator] FATAL: %s still broken after DNS migration: %s" % (key, val))

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

apply_addon_options

cp -f "$CFG/.env" /app/.env

# ---------------------------------------------------------------------------
# Persistent state
# ---------------------------------------------------------------------------
for f in gmailSecret.json token.pickle token_calendar.pickle todo.json; do
    if [ ! -e "$CFG/$f" ] && [ -e "/app/$f" ] && [ ! -L "/app/$f" ]; then
        cp -f "/app/$f" "$CFG/$f"
        echo "Seeded $f into persistent config."
    fi
    if [ -e "$CFG/$f" ]; then
        ln -sf "$CFG/$f" "/app/$f"
    fi
done

[ -e "$CFG/.seen_email_ids" ] || : > "$CFG/.seen_email_ids"
ln -sf "$CFG/.seen_email_ids" /app/.seen_email_ids

mkdir -p "$CFG/elitedate" "$CFG/tinder"
[ -e "$CFG/elitedate_state.json" ] || echo '{"queue":[]}' > "$CFG/elitedate_state.json"
[ -e "$CFG/tinder_state.json" ] || echo '{"queue":[]}' > "$CFG/tinder_state.json"
ln -sf "$CFG/elitedate_state.json" /app/elitedate_state.json
ln -sf "$CFG/tinder_state.json" /app/tinder_state.json

LOG_LEVEL="${LOG_LEVEL:-info}"
echo "Log level: ${LOG_LEVEL}"
echo "Dating bots: ELITEDATE_BOT_URL=${ELITEDATE_BOT_URL:-<unset>} TINDER_BOT_URL=${TINDER_BOT_URL:-<unset>}"

# Refuse to start with known-broken hostnames (catches Supervisor-injected env too)
case "${ELITEDATE_BOT_URL:-}" in
    *://haos_elitedate*) echo "[orchestrator] FATAL: ELITEDATE_BOT_URL still haos_elitedate — image stale or migration failed"; exit 1 ;;
esac
case "${TINDER_BOT_URL:-}" in
    *://haos_tinder*) echo "[orchestrator] FATAL: TINDER_BOT_URL still haos_tinder — image stale or migration failed"; exit 1 ;;
esac

exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level "${LOG_LEVEL}"
