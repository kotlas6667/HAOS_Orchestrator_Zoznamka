# Changelog

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
