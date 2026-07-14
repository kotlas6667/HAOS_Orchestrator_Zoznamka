# Changelog

## 1.1.1

- Oprava Docker buildu: žiadny `COPY .env` (súbor nie je v gite)
- `.dockerignore` vylučuje ED/Tinder/chrome-profile z kontextu orchestrátora

## 1.1.0

- Ľahký image bez Chromium — Elite Date a Tinder sú samostatné add-ony
- Orchestrátor nespúšťa Selenium procesy

## 1.0.1

- Monolitický image s Chromium a oboma botmi (zastarané)
