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

**Persistence** is flat files, not a database: `todo.json` (todo_tool), `.seen_email_ids`, `token.pickle` / `token_calendar.pickle` (Google OAuth tokens from `google-auth-oauthlib`).

**Networking note:** `app/main.py` sets `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` at import time to a combined CA bundle (for a corporate proxy), and several `httpx`/aiohttp clients explicitly disable SSL verification (`verify=False` / `CERT_NONE`) — this is intentional for the target network environment, not an oversight.

## Elite Date integration (elitedate_bot/)

A second process — `elitedate_bot/` — automates a personal Elite Date account (a dating site with no public API) via Selenium, and hands the "which reply to send" decision to the user over Discord. It talks to the orchestrator over localhost HTTP in both directions (no polling of the orchestrator needed):

- **Bot → orchestrator:** `elitedate_bot/poller.py` runs a loop (randomized 90-180s interval) that calls `EliteDateClient.check_new_messages()` (Selenium, `elitedate_bot/elitedate_client.py`) and POSTs any new message to the orchestrator's `POST /api/elitedate/incoming` (`app/main.py`).
- **Orchestrator side:** `app/tools/elitedate_dispatch.handle_incoming()` generates two alternative AI reply drafts via GPT (`app/tools/elitedate_reply_provider.py`), stores them in a FIFO queue on disk (`elitedate_state.json`, via `app/tools/elitedate_state.py` — only the head of the queue is `awaiting_selection` at any time, to keep a bare "1"/"2" Discord reply unambiguous), and posts the two options to Discord.
- **Orchestrator → bot:** When the user replies "1", "2", or free text in Discord, `app/discord_bot.py`'s `on_message` intercepts it **before** LLM routing (calling `elitedate_dispatch.handle_selection()`) whenever a conversation is `awaiting_selection` — this mirrors the existing email-navigation intercept (`_is_navigation_request`) already in that file. On a valid selection, the orchestrator POSTs the chosen text to the bot's own local FastAPI server (`elitedate_bot/server.py`, `POST /send`), which drives Selenium to actually send it.
- **Selenium DOM selectors are placeholders.** `elitedate_client.py`'s `login()`, `check_new_messages()`, and `send_reply()` need real CSS selectors filled in from Elite Date's actual DOM (inspect via browser DevTools) — Elite Date's markup isn't something to guess at.
- The Selenium `webdriver.Chrome` instance is not safe for concurrent use — both the poll loop and incoming `/send` calls acquire `elitedate_bot/shared_state.driver_lock` before touching it, and blocking Selenium calls are run via `asyncio.to_thread`.
- **Packaging:** the main `Dockerfile`/`run.sh` (HAOS add-on) bundles `elitedate_bot/` and installs `chromium` + `chromium-driver` alongside the orchestrator, launching `python -m elitedate_bot.main` as a background process before the orchestrator's `uvicorn` (set `ELITEDATE_BOT_ENABLED=false` in `.env` to skip it). `run.sh` force-exports `BROWSER_BINARY=/usr/bin/chromium` / `WEBDRIVER_PATH=/usr/bin/chromedriver` so a Windows-dev `.env` (desktop Chrome path) never leaks into the container — real env vars win over `.env` values in pydantic-settings. `elitedate_bot/elitedate-bot.service.example` is kept for running it as a standalone systemd service outside HAOS instead (e.g. directly on the Pi) — inside the shared add-on container a Selenium crash currently has no per-process supervision/restart, unlike that standalone setup.
- Elite Date's ToS almost certainly prohibits automated/scripted use of the account — this is a known, accepted risk (account ban), not a technical concern to engineer around.

## Notes for future edits to this file

Keep this file updated as the project evolves — new tools, changed routing rules, new entrypoints, or architectural shifts should be reflected here so future sessions don't need to re-explore the whole codebase.
