# HAOS Orchestrator

AI orchestrator for Home Assistant OS — natural language (mostly Slovak) controls your smart home and related services via GPT routing.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2024.6+-41BDF5.svg)](https://www.home-assistant.io/)

Repo: [kotlas6667/HAOS_Orchestrator_Zoznamka](https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka)

---

## What this is

A FastAPI orchestrator (HA add-on) accepts a prompt from the **web dashboard**, **Discord bot**, or HTTP API. GPT decides which internal tool to use, the tool runs, and a structured response is returned.

**This is not a standalone voice assistant.** The orchestrator has no STT/TTS and no Wyoming server. You do not speak directly “into” this add-on via a Home Assistant Voice PE microphone — voice is handled by HA Assist outside this project. An optional custom conversation integration can forward *text* from the Assist pipeline to `POST /api/voice` and return a text reply; the orchestrator itself does not process audio.

### Three HA add-ons in this repository

| Add-on | Slug | Port | Description |
|--------|------|------|-------------|
| **HAOS Orchestrator** | `haos_orchestrator` | `8000` (+ noVNC `6082`) | API, dashboard, Discord, Gmail/Calendar, HA, weather, TODO |
| **Elite Date bot** | `haos_elitedate` | `8600` | Selenium + Discord reply handoff |
| **Tinder bot** | `haos_tinder` | `8601` (+ noVNC `6080`) | Selenium + Discord reply handoff |

Elite Date and Tinder are **not** started by the main orchestrator — they are separate add-ons with their own Chromium.

---

## Features

### Home Assistant
- Entity state, turn on / off / toggle, service calls
- List and trigger automations
- Fuzzy search by name (does not invent `entity_id` values)
- REST API against Core (`HA_URL` + long-lived token)

### Weather
- Current conditions, forecast, hourly forecast
- OpenWeather (set the API key in Settings; provider must be `openweather`, not only mock)

### Gmail + Google Calendar (multi-account)
- Read / count / send email
- Today / upcoming / create and update events
- Sign-in via **noVNC** (port **6082**) — Desktop OAuth client (`gmailSecret.json`)
- One OAuth consent = Gmail + Calendar tokens; more accounts = more logins
- Accounts: `google_accounts.json`, tokens: `google_tokens/*.pickle`

### Discord
- Full bot (conversation history, prefix / mention, whitelist)
- Webhook notifications (unread email, morning summary, dating reply drafts)
- Intercepts replies `1` / `2` / `4` for Elite Date and Tinder (before LLM routing)

### TODO
- Tasks in `todo.json` (add, list, complete, delete, clear completed)

### AI Chat
- GPT fallback for general questions
- Routing via `gpt-4o-mini` (or `OPENAI_MODEL`); dating drafts may use a stronger `DATING_REPLY_MODEL` (default `gpt-4o`)

### Dating status
- Tool `dating_status` — e.g. “is Tinder up?”, “ED messages?” (bot reachability, poll status, reply queue)

### Elite Date (separate add-on)
- Inbox poll (90–180 s), new messages → Discord with 2 AI draft replies
- Choose `1` / `2` / free text / `4` (regenerate) → Selenium `/send`
- Optional morning greets (`morning_greet_enabled`)
- Details: [`elitedate_bot/README.md`](elitedate_bot/README.md)

### Tinder (separate add-on)
- Same Discord handoff model as Elite Date
- First login via noVNC (`6080`), session stored in Chrome profile
- Details: [`tinder_bot/README.md`](tinder_bot/README.md), [`tinder_bot/HAOS_LOGIN.md`](tinder_bot/HAOS_LOGIN.md)

### Background jobs (orchestrator)
- Periodic unread email → Discord (dedup via `.seen_email_ids`)
- Daily morning summary (~07:00): weather + unread count → Discord

---

## Installation (GitHub Add-on Store)

**Local sync into `/addons` is no longer supported.** Install and update via the GitHub Add-on Store.

1. In HA: **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`
3. Install **HAOS Orchestrator** (and Elite Date / Tinder if needed)
4. Fill in Settings (at least `openai_api_key`, `ha_token`) → Start
5. Dashboard: HA panel **Orchestrator** (ingress) or `http://<HA_IP>:8000/`

DNS between add-ons and updates: [`deploy/UPDATE_VIA_GITHUB.md`](deploy/UPDATE_VIA_GITHUB.md).

GitHub Store hostnames look like `{repo_hash}-haos-…` — use the value from **Add-on → Info → Hostname**, not a guess from the docs.

| Add-on | Typical URL |
|--------|-------------|
| Orchestrator | `http://{hash}-haos-orchestrator:8000` |
| Elite Date | `http://{hash}-haos-elitedate:8600` |
| Tinder | `http://{hash}-haos-tinder:8601` |

---

## Quick start — example prompts

**Home Assistant:**
- “Zapni svetlo v obývačke” (Turn on the living room light)
- “Aká je teplota v spálni?” (What’s the bedroom temperature?)
- “Ukáž všetky zariadenia” (Show all devices)

**Weather:**
- “Aké je počasie v Bratislave?” (What’s the weather in Bratislava?)
- “Predpoveď na 3 dni” (3-day forecast)

**Gmail / Calendar:**
- “Ukáž neprečítané emaily” (Show unread emails)
- “Čo mám dnes?” / “Udalosti tento týždeň” (What’s on today? / Events this week)

**TODO / chat:**
- “Pridaj úlohu: kúpiť mlieko” (Add task: buy milk)
- “Akú má dnes meniny?” (Whose name day is it today?)

**Dating status:**
- “Ide Tinder?” / “Správy na ED?” (Is Tinder up? / ED messages?)

---

## Configuration

In the HA add-on Settings (or `.env` for local runs). Key orchestrator options:

| Option | Meaning |
|--------|---------|
| `openai_api_key` | Routing + chat (+ email summaries) |
| `openai_model` | Default `gpt-4o-mini` |
| `dating_reply_model` | Model for ED/Tinder drafts (default `gpt-4o`) |
| `ha_url` / `ha_token` | Core API |
| `weather_default_city` / `openweather_api_key` | Weather |
| `discord_bot_enabled` / `discord_bot_token` / `discord_bot_channel_id` | Discord bot |
| `discord_webhook_url` | Notifications |
| `elitedate_bot_url` / `tinder_bot_url` | Peer add-on URLs |
| `elitedate_auto_send` / `tinder_auto_send` | Auto-send draft replies |
| `dating_reply_skill` | Shared skill for AI drafts (or dashboard textarea) |
| `google_accounts_enabled` | Enables noVNC on port 6082 for Google login |

Example `.env`: see [`.env.example`](.env.example).

### Gmail / Calendar via noVNC

1. [Google Cloud Console](https://console.cloud.google.com/) → enable Gmail API + Calendar API
2. OAuth client **Desktop app** → put JSON at `/data/orchestrator/config/gmailSecret.json`
3. Settings → **Google VNC login** = on → Save → Restart
4. Open `http://<HA_IP>:6082/vnc.html`
5. Dashboard → **Sign in via VNC** → finish the Google account in Chromium
6. Another account = repeat step 5. Turning the switch off + restart stops noVNC; tokens remain.

---

## API (orchestrator)

### Core
- `GET /` — web dashboard
- `GET /health` — health check
- `POST /api/prompt` — process a prompt (structured response)
- `POST /api/voice` — text reply ready for TTS (used by the optional HA conversation integration)

### Dashboard services
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

- Clock / name days, mini weather, uptime
- Chat for testing prompts
- TODO widget, calendar (upcoming)
- Tool status, Google accounts + VNC login
- Textarea for the shared dating reply skill

---

## Discord bot

1. Enable `discord_bot_enabled` + token (Message Content Intent in the Discord Developer Portal)
2. In the channel: mention, prefix, or free text depending on settings
3. When a dating conversation is awaiting selection, reply `1` / `2` / free text / `4` (regenerate drafts)

---

## Optional HA Assist integration

`homeassistant_integration/custom_components/haos_orchestrator_conversation/` is a custom conversation agent:

1. Copy the component into `custom_components/` on HA
2. Add the integration and set the orchestrator URL
3. Assist sends text to `POST /api/voice` and speaks the returned `reply`

This is **not** a built-in voice mode of the add-on and is **not** part of the Store install.

---

## Project structure

```
HAOS_Orchestrator_Zoznamka/
├── config.json                 # HA add-on: orchestrator
├── repository.yaml             # GitHub Add-on Store
├── Dockerfile / run.sh
├── deploy/UPDATE_VIA_GITHUB.md
├── app/
│   ├── main.py                 # FastAPI + background jobs
│   ├── orchestrator.py / router.py
│   ├── discord_bot.py / discord_chat.py
│   ├── config.py
│   ├── tools/                  # registry + tools + providers
│   ├── templates/index.html    # dashboard
│   └── static/
├── elitedate_bot/              # separate add-on
├── tinder_bot/                 # separate add-on
└── homeassistant_integration/  # optional Assist conversation agent
```

New tool: register in `app/tools/registry.py` and describe it in the router prompt in `app/router.py`.

---

## Development (local)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# fill in OPENAI_API_KEY, HA_TOKEN, …

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# or: ./start.sh
```

Docker:

```bash
docker build -t haos-orchestrator .
docker run -p 8000:8000 haos-orchestrator
```

---

## Troubleshooting

**Add-on won’t start** — check Supervisor logs; verify `ha_token` / `openai_api_key`.

**HA not responding** — long-lived token, URL `http://supervisor/core:8123`, add-on network access.

**Weather stuck on mock** — set OpenWeather API key; provider must be live (`openweather`), not `mock`.

**Discord bot silent** — token, Message Content Intent, channel / whitelist.

**Gmail / Calendar** — follow the VNC steps above; Desktop OAuth JSON at `gmailSecret.json`.

**Dating bots unreachable** — put each add-on’s Info → Hostname into the peer URL; see [`deploy/UPDATE_VIA_GITHUB.md`](deploy/UPDATE_VIA_GITHUB.md). Before using ED/Tinder in a normal browser, **stop** the bot add-on first (a second session kills the Selenium login).

---

## License

MIT — see [LICENSE](LICENSE) if present in the repository.

---

**HAOS Orchestrator** — AI routing for smart home, Gmail/Calendar, Discord, and separate dating bots.
