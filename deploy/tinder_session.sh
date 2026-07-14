#!/usr/bin/env bash
# Tinder session workflow — noVNC prihlásenie a prepnutie do headless prevádzky.
#
# Použitie (na HA cez SSH):
#   bash deploy/tinder_session.sh status
#   bash deploy/tinder_session.sh begin-login [IP_HA]     # headless=false + rebuild
#   bash deploy/tinder_session.sh wait-login              # čaká na logged_in v /health
#   bash deploy/tinder_session.sh finish-login            # headless=true + restart
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

HA_IP="${2:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
WAIT_SEC="${WAIT_SEC:-600}"

cmd="${1:-status}"

case "$cmd" in
    status)
        grep '"version"' /addons/haos_tinder/config.json 2>/dev/null || true
        check_tinder_profile
        opts="$(addon_data_dir tinder)/options.json"
        if [ -f "$opts" ]; then
            echo "options.json:"
            python3 -m json.tool "$opts" 2>/dev/null || cat "$opts"
        fi
        ;;

    begin-login)
        echo "==> Nastavujem tinder_headless=false"
        set_tinder_option tinder_headless false
        ha_rebuild tinder
        echo ""
        echo "=============================================="
        echo "  1) Otvor v prehliadači:"
        echo "     http://${HA_IP}:6080/vnc.html"
        echo "  2) Prihlás sa telefónom + OTP (NIE Google)"
        echo "  3) Spusti: bash $SCRIPT_DIR/tinder_session.sh wait-login"
        echo "     alebo sleduj log add-onu: Login detected..."
        echo "  4) Potom: bash $SCRIPT_DIR/tinder_session.sh finish-login"
        echo "=============================================="
        ;;

    wait-login)
        echo "Čakám max ${WAIT_SEC}s na logged_in=true (curl :8601/health)..."
        deadline=$((SECONDS + WAIT_SEC))
        while [ "$SECONDS" -lt "$deadline" ]; do
            resp="$(check_tinder_health)"
            echo "$(date +%H:%M:%S) $resp"
            if echo "$resp" | grep -q '"logged_in"[[:space:]]*:[[:space:]]*true'; then
                echo "OK — session aktívna. Spusti: bash $SCRIPT_DIR/tinder_session.sh finish-login"
                exit 0
            fi
            sleep 10
        done
        echo "Timeout — skontroluj noVNC a log add-onu." >&2
        exit 1
        ;;

    finish-login)
        echo "==> Nastavujem tinder_headless=true"
        set_tinder_option tinder_headless true
        ha_restart tinder
        sleep 8
        resp="$(check_tinder_health)"
        echo "$resp"
        if echo "$resp" | grep -q '"logged_in"[[:space:]]*:[[:space:]]*true'; then
            echo "Hotovo — Tinder bot beží headless."
        else
            echo "WARN: health ešte neukazuje logged_in — pozri log add-onu." >&2
            exit 1
        fi
        ;;

    *)
        echo "Použitie: $0 {status|begin-login|wait-login|finish-login} [IP_HA]" >&2
        exit 1
        ;;
esac
