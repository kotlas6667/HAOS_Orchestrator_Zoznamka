from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import FastAPI, Request

from tinder_bot import shared_state
from tinder_bot.config import settings
from tinder_bot.session import run_with_recovery, session_alive

app = FastAPI(title="Tinder Bot")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "logged_in": shared_state.client is not None,
        "session_alive": session_alive(shared_state.client),
    }


@app.get("/debug/page")
async def debug_page() -> dict:
    """Quick snapshot of current Chrome page without navigating."""
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}
    try:
        async with shared_state.driver_lock:
            def _snap():
                c = shared_state.client
                url = c.driver.current_url
                title = c.driver.title
                count = c._count_conversation_previews()
                body = c.driver.execute_script("return (document.body.innerText||'').slice(0,300);") or ""
                return {"url": url, "title": title, "preview_count": count, "body_snippet": body}

            result = await run_with_recovery(_snap)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return {"status": "ok", **result}


@app.get("/debug/inbox")
async def debug_inbox() -> dict:
    """Show current page URL and first visible conversation senders."""
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}
    import asyncio

    try:
        async with shared_state.driver_lock:
            def _inspect():
                c = shared_state.client
                c._navigate_to_inbox()
                url = c.driver.current_url
                rows = c._list_conversations()
                raw_count = c.driver.execute_script(
                    'return document.querySelectorAll("a[href*=\'/app/messages/\']").length'
                )
                senders = [r.get("name") or "<no name>" for r in rows[:20]]
                previews = [r.get("preview", "")[:40] for r in rows[:5]]
                return {
                    "url": url,
                    "title": c.driver.title,
                    "items_visible": len(rows),
                    "raw_anchors": raw_count,
                    "senders": senders,
                    "sample_previews": previews,
                    "body_snippet": (c.driver.execute_script("return (document.body.innerText||'').slice(0,200);") or ""),
                }

            result = await run_with_recovery(_inspect)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return result


@app.post("/debug/poll")
async def debug_poll() -> dict:
    """Run one check_new_messages cycle (for testing — does not skip poll interval)."""
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}
    try:
        async with shared_state.driver_lock:
            messages = await run_with_recovery(shared_state.client.check_new_messages)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return {"status": "ok", "new_messages": len(messages), "messages": messages}


@app.post("/debug/reload-inbox")
async def debug_reload_inbox() -> dict:
    """Force navigation to Správy tab and return inbox snapshot."""
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}
    try:
        async with shared_state.driver_lock:
            def _reload():
                c = shared_state.client
                c._navigate_to_inbox(fast=True)
                rows = c._list_conversations()
                return {
                    "url": c.driver.current_url,
                    "title": c.driver.title,
                    "spravy_tab_active": c._spravy_tab_active(),
                    "preview_count": c._count_conversation_previews(),
                    "senders": [r.get("name") for r in rows[:10]],
                    "previews": [(r.get("preview") or "")[:50] for r in rows[:5]],
                }

            result = await run_with_recovery(_reload)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return {"status": "ok", **result}


@app.post("/debug/push-discord")
async def debug_push_discord(request: Request) -> dict:
    """Fetch a sender's thread and POST it to the orchestrator (Discord prompt)."""
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}

    data = await request.json() if request.headers.get("content-length") else {}
    sender_query = str(data.get("sender") or "latest").strip()
    submit = bool(data.get("submit", False))
    occurrence = int(data.get("occurrence") or 1)
    if occurrence < 1:
        occurrence = 1
    use_latest = sender_query.lower() in {"", "latest", "last", "posledna", "posledná"}

    try:
        async with shared_state.driver_lock:
            def _fetch():
                c = shared_state.client
                if use_latest:
                    match = c.find_latest_received_conversation()
                    match_id = match["match_id"]
                    sender = match.get("name") or "Neznámy"
                    their_msg = c._latest_received_message()
                    my_msg = c._latest_sent_message()
                    if not their_msg:
                        raise RuntimeError(f"No received message visible in chat with {sender}")
                    return {
                        "conversation_id": match_id,
                        "sender": sender,
                        "message": their_msg,
                        "my_last_message": my_msg,
                    }

                c._navigate_to_inbox(fast=True)
                rows = c._list_conversations()
                match = None
                wanted = sender_query.lower()
                matches: list[dict[str, str]] = []
                seen_ids: set[str] = set()
                for _ in range(5):
                    rows = c._list_conversations()
                    for row in rows:
                        match_id = (row.get("match_id") or "").strip()
                        name = (row.get("name") or "").strip()
                        if not match_id or match_id in seen_ids:
                            continue
                        if name and (wanted in name.lower() or name.lower() in wanted):
                            seen_ids.add(match_id)
                            matches.append(row)
                    if len(matches) >= occurrence:
                        break
                    scrolled = c.driver.execute_script(
                        """
                        const grid = document.querySelector('.ReactVirtualized__Grid') ||
                                     document.querySelector('[class*=messageList]') ||
                                     document.querySelector('main');
                        if (!grid) return false;
                        const before = grid.scrollTop;
                        grid.scrollTop = before + Math.max(300, grid.clientHeight * 0.8);
                        return grid.scrollTop > before;
                        """
                    )
                    if not scrolled:
                        break
                    time.sleep(0.4)
                if len(matches) >= occurrence:
                    match = matches[occurrence - 1]
                if match is None:
                    names = [r.get("name") for r in rows[:30]]
                    raise RuntimeError(
                        f"Sender {sender_query!r} occurrence {occurrence} not found. Visible: {names}"
                    )

                match_id = match["match_id"]
                sender = match.get("name") or sender_query
                c._open_conversation(match_id)
                their_msg = c._latest_received_message()
                my_msg = c._latest_sent_message()
                if not their_msg:
                    raise RuntimeError(f"No received message visible in chat with {sender}")
                return {
                    "conversation_id": match_id,
                    "sender": sender,
                    "message": their_msg,
                    "my_last_message": my_msg,
                }

            payload = await run_with_recovery(_fetch)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    try:
        async with httpx.AsyncClient(timeout=max(settings.wait_timeout_sec, settings.spravy_settle_sec + 5)) as client:
            response = await client.post(
                f"{settings.orchestrator_url}/api/tinder/incoming",
                json={**payload, "submit": submit},
            )
            response.raise_for_status()
            orch = response.json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"orchestrator: {exc}", "fetch": payload}

    return {"status": "ok", "fetch": payload, "orchestrator": orch}


@app.post("/send")
async def send(request: Request) -> dict:
    """Called by orchestrator after user picks a reply.

    By default this endpoint only inserts text into Tinder's input without
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
