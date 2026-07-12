from __future__ import annotations

import asyncio

from fastapi import FastAPI, Request

from elitedate_bot import shared_state
from elitedate_bot.session import run_with_recovery, session_alive

app = FastAPI(title="EliteDate Bot")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "logged_in": shared_state.client is not None,
        "session_alive": session_alive(shared_state.client),
    }


@app.get("/debug/inbox")
async def debug_inbox() -> dict:
    """Show current page URL and first visible conversation senders."""
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}
    import time
    from selenium.webdriver.by import By
    from selenium.webdriver.support import expected_conditions as EC
    try:
        async with shared_state.driver_lock:
            def _inspect():
                c = shared_state.client
                c.driver.get(c._messages_url())
                try:
                    c._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".conversation-section-list")))
                except Exception:
                    pass
                time.sleep(0.5)
                url = c.driver.current_url
                items = c.driver.find_elements(By.CSS_SELECTOR, ".conversation-section-list .col-message")
                senders = []
                for item in items[:20]:
                    try:
                        name = item.find_element(By.CSS_SELECTOR, "h5").text.strip()
                        senders.append(name)
                    except Exception:
                        senders.append("<no h5>")
                return {"url": url, "items_visible": len(items), "senders": senders}
            result = await run_with_recovery(_inspect)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return result


@app.post("/conversation/find")
async def find_conversation(request: Request) -> dict:
    """Find an existing EliteDate conversation by sender/date and return context."""
    data = await request.json()
    sender = data.get("sender", "").strip()
    date_hint = data.get("date_hint", "").strip()

    if not sender:
        return {"status": "error", "error": "sender is required"}

    if shared_state.client is None:
        return {"status": "error", "error": "Bot is not logged in yet"}

    try:
        async with shared_state.driver_lock:
            snapshot = await run_with_recovery(
                shared_state.client.find_conversation_snapshot,
                sender,
                date_hint,
            )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    if not snapshot.get("conversation_id"):
        snapshot["conversation_id"] = f"manual:{sender}:{date_hint or 'no-date'}"

    if not snapshot.get("message"):
        return {"status": "error", "error": "conversation found but message context is empty", "snapshot": snapshot}

    return {"status": "success", "conversation": snapshot}


@app.post("/send")
async def send(request: Request) -> dict:
    """Called by orchestrator after user picks a reply.

    By default this endpoint only inserts text into EliteDate input without
    submitting. Set `submit=true` to click send.
    """
    data = await request.json()
    conversation_id = data.get("conversation_id", "").strip()
    text = data.get("text", "").strip()
    sender = data.get("sender", "").strip()
    expected_message = data.get("expected_message", "").strip()
    submit = bool(data.get("submit", False))

    if not conversation_id or not text:
        return {"status": "error", "error": "conversation_id and text are required"}

    if shared_state.client is None:
        return {"status": "error", "error": "Bot is not logged in yet"}

    try:
        async with shared_state.driver_lock:
            ok = await run_with_recovery(
                shared_state.client.send_reply,
                conversation_id,
                text,
                submit=submit,
                sender=sender,
                expected_message=expected_message,
            )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    return {
        "status": "success" if ok else "error",
        "mode": "sent" if submit else "inserted",
    }
