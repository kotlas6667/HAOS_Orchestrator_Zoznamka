# Changelog

## 1.2.3

- Lepšia diagnostika /data mountu a Cookies v logu
- Jasnšie chybové hlášky (profil v kontajneri vs expirovaná session)
- `--password-store=basic` vždy (dešifrovanie cookies v Linux add-one)

## 1.2.2

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
