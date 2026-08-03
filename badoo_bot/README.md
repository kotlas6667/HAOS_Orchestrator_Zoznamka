# HAOS Badoo Bot

Samostatný Selenium add-on pre [badoo.com](https://badoo.com). Tretia zoznamka popri **Elite Date** (`8600`) a **Tinder** (`8601`/`6080`) — rovnaký model: prvé prihlásenie cez **noVNC + Google**, session v Chrome profile.

## Stav

- ✅ Login (noVNC / Google / profile reuse)
- ⏳ Inbox polling + Discord handoff (ďalší krok)
- ⏳ `/send` odpovede

## Prvé prihlásenie

| | Prvý štart | Potom |
|--|------------|-------|
| `badoo_headless` | **false** (noVNC) | **true** |
| Port noVNC | **6081** | vypnutý |
| API | **8602** | **8602** |

Súbežne s Elite Date (`8600`) a Tinderom (`8601` / noVNC `6080`) — Badoo ich nenahrádza.

1. `badoo_headless=false` → Uložiť → Štart  
2. Otvor `http://<IP_HA>:6081/vnc.html`  
3. Prihlás sa **cez Google**  
4. Po `Login detected` v logu: `badoo_headless=true` → Reštart  

Detail: [HAOS_LOGIN.md](HAOS_LOGIN.md)

## Env / HA options

| HA option | Env | Default |
|-----------|-----|---------|
| `badoo_headless` | `BADOO_HEADLESS` | false (first install) |
| `orchestrator_url` | `ORCHESTRATOR_URL` | `{hash}-haos-orchestrator:8000` |
| `poll_enabled` | `BADOO_POLL_ENABLED` | **false** (zatiaľ) |
| `login_wait_sec` | `BADOO_LOGIN_WAIT_SEC` | 600 |
| (fixed) | `BADOO_USER_DATA_DIR` | `/data/chrome-profile` |
| | `BADOO_BOT_PORT` | 8602 |

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | `logged_in`, `session_alive` |
| GET | `/debug/page` | Current URL / body snippet |
| POST | `/send` | Placeholder (zatiaľ error) |
