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

# run.sh supervisors read TINDER_BOT_ENABLED / ELITEDATE_BOT_ENABLED from the
# shell environment — load /app/.env so .env toggles actually apply at startup.
if [ -f /app/.env ]; then
    set -a
    # shellcheck disable=SC1091
    . /app/.env
    set +a
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

# Seen-elitedate-messages cache: same persistence treatment.
mkdir -p "$CFG/elitedate"
[ -e "$CFG/elitedate/.seen_messages.json" ] || echo "[]" > "$CFG/elitedate/.seen_messages.json"
ln -sf "$CFG/elitedate/.seen_messages.json" /app/elitedate_bot/.seen_messages.json
[ -e "$CFG/elitedate/.conversation_last_messages.json" ] || echo "{}" > "$CFG/elitedate/.conversation_last_messages.json"
ln -sf "$CFG/elitedate/.conversation_last_messages.json" /app/elitedate_bot/.conversation_last_messages.json

# Seen-tinder-messages cache: same persistence treatment.
mkdir -p "$CFG/tinder"
[ -e "$CFG/tinder/.seen_messages.json" ] || echo "[]" > "$CFG/tinder/.seen_messages.json"
ln -sf "$CFG/tinder/.seen_messages.json" /app/tinder_bot/.seen_messages.json

# Persistent Chrome profile for Tinder's login session (phone-OTP/captcha
# can't be re-solved headlessly on every restart) — keep it under /data so it
# survives container rebuilds.
mkdir -p "$CFG/tinder/chrome-profile"
# Seed Tinder login session from bundled slim profile (copied via copy_tinder_profile_to_haos.ps1).
if [ ! -e "$CFG/tinder/chrome-profile/Default/Cookies" ] && [ -d "/app/data/orchestrator/config/tinder/chrome-profile/Default" ]; then
    echo "Seeding Tinder chrome profile into persistent storage..."
    cp -a /app/data/orchestrator/config/tinder/chrome-profile/. "$CFG/tinder/chrome-profile/"
fi

# ---------------------------------------------------------------------------
# elitedate_bot (Selenium against Elite Date)
# ---------------------------------------------------------------------------
# BROWSER_BINARY/WEBDRIVER_PATH in .env are typically set for local Windows
# dev (desktop Chrome). Force the in-image Chromium/chromedriver here so the
# container never picks up a Windows path. Real env vars win over .env in
# pydantic-settings, so this override is safe regardless of .env contents.
export BROWSER=chrome
export BROWSER_BINARY=/usr/bin/chromium
export WEBDRIVER_PATH=/usr/bin/chromedriver
export HEADLESS=true

# Poor-man's supervisor: restarts elitedate_bot on crash (Selenium/Chrome
# dying is expected occasionally), but gives up after too many restarts in a
# short window instead of respawning a permanently-broken process forever.
supervise_elitedate_bot() {
    set +e
    cd /app
    local max_restarts=5
    local window_sec=600
    local restart_times=()

    while true; do
        python -m elitedate_bot.main
        local code=$?
        local now
        now=$(date +%s)

        local pruned=()
        local t
        for t in "${restart_times[@]}"; do
            if [ $((now - t)) -lt "$window_sec" ]; then
                pruned+=("$t")
            fi
        done
        restart_times=("${pruned[@]}")
        restart_times+=("$now")

        echo "[elitedate_bot] exited with code $code (${#restart_times[@]}/${max_restarts} restarts in last ${window_sec}s)"
        if [ "${#restart_times[@]}" -ge "$max_restarts" ]; then
            echo "[elitedate_bot] too many restarts, giving up. Fix the underlying issue and restart the add-on."
            break
        fi
        sleep 5
    done
}

if [ "${ELITEDATE_BOT_ENABLED:-true}" = "true" ]; then
    echo "Starting elitedate_bot in background (supervised)..."
    # /data isn't mapped to a host-visible folder for this add-on, so route
    # output through the main process's stdout (visible in the add-on's Log
    # tab) instead of a file nobody can read, prefixed to tell it apart.
    supervise_elitedate_bot 2>&1 | sed -u 's/^/[elitedate_bot] /' &
    ELITEDATE_SUPERVISOR_PID=$!
else
    echo "elitedate_bot disabled (ELITEDATE_BOT_ENABLED=false)."
    ELITEDATE_SUPERVISOR_PID=""
fi

# ---------------------------------------------------------------------------
# tinder_bot (Selenium against Tinder)
# ---------------------------------------------------------------------------
# Same rationale as elitedate_bot above: force the in-image Chromium here,
# under Tinder-specific env var names so it never collides with elitedate_bot's
# BOT_HOST/BOT_PORT/etc. when both run from the same shared .env.
export TINDER_BROWSER=chrome
export TINDER_BROWSER_BINARY=/usr/bin/chromium
export TINDER_WEBDRIVER_PATH=/usr/bin/chromedriver
export TINDER_HEADLESS=true
export TINDER_USER_DATA_DIR="${TINDER_USER_DATA_DIR:-$CFG/tinder/chrome-profile}"

supervise_tinder_bot() {
    set +e
    cd /app
    local max_restarts=5
    local window_sec=600
    local restart_times=()

    while true; do
        python -m tinder_bot.main
        local code=$?
        local now
        now=$(date +%s)

        local pruned=()
        local t
        for t in "${restart_times[@]}"; do
            if [ $((now - t)) -lt "$window_sec" ]; then
                pruned+=("$t")
            fi
        done
        restart_times=("${pruned[@]}")
        restart_times+=("$now")

        echo "[tinder_bot] exited with code $code (${#restart_times[@]}/${max_restarts} restarts in last ${window_sec}s)"
        if [ "${#restart_times[@]}" -ge "$max_restarts" ]; then
            echo "[tinder_bot] too many restarts, giving up. Fix the underlying issue and restart the add-on."
            break
        fi
        sleep 5
    done
}

if [ "${TINDER_BOT_ENABLED:-true}" = "true" ]; then
    echo "Starting tinder_bot in background (supervised, 20s delay)..."
    (
        sleep 20
        supervise_tinder_bot 2>&1 | sed -u 's/^/[tinder_bot] /'
    ) &
    TINDER_SUPERVISOR_PID=$!
else
    echo "tinder_bot disabled (TINDER_BOT_ENABLED=false)."
    TINDER_SUPERVISOR_PID=""
fi

_shutdown() {
    echo "Shutting down HAOS Orchestrator add-on..."
    local pid
    for pid in "${ELITEDATE_SUPERVISOR_PID}" "${TINDER_SUPERVISOR_PID}"; do
        if [ -n "$pid" ]; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    for pid in $(jobs -p); do
        kill -TERM "$pid" 2>/dev/null || true
    done
    sleep 2
    for pid in $(jobs -p); do
        kill -KILL "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap _shutdown SIGTERM SIGINT

# Log level (falls back to info)
LOG_LEVEL="${LOG_LEVEL:-info}"
echo "Log level: ${LOG_LEVEL}"

# Start the application.
# IMPORTANT: single worker only. The app starts background tasks in its
# lifespan (Discord bot, email polling, morning summary) that must not be
# duplicated across worker processes.
# Do not `exec` here: we must stay PID 1 so Docker's SIGTERM reaches our trap
# and background elitedate/tinder supervisors (and their Chrome children) are
# killed cleanly instead of outliving a stop request.
python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level "${LOG_LEVEL}"
