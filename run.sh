#!/usr/bin/env bash
#
# HAOS Orchestrator Add-on Entry Point
#
# Elite Date a Tinder bežia ako SAMOSTATNÉ add-ony — tento kontajner ich nespúšťa.
#
set -e

echo "Starting HAOS Orchestrator Add-on..."

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

# GitHub-store DNS = {repo_hash}-haos-* (nie local-haos-*, ani haos_*)
ELITEDATE_BOT_URL=http://8c003d88-haos-elitedate:8600
ELITEDATE_AUTO_SEND=false
TINDER_BOT_URL=http://8c003d88-haos-tinder:8601
TINDER_AUTO_SEND=false
EOF
    echo "Seeded $CFG/.env — vyplň Nastavenia add-onu a reštartuj."
fi

apply_addon_options() {
    python3 - <<'PY'
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from addon_dns import is_broken_url, persist_self_options, resolve_url  # noqa: E402

options_path = Path("/data/options.json")
env_path = Path("/data/orchestrator/config/.env")
text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""

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
            updates[env_key] = str(val).strip()
else:
    print("[orchestrator] No /data/options.json — keeping .env defaults")

# Multiline reply skills → sidecar .md (`.env` nezvláda viacriadkový text spoľahlivo)
cfg_dir = env_path.parent
cfg_dir.mkdir(parents=True, exist_ok=True)
for opt_key, filename in (
    ("elitedate_reply_skill", "elitedate_reply_skill.md"),
    ("tinder_reply_skill", "tinder_reply_skill.md"),
):
    raw = opts.get(opt_key) if opts else None
    content = raw.strip() if isinstance(raw, str) else ""
    skill_path = cfg_dir / filename
    skill_path.write_text((content + "\n") if content else "", encoding="utf-8")
    print(f"[orchestrator] Reply skill {filename}: {len(content)} chars ({'custom' if content else 'empty→bundled'})")

# Read current dating URLs from options/.env then resolve via Supervisor / hash DNS
def _current(key: str) -> str:
    if key in updates:
        return updates[key]
    m = re.search(rf"(?m)^{re.escape(key)}=(.*)$", text)
    return m.group(1).strip() if m else ""

ed = resolve_url(
    _current("ELITEDATE_BOT_URL"),
    slug_suffix="haos_elitedate",
    port=8600,
    label="orchestrator/ed",
)
td = resolve_url(
    _current("TINDER_BOT_URL"),
    slug_suffix="haos_tinder",
    port=8601,
    label="orchestrator/tinder",
)
updates["ELITEDATE_BOT_URL"] = ed
updates["TINDER_BOT_URL"] = td

# Persist corrected URLs into options.json + Supervisor (HA UI often stuck on haos_*)
ui_patch = {}
if opts and options_path.is_file():
    ui_changed = False
    for opt_key, env_key in (
        ("elitedate_bot_url", "ELITEDATE_BOT_URL"),
        ("tinder_bot_url", "TINDER_BOT_URL"),
    ):
        if env_key in updates and str(opts.get(opt_key) or "") != updates[env_key]:
            print(f"[orchestrator] Patch options.json {opt_key} → {updates[env_key]}")
            opts[opt_key] = updates[env_key]
            ui_patch[opt_key] = updates[env_key]
            ui_changed = True
    if ui_changed:
        options_path.write_text(json.dumps(opts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if ui_patch:
    persist_self_options(ui_patch)

for env_key, env_val in updates.items():
    pattern = re.compile(rf"(?m)^{re.escape(env_key)}=.*$")
    line = f"{env_key}={env_val}"
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
    export_lines.append(f"{env_key}={env_val}")
print("[orchestrator] Applied HA Nastavenia → .env:")
for line in export_lines:
    key = line.split("=", 1)[0]
    if key in secret_keys:
        print(f"  {key}=***")
    else:
        print(f"  {line}")

print(f"[orchestrator] dating URLs: ELITEDATE_BOT_URL={ed} TINDER_BOT_URL={td}")
for key, val in (("ELITEDATE_BOT_URL", ed), ("TINDER_BOT_URL", td)):
    if is_broken_url(val):
        print(f"[orchestrator] WARNING: {key} looks broken: {val}")

Path("/tmp/ha_options_export.env").write_text("\n".join(export_lines) + "\n", encoding="utf-8")
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

# AI reply skills (HA Nastavenia → /data/.../*.md; providers čítajú tieto súbory)
[ -e "$CFG/elitedate_reply_skill.md" ] || : > "$CFG/elitedate_reply_skill.md"
[ -e "$CFG/tinder_reply_skill.md" ] || : > "$CFG/tinder_reply_skill.md"
ln -sf "$CFG/elitedate_reply_skill.md" /app/elitedate_reply_skill.user.md
ln -sf "$CFG/tinder_reply_skill.md" /app/tinder_reply_skill.user.md

LOG_LEVEL="${LOG_LEVEL:-info}"
echo "Log level: ${LOG_LEVEL}"
echo "Dating bots: ELITEDATE_BOT_URL=${ELITEDATE_BOT_URL:-<unset>} TINDER_BOT_URL=${TINDER_BOT_URL:-<unset>}"

exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level "${LOG_LEVEL}"
