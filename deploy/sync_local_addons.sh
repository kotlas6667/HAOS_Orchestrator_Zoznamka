#!/usr/bin/env bash
# ZASTARANÉ — lokálne /addons sync už nepoužívame.
# Aktualizácia ide výhradne cez GitHub Obchod doplnkov.
#
# Pozri: deploy/UPDATE_VIA_GITHUB.md
#
echo "ERROR: Lokálny sync (/addons) už nie je podporovaný." >&2
echo "Aktualizuj cez GitHub Obchod:" >&2
echo "  Nastavenia → Doplnky → Obchod → ⋮ → Skontrolovať aktualizácie" >&2
echo "Návod: deploy/UPDATE_VIA_GITHUB.md" >&2
exit 1
