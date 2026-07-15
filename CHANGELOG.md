# Changelog

## 1.2.6

- URL peer botov: **prázdne = auto** cez Supervisor (žiadny hardcoded hash v Nastaveniach)
- `local-haos-*` / `haos_*` sa pri štarte prepíšu na aktuálny hostname z Supervisora

## 1.2.5

- Pokus o GitHub DNS cez repo hash (nahradené 1.2.6 auto-discover)

## 1.2.4

- Force DNS migrácia + startup banner `image version=…`
- Refuse start pri zjavne zlých dating URL

## 1.2.3

- Elite Date: detekcia správ cez JSON preview cache (ako Tinder)
- Perzistentné `.conversation_previews.json` pre ED aj Tinder v `/data`
- Aktualizácia len cez GitHub Obchod (`deploy/UPDATE_VIA_GITHUB.md`) — bez `/addons` sync

## 1.2.2

- Robustná DNS migrácia hostnamov (`haos_*` → `local-haos-*`) pri každom štarte
- Startup probe Elite Date / Tinder (`/health`) — jasný log ak DNS/URL zlyhá
- Nový tool `dating_status` (Discord: „správy na ed?“ už nejde do Gmailu)

## 1.2.1

- Oprava DNS medzi add-onmi: `local-haos-*` namiesto neplatného `haos_*`
- Auto-migrácia starých URL pri štarte (`run.sh`)

## 1.2.0

- Možnosti v HA UI: OpenAI, HA token, Discord, ED/Tinder URL, počasie
- Sync `/data/options.json` → `/data/orchestrator/config/.env` pri štarte
- Slovenské popisy polí v Nastaveniach (`translations/sk.yaml`)

## 1.1.1

- Oprava Docker buildu: žiadny `COPY .env` (súbor nie je v gite)
- `.dockerignore` vylučuje ED/Tinder/chrome-profile z kontextu orchestrátora

## 1.1.0

- Ľahký image bez Chromium — Elite Date a Tinder sú samostatné add-ony
- Orchestrátor nespúšťa Selenium procesy

## 1.0.1

- Monolitický image s Chromium a oboma botmi (zastarané)
