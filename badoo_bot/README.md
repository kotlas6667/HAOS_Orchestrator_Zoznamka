# HAOS Badoo Bot

Samostatný Selenium add-on pre [badoo.com](https://badoo.com). Tretia zoznamka popri **Elite Date** (`8600`) a **Tinder** (`8601`/`6080`) — rovnaký model: noVNC login, inbox poll, Discord návrhy odpovedí.

## Stav

- ✅ Login (noVNC / Google / profile reuse)
- ✅ Inbox polling → orchestrátor → Discord
- ✅ `/send` po výbere `1`/`2`/`3`/`4` v Discorde
- ✅ Audio správy → prepis do textu v orchestrátore → Discord návrhy

## Prvé prihlásenie

| | Prvý štart | Potom |
|--|------------|-------|
| `badoo_headless` | **false** (noVNC) | **true** |
| Port noVNC | **6081** | vypnutý |
| API | **8602** | **8602** |

Súbežne s Elite Date (`8600`) a Tinderom (`8601` / noVNC `6080`) — Badoo ich nenahrádza.

1. `badoo_headless=false` → Uložiť → Štart  
2. Otvor `http://<IP_HA>:6081/vnc.html` (cez Tailscale: `http://<TAILSCALE_IP>:6081/vnc.html`)  
3. Prihlás sa **cez Google**  
4. Po `Login detected` v logu: `badoo_headless=true` → Reštart  
5. Zapni `poll_enabled=true`. Flow: login → encounters → cookies/rate dismiss → tab **Chats** (`data-qa=connections`) → list `csms-connections-list` → preview cache ako Tinder.

Detail: [HAOS_LOGIN.md](HAOS_LOGIN.md)

## Env / HA options

| HA option | Env | Default |
|-----------|-----|---------|
| `badoo_headless` | `BADOO_HEADLESS` | true (po prvom logine) |
| `orchestrator_url` | `ORCHESTRATOR_URL` | `{hash}-haos-orchestrator:8000` |
| `poll_enabled` | `BADOO_POLL_ENABLED` | **true** |
| `login_wait_sec` | `BADOO_LOGIN_WAIT_SEC` | 600 |
| `auto_send` | `BADOO_AUTO_SEND` | false |
| (fixed) | `BADOO_USER_DATA_DIR` | `/data/chrome-profile` |
| | `BADOO_BOT_PORT` | 8602 |
| orchestrator AI | `DATING_REPLY_PROVIDER` | `openai` |
| orchestrator AI | `GEMINI_API_KEY` | empty |
| orchestrator AI | `DATING_REPLY_GEMINI_MODEL` | `gemini-2.5-flash` |

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | `logged_in`, `session_alive` |
| GET | `/debug/page` | Current URL / body |
| GET | `/debug/inbox` | Inbox snapshot |
| POST | `/debug/poll` | One inbox check |
| POST | `/debug/push-discord` | Manual → orchestrator |
| POST | `/send` | Orchestrator reply insert/send |

## Discord ovládanie návrhov

- `1` až `4` — vyber AI draft
- `5 tvoj text` — vlastná odpoveď
- `6` — nové návrhy cez default provider
- `6 gemini` — nové návrhy cez Gemini
- `6 gpt` — nové návrhy cez OpenAI
