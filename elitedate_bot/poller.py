from __future__ import annotations

import asyncio

import httpx

from elitedate_bot import shared_state
from elitedate_bot.config import settings
from elitedate_bot.session import run_client_method


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
    """Periodically diff inbox state against JSON cache and notify on new incoming messages."""
    first = True

    while True:
        if not first:
            await asyncio.sleep(settings.poll_interval_sec)
        first = False

        if shared_state.client is None:
            continue

        try:
            async with shared_state.driver_lock:
                messages = await run_client_method("check_new_messages")
        except Exception as exc:  # noqa: BLE001
            print(f"[elitedate_bot] check_new_messages failed: {exc}")
            continue

        for msg in messages:
            try:
                await _notify_orchestrator(msg)
            except Exception as exc:  # noqa: BLE001
                print(f"[elitedate_bot] Failed to notify orchestrator: {exc}")
