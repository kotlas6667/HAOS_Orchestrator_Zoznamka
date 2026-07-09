#!/usr/bin/env bash
#
# HAOS Orchestrator Add-on Entry Point
#
# Configuration is driven by the .env bundled into the image (/app/.env).
# You can override it persistently by placing your own .env in the add-on
# config folder: /data/orchestrator/config/.env
#
set -e

echo "Starting HAOS Orchestrator Add-on..."

CFG=/data/orchestrator/config
mkdir -p /data/orchestrator/logs "$CFG" /data/orchestrator/tokens

# ---------------------------------------------------------------------------
# Configuration (.env)
# ---------------------------------------------------------------------------
# A custom .env placed in the config folder wins over the bundled one.
if [ -f "$CFG/.env" ]; then
    echo "Using persistent config from $CFG/.env"
    cp -f "$CFG/.env" /app/.env
else
    echo "Using bundled configuration (/app/.env)"
fi

# ---------------------------------------------------------------------------
# Persistent state
# ---------------------------------------------------------------------------
# The app resolves these files relative to /app (its working directory).
# We seed them from the image on first boot, then symlink /app -> /data so
# that OAuth token refreshes, the TODO list and the seen-email cache survive
# restarts and image rebuilds.
for f in gmailSecret.json token.pickle token_calendar.pickle todo.json; do
    if [ ! -e "$CFG/$f" ] && [ -e "/app/$f" ] && [ ! -L "/app/$f" ]; then
        cp -f "/app/$f" "$CFG/$f"
        echo "Seeded $f into persistent config."
    fi
    if [ -e "$CFG/$f" ]; then
        ln -sf "$CFG/$f" "/app/$f"
    fi
done

# Seen-email cache: always keep a persistent, writable copy.
[ -e "$CFG/.seen_email_ids" ] || : > "$CFG/.seen_email_ids"
ln -sf "$CFG/.seen_email_ids" /app/.seen_email_ids

# Log level (falls back to info)
LOG_LEVEL="${LOG_LEVEL:-info}"
echo "Log level: ${LOG_LEVEL}"

# Start the application.
# IMPORTANT: single worker only. The app starts background tasks in its
# lifespan (Discord bot, email polling, morning summary) that must not be
# duplicated across worker processes.
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level "${LOG_LEVEL}"
