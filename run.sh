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
DATING_REPLY_MODEL=gpt-4o
DATING_REPLY_PROVIDER=openai
GEMINI_API_KEY=
DATING_REPLY_GEMINI_MODEL=gemini-2.5-flash

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
BADOO_BOT_URL=http://8c003d88-haos-badoo:8602
BADOO_AUTO_SEND=false

# Google (Gmail + Calendar) — multi-account; zapni v HA Nastaveniach alebo na dashboarde
GOOGLE_ACCOUNTS_ENABLED=false
GMAIL_PROVIDER=mock
CALENDAR_PROVIDER=mock
GMAIL_CREDENTIALS_JSON=/data/orchestrator/config/gmailSecret.json
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
        "dating_reply_model": "DATING_REPLY_MODEL",
        "dating_reply_provider": "DATING_REPLY_PROVIDER",
        "gemini_api_key": "GEMINI_API_KEY",
        "dating_reply_gemini_model": "DATING_REPLY_GEMINI_MODEL",
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
        "badoo_bot_url": "BADOO_BOT_URL",
        "elitedate_auto_send": "ELITEDATE_AUTO_SEND",
        "tinder_auto_send": "TINDER_AUTO_SEND",
        "badoo_auto_send": "BADOO_AUTO_SEND",
        "google_accounts_enabled": "GOOGLE_ACCOUNTS_ENABLED",
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

# Multiline shared dating skill → sidecar .md (`.env` nezvláda viacriadkový text spoľahlivo)
cfg_dir = env_path.parent
cfg_dir.mkdir(parents=True, exist_ok=True)
raw_skill = opts.get("dating_reply_skill") if opts else None
# Spätná kompatibilita: ak nové pole prázdne, zober staré ED/Tinder polia.
if not (isinstance(raw_skill, str) and raw_skill.strip()) and opts:
    for legacy_key in ("elitedate_reply_skill", "tinder_reply_skill"):
        legacy = opts.get(legacy_key)
        if isinstance(legacy, str) and legacy.strip():
            raw_skill = legacy
            print(f"[orchestrator] dating_reply_skill: using legacy {legacy_key}")
            break
skill_content = raw_skill.strip() if isinstance(raw_skill, str) else ""
skill_path = cfg_dir / "dating_reply_skill.md"
# Nevymaž custom skill z dashboardu / súboru, keď je HA jednoriadkové pole prázdne.
if skill_content:
    skill_path.write_text(skill_content + "\n", encoding="utf-8")
    print(f"[orchestrator] Reply skill dating_reply_skill.md: {len(skill_content)} chars (from HA Nastavenia)")
elif skill_path.is_file() and skill_path.stat().st_size > 0:
    existing = skill_path.read_text(encoding="utf-8").strip()
    print(
        f"[orchestrator] Reply skill dating_reply_skill.md: {len(existing)} chars "
        "(kept existing file — edit via dashboard textarea)"
    )
else:
    skill_path.write_text("", encoding="utf-8")
    print("[orchestrator] Reply skill dating_reply_skill.md: empty → bundled default")

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
bd = resolve_url(
    _current("BADOO_BOT_URL"),
    slug_suffix="haos_badoo",
    port=8602,
    label="orchestrator/badoo",
)
updates["ELITEDATE_BOT_URL"] = ed
updates["TINDER_BOT_URL"] = td
updates["BADOO_BOT_URL"] = bd

# Persist corrected URLs into options.json + Supervisor (HA UI often stuck on haos_*)
ui_patch = {}
if opts and options_path.is_file():
    ui_changed = False
    for opt_key, env_key in (
        ("elitedate_bot_url", "ELITEDATE_BOT_URL"),
        ("tinder_bot_url", "TINDER_BOT_URL"),
        ("badoo_bot_url", "BADOO_BOT_URL"),
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

print(f"[orchestrator] dating URLs: ELITEDATE_BOT_URL={ed} TINDER_BOT_URL={td} BADOO_BOT_URL={bd}")
for key, val in (("ELITEDATE_BOT_URL", ed), ("TINDER_BOT_URL", td), ("BADOO_BOT_URL", bd)):
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
for f in gmailSecret.json credentials.json token.pickle token_calendar.pickle todo.json google_accounts.json; do
    if [ ! -e "$CFG/$f" ] && [ -e "/app/$f" ] && [ ! -L "/app/$f" ]; then
        cp -f "/app/$f" "$CFG/$f"
        echo "Seeded $f into persistent config."
    fi
    if [ -e "$CFG/$f" ]; then
        ln -sf "$CFG/$f" "/app/$f"
    fi
done

# Multi-account Google OAuth tokens (one pickle per account)
mkdir -p "$CFG/google_tokens"
ln -sfn "$CFG/google_tokens" /app/google_tokens

[ -e "$CFG/.seen_email_ids" ] || : > "$CFG/.seen_email_ids"
ln -sf "$CFG/.seen_email_ids" /app/.seen_email_ids

# If HA switch is on, force oauth providers in .env for this boot
if [ "${GOOGLE_ACCOUNTS_ENABLED:-false}" = "true" ] || [ "${GOOGLE_ACCOUNTS_ENABLED:-false}" = "True" ]; then
    python3 - <<'PY'
from pathlib import Path
p = Path("/data/orchestrator/config/.env")
text = p.read_text(encoding="utf-8") if p.is_file() else ""
lines = text.splitlines()
updates = {"GMAIL_PROVIDER": "oauth", "CALENDAR_PROVIDER": "oauth", "GOOGLE_ACCOUNTS_ENABLED": "true"}
out, seen = [], set()
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)
for k, v in updates.items():
    if k not in seen:
        out.append(f"{k}={v}")
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("[orchestrator] GOOGLE_ACCOUNTS_ENABLED → GMAIL/CALENDAR_PROVIDER=oauth")
PY
    cp -f "$CFG/.env" /app/.env
fi

mkdir -p "$CFG/elitedate" "$CFG/tinder"
[ -e "$CFG/elitedate_state.json" ] || echo '{"queue":[]}' > "$CFG/elitedate_state.json"
[ -e "$CFG/tinder_state.json" ] || echo '{"queue":[]}' > "$CFG/tinder_state.json"
[ -e "$CFG/badoo_state.json" ] || echo '{"queue":[]}' > "$CFG/badoo_state.json"
ln -sf "$CFG/elitedate_state.json" /app/elitedate_state.json
ln -sf "$CFG/tinder_state.json" /app/tinder_state.json
ln -sf "$CFG/badoo_state.json" /app/badoo_state.json

# AI reply skill (HA Nastavenia → shared sidecar; ED + Tinder providers)
[ -e "$CFG/dating_reply_skill.md" ] || : > "$CFG/dating_reply_skill.md"
ln -sf "$CFG/dating_reply_skill.md" /app/dating_reply_skill.user.md

LOG_LEVEL="${LOG_LEVEL:-info}"
echo "Log level: ${LOG_LEVEL}"
echo "Dating bots: ELITEDATE_BOT_URL=${ELITEDATE_BOT_URL:-<unset>} TINDER_BOT_URL=${TINDER_BOT_URL:-<unset>} BADOO_BOT_URL=${BADOO_BOT_URL:-<unset>}"
echo "Google VNC: GOOGLE_ACCOUNTS_ENABLED=${GOOGLE_ACCOUNTS_ENABLED:-false}"

# ---------------------------------------------------------------------------
# noVNC — Google login (ako Tinder). Zapni switch → Reštart → otvor :6082/vnc.html
# ---------------------------------------------------------------------------
start_novnc_if_needed() {
    if [ "${GOOGLE_ACCOUNTS_ENABLED:-false}" = "true" ] || [ "${GOOGLE_ACCOUNTS_ENABLED:-false}" = "True" ] \
       || [ "${GOOGLE_ACCOUNTS_ENABLED:-false}" = "1" ]; then
        export DISPLAY="${DISPLAY:-:99}"
        mkdir -p /data/orchestrator/config/chrome-google
        if ! pgrep -f "Xvfb $DISPLAY" >/dev/null 2>&1; then
            echo "[orchestrator] Starting Xvfb on $DISPLAY..."
            Xvfb "$DISPLAY" -screen 0 1366x768x24 -ac +extension GLX +render -noreset &
            sleep 2
        fi
        if ! pgrep -x x11vnc >/dev/null 2>&1; then
            echo "[orchestrator] Starting x11vnc..."
            x11vnc -display "$DISPLAY" -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared -bg -o /tmp/x11vnc.log
        fi
        if ! pgrep -f "websockify.*6082" >/dev/null 2>&1; then
            echo "[orchestrator] Starting noVNC on port 6082..."
            websockify --web=/usr/share/novnc 6082 localhost:5900 &
            sleep 1
        fi
        # Nie čierna obrazovka — uvítacia stránka v Chromiu
        xsetroot -solid "#1a2332" 2>/dev/null || true
        if command -v python3 >/dev/null 2>&1; then
            (cd /app && DISPLAY="$DISPLAY" python3 -c "
from app.tools.google_vnc_oauth import show_vnc_welcome
show_vnc_welcome()
" 2>/dev/null || true) &
        fi
        echo "[orchestrator] =============================================="
        echo "[orchestrator] Google login cez noVNC:"
        echo "[orchestrator]   http://<IP_HA>:6082/vnc.html"
        echo "[orchestrator] Dashboard → „Prihlásiť cez VNC“ (alebo API)."
        echo "[orchestrator] Jeden login = Gmail + Kalendár. Viac účtov = znova."
        echo "[orchestrator] Potom môžeš switch vypnúť → Reštart (tokeny ostanú)."
        echo "[orchestrator] =============================================="
    else
        echo "[orchestrator] Google noVNC vypnuté (google_accounts_enabled=false)."
    fi
}

start_novnc_if_needed

exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level "${LOG_LEVEL}"
