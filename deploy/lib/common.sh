#!/usr/bin/env bash
# Spoločné cesty a helpery pre deploy skripty na HAOS.
set -euo pipefail

REPO="${REPO:-/addons/haos_orchestrator}"
BRANCH="${BRANCH:-cursor/separate-ed-tinder-addons-687c}"
SUPERVISOR_DATA="${SUPERVISOR_DATA:-/mnt/data/supervisor/addons/data}"

addon_data_dir() {
    case "$1" in
        orchestrator) echo "$SUPERVISOR_DATA/local_haos_orchestrator" ;;
        elitedate)    echo "$SUPERVISOR_DATA/local_haos_elitedate" ;;
        tinder)       echo "$SUPERVISOR_DATA/local_haos_tinder" ;;
        *) echo "Unknown addon: $1" >&2; return 1 ;;
    esac
}

addon_slug() {
    case "$1" in
        orchestrator) echo "local_haos_orchestrator" ;;
        elitedate)    echo "local_haos_elitedate" ;;
        tinder)       echo "local_haos_tinder" ;;
        *) echo "Unknown addon: $1" >&2; return 1 ;;
    esac
}

have_ha_cli() {
    command -v ha >/dev/null 2>&1
}

ha_rebuild() {
    local name="$1"
    local slug
    slug="$(addon_slug "$name")"
    if have_ha_cli; then
        echo "==> ha addons rebuild $slug"
        ha addons rebuild "$slug"
    else
        echo "WARN: 'ha' CLI nie je k dispozícii — Rebuild v UI: Info → ⋮ → Rebuild ($slug)" >&2
    fi
}

ha_restart() {
    local name="$1"
    local slug
    slug="$(addon_slug "$name")"
    if have_ha_cli; then
        echo "==> ha addons restart $slug"
        ha addons restart "$slug"
    else
        echo "WARN: reštart $slug ručne v UI" >&2
    fi
}

set_tinder_option() {
    local key="$1"
    local value="$2"
    local data_dir config_json options_json
    data_dir="$(addon_data_dir tinder)"
    config_json="/addons/haos_tinder/config.json"
    options_json="$data_dir/options.json"
    mkdir -p "$data_dir"
    python3 - "$key" "$value" "$config_json" "$options_json" <<'PY'
import json, sys
key, value, config_path, options_path = sys.argv[1:5]
# Parse value: bool / int / str
if value.lower() in ("true", "false"):
    parsed = value.lower() == "true"
elif value.isdigit():
    parsed = int(value)
else:
    parsed = value
opts = {}
try:
    with open(options_path, encoding="utf-8") as f:
        opts = json.load(f)
except FileNotFoundError:
    pass
if not opts:
    try:
        with open(config_path, encoding="utf-8") as f:
            opts = json.load(f).get("options", {})
    except FileNotFoundError:
        opts = {}
opts[key] = parsed
with open(options_path, "w", encoding="utf-8") as f:
    json.dump(opts, f, indent=2)
    f.write("\n")
print(f"options.json: {key}={parsed!r} → {options_path}")
PY
}

check_tinder_health() {
    curl -sf --max-time 10 "http://127.0.0.1:8601/health" 2>/dev/null || echo '{"status":"unreachable"}'
}

check_tinder_profile() {
    local host_cookie container_cookie
    host_cookie="$(addon_data_dir tinder)/chrome-profile/Default/Network/Cookies"
    echo "--- Chrome profil ---"
    if [ -f "$host_cookie" ]; then
        echo "Host:   OK $(stat -c%s "$host_cookie" 2>/dev/null || echo '?') B  $host_cookie"
    else
        echo "Host:   CHÝBA $host_cookie"
    fi
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'addon_local_haos_tinder'; then
        if docker exec addon_local_haos_tinder test -f /data/chrome-profile/Default/Network/Cookies 2>/dev/null; then
            container_cookie="$(docker exec addon_local_haos_tinder stat -c%s /data/chrome-profile/Default/Network/Cookies 2>/dev/null || echo '?')"
            echo "Kontajner: OK ${container_cookie} B  /data/chrome-profile/Default/Network/Cookies"
        else
            echo "Kontajner: CHÝBA /data/chrome-profile/Default/Network/Cookies (mount problém?)"
        fi
    else
        echo "Kontajner: add-on nebeží"
    fi
    echo "--- Health ---"
    check_tinder_health
    echo
}
