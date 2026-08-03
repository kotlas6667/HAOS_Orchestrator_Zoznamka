from __future__ import annotations

from fastapi import FastAPI

from badoo_bot import shared_state
from badoo_bot.config import settings
from badoo_bot.session import run_with_recovery, session_alive

app = FastAPI(title="Badoo Bot")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "logged_in": shared_state.client is not None,
        "session_alive": session_alive(shared_state.client),
        "poll_enabled": settings.poll_enabled,
        "auto_send": settings.auto_send,
        "service": "badoo",
    }


@app.get("/debug/page")
async def debug_page() -> dict:
    """Snapshot of current Chrome page without navigating."""
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}
    try:
        async with shared_state.driver_lock:

            def _snap():
                c = shared_state.client
                url = c.driver.current_url
                title = c.driver.title
                body = (
                    c.driver.execute_script(
                        "return (document.body.innerText||'').slice(0,300);"
                    )
                    or ""
                )
                return {
                    "url": url,
                    "title": title,
                    "logged_in": c._is_logged_in(),
                    "body_snippet": body,
                }

            result = await run_with_recovery(_snap)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return {"status": "ok", **result}


@app.post("/send")
async def send_reply(payload: dict) -> dict:
    """Placeholder — inbox/send comes after login is verified."""
    return {
        "status": "error",
        "error": "Badoo /send ešte nie je implementované — over najprv login cez /health a /debug/page.",
        "received": {
            "conversation_id": payload.get("conversation_id"),
            "has_text": bool(payload.get("text") or payload.get("message")),
        },
    }
