# Changelog

## [1.2.9] / Elite Date [1.2.8] / Tinder [1.2.11] - 2026-07-15

### Fixed
- DNS hash sa berie zo **Supervisor** (skutočný slug, napr. `03146090-haos-*`), nie z hardcoded `8c003d88`.
- Ak je v Nastaveniach iný hash než na HA, pri štarte sa prepíše podľa nainštalovaných add-onov.
- Tip: nepoužívaj Elite Date / Tinder **web naraz** so zapnutým botom — server často vyhodí Selenium session.

## [1.2.8] / Elite Date [1.2.7] / Tinder [1.2.10] - 2026-07-15

### Fixed
- Stuck `http://haos_elitedate:8600` / `haos_tinder` v Nastaveniach: pri štarte sa prepíšu cez Supervisor API na `http://8c003d88-haos-*`.
- Discord: „správy na ed?“ / „elite dáte“ už nejde do Gmailu (keyword intercept → `dating_status`).
- Pri štarte Discord alert, ak dating boty majú zlú URL alebo sú nedostupné.

## [1.2.7] / Elite Date [1.2.6] / Tinder [1.2.9] - 2026-07-15

### Fixed
- Vrátené predvolené URL `http://8c003d88-haos-*` (ako v 1.2.5) — prázdne „auto“ polia z 1.2.6 späť neplatia.
- Ak už máš fill-in hostname a boty bežia, nič nemen. Po update stačí restart orchestratora.

## 1.2.5

- **GitHub DNS fix:** hostname je `{repo_hash}-haos-*` (u nás `8c003d88-…`), nie `local-haos-*`
- Auto-resolve cez Supervisor API + oprava `options.json` pri štarte
- `local-haos-*` / `haos_*` sa považujú za neplatné a prepíšu sa

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
