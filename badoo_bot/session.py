from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from selenium.common.exceptions import InvalidSessionIdException

from badoo_bot import shared_state
from badoo_bot.badoo_client import BadooClient
from badoo_bot.browser import build_driver
from badoo_bot.config import settings

T = TypeVar("T")

_DEAD_SESSION_MARKERS = (
    "invalid session id",
    "no such window",
    "failed to establish a new connection",
    "connection refused",
    "target machine actively refused",
    "disconnected: not connected to devtools",
    "unable to receive message from renderer",
    "timed out receiving message from renderer",
    "chrome not reachable",
    "session deleted as the browser has closed",
    "tab crashed",
)


def is_dead_session_error(exc: BaseException) -> bool:
    if isinstance(exc, InvalidSessionIdException):
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _DEAD_SESSION_MARKERS)


def session_alive(client: BadooClient | None) -> bool:
    if client is None:
        return False
    try:
        _ = client.driver.current_url
        return True
    except Exception:  # noqa: BLE001
        return False


async def rebuild_session() -> BadooClient:
    """Quit the dead driver, start a new one, and log back into Badoo."""
    old = shared_state.client
    if old is not None:
        try:
            await asyncio.to_thread(old.driver.quit)
        except Exception:  # noqa: BLE001
            pass
    shared_state.client = None

    await asyncio.sleep(3)
    if settings.user_data_dir:
        try:
            from pathlib import Path

            profile = Path(settings.user_data_dir)
            for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                lock = profile / name
                if lock.exists() or lock.is_symlink():
                    lock.unlink(missing_ok=True)
                    print(f"[badoo_bot] Removed stale {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[badoo_bot] Profile lock cleanup failed: {exc}")

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            driver = await asyncio.to_thread(build_driver)
            client = BadooClient(driver)
            await asyncio.to_thread(client.login)
            shared_state.client = client
            print("[badoo_bot] Selenium session rebuilt and re-logged in.")
            return client
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc).lower()
            if attempt < 2 and (
                is_dead_session_error(exc)
                or "failed to write prefs" in msg
                or "user data directory" in msg
            ):
                print(f"[badoo_bot] Chrome startup failed on rebuild attempt {attempt + 1}, retrying...")
                await asyncio.sleep(5)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("rebuild_session failed without an exception")


async def run_with_recovery(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run a blocking Selenium call; rebuild the browser session on crash."""
    last_exc: Exception | None = None
    max_attempts = 3
    for attempt in range(max_attempts):
        if not session_alive(shared_state.client):
            await rebuild_session()
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if is_dead_session_error(exc) and attempt < max_attempts - 1:
                print(f"[badoo_bot] Dead session ({exc}); rebuilding...")
                await rebuild_session()
                await asyncio.sleep(1.5)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("run_with_recovery failed without an exception")


async def run_client_method(method_name: str, /, *args: Any, **kwargs: Any) -> T:
    def _call() -> T:
        client = shared_state.client
        if client is None:
            raise RuntimeError("client is not initialized")
        return getattr(client, method_name)(*args, **kwargs)

    return await run_with_recovery(_call)
