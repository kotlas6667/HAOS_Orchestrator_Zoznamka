from __future__ import annotations

import asyncio

from badoo_bot.badoo_client import BadooClient

# Selenium driver is not safe for concurrent use (poll loop + /send).
driver_lock = asyncio.Lock()
client: BadooClient | None = None
