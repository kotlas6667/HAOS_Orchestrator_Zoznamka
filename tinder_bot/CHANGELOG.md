# Changelog

## 1.2.10

- Stuck `ORCHESTRATOR_URL=http://haos_orchestrator:8000` sa pri štarte prepíše cez Supervisor na `http://8c003d88-haos-orchestrator:8000`

## 1.2.7

- GitHub DNS: `ORCHESTRATOR_URL=http://8c003d88-haos-orchestrator:8000` (+ auto-discover)
- `hassio_api` pre resolúciu hostname cez Supervisor

## 1.2.6

- `.conversation_previews.json` prežíva rebuild (`/data`)

## 1.2.5

- Robustná DNS migrácia ORCHESTRATOR_URL (`haos_*` → `local-haos-*`)
- Vždy force `TINDER_BOT_HOST=0.0.0.0` pri štarte

## 1.2.4

- Oprava DNS na orchestrátor: `http://local-haos-orchestrator:8000`
- Auto-migrácia starého `haos_orchestrator` hostname pri štarte

## 1.2.3

- Lepšia diagnostika /data mountu a Cookies v logu
- Jasnšie chybové hlášky (profil v kontajneri vs expirovaná session)
- `--password-store=basic` vždy (dešifrovanie cookies v Linux add-one)

## 1.2.2

- `deploy/HAOS_DEPLOY.md` — kompletný návod pre HAOS
- Skripty `update_addons.sh`, `tinder_session.sh` (automatizácia sync/rebuild/noVNC)

- CHANGELOG pre HA update dialóg
- Poznámka: pri lokálnom add-one používaj **Rebuild**, ak „Aktualizovať“ ukazuje rovnakú verziu

## 1.2.1

- Slovenské popisy polí v Nastaveniach (`translations/sk.yaml`)

## 1.2.0

- Možnosti v HA UI: `tinder_headless`, `orchestrator_url`, polling, geolokácia
- Sync `/data/options.json` → `/data/.env` pri štarte

## 1.1.0

- noVNC prihlásenie na porte 6080 (`TINDER_HEADLESS=false`)
- Xvfb + x11vnc + websockify v Dockerfile

## 1.0.0

- Samostatný Tinder bot add-on (port 8601)
- Oddelený od orchestrátora
