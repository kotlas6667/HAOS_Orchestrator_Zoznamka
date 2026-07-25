# HAOS Orchestrator

AI orchestrátor pre Home Assistant OS — prirodzený jazyk (väčšinou slovenčina) ovláda smart home a súvisiace služby cez GPT routing.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2024.6+-41BDF5.svg)](https://www.home-assistant.io/)

Repo: [kotlas6667/HAOS_Orchestrator_Zoznamka](https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka)

---

## Čo to je

Jeden FastAPI orchestrátor (HA add-on) prijme prompt z **web dashboardu**, **Discord bota** alebo HTTP API, GPT rozhodne ktorý interný tool použiť, tool sa spustí a vráti štruktúrovanú odpoveď.

**Toto nie je samostatný hlasový asistent.** Orchestrátor neobsahuje STT/TTS ani Wyoming server. Nehovoríš priamo „do“ tohto add-onu cez mikrofón Home Assistant Voice PE — hlas rieši HA Assist mimo tohto projektu. Voliteľná custom conversation integrácia vie poslať *text* z Assist pipeline na `POST /api/voice` a vrátiť textovú odpoveď; samotný orchestrátor audio nespracúva.

### Tri HA add-ony v tomto repozitári

| Add-on | Slug | Port | Popis |
|--------|------|------|--------|
| **HAOS Orchestrator** | `haos_orchestrator` | `8000` (+ noVNC `6082`) | API, dashboard, Discord, Gmail/Calendar, HA, počasie, TODO |
| **Elite Date bot** | `haos_elitedate` | `8600` | Selenium + Discord handoff odpovedí |
| **Tinder bot** | `haos_tinder` | `8601` (+ noVNC `6080`) | Selenium + Discord handoff odpovedí |

Elite Date a Tinder **nespúšťa** hlavný orchestrátor — sú samostatné add-ony s vlastným Chromium.

---

## Funkcie

### Home Assistant
- Stav entít, zapnúť / vypnúť / toggle, volanie služieb
- Zoznam a spúšťanie automatizácií
- Fuzzy vyhľadávanie podľa názvu (nie vymýšľanie `entity_id`)
- REST API voči Core (`HA_URL` + long-lived token)

### Počasie
- Aktuálne počasie, predpoveď, hodinová predpoveď
- OpenWeather (v Nastaveniach treba API kľúč; provider musí byť `openweather`, nie len mock)

### Gmail + Google Calendar (multi-account)
- Čítanie / počítanie / odosielanie mailov
- Dnes / upcoming / vytváranie a úprava udalostí
- Prihlásenie cez **noVNC** (port **6082**) — Desktop OAuth client (`gmailSecret.json`)
- Jeden OAuth súhlas = Gmail + Calendar tokeny; viac účtov = viac loginov
- Účty: `google_accounts.json`, tokeny: `google_tokens/*.pickle`

### Discord
- Plný bot (história konverzácie, prefix / mention, whitelist)
- Webhook notifikácie (neprečítané maily, ranný súhrn, dating návrhy)
- Intercept odpovedí `1` / `2` / `4` pre Elite Date a Tinder (pred LLM routingom)

### TODO
- Úlohy v `todo.json` (pridať, zoznam, hotovo, zmazať, vyčistiť hotové)

### AI Chat
- GPT fallback pre všeobecné otázky
- Routing cez `gpt-4o-mini` (alebo `OPENAI_MODEL`); dating návrhy môžu ísť cez silnejší `DATING_REPLY_MODEL` (default `gpt-4o`)

### Dating status
- Tool `dating_status` — „ide Tinder?“, „správy na ED?“ (reachability botov, poll, fronta odpovedí)

### Elite Date (samostatný add-on)
- Poll inboxu (90–180 s), nové správy → Discord s 2 AI návrhmi
- Výber `1`/`2`/voľný text / `4` (znova navrhnúť) → Selenium `/send`
- Voliteľné ranné pozdravy (`morning_greet_enabled`)
- Detail: [`elitedate_bot/README.md`](elitedate_bot/README.md)

### Tinder (samostatný add-on)
- Rovnaký Discord handoff model ako Elite Date
- Prvé prihlásenie cez noVNC (`6080`), session v Chrome profile
- Detail: [`tinder_bot/README.md`](tinder_bot/README.md), [`tinder_bot/HAOS_LOGIN.md`](tinder_bot/HAOS_LOGIN.md)

### Background joby (orchestrátor)
- Periodické neprečítané maily → Discord (dedup `.seen_email_ids`)
- Denný ranný súhrn (~07:00): počasie + počet mailov → Discord

---

## Inštalácia (GitHub Obchod)

**Lokálny sync do `/addons` už nie je podporovaný.** Inštalácia a update idú cez GitHub Add-on Store.

1. V HA: **Nastavenia → Doplnky → Obchody s doplnkami → ⋮ → Repozitáre**
2. Pridaj: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`
3. Nainštaluj **HAOS Orchestrator** (a podľa potreby Elite Date / Tinder)
4. Vyplň Nastavenia (aspoň `openai_api_key`, `ha_token`) → Štart
5. Dashboard: HA panel **Orchestrator** (ingress) alebo `http://<IP_HA>:8000/`

DNS medzi add-onmi a update: [`deploy/UPDATE_VIA_GITHUB.md`](deploy/UPDATE_VIA_GITHUB.md).

Hostname z GitHub Obchodu je `{repo_hash}-haos-…` — ber hodnotu z **Add-on → Info → Hostname**, nie tip z dokumentácie.

| Add-on | Typická URL |
|--------|-------------|
| Orchestrátor | `http://{hash}-haos-orchestrator:8000` |
| Elite Date | `http://{hash}-haos-elitedate:8600` |
| Tinder | `http://{hash}-haos-tinder:8601` |

---

## Rýchly štart — príklady promptov

**Home Assistant:**
- „Zapni svetlo v obývačke“
- „Aká je teplota v spálni?“
- „Ukáž všetky zariadenia“

**Počasie:**
- „Aké je počasie v Bratislave?“
- „Predpoveď na 3 dni“

**Gmail / Calendar:**
- „Ukáž neprečítané emaily“
- „Čo mám dnes?“ / „Udalosti tento týždeň“

**TODO / chat:**
- „Pridaj úlohu: kúpiť mlieko“
- „Akú má dnes meniny?“

**Dating status:**
- „Ide Tinder?“ / „Správy na ED?“

---

## Konfigurácia

V HA Nastaveniach add-onu (alebo `.env` pri lokálnom behu). Kľúčové možnosti orchestrátora:

| Možnosť | Význam |
|---------|--------|
| `openai_api_key` | Routing + chat (+ súhrny mailov) |
| `openai_model` | Default `gpt-4o-mini` |
| `dating_reply_model` | Model pre ED/Tinder návrhy (default `gpt-4o`) |
| `ha_url` / `ha_token` | Core API |
| `weather_default_city` / `openweather_api_key` | Počasie |
| `discord_bot_enabled` / `discord_bot_token` / `discord_bot_channel_id` | Discord bot |
| `discord_webhook_url` | Notifikácie |
| `elitedate_bot_url` / `tinder_bot_url` | URL peer add-onov |
| `elitedate_auto_send` / `tinder_auto_send` | Auto-odoslanie návrhov |
| `dating_reply_skill` | Spoločný skill pre AI návrhy (alebo textarea na dashboarde) |
| `google_accounts_enabled` | Zapne noVNC na porte 6082 pre Google login |

Príklad `.env`: pozri [`.env.example`](.env.example).

### Gmail / Calendar cez noVNC

1. [Google Cloud Console](https://console.cloud.google.com/) → Gmail API + Calendar API
2. OAuth client **Desktop app** → JSON do `/data/orchestrator/config/gmailSecret.json`
3. Nastavenia → **Google VNC prihlásenie** = zapnuté → Uložiť → Reštart
4. Otvor `http://<IP_HA>:6082/vnc.html`
5. Dashboard → **Prihlásiť cez VNC** → v Chromiu dokonči Google účet
6. Ďalší účet = zopakuj krok 5. Vypnutie switchu + reštart vypne noVNC; tokeny ostanú.

---

## API (orchestrátor)

### Core
- `GET /` — web dashboard
- `GET /health` — health check
- `POST /api/prompt` — spracovanie promptu (štruktúrovaná odpoveď)
- `POST /api/voice` — textová odpoveď pripravená na TTS (používa voliteľná HA conversation integrácia)

### Služby dashboardu
- `POST /api/weather`, `GET /api/weather/hourly`
- `POST /api/messages`
- `GET|POST /api/todos`, `PATCH|DELETE /api/todos/{id}`
- `GET /api/calendar/today`, `GET /api/calendar/upcoming`

### Google multi-account
- `GET /api/google/status`, `PUT /api/google/settings`
- `POST /api/google/oauth/vnc-start`, `GET /api/google/oauth/vnc-status`, …
- `DELETE /api/google/accounts/{id}`, `PUT /api/google/accounts/{id}/default`

### Dating
- `GET|PUT /api/dating-skill`
- `POST /api/elitedate/incoming`, `POST /api/elitedate/morning_greet`
- `POST /api/tinder/incoming`

---

## Dashboard

- Hodiny / meniny, mini počasie, uptime
- Chat na testovanie promptov
- TODO widget, kalendár (upcoming)
- Stav toolov, Google účty + VNC login
- Textarea spoločného dating reply skillu

---

## Discord bot

1. Zapni `discord_bot_enabled` + token (Message Content Intent v Discord Developer Portal)
2. Bot v kanáli: mention, prefix, alebo voľný text podľa nastavenia
3. Pri čakajúcej dating konverzácii odpovedz `1` / `2` / voľný text / `4` (nové návrhy)

---

## Voliteľná HA Assist integrácia

V `homeassistant_integration/custom_components/haos_orchestrator_conversation/` je custom conversation agent:

1. Skopíruj komponentu do `custom_components/` na HA
2. Pridaj integráciu a nastav URL orchestrátora
3. Assist pošle text na `POST /api/voice` a prečíta vrátený `reply`

Toto **nie je** zabudovaný hlasový mód add-onu a nie je súčasťou inštalácie z Obchodu.

---

## Štruktúra projektu

```
HAOS_Orchestrator_Zoznamka/
├── config.json                 # HA add-on: orchestrátor
├── repository.yaml             # GitHub Add-on Store
├── Dockerfile / run.sh
├── deploy/UPDATE_VIA_GITHUB.md
├── app/
│   ├── main.py                 # FastAPI + background joby
│   ├── orchestrator.py / router.py
│   ├── discord_bot.py / discord_chat.py
│   ├── config.py
│   ├── tools/                  # registry + tools + providery
│   ├── templates/index.html    # dashboard
│   └── static/
├── elitedate_bot/              # samostatný add-on
├── tinder_bot/                 # samostatný add-on
└── homeassistant_integration/  # voliteľný Assist conversation agent
```

Nový tool: zaregistruj v `app/tools/registry.py` a doplň popis do router promptu v `app/router.py`.

---

## Vývoj (lokálne)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# vyplň OPENAI_API_KEY, HA_TOKEN, …

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# alebo: ./start.sh
```

Docker:

```bash
docker build -t haos-orchestrator .
docker run -p 8000:8000 haos-orchestrator
```

---

## Riešenie problémov

**Add-on nenaštartuje** — logy v Supervisor; skontroluj `ha_token` / `openai_api_key`.

**HA neodpovedá** — long-lived token, URL `http://supervisor/core:8123`, sieť add-onu.

**Počasie mock** — nastav OpenWeather API kľúč; provider musí byť live (`openweather`), nie `mock`.

**Discord bot mlčí** — token, Message Content Intent, kanál / whitelist.

**Gmail / Calendar** — VNC postup vyššie; Desktop OAuth JSON na `gmailSecret.json`.

**Dating boty sa nevidia** — Hostname z Info každého add-onu do peer URL; pozri [`deploy/UPDATE_VIA_GITHUB.md`](deploy/UPDATE_VIA_GITHUB.md). Pri manuálnom webe ED/Tinder najprv **zastav** bot add-on (druhá session zabíja Selenium login).

---

## Licencia

MIT — pozri [LICENSE](LICENSE), ak je v repozitári.

---

**HAOS Orchestrator** — AI routing pre smart home, Gmail/Calendar, Discord a samostatné dating boty.
