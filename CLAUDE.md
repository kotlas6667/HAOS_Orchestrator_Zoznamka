# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HAOS Orchestrator is a Home Assistant Add-on / standalone Python service that lets users control a smart home and related services (Gmail, Google Calendar, weather, Discord, TODOs) via natural-language prompts (mostly Slovak). A FastAPI app receives a prompt from the web dashboard, a Discord bot, a Home Assistant Voice PE integration, or the custom HA conversation agent, uses GPT to decide which internal "tool" should handle it, runs that tool, and returns a structured result.

## Running it

```bash
# venv + deps
python -m venv .venv
.\.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# config
cp .env.example .env            # then fill in OPENAI_API_KEY, HA_TOKEN, etc.

# run (dev, auto-reload)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# or: start.bat (Windows) / start.sh (Linux, used for local/dev)
# run.sh is the Home Assistant add-on entrypoint (production)
```

No test suite exists in this repo. There's no lint/build step beyond running the app.

Docker: `docker build -t haos-orchestrator .` then `docker run -p 8000:8000 haos-orchestrator`.

## Architecture

**Request flow:** entrypoint (dashboard `/api/prompt`, Discord bot, or HA conversation agent) → `Orchestrator.handle_prompt()` (`app/orchestrator.py`) → `llm_route()` (`app/router.py`) asks GPT which tool + params to use → orchestrator looks up the tool in the registry and calls `tool.run(prompt, context=params)` → returns a `PromptResponse` (route, summary, `ToolExecution` with the raw result dict).

**Routing is prompt-engineered, not code-branched.** `app/router.py`'s `_ROUTER_SYSTEM_PROMPT` is a big instruction block listing every tool, its params, and Slovak-language disambiguation rules (e.g. distinguishing "weather in a city" from "temperature in a room" → homeassistant vs weather). When adding or changing tool behavior driven by user phrasing, this prompt is very often the file that actually needs editing, not the tool code.

**Tool pattern** (`app/tools/`):
- `base.py` defines the abstract `Tool` class: class attrs `name`, `description`, and `async def run(self, prompt, context=None) -> dict`.
- Each tool is `app/tools/<name>_tool.py`, and if it talks to an external service it delegates to a `<name>_provider.py` implementing a `Protocol` with a `Mock...Provider` and a real provider (e.g. `MockHomeAssistantProvider` / `RealHomeAssistantProvider` in `homeassistant_provider.py`). Provider selection reads from `app/config.py` settings (e.g. `HA_PROVIDER=mock|real`), so every integration degrades to a mock instead of failing when unconfigured.
- New tools are wired in exactly two places: `app/tools/registry.py` (`build_tool_registry()` list) and the router's system prompt in `app/router.py`. `Orchestrator` itself needs no changes unless the tool needs special context handling (see the `chat` tool's history injection in `orchestrator.py:32-36`).
- Tool `run()` context dicts are the routing `params` extracted by the LLM — tools should tolerate missing/empty params (e.g. `weather_tool.py` falls back to `settings.weather_default_city`).

**Settings** (`app/config.py`) is one `pydantic-settings` `Settings` object reading `.env`, exposed as the module-level `settings` singleton. Every external integration has a `<name>_provider: str = "mock"` switch plus its credentials — check this file to see what's mockable vs. what needs real credentials.

**Entrypoints beyond the dashboard:**
- `app/discord_bot.py` — full discord.py client with per-user conversation history and email pagination state, reused against the same `Orchestrator`.
- `app/discord_chat.py` — formats `PromptResponse` into human-readable Discord/speech text (`build_discord_reply`, `clean_for_speech`), used by both the Discord bot and the `/api/voice` endpoint.
- `homeassistant_integration/custom_components/haos_orchestrator_conversation/` — a Home Assistant custom component that registers this service as a HA conversation agent, calling the orchestrator's HTTP API.

**Background jobs** in `app/main.py`'s `lifespan()`: periodic unread-email polling with Discord notification (`check_emails_periodically`, dedup via `.seen_email_ids`), a daily 07:00 weather+email summary (`send_morning_summary`), and optional Discord bot startup.

**Persistence** is flat files, not a database: `todo.json` (todo_tool), `.seen_email_ids`, `token.pickle` / `token_calendar.pickle` (legacy single Google OAuth), plus multi-account `google_accounts.json` + `google_tokens/*.pickle` (combined Gmail+Calendar scopes via dashboard/HA switch `google_accounts_enabled`).

**Google multi-account + noVNC:** HA switch `google_accounts_enabled` (like Tinder’s `tinder_headless=false`) starts Xvfb/x11vnc/noVNC on port **6082** (`run.sh`). User opens `http://<IP_HA>:6082/vnc.html`, dashboard „Prihlásiť cez VNC“ launches Chromium on `DISPLAY=:99` (`app/tools/google_vnc_oauth.py`) with Desktop OAuth client — one consent yields Gmail+Calendar tokens into `google_tokens/*.pickle` + `google_accounts.json`. Turning the switch off + restart stops VNC; accounts remain. Client secrets: Desktop `gmailSecret.json` under `/data/orchestrator/config/`.

**Networking note:** `app/main.py` sets `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` at import time to a combined CA bundle (for a corporate proxy), and several `httpx`/aiohttp clients explicitly disable SSL verification (`verify=False` / `CERT_NONE`) — this is intentional for the target network environment, not an oversight.

## Elite Date integration (elitedate_bot/)

A second process — `elitedate_bot/` — automates a personal Elite Date account (a dating site with no public API) via Selenium, and hands the "which reply to send" decision to the user over Discord. It talks to the orchestrator over localhost HTTP in both directions (no polling of the orchestrator needed):

- **Bot → orchestrator:** `elitedate_bot/poller.py` runs a loop (randomized 90-180s interval) that calls `EliteDateClient.check_new_messages()` (Selenium, `elitedate_bot/elitedate_client.py`) and POSTs any new message to the orchestrator's `POST /api/elitedate/incoming` (`app/main.py`). Toggle via HA option `poll_enabled` / `POLL_ENABLED` (default true) — same as Tinder; when false, inbox is not scanned but Discord `/send` still works.
- **New-message detection (ED):** compares inbox-row preview per conversation against `elitedate_bot/.conversation_previews.json` (persisted under `/data`); opens a chat only when preview changes and last bubble is from them. Seeding (empty cache / first sighting) never notifies Discord. Preview for a pending candidate is committed only after Discord succeeds (`commit_preview`); `/api/elitedate/incoming` returns `discord: true/false` so the poller can retry on webhook/timeout failure.
- **Morning greet (ED, optional):** when `MORNING_GREET_ENABLED=true` / HA `morning_greet_enabled`, daily at 07:00 `morning_greet.py` opens `/ucet/novi-clenove`, opens filter via `button.btn-partner-filter` (only if `#search_filter_form_ageFrom` not visible), sets `#search_filter_form_ageFrom/To` + `#search_filter_form_heightTo` + noUiSlider distance, submits `#search_filter_form_submit`, collects `a.c-card` across pages via **Ďalšie** (`listFrom=`), walks until *sent* `morning_greet_max_profiles` or *opened* `morning_greet_max_opens` (default 20), opens `a.send-message-btn`, sends `Ahoj :-)` only on empty chats, then **always** POSTs summary to orchestrator `POST /api/elitedate/morning_greet` → Discord (success, zero sent, or failure). Processed IDs in `.morning_greeted.json`. Debug: `POST /debug/morning_greet`.
- **Orchestrator side:** `app/tools/elitedate_dispatch.handle_incoming()` generates two alternative AI reply drafts via GPT (`app/tools/elitedate_reply_provider.py`, model `dating_reply_model` default `gpt-4o` — separate from routing `openai_model` / `gpt-4o-mini`), using shared skill from dashboard textarea / sidecar `/data/orchestrator/config/dating_reply_skill.md` (`GET/PUT /api/dating-skill`; HA `dating_reply_skill` is single-line only and optional), else bundled `elitedate_reply_skill.md` / `tinder_reply_skill.md`. Same skill applies to Tinder. Drafts go to a FIFO queue on disk (`elitedate_state.json`, via `app/tools/elitedate_state.py` — only the head of the queue is `awaiting_selection` at any time, to keep a bare "1"/"2" Discord reply unambiguous), then Discord gets the full last message + options. Option **4** / „Navrhni ďalšie odpovede“ regenerates fresh drafts and re-posts the prompt (same thread ID). Auto-send uses orch `elitedate_auto_send` / `tinder_auto_send` (OR bot-local `auto_send` on Tinder).
- **Orchestrator → bot:** When the user replies "1", "2", "4", or free text in Discord, `app/discord_bot.py`'s `on_message` intercepts it **before** LLM routing (calling `elitedate_dispatch.handle_selection()`) whenever a conversation is `awaiting_selection` — this mirrors the existing email-navigation intercept (`_is_navigation_request`) already in that file. On a valid selection, the orchestrator POSTs the chosen text to the bot's own local FastAPI server (`elitedate_bot/server.py`, `POST /send`), which drives Selenium to actually send it.
- **Selenium DOM selectors are placeholders.** `elitedate_client.py`'s `login()`, `check_new_messages()`, and `send_reply()` need real CSS selectors filled in from Elite Date's actual DOM (inspect via browser DevTools) — Elite Date's markup isn't something to guess at.
- **Session recovery:** `elitedate_bot/session.py` rebuilds Chrome and re-logs in on `invalid session id` / dead browser; poller and `/send` use `run_with_recovery()`.
- The Selenium `webdriver.Chrome` instance is not safe for concurrent use — both the poll loop and incoming `/send` calls acquire `elitedate_bot/shared_state.driver_lock` before touching it, and blocking Selenium calls are run via `asyncio.to_thread`.
- **Packaging:** Elite Date beží ako **samostatný HA add-on** (`elitedate_bot/`, slug `haos_elitedate`, DNS `local-haos-elitedate:8600`). Orchestrátor ho volá cez `ELITEDATE_BOT_URL` (Nastavenia / `.env`). `run.sh` pri štarte migruje staré hostname `haos_*` → `local-haos-*`. Hlavný orchestrátor už bundlovaný Chromium nespúšťa. Inštalácia/aktualizácia: **iba GitHub Obchod** (`deploy/UPDATE_VIA_GITHUB.md`) — lokálny `/addons` sync nie je podporovaný.
- Elite Date's ToS almost certainly prohibits automated/scripted use of the account — this is a known, accepted risk (account ban), not a technical concern to engineer around.

## Tinder integration (tinder_bot/)

Mirrors `elitedate_bot/` — a separate Selenium process on Tinder web (`tinder.com/app/...`), Discord handoff for reply selection:

- **Bot → orchestrator:** `tinder_bot/poller.py` polls `TinderClient.check_new_messages()` and POSTs to `POST /api/tinder/incoming`. First poll runs immediately on startup; then 90–180s randomized interval.
- **Orchestrator side:** `app/tools/tinder_dispatch.py` + `tinder_reply_provider.py` + `tinder_state.json` (same FIFO queue pattern as Elite Date).
- **Orchestrator → bot:** Discord `on_message` intercepts "1"/"2"/"4"/„Navrhni ďalšie odpovede“/free text when the referenced prompt contains "Tinder" (or bare regenerate when a Tinder entry is awaiting) → `tinder_dispatch.handle_selection()` → `POST` to `tinder_bot` `/send` (or regenerate + re-post prompt).
- **Login:** Tinder uses phone OTP / Google / Facebook — not automatable. Set `TINDER_USER_DATA_DIR`, run once with `TINDER_HEADLESS=false`, log in manually; session persists in Chrome profile.
- **Session recovery:** Both bots rebuild the Selenium session automatically on `invalid session id` / dead Chrome (`tinder_bot/session.py`, `elitedate_bot/session.py`); poller and `/send` use `run_with_recovery()`.
- **UI quirk:** Tinder opens on **Zhody** (matches grid) by default. `TinderClient._navigate_to_inbox()` always clicks the **Správy** tab first. Only list rows with a message preview count as conversations — Zhody match tiles (`a[href*='/app/messages/']` without preview) are ignored.
- **New-message detection:** compares preview text per conversation against `tinder_bot/.conversation_previews.json`; opens a chat only when preview changes and last bubble is from them. Seeding (`previous_preview is None`) never opens chats. Same retry-safe preview commit as Elite Date (`commit_preview` after `discord: true`).
- **Debug endpoints:** `GET /health`, `GET /debug/inbox`, `POST /debug/poll` on port 8601 (default).
- **Packaging:** samostatný HA add-on (`tinder_bot/`, slug `haos_tinder`, DNS `local-haos-tinder:8601`). Orchestrátor → `TINDER_BOT_URL`. Rovnaká DNS migrácia `haos_*` → `local-haos-*` pri štarte. See `tinder_bot/README.md`.
- Status v Discorde: tool `dating_status` (router) — otázky typu „správy na ed?“ / „ide Tinder?“ idú sem, nie do Gmailu.

## Badoo integration (badoo_bot/)

Third dating bot alongside `elitedate_bot/` and `tinder_bot/` — does **not** replace either. Mirrors `tinder_bot/` (Selenium + Chrome profile + noVNC + Discord handoff).

- **Login:** `badoo_headless=false` → noVNC **6081** → Google → `Login detected` → `badoo_headless=true`. Profile: `/data/chrome-profile`.
- **Bot → orchestrator:** `poller.py` → `POST /api/badoo/incoming` (preview cache + `commit_preview` after Discord OK). Default poll on.
- **Orchestrator:** `badoo_dispatch` + `badoo_state.json` + `badoo_reply_provider` (shared dating skill). Discord title contains **Badoo**.
- **Orchestrator → bot:** Discord `1`/`2`/`4`/free text → `badoo_dispatch.handle_selection()` → `POST` `{badoo_bot_url}/send`.
- **API:** port **8602** — `/health`, `/debug/page`, `/debug/inbox`, `/debug/poll`, `/send`.
- **Packaging:** slug `haos_badoo`. See `badoo_bot/HAOS_LOGIN.md`, `badoo_bot/README.md`.
- **Port map:** Elite Date `8600` · Tinder `8601`/`6080` · Badoo `8602`/`6081` · Google orch `6082`.

## Notes for future edits to this file

Keep this file updated as the project evolves — new tools, changed routing rules, new entrypoints, or architectural shifts should be reflected here so future sessions don't need to re-explore the whole codebase.
