from pathlib import Path
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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
    if settings.gmail_provider != "oauth":
        return False
    credentials = settings.gmail_credentials_json
    if not credentials:
        return False
    return Path(credentials).exists()


async def check_emails_periodically():
    """Check for new emails every 5 minutes, notify Discord only about new ones."""
    global _seen_email_ids
    while True:
        try:
            response = await gmail_tool.provider.get_emails(query="is:unread", max_results=10)
            emails = response.get("emails", [])
            new_ids_added = False
            for email in emails:
                msg_id = email.get("message_id")
                if not msg_id or msg_id in _seen_email_ids:
                    continue
                _seen_email_ids.add(msg_id)
                new_ids_added = True
                # Send Discord notification for genuinely new emails
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

            # Email count
            email_response = await gmail_tool.provider.get_emails(query="is:unread", max_results=50)
            email_count = len(email_response.get("emails", []))

            # Build summary
            lines = [
                "☀️ **Dobré ráno!**",
                f"",
                f"🌡️ **Počasie v {city}:** {temp}°C, {forecast}",
                f"📧 **Neprečítané emaily:** {email_count}",
            ]

            if email_count > 0:
                emails = email_response.get("emails", [])[:3]
                lines.append("")
                for mail in emails:
                    sender = mail.get("from", "?").split("<")[0].strip().strip('"')
                    subject = mail.get("subject", "(bez predmetu)")
                    lines.append(f"  • **{subject}** od {sender}")

            await notifier.send_message("\n".join(lines))
            print(f"[OK] Morning summary sent at {datetime.now().strftime('%H:%M')}")
        except Exception as e:
            print(f"Error sending morning summary: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks when FastAPI starts."""
    if _gmail_background_enabled():
        asyncio.create_task(check_emails_periodically())
        asyncio.create_task(send_morning_summary())
    else:
        print("[INFO] Gmail background tasks disabled (missing OAuth credentials file or provider not oauth).")

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

    if not conversation_id or not message:
        return {"status": "error", "error": "conversation_id and message are required"}

    entry = await elitedate_dispatch.handle_incoming(
        conversation_id,
        sender,
        message,
        my_last_message=my_last_message,
        submit=submit,
    )
    return {"status": "success", "entry": entry}


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

    if not conversation_id or not message:
        return {"status": "error", "error": "conversation_id and message are required"}

    entry = await tinder_dispatch.handle_incoming(
        conversation_id,
        sender,
        message,
        my_last_message=my_last_message,
        submit=submit,
    )
    return {"status": "success", "entry": entry}
