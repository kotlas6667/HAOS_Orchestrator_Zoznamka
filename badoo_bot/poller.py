from __future__ import annotations

import asyncio
import random

from badoo_bot.config import settings
from badoo_bot.session import run_client_method


async def poll_loop() -> None:
    """Placeholder poll loop — inbox detection comes after login milestone."""
    print("[badoo_bot] Poll loop started (inbox not implemented yet).")
    while True:
        try:
            messages = await run_client_method("check_new_messages")
            if messages:
                print(f"[badoo_bot] check_new_messages returned {len(messages)} (unexpected until inbox wired)")
        except Exception as exc:  # noqa: BLE001
            print(f"[badoo_bot] poll error: {exc}")
        delay = random.uniform(settings.poll_interval_min_sec, settings.poll_interval_max_sec)
        await asyncio.sleep(delay)
