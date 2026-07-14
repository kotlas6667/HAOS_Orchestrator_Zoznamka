#!/usr/bin/env bash
# Skopíruj aktuálne add-ony z git repa do /addons/* (HAOS local add-ons).
# Spusti na HA cez SSH:
#   bash /addons/haos_orchestrator/deploy/sync_local_addons.sh
set -euo pipefail

REPO="${REPO:-/addons/haos_orchestrator}"
BRANCH="${BRANCH:-main}"

if [ ! -d "$REPO/.git" ]; then
    echo "ERROR: $REPO nie je git repo. Nastav REPO=..." >&2
    exit 1
fi

cd "$REPO"
echo "==> git fetch + checkout $BRANCH"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"

echo "==> sync elitedate → /addons/haos_elitedate"
rm -rf /addons/haos_elitedate
cp -a "$REPO/elitedate_bot" /addons/haos_elitedate

if [ -d "$REPO/tinder_bot/config.json" ]; then
    echo "==> sync tinder → /addons/haos_tinder"
    rm -rf /addons/haos_tinder
    cp -a "$REPO/tinder_bot" /addons/haos_tinder
fi

echo ""
echo "Verzie na disku:"
grep '"version"' /addons/haos_elitedate/config.json
[ -f /addons/haos_tinder/config.json ] && grep '"version"' /addons/haos_tinder/config.json || true
echo ""
echo "Elite Date options:"
grep -E 'elitedate_email|orchestrator_url' /addons/haos_elitedate/config.json || true
echo ""
echo "Hotovo. Ďalej v HA UI:"
echo "  1) Nastavenia → Systém → Supervisor → Reštart"
echo "  2) Obchod doplnkov → ⋮ → Skontrolovať aktualizácie"
echo "  3) HAOS Elite Date Bot → Info → tri bodky → REBUILD"
echo ""
echo "Alebo cez SSH: ha addons rebuild local_haos_elitedate"
