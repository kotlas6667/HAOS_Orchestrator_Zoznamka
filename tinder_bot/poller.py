from __future__ import annotations

import asyncio
import hashlib
import json
import random
from pathlib import Path

import httpx

from tinder_bot import shared_state
from tinder_bot.config import settings
from tinder_bot.session import rebuild_session, run_client_method

_SEEN_FILE = Path(settings.seen_messages_file)
_BACKOFF_BASE_SEC = 60.0
_BACKOFF_MAX_SEC = 900.0
_consecutive_failures = 0


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
            f"{settings.orchestrator_url}/api/tinder/incoming",
            json={
                "conversation_id": msg["conversation_id"],
                "sender": msg["sender"],
                "message": msg["message"],
                "my_last_message": msg.get("my_last_message", ""),
            },
        )
        response.raise_for_status()


def _failure_backoff_sec() -> float:
    if _consecutive_failures <= 0:
        return 0.0
    return min(_BACKOFF_BASE_SEC * (2 ** (_consecutive_failures - 1)), _BACKOFF_MAX_SEC)


async def poll_loop() -> None:
    """Runs forever: periodically checks for new Tinder messages and
    forwards genuinely new ones to the orchestrator."""
    global _consecutive_failures
    seen = _load_seen()
    # Let elitedate_bot grab Chrome first; both bots polling at once OOMs Pi easily.
    await asyncio.sleep(45)
    first = True

    while True:
        if not first:
            wait_s = random.uniform(settings.poll_interval_min_sec, settings.poll_interval_max_sec)
            wait_s += _failure_backoff_sec()
            if wait_s > settings.poll_interval_max_sec:
                print(
                    f"[tinder_bot] {_consecutive_failures} consecutive poll failures — "
                    f"backing off {int(wait_s)}s before next attempt"
                )
            await asyncio.sleep(wait_s)
        first = False

        if shared_state.client is None:
            try:
                async with shared_state.driver_lock:
                    await rebuild_session()
            except Exception as exc:  # noqa: BLE001
                _consecutive_failures += 1
                print(f"[tinder_bot] rebuild_session failed: {exc}")
            continue

        try:
            async with shared_state.driver_lock:
                messages = await run_client_method("check_new_messages")
        except Exception as exc:  # noqa: BLE001
            _consecutive_failures += 1
            print(f"[tinder_bot] check_new_messages failed: {exc}")
            continue

        _consecutive_failures = 0

        new_count = 0
        for msg in messages:
            key = _message_key(msg)
            if key in seen:
                continue
            seen.add(key)
            new_count += 1
            try:
                await _notify_orchestrator(msg)
            except Exception as exc:  # noqa: BLE001
                print(f"[tinder_bot] Failed to notify orchestrator: {exc}")
                seen.discard(key)  # retry next cycle

        if new_count:
            _save_seen(seen)
