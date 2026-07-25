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

| Add-on | Slug | Port(s) | Description |
|--------|------|---------|-------------|
| **HAOS Orchestrator** | `haos_orchestrator` | `8000`, noVNC `6082` | API, dashboard, Discord, Gmail/Calendar, HA, weather, TODO |
| **Elite Date bot** | `haos_elitedate` | `8600` | Selenium + Discord reply handoff |
| **Tinder bot** | `haos_tinder` | `8601`, noVNC `6080` | Selenium + Discord reply handoff |

Elite Date and Tinder are **not** started by the main orchestrator — they are separate add-ons with their own Chromium.

**Port note:** Google login noVNC is **6082**; Tinder login noVNC is **6080**. Both can run at the same time (older builds wrongly shared 6080).

---

## Features

### Home Assistant
- Entity state, turn on / off / toggle, service calls
- List and trigger automations
- Fuzzy search by name (does not invent `entity_id` values)
- REST API against Core (`HA_URL` + long-lived token)

### Weather
- Current conditions, forecast, hourly forecast
- OpenWeather when API key is set and provider is live (not stuck on mock)

### Gmail + Google Calendar (multi-account)
- Read / count / send email
- Today / upcoming / create and update events
- Sign-in via **noVNC** (port **6082**) — Desktop OAuth client (`gmailSecret.json`)
- One OAuth consent = Gmail + Calendar tokens; more accounts = more logins
- Accounts: `google_accounts.json`, tokens: `google_tokens/*.pickle`

### Discord
- Full bot (conversation history, prefix / mention, optional user whitelist)
- Webhook notifications (unread email, morning summary, dating reply drafts + optional profile photo)
- Intercepts replies `1` / `2` / `4` (or “Navrhni ďalšie odpovede”) for Elite Date and Tinder **before** LLM routing

### TODO
- Tasks in `todo.json` (add, list, complete, delete, clear completed)

### AI Chat
- GPT fallback for general questions
- Routing via `openai_model` (default `gpt-4o-mini`); dating drafts via `dating_reply_model` (default `gpt-4o`)

### Dating status
- Tool `dating_status` — bot reachability, login/session, poll flag, pending reply queue

### Elite Date (separate add-on)
- Inbox poll (randomized ~90–180 s), new messages → Discord with 2 AI drafts
- Choose `1` / `2` / free text / `4` → Selenium `POST /send`
- Optional morning greets on “new members”
- Details: [`elitedate_bot/README.md`](elitedate_bot/README.md)

### Tinder (separate add-on)
- Same Discord handoff model
- First login via noVNC (`6080`); session in Chrome profile under `/data`
- Details: [`tinder_bot/README.md`](tinder_bot/README.md), [`tinder_bot/HAOS_LOGIN.md`](tinder_bot/HAOS_LOGIN.md)

### Background jobs (orchestrator)
- Periodic unread email → Discord (dedup `.seen_email_ids`; needs OpenAI + Discord webhook)
- Daily morning summary (~07:00): weather + unread count → Discord

---

## Installation (GitHub Add-on Store)

**Local sync into `/addons` is no longer supported.** Install and update only via the GitHub Add-on Store.

1. In HA: **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add exactly: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`  
   (different URL shapes — `.git`, trailing `/` — produce a **different** DNS hash)
3. Install **HAOS Orchestrator**, and optionally **Elite Date** / **Tinder**
4. Configure Settings (see below) → Start
5. Dashboard: HA sidebar **Orchestrator** (ingress) or `http://<HA_IP>:8000/`

Also see [`deploy/UPDATE_VIA_GITHUB.md`](deploy/UPDATE_VIA_GITHUB.md).

### Peer DNS (critical)

From the GitHub store, hostnames are **not** `local-haos-*` and **not** bare `haos_*`.

```
http://{repo_hash}-{slug-with-dashes}:{port}
```

`repo_hash` = first 8 hex chars of SHA1 of the **exact** store repository URL you added.

**Always copy Hostname from Add-on → Info**, e.g.:

| Add-on | URL pattern |
|--------|-------------|
| Orchestrator | `http://{hash}-haos-orchestrator:8000` |
| Elite Date | `http://{hash}-haos-elitedate:8600` |
| Tinder | `http://{hash}-haos-tinder:8601` |

Recent versions resolve peer URLs via **Supervisor** at startup and rewrite broken defaults. If bots still cannot reach each other, paste Info → Hostname into Settings manually, Save, and restart all three.

**Broken hostnames (will not work on GitHub-store installs):**  
`haos_orchestrator`, `haos-elitedate`, `local-haos-tinder`, etc.

---

## Quick start — example prompts

**Home Assistant:** “Zapni svetlo v obývačke”, “Aká je teplota v spálni?”, “Ukáž všetky zariadenia”

**Weather:** “Aké je počasie v Bratislave?”, “Predpoveď na 3 dni”

**Gmail / Calendar:** “Ukáž neprečítané emaily”, “Čo mám dnes?”, “Udalosti tento týždeň”

**TODO / chat:** “Pridaj úlohu: kúpiť mlieko”, “Akú má dnes meniny?”

**Dating status:** “Ide Tinder?”, “Správy na ED?”

---

## Full configuration reference

Secrets (API keys, tokens, passwords, webhook URLs, emails, phone numbers) belong only in HA Settings or your private `.env` — never commit them.

### 1) HAOS Orchestrator — Add-on Settings

| Option | Default | Description |
|--------|---------|-------------|
| `log_level` | `info` | Use `debug` only while diagnosing |
| `openai_api_key` | *(empty)* | **Required** for GPT routing, chat, email summaries, dating drafts |
| `openai_model` | `gpt-4o-mini` | Cheap model for tool routing + normal chat |
| `dating_reply_model` | `gpt-4o` | Stronger model for ED/Tinder Discord draft replies only |
| `ha_url` | `http://supervisor/core:8123` | Home Assistant Core API (leave default inside HAOS) |
| `ha_token` | *(empty)* | Long-lived access token from your HA user profile |
| `weather_default_city` | e.g. `Senica` | City when the prompt does not name one |
| `openweather_api_key` | *(empty)* | Without a key, weather stays mock |
| `discord_bot_enabled` | `false` | Start the Discord.py bot inside the orchestrator |
| `discord_bot_token` | *(empty)* | Bot token; enable **Message Content Intent** |
| `discord_bot_channel_id` | *(empty)* | Limit listening to one channel; empty = all channels the bot can see |
| `discord_webhook_url` | *(empty)* | Notifications: morning summary, unread mail, dating prompts |
| `elitedate_bot_url` | store default | `http://{hash}-haos-elitedate:8600` from Elite Date → Info |
| `tinder_bot_url` | store default | `http://{hash}-haos-tinder:8601` from Tinder → Info |
| `elitedate_auto_send` | `false` | `true` = Discord choice also sends; `false` = fill field only |
| `tinder_auto_send` | `false` | Same for Tinder (Tinder add-on also has its own `auto_send`) |
| `dating_reply_skill` | *(empty)* | Optional **one-line** HA field. Long skill → dashboard editor (source of truth). Empty HA field does **not** wipe a skill saved on the dashboard |
| `google_accounts_enabled` | `false` | `true` + Save + Restart → noVNC on **6082** for Google Desktop OAuth |

**Network (Supervisor):** map `8000/tcp` and `6082/tcp` if you need LAN access outside ingress.

### 2) Elite Date bot — Add-on Settings

| Option | Default | Description |
|--------|---------|-------------|
| `log_level` | `info` | Logging verbosity |
| `elitedate_email` | *(empty)* | Elite Date login email |
| `elitedate_password` | *(empty)* | Elite Date password |
| `orchestrator_url` | store default | `http://{hash}-haos-orchestrator:8000` |
| `elitedate_login_url` | site login URL | Override only if the login page changes |
| `headless` | `true` | Normal background Chromium |
| `poll_enabled` | `true` | Inbox scanning. If `false`, Discord `/send` still works |
| `morning_greet_enabled` | `false` | Daily ~07:00 greets on new members |
| `morning_greet_max_profiles` | `10` | Max **sent** “Ahoj :-)” greets per run (1–50) |
| `morning_greet_max_opens` | `20` | Max **opened** profiles per run (1–100) — anti-loop |

Chrome profile persists under `/data`. After Chrome/startup fixes, a **Docker image rebuild** (not only Restart) may be required.

### 3) Tinder bot — Add-on Settings

| Option | Default | Description |
|--------|---------|-------------|
| `log_level` | `info` | Logging verbosity |
| `tinder_headless` | `false` on first install | **`false`** = noVNC login on **6080**; **`true`** = headless production |
| `orchestrator_url` | store default | `http://{hash}-haos-orchestrator:8000` |
| `poll_enabled` | `true` | Inbox polling |
| `login_wait_sec` | `600` | How long to wait for manual login when headless is false |
| `tinder_phone` | *(empty)* | Optional hint only — login is still manual OTP in VNC |
| `geolocation_enabled` | `true` | Spoof geolocation for the browser |
| `geolocation_lat` / `geolocation_lon` | optional | Coordinates if geolocation is enabled |
| `auto_send` | `false` | Bot-local auto-send (OR’d with orchestrator `tinder_auto_send`) |

**First Tinder login (do this inside the add-on, not by copying a Windows Chrome profile):**

1. Set `tinder_headless=false`, save, start/rebuild
2. Open `http://<HA_IP>:6080/vnc.html`
3. Log in with **phone + OTP** (Google/Facebook login is unreliable for automation)
4. Wait in logs for login/session saved
5. Set `tinder_headless=true` → Save → Restart (noVNC stops; session stays in `/data/chrome-profile`)

Windows/WSL Chrome profiles **do not** work on HAOS (different cookie encryption).

### 4) Gmail / Calendar via noVNC (orchestrator)

1. [Google Cloud Console](https://console.cloud.google.com/) → enable **Gmail API** + **Calendar API**
2. Create OAuth client type **Desktop app** → download JSON → place as:
   `/data/orchestrator/config/gmailSecret.json`
3. Orchestrator Settings → `google_accounts_enabled=true` → Save → **Restart**
4. Open `http://<HA_IP>:6082/vnc.html`  
   (If the screen is black: wait for the welcome Chromium page, or use **Refresh VNC** on the dashboard)
5. Dashboard → **Sign in via VNC** → complete Google consent in that Chromium  
   → tokens for **both** Gmail and Calendar
6. More mailboxes = repeat step 5  
7. Set `google_accounts_enabled=false` + Restart to stop noVNC; **accounts remain**

### 5) Discord usage details

1. Developer Portal → bot → enable **Message Content Intent**
2. Invite bot to the server; set token + optionally channel ID
3. Dating flow: new ED/Tinder message → webhook posts last message + options `1` / `2` / `4`  
   - `1` / `2` = pick a draft  
   - free text = custom reply  
   - `4` or “Navrhni ďalšie odpovede” = regenerate drafts (same thread id)
4. Only the **head** of the pending queue is `awaiting_selection` at a time (so bare `1`/`2` stay unambiguous)
5. Unread-mail / morning-summary webhooks need a valid `discord_webhook_url` (and OpenAI for summaries)

### 6) Local / `.env` development (extra knobs)

HA Settings cover production. For local runs, copy [`.env.example`](.env.example). Extra variables **not** all exposed in the HA UI:

| Variable | Notes |
|----------|--------|
| `HA_PROVIDER` | `real` / `mock` |
| `WEATHER_PROVIDER` | Must be `openweather` for live weather; add-on seed may leave `mock` until key is set |
| `DISCORD_PROVIDER` | Webhook tool needs `discord_webhook` / `webhook` — not only a URL with provider left on `mock` |
| `DISCORD_BOT_PREFIX` | e.g. `!`; empty = no prefix |
| `DISCORD_BOT_REQUIRE_MENTION` | Require @mention |
| `DISCORD_BOT_ALLOWED_USERS` | Comma-separated Discord user IDs; empty = allow all |
| `DISCORD_USERNAME` | Webhook display name |
| `GMAIL_PROVIDER` / `CALENDAR_PROVIDER` | `oauth` vs `mock` |
| `GMAIL_CREDENTIALS_JSON` / token paths | Local paths to secrets/tokens |
| `ELITEDATE_BOT_URL` / `TINDER_BOT_URL` | e.g. `http://127.0.0.1:8600` locally |
| `DATING_REPLY_SKILL` | Optional skill text |

Never commit real `.env`, OAuth JSON, or `*.pickle` token files.

### 7) Optional HA Assist conversation component

Path: `homeassistant_integration/custom_components/haos_orchestrator_conversation/`

1. Copy into HA `custom_components/`
2. Add integration → set orchestrator base URL
3. Assist text → `POST /api/voice` → TTS speaks `reply`

Not part of the Add-on Store install; not a built-in voice stack inside the orchestrator.

---

## API (orchestrator)

### Core
- `GET /` — web dashboard
- `GET /health` — health check
- `POST /api/prompt` — structured prompt processing
- `POST /api/voice` — speech-ready text reply

### Dashboard services
- `POST /api/weather`, `GET /api/weather/hourly`
- `POST /api/messages`
- `GET|POST /api/todos`, `PATCH|DELETE /api/todos/{id}`
- `GET /api/calendar/today`, `GET /api/calendar/upcoming`

### Google multi-account
- `GET /api/google/status`, `PUT /api/google/settings`
- `POST /api/google/oauth/vnc-welcome`, `GET /api/google/oauth/vnc-status`, `POST /api/google/oauth/vnc-start`
- `GET /api/google/oauth/start`, `GET /api/google/oauth/callback`
- `DELETE /api/google/accounts/{id}`, `PUT /api/google/accounts/{id}/default`

### Dating
- `GET|PUT /api/dating-skill`
- `POST /api/elitedate/incoming`, `POST /api/elitedate/morning_greet`
- `POST /api/tinder/incoming`

### Bot debug (on each bot add-on)
- Elite Date `8600`: `GET /health`, `GET /debug/inbox`, `POST /debug/poll`, `POST /debug/morning_greet`, `POST /send`
- Tinder `8601`: `GET /health`, `GET /debug/inbox`, `POST /debug/poll`, `POST /debug/push-discord`, `POST /send`

---

## Dashboard

- Clock / name days, mini weather, uptime
- Chat for testing prompts
- TODO + calendar widgets
- Tool status, Google accounts + VNC controls (**Sign in via VNC**, **Refresh VNC**)
- Multi-line **dating reply skill** editor (preferred over the one-line HA option)

---

## Project structure

```
HAOS_Orchestrator_Zoznamka/
├── config.json / repository.yaml
├── Dockerfile / run.sh
├── deploy/UPDATE_VIA_GITHUB.md
├── docs/assets/                # README images (e.g. Lightning tip QR)
├── app/                        # orchestrator FastAPI
├── elitedate_bot/              # separate add-on
├── tinder_bot/                 # separate add-on
└── homeassistant_integration/  # optional Assist agent
```

New tool: register in `app/tools/registry.py` **and** describe it in `app/router.py` system prompt.

---

## Development (local)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# fill secrets locally only

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# or: ./start.sh
```

```bash
docker build -t haos-orchestrator .
docker run -p 8000:8000 haos-orchestrator
```

---

## Troubleshooting & known issues

Issues below are ones this project has already hit in production. Use placeholders like `<HA_IP>` and `{hash}` — never paste real tokens, webhooks, or passwords into issues/docs.

### Networking / DNS between add-ons
- **Symptom:** dating status unreachable, `/send` fails, empty Discord errors after choosing `1`/`2`
- **Cause:** wrong peer URL (`local-haos-*`, bare `haos_*`, or hash from a different store URL)
- **Fix:** Add-on → **Info → Hostname** into `elitedate_bot_url` / `tinder_bot_url` / `orchestrator_url` → Save → restart all three
- Newer builds auto-fix via Supervisor; still verify if something looks stuck

### Store update does not appear
- Remove/re-add the repository, reload the store, or rebuild the add-on image
- Some Chrome fixes need **Rebuild**, not only Restart

### Second browser session kills Selenium
- **Do not** open Elite Date / Tinder in a normal browser while the bot add-on is running
- Site often drops the other session → poller stops seeing new messages
- Manual web use: **Stop** the bot add-on first, then start it again afterward

### Discord
- Bot silent → Message Content Intent, correct token, channel ID / whitelist, bot actually in the server
- Dating reply `1`/`2` does nothing → no conversation in `awaiting_selection`, or wrong channel; check orchestrator/bot logs
- Empty error after Tinder send → historically a short HTTP timeout; current builds use a longer wait (~90s) and clearer errors
- Webhook notifications missing → set `discord_webhook_url`; email summaries also need `openai_api_key`
- Option `4` regenerates drafts; keep replies in the same dating context/thread

### Google noVNC (`6082`)
- **Black screen:** welcome Chromium should open on start; use dashboard **Refresh VNC**; only click **Sign in via VNC** after VNC shows a desktop
- **Port conflict with Tinder:** Google = **6082**, Tinder = **6080** (do not point Google login at 6080)
- OAuth must be **Desktop** client JSON at `gmailSecret.json` — Web redirect flow is not the HAOS path
- Turning the VNC switch off does not delete accounts

### Tinder login / Chrome
- Must log in via add-on noVNC; do not copy Windows profiles
- Prefer phone OTP over Google/Facebook
- Chrome crash loops (`Unable to receive message from renderer`, `invalid session id`) → update to builds without `--single-process`, ensure `shm_size` is large enough, let session recovery rebuild Chrome
- After profile corruption, rebuild/restart; Tinder session lives under `/data/chrome-profile`

### Elite Date Chrome / morning greet
- Startup failures → rebuild image (libraries + profile reset / `/tmp` fallback)
- Morning greet / poll should rebuild session on Chromium death instead of dying once
- Inbox is virtualized — poller scrolls; missed messages often meant an old build without scroll
- Preview cache commits only after Discord notify succeeds (`discord: true`) so timeouts can retry without losing the event

### Weather / HA / OpenAI
- Weather always fake → missing OpenWeather key or `WEATHER_PROVIDER=mock`
- HA commands fail → invalid/expired long-lived token or wrong `ha_url`
- Everything falls through to weak chat → missing `openai_api_key` (router cannot pick tools)

### Auto-send confusion
- Orchestrator flags: `elitedate_auto_send` / `tinder_auto_send`
- Tinder also has bot-local `auto_send`
- `false` = insert text only; `true` = actually send
- Older bugs ignored orchestrator auto-send when queue had `submit=false` — use current versions

### Dating skill editor
- HA Settings field is **single-line** only
- Use the dashboard multi-line skill editor for real prompts
- Empty HA skill field must not erase a dashboard-saved skill (fixed in recent orchestrator versions)

### Health checks
```bash
# From a host that can reach the mapped ports — use your HA IP, not a documented example IP
curl http://<HA_IP>:8000/health
curl http://<HA_IP>:8600/health
curl http://<HA_IP>:8601/health
```

Expect JSON with `status` / login / `poll_enabled` fields depending on the bot.

---

## Buy me a coffee

If this project saved you time and you’d like to say thanks, a coffee tip is much appreciated — totally optional.

**PayPal** (recommended — permanent link):

[paypal.me/Kotlas6667](https://www.paypal.me/Kotlas6667)

**Bitcoin Lightning** (optional — scan QR or paste into a Lightning wallet):

<p align="center">
  <img src="docs/assets/buy-me-a-coffee-ln.png" alt="Lightning invoice QR — buy me a coffee" width="280" />
</p>

```
lnbc1p4xgh36pp5tqnyhxgtfhpkzzsz7wshmqvyj346uxc2usdkzlyqxhztyguxxarscqzyssp548l30ygf4w8sztud8y0aqd2f3wsvmaav4n2qvskr0dg644z8e9rs9q7sqqqqqqqqqqqqqqqqqqqsqqqqqysgqdqqmqz9gxqyjw5qrzjqwryaup9lh50kkranzgcdnn2fgvx390wgj5jd07rwr3vxeje0glcllayv8wtdkpfkgqqqqlgqqqqqeqqjq4dq3n49c6wguuskqdg4teq8yxrrjzpqpzzt2se32cqje3csajsrzrh95tfx6d3zp0n5e3yv6tfqk7y64ksax4yfq9dhjjrq5vp2gtaqq6vejm2
```

Lightning invoices can expire. If payment fails, use PayPal above or open a GitHub issue for a fresh invoice.

---

## License

MIT — see [LICENSE](LICENSE) if present in the repository.

---

**HAOS Orchestrator** — AI routing for smart home, Gmail/Calendar, Discord, and separate dating bots.
