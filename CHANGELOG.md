# Changelog

## Tinder [1.2.14] / Elite Date [1.3.8] - 2026-07-17

### Fixed
- Chrome 150 crash loop (`Unable to receive message from renderer` / `invalid session id`) — odstránené `--single-process`.
- Tinder `/send`: spoľahlivejšie čakanie na textarea + jasnejšie chyby.

## [1.2.16] / Tinder [1.2.13] / Elite Date [1.3.7] - 2026-07-16

### Fixed
- Discord výber `1/2` na Tinderi: orchestrátor mal timeout **10 s** na `/send` → prázdna chyba
  `Nepodarilo sa vložiť odpoveď cez bota:` (`httpx.ReadTimeout` bez textu).
  Teraz 90 s + čitateľná správa (URL, auto_send, typ chyby).

## [1.2.15] - 2026-07-16

### Added
- Discord Tinder/Elite Date: voľba **4️⃣ nové návrhy odpovedí** (alebo text „Navrhni ďalšie odpovede“) —
  vygeneruje nové AI návrhy a znova pošle prompt so rovnakým ID vlákna.

## [1.2.14] - 2026-07-16

### Fixed
- AI návrhy: providers čítajú `dating_reply_skill` (oprava AttributeError po zlúčení polí).

## [1.2.13] - 2026-07-16

### Changed
- Jeden spoločný textbox **Skill pre AI návrhy (ED + Tinder)** namiesto dvoch polí.

## [1.2.12] - 2026-07-16

### Added
- Nastavenia: skill pre AI návrhy odpovedí v Discorde (GPT zohľadní pri 2 návrhoch).

## Elite Date [1.3.6] - 2026-07-15

### Added
- Ranné pozdravy: paginácia **Ďalšie** na Noví členovia — po prvej stránke načíta ďalšie karty.

## Elite Date [1.3.5] / Orchestrátor [1.2.11] - 2026-07-15

### Added
- ED: nastavenie **Max. prehľadaných profilov** (`morning_greet_max_opens`, default 20).
- ED → Orchestrátor → Discord: ranný súhrn s menami a počtom pozdravených / prehľadaných.
- Endpoint `POST /api/elitedate/morning_greet`.

## Elite Date [1.3.4] - 2026-07-15

### Changed
- Ranné pozdravy: `morning_greet_max_profiles` počíta len **odoslané** „Ahoj :-)“.
  Profily s históriou sa preskakujú, kým sa nenájde cieľový počet prázdnych chatov.

## Elite Date [1.3.3] - 2026-07-15

### Fixed
- Ranné pozdravy: reálne DOM selektory (`btn-partner-filter`, `#search_filter_form_*`,
  `#search_filter_form_submit`, `a.c-card`, `a.send-message-btn`) — oprava
  „Filtrovať button not found“ (text v nested span + omylom zatvorený filter panel).

## Elite Date [1.3.2] - 2026-07-15

### Fixed
- ED poll ako Tinder: detekcia nových správ cez plain preview cache + otvorenie chatu podľa ID (oprava stale DOM / stratených notifikácií).

## Elite Date [1.3.1] - 2026-07-15

### Fixed
- Docker image teraz obsahuje `morning_greet.py` (inak import crash pri štarte).
- `TZ=Europe/Bratislava` pre ranný beh o 07:00 lokálne.

## [1.2.10] / Elite Date [1.2.9] / Tinder [1.2.12] - 2026-07-15

### Added
- Elite Date: prepínač **Automatické sledovanie správ** (`poll_enabled`) — rovnako ako Tinder.
  VYPNUTÉ pri používaní webu; Discord `/send` ostáva aktívny.
- `dating_status` zobrazí, keď je ED poll vypnutý.

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
