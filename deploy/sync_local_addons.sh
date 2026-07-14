#!/usr/bin/env bash
# Skopíruj aktuálne add-ony z git repa do /addons/* (HAOS local add-ons).
# Preferuj GitHub repo v Obchode doplnkov — tento script je záloha pre rýchle ladenie.
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

echo "==> sync tinder → /addons/haos_tinder"
rm -rf /addons/haos_tinder
cp -a "$REPO/tinder_bot" /addons/haos_tinder

echo ""
echo "Verzie na disku (/addons/*):"
grep '"version"' /addons/haos_elitedate/config.json /addons/haos_tinder/config.json
echo ""
echo "Poznámka: koreň $REPO = HAOS Orchestrator (local). Pre GitHub Obchod doplnkov"
echo "          tento sync nie je potrebný — stačí push na main + Aktualizovať v UI."
echo ""

if command -v ha >/dev/null 2>&1; then
    echo "==> ha supervisor reload"
    ha supervisor reload || true
fi

echo ""
echo "Hotovo. Ďalej:"
echo "  ha addons rebuild local_haos_elitedate"
echo "  ha addons rebuild local_haos_tinder"
echo "  (orchestrátor: Rebuild local_haos_orchestrator alebo z Obchodu)"
