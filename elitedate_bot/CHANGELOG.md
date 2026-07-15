# Changelog

## 1.3.0

- Ranné pozdravy na **Noví členovia** (`/ucet/novi-clenove`):
  filter (vek 34–41, výška do 166, 75 km, iba s fotkou), otvorenie profilu,
  „Napísať správu“, odoslanie „Ahoj :-)“ len ak je konverzácia prázdna
- HA Nastavenia: `morning_greet_enabled`, `morning_greet_max_profiles`
- Ochrana pred zacyklením: `/data/.morning_greeted.json` (spracované profilové ID + dátum behu)
- Manuálny test: `POST /debug/morning_greet`

## 1.2.4

- GitHub DNS: `ORCHESTRATOR_URL=http://8c003d88-haos-orchestrator:8000` (+ auto-discover)
- `hassio_api` pre resolúciu hostname cez Supervisor

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
