#!/usr/bin/env bash
#
# HAOS Orchestrator Add-on Entry Point
#
# Configuration is driven by the .env bundled into the image (/app/.env),
# or overridden by /data/orchestrator/config/.env.
#
# Elite Date a Tinder bežia ako SAMOSTATNÉ add-ony (elitedate_bot/, tinder_bot/)
# — tento kontajner ich nespúšťa, aby Pi 5 nemuselo ťahať dva Chromium procesy
# spolu s orchestrátorom.
#
set -e

echo "Starting HAOS Orchestrator Add-on..."

CFG=/data/orchestrator/config
mkdir -p /data/orchestrator/logs "$CFG" /data/orchestrator/tokens

# ---------------------------------------------------------------------------
# Configuration (.env)
# ---------------------------------------------------------------------------
if [ -f "$CFG/.env" ]; then
    echo "Using persistent config from $CFG/.env"
    cp -f "$CFG/.env" /app/.env
elif [ -f /app/.env ]; then
    echo "Using bundled configuration (/app/.env)"
else
    echo "WARNING: no .env found — copy .env.example to $CFG/.env and restart."
fi

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

# Elite Date / Tinder queue state (Discord handoff) — stále u orchestrátora.
mkdir -p "$CFG/elitedate" "$CFG/tinder"
[ -e "$CFG/elitedate_state.json" ] || echo '{"queue":[]}' > "$CFG/elitedate_state.json"
[ -e "$CFG/tinder_state.json" ] || echo '{"queue":[]}' > "$CFG/tinder_state.json"
ln -sf "$CFG/elitedate_state.json" /app/elitedate_state.json
ln -sf "$CFG/tinder_state.json" /app/tinder_state.json

LOG_LEVEL="${LOG_LEVEL:-info}"
echo "Log level: ${LOG_LEVEL}"
echo "Dating bots are external add-ons — set ELITEDATE_BOT_URL / TINDER_BOT_URL in .env."

# Single worker only (Discord bot + email polling must not be duplicated).
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level "${LOG_LEVEL}"
