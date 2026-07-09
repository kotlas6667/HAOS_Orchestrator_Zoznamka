from __future__ import annotations

import asyncio

from tinder_bot.tinder_client import TinderClient

# The Selenium driver is not safe to drive from two places at once (the poll
# loop and an incoming /send request could otherwise both navigate the same
# browser tab simultaneously). Everything that touches `client` must hold
# this lock first.
driver_lock = asyncio.Lock()
client: TinderClient | None = None
