from pathlib import Path
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.discord_chat import build_discord_reply, clean_for_speech
from app.orchestrator import Orchestrator
from app.schemas import MessageRequest, MessageResponse, PromptRequest, PromptResponse, WeatherRequest, WeatherResponse
from app.tools.messages_tool import MessagesTool
from app.tools.weather_tool import WeatherTool
from app.tools.gmail_tool import GmailTool
import asyncio
from contextlib import asynccontextmanager

import certifi
from pathlib import Path as _Path

# Use combined CA bundle (Zscaler proxy + Mozilla CAs), fallback to certifi
_PROJECT_ROOT = _Path(__file__).resolve().parent.parent
_COMBINED_CA = _PROJECT_ROOT / "ca-bundle-combined.pem"
_ca_bundle = str(_COMBINED_CA) if _COMBINED_CA.exists() else certifi.where()
os.environ["SSL_CERT_FILE"] = _ca_bundle
os.environ["REQUESTS_CA_BUNDLE"] = _ca_bundle

orchestrator = Orchestrator()
weather_tool = WeatherTool()
messages_tool = MessagesTool()
gmail_tool = GmailTool()

# Track already-processed email IDs to avoid re-sending old emails to Discord
_SEEN_IDS_FILE = _Path(__file__).resolve().parent.parent / ".seen_email_ids"


def _load_seen_ids() -> set[str]:
    """Load previously seen email IDs from disk."""
    if _SEEN_IDS_FILE.exists():
        return set(_SEEN_IDS_FILE.read_text(encoding="utf-8").splitlines())
    return set()


def _save_seen_ids(ids: set[str]) -> None:
    """Persist seen email IDs to disk."""
    _SEEN_IDS_FILE.write_text("\n".join(ids), encoding="utf-8")


_seen_email_ids: set[str] = _load_seen_ids()

_DISCORD_BOT_LOCK_FILE = _Path(__file__).resolve().parent.parent / ".discord_bot.lock"


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_discord_bot_lock() -> bool:
    """Ensure only one process in the workspace starts the Discord bot."""
    if _DISCORD_BOT_LOCK_FILE.exists():
        try:
            data = json.loads(_DISCORD_BOT_LOCK_FILE.read_text(encoding="utf-8"))
            owner_pid = int(data.get("pid") or 0)
        except Exception:
            owner_pid = 0

        if owner_pid and _is_process_alive(owner_pid):
            print(f"[INFO] Discord bot lock active (pid={owner_pid}); skipping duplicate bot startup.")
            return False

        try:
            _DISCORD_BOT_LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    payload = {"pid": os.getpid()}
    _DISCORD_BOT_LOCK_FILE.write_text(json.dumps(payload), encoding="utf-8")
    return True


def _release_discord_bot_lock() -> None:
    try:
        if _DISCORD_BOT_LOCK_FILE.exists():
            data = json.loads(_DISCORD_BOT_LOCK_FILE.read_text(encoding="utf-8"))
            owner_pid = int(data.get("pid") or 0)
            if owner_pid == os.getpid():
                _DISCORD_BOT_LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _gmail_background_enabled() -> bool:
    from app.tools import google_accounts

    # Background poll as soon as at least one account has a token
    if google_accounts.list_accounts():
        return True
    if settings.gmail_provider != "oauth":
        return False
    credentials = settings.gmail_credentials_json
    if not credentials:
        return google_accounts.find_credentials_path() is not None
    return Path(credentials).exists()


async def check_emails_periodically():
    """Check for new emails every minute across all connected Google accounts."""
    global _seen_email_ids
    while True:
        try:
            providers = gmail_tool.all_real_providers()
            if not providers and hasattr(gmail_tool, "provider"):
                providers = [gmail_tool.provider]
            new_ids_added = False
            for provider in providers:
                try:
                    response = await provider.get_emails(query="is:unread", max_results=10)
                except Exception as e:
                    print(f"Error checking emails ({getattr(provider, 'account_email', '?')}): {e}")
                    continue
                emails = response.get("emails", [])
                account = getattr(provider, "account_email", None) or getattr(provider, "_account_email", None)
                for email in emails:
                    msg_id = email.get("message_id")
                    if not msg_id or msg_id in _seen_email_ids:
                        continue
                    _seen_email_ids.add(msg_id)
                    new_ids_added = True
                    if account:
                        email.setdefault("account", account)
                    try:
                        await gmail_tool.discord.send_email_summary(email)
                    except Exception as e:
                        print(f"Error sending Discord notification: {e}")
            if new_ids_added:
                _save_seen_ids(_seen_email_ids)
        except Exception as e:
            print(f"Error checking emails: {e}")
        await asyncio.sleep(60)  # 1 minúta


async def send_morning_summary():
    """Send daily morning summary at 7:00 — weather + email count."""
    from app.tools.discord_notifier import DiscordNotifier
    notifier = DiscordNotifier()

    while True:
        now = asyncio.get_event_loop().time()
        from datetime import datetime, timedelta
        current = datetime.now()
        # Calculate seconds until next 7:00
        target = current.replace(hour=7, minute=0, second=0, microsecond=0)
        if current >= target:
            target += timedelta(days=1)
        wait_seconds = (target - current).total_seconds()
        await asyncio.sleep(wait_seconds)

        try:
            # Weather
            weather_result = await weather_tool.run("počasie", context={"city": settings.weather_default_city})
            city = weather_result.get("city", settings.weather_default_city)
            temp = weather_result.get("temperature_c", "?")
            forecast = weather_result.get("forecast", "?")

            # Email count across all Google accounts
            providers = gmail_tool.all_real_providers()
            if not providers:
                providers = [gmail_tool.provider]
            all_emails: list[dict] = []
            for provider in providers:
                try:
                    email_response = await provider.get_emails(query="is:unread", max_results=50)
                    for mail in email_response.get("emails", []):
                        acc = getattr(provider, "account_email", None) or getattr(provider, "_account_email", None)
                        if acc:
                            mail.setdefault("account", acc)
                        all_emails.append(mail)
                except Exception as e:
                    print(f"Morning summary email fetch failed: {e}")
            email_count = len(all_emails)

            # Build summary
            lines = [
                "☀️ **Dobré ráno!**",
                f"",
                f"🌡️ **Počasie v {city}:** {temp}°C, {forecast}",
                f"📧 **Neprečítané emaily:** {email_count}",
            ]

            if email_count > 0:
                lines.append("")
                for mail in all_emails[:3]:
                    sender = mail.get("from", "?").split("<")[0].strip().strip('"')
                    subject = mail.get("subject", "(bez predmetu)")
                    acc = mail.get("account")
                    suffix = f" ({acc})" if acc else ""
                    lines.append(f"  • **{subject}** od {sender}{suffix}")

            await notifier.send_message("\n".join(lines))
            print(f"[OK] Morning summary sent at {datetime.now().strftime('%H:%M')}")
        except Exception as e:
            print(f"Error sending morning summary: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks when FastAPI starts."""
    from app.tools import google_accounts

    # Sync HA/env switch into google_accounts.json + migrate legacy token.pickle
    if settings.google_accounts_enabled:
        google_accounts.set_enabled(True)
    google_accounts.migrate_legacy_single_account()
    gmail_tool.reload_providers()
    cal_tool = orchestrator.tools.get("calendar")
    if cal_tool is not None and hasattr(cal_tool, "reload_providers"):
        cal_tool.reload_providers()

    if _gmail_background_enabled():
        asyncio.create_task(check_emails_periodically())
        asyncio.create_task(send_morning_summary())
    else:
        print("[INFO] Gmail background tasks disabled (Google účty vypnuté alebo bez tokenu).")

    # Probe dating bots once at startup — wrong DNS shows up immediately in logs + Discord.
    async def _probe_dating_bots() -> None:
        import httpx

        from addon_dns import default_url, is_broken_url

        print(
            f"[dating] configured URLs: elitedate={settings.elitedate_bot_url} "
            f"tinder={settings.tinder_bot_url}"
        )
        targets = (
            ("Elite Date", settings.elitedate_bot_url, "haos_elitedate", 8600),
            ("Tinder", settings.tinder_bot_url, "haos_tinder", 8601),
        )
        failures: list[str] = []
        for label, base, slug, port in targets:
            url = f"{base.rstrip('/')}/health"
            hint = default_url(slug, port)
            if is_broken_url(base):
                msg = (
                    f"[dating] {label} URL je rozbitá: {base} "
                    f"— nastav Nastavenia na {hint} a reštartuj"
                )
                print(msg)
                failures.append(f"❌ **{label}:** zlá URL `{base}` → použi `{hint}`")
                continue
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    body = r.json() if r.content else {}
                print(
                    f"[dating] {label} OK @ {base} "
                    f"(logged_in={body.get('logged_in')} session_alive={body.get('session_alive')})"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[dating] {label} NEDOSTUPNÝ @ {base} — {exc}")
                failures.append(
                    f"❌ **{label}:** nedostupný `{base}` — {exc}. "
                    f"Skontroluj, že add-on beží a URL je `{hint}`."
                )

        if failures and settings.discord_webhook_url:
            try:
                from app.tools.discord_notifier import DiscordNotifier

                await DiscordNotifier().send_message(
                    "**Dating boty — problém pri štarte orchestratora**\n"
                    + "\n".join(failures)
                    + "\n\nBez správnej DNS URL nepríde notifikácia o novej správe z ED/Tinder."
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[dating] Discord alert failed: {exc}")

    asyncio.create_task(_probe_dating_bots())

    # Start Discord bot if enabled
    discord_task = None
    if settings.discord_bot_enabled and settings.discord_bot_token and _acquire_discord_bot_lock():
        import logging
        logging.basicConfig(level=logging.INFO)

        from app.discord_bot import OrchestratorDiscordClient

        client = OrchestratorDiscordClient(
            settings=settings, orchestrator=orchestrator, ssl_context=None
        )
        discord_task = asyncio.create_task(client.start(settings.discord_bot_token))
        print("Discord bot starting...")

    yield

    if discord_task and not discord_task.done():
        discord_task.cancel()
    _release_discord_bot_lock()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    ha_active = (
        getattr(settings, "ha_provider", "mock") == "real"
        and bool(getattr(settings, "ha_token", None))
    )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "weather_city": settings.weather_default_city,
            "ha_provider": "real" if ha_active else "mock",
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.post("/api/prompt", response_model=PromptResponse)
async def process_prompt(payload: PromptRequest) -> PromptResponse:
    return await orchestrator.handle_prompt(payload.prompt, history=payload.history or None)


@app.post("/api/voice")
async def process_voice(payload: PromptRequest) -> dict:
    """Voice-assistant endpoint (e.g. Home Assistant Voice PE) — returns a single
    speech-ready reply string instead of the raw structured tool result."""
    response = await orchestrator.handle_prompt(payload.prompt, history=payload.history or None)
    reply = clean_for_speech(build_discord_reply(payload.prompt, response))
    return {"reply": reply, "route": response.route}


@app.post("/api/weather", response_model=WeatherResponse)
async def process_weather(payload: WeatherRequest) -> WeatherResponse:
    result = await weather_tool.run(f"weather in {payload.city}", context={"city": payload.city})
    return WeatherResponse(result=result)


@app.get("/api/weather/hourly")
async def get_hourly_forecast(city: str = ""):
    """Return hourly forecast (next 12 hours) for the dashboard."""
    target_city = city.strip() or settings.weather_default_city
    result = await weather_tool.run(
        "hourly forecast",
        context={"action": "hourly", "city": target_city},
    )
    return result


@app.post("/api/messages", response_model=MessageResponse)
async def process_messages(payload: MessageRequest) -> MessageResponse:
    result = await messages_tool.run(
        payload.message,
        context={"destination": payload.destination, "message": payload.message},
    )
    return MessageResponse(result=result)


# TODO API endpoints
from app.tools.todo_tool import _load_todos, _save_todos


@app.get("/api/todos")
async def get_todos():
    todos = _load_todos()
    return {"todos": todos}


@app.post("/api/todos")
async def add_todo(request: Request):
    data = await request.json()
    task = data.get("task", "").strip()
    if not task:
        return {"status": "error", "error": "Prázdna úloha"}
    from datetime import datetime
    todos = _load_todos()
    new_task = {
        "id": (max(t["id"] for t in todos) + 1) if todos else 1,
        "task": task,
        "done": False,
        "created": datetime.now().isoformat(timespec="minutes"),
    }
    todos.append(new_task)
    _save_todos(todos)
    return {"status": "success", "task": new_task}


@app.patch("/api/todos/{task_id}")
async def toggle_todo(task_id: int):
    todos = _load_todos()
    for t in todos:
        if t["id"] == task_id:
            t["done"] = not t["done"]
            _save_todos(todos)
            return {"status": "success", "task": t}
    return {"status": "error", "error": "Nenájdené"}


@app.delete("/api/todos/{task_id}")
async def delete_todo(task_id: int):
    todos = _load_todos()
    todos = [t for t in todos if t["id"] != task_id]
    _save_todos(todos)
    return {"status": "success"}


# Calendar API endpoint
try:
    from app.tools.calendar_tool import CalendarTool
    _calendar_tool = CalendarTool()
except Exception as e:
    print(f"Warning: Calendar tool init failed: {e}")
    _calendar_tool = None


@app.get("/api/calendar/today")
async def get_today_events():
    if _calendar_tool is None:
        return {"status": "error", "events": [], "error": "Calendar tool not initialized"}
    result = await _calendar_tool.run("today", context={"action": "today"})
    return result


@app.get("/api/calendar/upcoming")
async def get_upcoming_events():
    if _calendar_tool is None:
        return {"status": "error", "events": [], "error": "Calendar tool not initialized"}
    result = await _calendar_tool.run("upcoming", context={"action": "upcoming", "days": 3})
    return result


# Shared dating reply skill (dashboard textarea — HA str? is single-line)
from app.tools.dating_skill import read_user_skill_file, save_user_skill
from app.tools import google_accounts


def _reload_google_tools() -> None:
    """Refresh Gmail/Calendar providers after enable/OAuth/remove."""
    gmail_tool.reload_providers()
    orch_gmail = orchestrator.tools.get("gmail")
    if orch_gmail is not None and hasattr(orch_gmail, "reload_providers"):
        orch_gmail.reload_providers()
    orch_cal = orchestrator.tools.get("calendar")
    if orch_cal is not None and hasattr(orch_cal, "reload_providers"):
        orch_cal.reload_providers()
    cal = globals().get("_calendar_tool")
    if cal is not None and hasattr(cal, "reload_providers"):
        cal.reload_providers()


def _request_public_base(request: Request) -> str:
    """Base URL for OAuth redirect (respects HA ingress / reverse proxy headers)."""
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    forwarded_proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    # Home Assistant ingress often sets X-Ingress-Path
    ingress = (request.headers.get("x-ingress-path") or "").rstrip("/")
    if forwarded_host:
        base = f"{forwarded_proto}://{forwarded_host}{ingress}"
    else:
        base = str(request.base_url).rstrip("/")
    return base.rstrip("/")


@app.get("/api/google/status")
async def google_status():
    """Dashboard: Google multi-account status (enabled switch, accounts, credentials)."""
    return google_accounts.status_payload()


@app.put("/api/google/settings")
async def google_settings(request: Request):
    """Zapni/vypni Google VNC režim. Zapnuté + HA reštart = noVNC :6080."""
    data = await request.json()
    if "enabled" not in data:
        return {"status": "error", "error": "enabled is required"}
    enabled = bool(data.get("enabled"))
    state = google_accounts.set_enabled(enabled)
    _reload_google_tools()
    payload = google_accounts.status_payload()
    payload["message"] = (
        "Google VNC zapnuté — v HA Nastaveniach Uložiť + Reštart, potom "
        "http://<IP_HA>:6080/vnc.html a „Prihlásiť cez VNC“."
        if enabled
        else "Google VNC vypnuté. Po reštarte noVNC zmizne; už uložené účty ostanú."
    )
    payload["state_enabled"] = state.get("enabled")
    return payload


@app.get("/api/google/oauth/vnc-status")
async def google_oauth_vnc_status():
    """Stav bežiaceho VNC Google prihlásenia."""
    from app.tools.google_vnc_oauth import vnc_login_status

    return vnc_login_status()


@app.post("/api/google/oauth/vnc-start")
async def google_oauth_vnc_start(request: Request):
    """Spustí Google login v Chromiu na noVNC displeji (switch musí byť zapnutý + reštart)."""
    from app.tools.google_vnc_oauth import start_vnc_oauth_background

    label = ""
    try:
        data = await request.json()
        if isinstance(data, dict):
            label = str(data.get("label") or "")
    except Exception:
        pass
    result = start_vnc_oauth_background(label=label)
    if result.get("status") == "started":
        # Po úspešnom logine thread uloží účet — poll status a reload tools cez callback
        asyncio.create_task(_watch_vnc_oauth_and_reload())
    return result


async def _watch_vnc_oauth_and_reload() -> None:
    """Po dokončení VNC OAuth obnov providery."""
    from app.tools.google_vnc_oauth import vnc_login_status

    for _ in range(200):  # ~10 min @ 3s
        await asyncio.sleep(3)
        st = vnc_login_status()
        if st.get("running"):
            continue
        if st.get("email"):
            _reload_google_tools()
            print(f"[google-vnc] providers reloaded after {st.get('email')}")
        break


@app.get("/api/google/oauth/start")
async def google_oauth_start(request: Request, label: str = ""):
    """Predvolene spustí VNC login; ?mode=web = starý browser redirect (ingress)."""
    mode = (request.query_params.get("mode") or "vnc").strip().lower()
    if mode != "web":
        from app.tools.google_vnc_oauth import start_vnc_oauth_background

        result = start_vnc_oauth_background(label=label)
        if result.get("status") == "started":
            asyncio.create_task(_watch_vnc_oauth_and_reload())
        # JSON always for VNC (dashboard fetch); redirect would be useless
        return result

    try:
        base = _request_public_base(request)
        redirect_uri = google_accounts.build_callback_uri(base)
        started = google_accounts.start_oauth(redirect_uri=redirect_uri, label=label)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"OAuth start zlyhal: {e}"}

    if request.query_params.get("redirect", "1") not in ("0", "false", "no"):
        return RedirectResponse(url=started["auth_url"], status_code=302)
    return {"status": "success", **started}


@app.get("/api/google/oauth/callback")
async def google_oauth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    """OAuth redirect URI — uloží token (Gmail + Kalendár) a pridá účet."""
    if error:
        return HTMLResponse(google_accounts.oauth_error_html(error), status_code=400)
    if not code or not state:
        return HTMLResponse(
            google_accounts.oauth_error_html("Chýba authorization code alebo state."),
            status_code=400,
        )
    try:
        entry = google_accounts.complete_oauth(state=state, code=code)
        _reload_google_tools()
        return HTMLResponse(google_accounts.oauth_success_html(entry.get("email", "?")))
    except Exception as e:
        return HTMLResponse(google_accounts.oauth_error_html(str(e)), status_code=400)


@app.delete("/api/google/accounts/{account_id}")
async def google_delete_account(account_id: str):
    try:
        google_accounts.remove_account(account_id)
        _reload_google_tools()
        return google_accounts.status_payload()
    except ValueError as e:
        return {"status": "error", "error": str(e)}


@app.put("/api/google/accounts/{account_id}/default")
async def google_set_default_account(account_id: str):
    try:
        google_accounts.set_default_account(account_id)
        _reload_google_tools()
        return google_accounts.status_payload()
    except ValueError as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/dating-skill")
async def get_dating_skill():
    """Multiline skill for ED + Tinder AI drafts (source of truth: sidecar .md)."""
    content, path = read_user_skill_file()
    return {
        "status": "success",
        "content": content,
        "path": path,
        "chars": len(content),
    }


@app.put("/api/dating-skill")
async def put_dating_skill(request: Request):
    """Save multiline skill from dashboard; takes effect on next AI draft (no restart)."""
    data = await request.json()
    content = data.get("content")
    if content is None:
        return {"status": "error", "error": "content is required"}
    if not isinstance(content, str):
        return {"status": "error", "error": "content must be a string"}
    if len(content) > 50_000:
        return {"status": "error", "error": "content too long (max 50000 chars)"}
    path = save_user_skill(content)
    return {
        "status": "success",
        "path": path,
        "chars": len(content),
    }


# Elite Date bot integration endpoint
from app.tools import elitedate_dispatch


@app.post("/api/elitedate/incoming")
async def elitedate_incoming(request: Request):
    """Called by the elitedate_bot process when it finds a new message."""
    data = await request.json()
    conversation_id = data.get("conversation_id", "").strip()
    sender = data.get("sender", "Neznámy").strip()
    message = data.get("message", "").strip()
    my_last_message = data.get("my_last_message", "").strip()
    submit = bool(data.get("submit", False))
    history = data.get("history") if isinstance(data.get("history"), list) else []
    photo_url = str(data.get("photo_url") or "").strip()
    photo_base64 = str(data.get("photo_base64") or "").strip()
    photo_content_type = str(data.get("photo_content_type") or "").strip()

    if not conversation_id or not message:
        return {"status": "error", "error": "conversation_id and message are required"}

    entry = await elitedate_dispatch.handle_incoming(
        conversation_id,
        sender,
        message,
        my_last_message=my_last_message,
        submit=submit,
        history=history,
        photo_url=photo_url,
        photo_base64=photo_base64,
        photo_content_type=photo_content_type,
    )
    discord_ok = bool(entry.get("prompt_message_id"))
    return {
        "status": "success" if discord_ok else "error",
        "discord": discord_ok,
        "message_id": entry.get("prompt_message_id"),
        "entry": entry,
        "error": None if discord_ok else "discord_notify_failed",
    }


@app.post("/api/elitedate/morning_greet")
async def elitedate_morning_greet(request: Request):
    """Súhrn ranných pozdravov z elitedate_bot → Discord (vždy — úspech aj neúspech)."""
    data = await request.json()
    return await elitedate_dispatch.handle_morning_greet_summary(data)


# Tinder bot integration endpoint
from app.tools import tinder_dispatch


@app.post("/api/tinder/incoming")
async def tinder_incoming(request: Request):
    """Called by the tinder_bot process when it finds a new message."""
    data = await request.json()
    conversation_id = data.get("conversation_id", "").strip()
    sender = data.get("sender", "Neznámy").strip()
    message = data.get("message", "").strip()
    my_last_message = data.get("my_last_message", "").strip()
    submit = bool(data.get("submit", False))
    history = data.get("history") if isinstance(data.get("history"), list) else []
    photo_url = str(data.get("photo_url") or "").strip()
    photo_base64 = str(data.get("photo_base64") or "").strip()
    photo_content_type = str(data.get("photo_content_type") or "").strip()

    if not conversation_id or not message:
        return {"status": "error", "error": "conversation_id and message are required"}

    entry = await tinder_dispatch.handle_incoming(
        conversation_id,
        sender,
        message,
        my_last_message=my_last_message,
        submit=submit,
        history=history,
        photo_url=photo_url,
        photo_base64=photo_base64,
        photo_content_type=photo_content_type,
    )
    discord_ok = bool(entry.get("prompt_message_id"))
    return {
        "status": "success" if discord_ok else "error",
        "discord": discord_ok,
        "message_id": entry.get("prompt_message_id"),
        "entry": entry,
        "error": None if discord_ok else "discord_notify_failed",
    }
