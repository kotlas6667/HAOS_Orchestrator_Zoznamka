from __future__ import annotations

import httpx
from fastapi import FastAPI, Request

from badoo_bot import shared_state
from badoo_bot.config import settings
from badoo_bot.session import run_client_method, run_with_recovery, session_alive

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
                    "preview_count": c._count_conversation_previews(),
                    "body_snippet": body,
                }

            result = await run_with_recovery(_snap)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return {"status": "ok", **result}


@app.get("/debug/inbox")
async def debug_inbox() -> dict:
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}
    try:
        async with shared_state.driver_lock:

            def _inspect():
                from badoo_bot.badoo_client import _INBOX_ROW_JS

                c = shared_state.client
                c._navigate_to_inbox()
                rows = c._list_conversations()
                raw = c.driver.execute_script(
                    _INBOX_ROW_JS
                    + """
                    const all = Array.from(document.querySelectorAll(
                      'button[data-qa="connections-item"], [data-qa="connections-item"]'
                    ));
                    const items = listConnectionItems();
                    return {
                      connections_item_total: all.length,
                      connections_item_filtered: items.length,
                      sample_types: all.slice(0, 8).map(el =>
                        el.getAttribute('data-qa-connections-item-type') || ''
                      ),
                      body_snippet: (document.body && document.body.innerText || '').slice(0, 280),
                    };
                    """
                ) or {}
                return {
                    "url": c.driver.current_url,
                    "title": c.driver.title,
                    "items_visible": len(rows),
                    "connections_item_total": raw.get("connections_item_total"),
                    "connections_item_filtered": raw.get("connections_item_filtered"),
                    "sample_types": raw.get("sample_types"),
                    "senders": [r.get("name") or "<no name>" for r in rows[:20]],
                    "match_ids": [r.get("match_id") or "" for r in rows[:10]],
                    "sample_previews": [(r.get("preview") or "")[:60] for r in rows[:5]],
                    "body_snippet": raw.get("body_snippet") or "",
                }

            result = await run_with_recovery(_inspect)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return result


@app.post("/debug/poll")
async def debug_poll() -> dict:
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}
    try:
        async with shared_state.driver_lock:
            messages = await run_client_method("check_new_messages")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    return {"status": "ok", "new_messages": len(messages), "messages": messages}


@app.post("/debug/push-discord")
async def debug_push_discord(request: Request) -> dict:
    if shared_state.client is None:
        return {"status": "error", "error": "not logged in"}

    data = await request.json() if request.headers.get("content-length") else {}
    sender_query = str(data.get("sender") or "latest").strip()
    submit = bool(data.get("submit", False))
    use_latest = sender_query.lower() in {"", "latest", "last", "posledna", "posledná"}

    try:
        async with shared_state.driver_lock:

            def _fetch():
                c = shared_state.client
                c._navigate_to_inbox(fast=True)
                rows = c._list_conversations_scrolled(max_steps=5)
                if not rows:
                    raise RuntimeError("Inbox is empty")
                if use_latest:
                    row = rows[0]
                else:
                    wanted = sender_query.lower()
                    row = None
                    for candidate in rows:
                        name = (candidate.get("name") or "").lower()
                        if wanted in name or name in wanted:
                            row = candidate
                            break
                    if row is None:
                        raise RuntimeError(
                            f"Sender {sender_query!r} not found. Visible: "
                            f"{[r.get('name') for r in rows[:20]]}"
                        )
                match_id = row["match_id"]
                sender = row.get("name") or sender_query or "Neznámy"
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
                    "history": c._extract_chat_history(max_messages=24),
                    "preview": row.get("preview") or their_msg,
                }

            payload = await run_with_recovery(_fetch)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.orchestrator_url}/api/badoo/incoming",
                json={**payload, "submit": submit},
            )
            response.raise_for_status()
            orch = response.json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"orchestrator: {exc}", "fetch": payload}

    return {"status": "ok", "fetch": payload, "orchestrator": orch}


@app.post("/send")
async def send(request: Request) -> dict:
    """Called by orchestrator after user picks a reply in Discord."""
    data = await request.json()
    conversation_id = data.get("conversation_id", "").strip()
    text = data.get("text", "").strip()
    sender = data.get("sender", "").strip()
    expected_message = data.get("expected_message", "").strip()
    submit = bool(data.get("submit", False)) or bool(settings.auto_send)

    if not conversation_id or not text:
        return {"status": "error", "error": "conversation_id and text are required"}

    if shared_state.client is None:
        return {"status": "error", "error": "Bot is not logged in yet"}

    print(f"[badoo_bot] /send submit={submit} (payload={bool(data.get('submit'))} auto_send={settings.auto_send})")

    try:
        async with shared_state.driver_lock:
            ok = await run_client_method(
                "send_reply",
                conversation_id,
                text,
                submit=submit,
                sender=sender,
                expected_message=expected_message,
            )
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or type(exc).__name__
        print(f"[badoo_bot] /send failed: {detail}")
        return {"status": "error", "error": detail}

    if not ok:
        return {
            "status": "error",
            "error": "send_reply returned False (chat/input not ready?)",
            "mode": "sent" if submit else "inserted",
        }
    return {
        "status": "success",
        "mode": "sent" if submit else "inserted",
    }
