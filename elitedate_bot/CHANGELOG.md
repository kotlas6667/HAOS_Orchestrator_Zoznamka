# Changelog

## 1.2.5

- `orchestrator_url` prázdne = auto cez Supervisor (žiadny hardcoded hash)

## 1.2.4

- `hassio_api` + pokus o DNS cez repo hash (nahradené auto-discover)

## 1.2.3

- Detekcia nových správ cez JSON cache (`.conversation_previews.json`) ako Tinder — nie tučné písmo
- Seed po reštarte bez spamovania Discordu; notifikácia až pri zmene preview + správa od nich
- Cache prežíva rebuild (`/data/.conversation_previews.json`)
- `POST /debug/poll` na manuálny test

## 1.2.2

- Robustná DNS migrácia ORCHESTRATOR_URL (`haos_*` → `local-haos-*`)
- Default `BOT_HOST=0.0.0.0` a `ORCHESTRATOR_URL=http://local-haos-orchestrator:8000`

## 1.2.1

- Oprava DNS na orchestrátor: `http://local-haos-orchestrator:8000`
- Auto-migrácia starého `haos_orchestrator` hostname pri štarte

## 1.2.0

- Možnosti v HA UI: `elitedate_email`, `elitedate_password`, `orchestrator_url`, `elitedate_login_url`, `headless`
- Sync `/data/options.json` → `/data/.env` pri štarte (rovnako ako Tinder bot)
- Slovenské popisy polí v Nastaveniach (`translations/sk.yaml`)
- Bez reštartovej slučky pri chýbajúcich prihlasovacích údajoch (exit 77)

## 1.1.0

- Príprava HA Nastavení (interná verzia)

## 1.0.0

- Samostatný Elite Date bot add-on (port 8600)
- Oddelený od orchestrátora
