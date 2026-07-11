from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from selenium.common.exceptions import InvalidSessionIdException

from tinder_bot import shared_state
from tinder_bot.browser import build_driver
from tinder_bot.tinder_client import TinderClient

T = TypeVar("T")

_DEAD_SESSION_MARKERS = (
    "invalid session id",
    "no such window",
    "failed to establish a new connection",
    "connection refused",
    "target machine actively refused",
    "disconnected: not connected to devtools",
    "chrome not reachable",
)


def is_dead_session_error(exc: BaseException) -> bool:
    if isinstance(exc, InvalidSessionIdException):
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _DEAD_SESSION_MARKERS)


def session_alive(client: TinderClient | None) -> bool:
    if client is None:
        return False
    try:
        _ = client.driver.current_url
        return True
    except Exception:  # noqa: BLE001
        return False


async def rebuild_session() -> TinderClient:
    """Quit the dead driver, start a new one, and log back into Tinder."""
    old = shared_state.client
    if old is not None:
        try:
            await asyncio.to_thread(old.driver.quit)
        except Exception:  # noqa: BLE001
            pass
    shared_state.client = None

    # Let Chrome release the profile lock after quit.
    await asyncio.sleep(2)

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            driver = await asyncio.to_thread(build_driver)
            client = TinderClient(driver)
            await asyncio.to_thread(client.login)
            shared_state.client = client
            print("[tinder_bot] Selenium session rebuilt and re-logged in.")
            return client
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc).lower()
            if attempt < 2 and ("failed to write prefs" in msg or "user data directory" in msg):
                print(f"[tinder_bot] Chrome profile locked on rebuild attempt {attempt + 1}, retrying...")
                await asyncio.sleep(4)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("rebuild_session failed without an exception")


async def run_with_recovery(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run a blocking Selenium call; rebuild the browser session once on crash."""
    last_exc: Exception | None = None
    for attempt in range(2):
        if not session_alive(shared_state.client):
            await rebuild_session()
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == 0 and is_dead_session_error(exc):
                print(f"[tinder_bot] Dead session ({exc}); rebuilding...")
                await rebuild_session()
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("run_with_recovery failed without an exception")
