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

if [ ! -f "$REPO/elitedate_bot/config.json" ]; then
    echo "ERROR: $REPO/elitedate_bot/config.json neexistuje na vetve $BRANCH." >&2
    echo "       Skús: BRANCH=cursor/elitedate-missing-credentials-graceful-ff0d bash $0" >&2
    exit 1
fi

echo "==> sync elitedate → /addons/haos_elitedate"
rm -rf /addons/haos_elitedate
cp -a "$REPO/elitedate_bot" /addons/haos_elitedate

if [ -d "$REPO/tinder_bot/config.json" ]; then
    echo "==> sync tinder → /addons/haos_tinder"
    rm -rf /addons/haos_tinder
    cp -a "$REPO/tinder_bot" /addons/haos_tinder
fi

echo ""
echo "Verzie na disku (/addons/*):"
grep '"version"' /addons/haos_elitedate/config.json
[ -f /addons/haos_tinder/config.json ] && grep '"version"' /addons/haos_tinder/config.json || true
echo ""
echo "Elite Date options (1.2.0+):"
grep -E 'elitedate_email|orchestrator_url' /addons/haos_elitedate/config.json || true
echo ""

# Obnov cache Supervisor-a (inak HA UI často neukáže novú verziu)
if command -v ha >/dev/null 2>&1; then
    echo "==> ha supervisor reload"
    ha supervisor reload || true
    echo ""
    echo "Nainštalovaná verzia (ak beží add-on):"
    ha addons info local_haos_elitedate 2>/dev/null | grep -E 'version|state' || true
else
    echo "(príkaz 'ha' nie je v PATH — reload urob v UI: Nastavenia → Systém → Supervisor → Reštart)"
fi

echo ""
echo "Hotovo. Ďalej v HA UI:"
echo "  1) Obchod doplnkov → ⋮ → Skontrolovať aktualizácie"
echo "  2) HAOS Elite Date Bot → Info → tri bodky → AKTUALIZOVAŤ alebo REBUILD"
echo ""
echo "Ak „Aktualizovať“ ukazuje rovnakú verziu alebo nič, vždy funguje:"
echo "  ha addons rebuild local_haos_elitedate"
echo ""
echo "Alebo jednorazovo zo staršej vetve:"
echo "  BRANCH=cursor/elitedate-missing-credentials-graceful-ff0d bash $0"
