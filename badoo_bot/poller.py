from __future__ import annotations

import asyncio
import hashlib
import json
import random
from pathlib import Path

import httpx

from badoo_bot import shared_state
from badoo_bot.config import settings
from badoo_bot.session import rebuild_session, run_client_method

_SEEN_FILE = Path(settings.seen_messages_file)
_ORCHESTRATOR_TIMEOUT_SEC = 120.0


def _load_seen() -> set[str]:
    if _SEEN_FILE.exists():
        return set(json.loads(_SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def _save_seen(seen: set[str]) -> None:
    _SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def _message_key(msg: dict) -> str:
    payload = f"{msg.get('conversation_id', '')}\n{msg.get('sender', '')}\n{msg.get('message', '')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _notify_orchestrator(msg: dict) -> dict:
    history = msg.get("history") or []
    if not isinstance(history, list):
        history = []
    payload = {
        "conversation_id": msg["conversation_id"],
        "sender": msg["sender"],
        "message": msg["message"],
        "my_last_message": msg.get("my_last_message", ""),
        "history": history,
    }
    for key in ("photo_url", "photo_base64", "photo_content_type"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            payload[key] = val.strip()
    async with httpx.AsyncClient(timeout=_ORCHESTRATOR_TIMEOUT_SEC) as client:
        response = await client.post(
            f"{settings.orchestrator_url}/api/badoo/incoming",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("orchestrator returned non-object JSON")
    if not data.get("discord"):
        err = data.get("error") or "discord_notify_failed"
        raise RuntimeError(f"Discord not confirmed: {err}")
    return data


async def _commit_preview(msg: dict) -> None:
    preview = str(msg.get("preview") or "").strip()
    conversation_id = str(msg.get("conversation_id") or "").strip()
    if not preview or not conversation_id:
        return
    if shared_state.client is None:
        return
    try:
        async with shared_state.driver_lock:
            await run_client_method("commit_preview", conversation_id, preview)
    except Exception as exc:  # noqa: BLE001
        print(f"[badoo_bot] commit_preview failed: {exc}")


async def poll_loop() -> None:
    """Periodically check Badoo inbox and forward new messages to the orchestrator."""
    seen = _load_seen()
    first = True

    while True:
        if not first:
            wait_s = random.uniform(settings.poll_interval_min_sec, settings.poll_interval_max_sec)
            await asyncio.sleep(wait_s)
        first = False

        if shared_state.client is None:
            print("[badoo_bot] poll: client missing — trying session rebuild…")
            try:
                async with shared_state.driver_lock:
                    await rebuild_session()
            except Exception as exc:  # noqa: BLE001
                print(f"[badoo_bot] poll: session rebuild failed: {exc}")
            continue

        try:
            async with shared_state.driver_lock:
                messages = await run_client_method("check_new_messages")
        except Exception as exc:  # noqa: BLE001
            print(f"[badoo_bot] check_new_messages failed: {exc}")
            continue

        if not messages:
            print("[badoo_bot] poll: no new messages this cycle")

        new_count = 0
        for msg in messages:
            key = _message_key(msg)
            if key in seen:
                continue
            seen.add(key)
            new_count += 1
            try:
                await _notify_orchestrator(msg)
                await _commit_preview(msg)
            except Exception as exc:  # noqa: BLE001
                print(f"[badoo_bot] Failed to notify orchestrator: {exc}")
                seen.discard(key)

        if new_count:
            _save_seen(seen)
