from __future__ import annotations

import asyncio
import hashlib
import json
import random
from pathlib import Path

import httpx

from elitedate_bot import shared_state
from elitedate_bot.config import settings
from elitedate_bot.session import run_client_method

_SEEN_FILE = Path(settings.seen_messages_file)


def _load_seen() -> set[str]:
    if _SEEN_FILE.exists():
        return set(json.loads(_SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def _save_seen(seen: set[str]) -> None:
    _SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def _message_key(msg: dict) -> str:
    payload = f"{msg.get('conversation_id', '')}\n{msg.get('sender', '')}\n{msg.get('message', '')}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


async def _notify_orchestrator(msg: dict) -> None:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{settings.orchestrator_url}/api/elitedate/incoming",
            json={
                "conversation_id": msg["conversation_id"],
                "sender": msg["sender"],
                "message": msg["message"],
                "my_last_message": msg.get("my_last_message", ""),
            },
        )
        response.raise_for_status()


async def poll_loop() -> None:
    """Runs forever: JSON preview cache detects new ED messages, then notify orchestrator.

    First poll runs immediately (seeds/diffs `.conversation_previews.json`); then
    randomized 90–180s interval. Extra `.seen_messages.json` dedup covers notify retries.
    """
    seen = _load_seen()
    first = True

    while True:
        if not first:
            wait_s = random.uniform(settings.poll_interval_min_sec, settings.poll_interval_max_sec)
            await asyncio.sleep(wait_s)
        first = False

        if shared_state.client is None:
            continue

        try:
            async with shared_state.driver_lock:
                messages = await run_client_method("check_new_messages")
        except Exception as exc:  # noqa: BLE001
            print(f"[elitedate_bot] check_new_messages failed: {exc}")
            continue

        new_count = 0
        for msg in messages:
            key = _message_key(msg)
            if key in seen:
                continue
            seen.add(key)
            new_count += 1
            try:
                await _notify_orchestrator(msg)
                print(
                    f"[elitedate_bot] Notified orchestrator: {msg.get('sender')} "
                    f"— {str(msg.get('message') or '')[:80]}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[elitedate_bot] Failed to notify orchestrator: {exc}")
                seen.discard(key)  # retry next cycle

        if new_count:
            _save_seen(seen)
        elif messages:
            # Deduped against .seen_messages.json — still useful in logs.
            print(f"[elitedate_bot] {len(messages)} candidate(s) already in seen cache")
