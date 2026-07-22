# Changelog

## 1.2.19

- **Poll:** scroll inboxu (virtual list) + bootstrap nových vlákien
- Rebuild session keď `client=None` (poll loop)
- Log `Poll done: rows=… preview_changes=… new=…`

## 1.2.18

- Preview cache commit až po `discord: true` (retry pri timeoute Discord/GPT)
- Timeout pollera → orchestrátor 120 s

## 1.2.17

- Poll: stiahne fotku matchu (`photo_base64`) a pošle ju orchestrátoru do Discordu

## 1.2.16

- Poll: extrahuje históriu chatu (`history`) pre AI návrhy v orchestrátore

## 1.2.15

- Nastavenie **Auto odoslať odpoveď** (`auto_send`) priamo v Tinder bote
- Celá posledná správa: spojiť za sebou idúce received bubliny (nie len posledný odsek)

## 1.2.14

- Chrome: odstránené `--single-process` / `--no-zygote` (Chrome 150 padal: renderer / invalid session id)
- `--headless=new`, `shm_size=1G`, wait timeout 30s, lepší `/send` (viac selektorov textarea)
- Rebuild: čistenie SingletonLock + recovery na renderer timeout

## 1.2.13

- `/send`: pri chybe vždy vráti text `error` (nie prázdny status)

## 1.2.12

- `/health` vracia `poll_enabled` (parity s Elite Date)

## 1.2.11

- URL orchestrátora podľa Supervisor slug (skutočný hash prefix), nie hardcoded `8c003d88`

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
