#!/usr/bin/env bash
# Aktualizuj local add-ony: git pull → cp → Rebuild → voliteľne health check.
#
# Použitie (na HA cez SSH):
#   bash /addons/haos_orchestrator/deploy/update_addons.sh
#   bash .../update_addons.sh --only tinder
#   bash .../update_addons.sh --sync-only          # bez Rebuild
#   bash .../update_addons.sh --restart-supervisor # pred Rebuild
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ONLY="all"
SYNC_ONLY=0
RESTART_SUPERVISOR=0

while [ $# -gt 0 ]; do
    case "$1" in
        --only) ONLY="$2"; shift 2 ;;
        --sync-only) SYNC_ONLY=1; shift ;;
        --restart-supervisor) RESTART_SUPERVISOR=1; shift ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *) echo "Neznámy argument: $1" >&2; exit 1 ;;
    esac
done

echo "========== HAOS deploy: sync add-ony =========="
bash "$SCRIPT_DIR/sync_local_addons.sh"

if [ "$RESTART_SUPERVISOR" = "1" ] && have_ha_cli; then
    echo "==> ha supervisor reload"
    ha supervisor reload || true
    sleep 5
fi

if [ "$SYNC_ONLY" = "1" ]; then
    echo "Sync hotový (--sync-only, preskočený Rebuild)."
    exit 0
fi

rebuild_one() {
    ha_rebuild "$1"
}

case "$ONLY" in
    all)
        rebuild_one orchestrator
        rebuild_one elitedate
        rebuild_one tinder
        ;;
    orchestrator|elitedate|tinder)
        rebuild_one "$ONLY"
        ;;
    *)
        echo "Neplatný --only: $ONLY (all|orchestrator|elitedate|tinder)" >&2
        exit 1
        ;;
esac

echo ""
echo "========== Overenie =========="
if [ "$ONLY" = "all" ] || [ "$ONLY" = "tinder" ]; then
    check_tinder_profile
fi
if [ "$ONLY" = "all" ] || [ "$ONLY" = "orchestrator" ]; then
    echo -n "Orchestrátor: "
    curl -sf --max-time 5 "http://127.0.0.1:8000/api/health" 2>/dev/null || echo "nedostupný (port 8000)"
fi
echo ""
echo "Hotovo. Pri local add-onoch vždy Rebuild, nie dialóg Aktualizovať."
