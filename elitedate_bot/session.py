from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from selenium.common.exceptions import InvalidSessionIdException

from elitedate_bot import shared_state
from elitedate_bot.browser import build_driver, reset_chrome_profile
from elitedate_bot.elitedate_client import EliteDateClient

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
    "session not created",
    "cannot find chrome binary",
    "devtoolsactiveport",
    "failed to write prefs",
    "user data directory",
)


def _retryable_startup_error(exc: BaseException) -> bool:
    if is_dead_session_error(exc):
        return True
    msg = str(exc).lower()
    if not msg.strip() or msg.strip() in {"message:", "message: "}:
        return True
    if "stacktrace" in msg and len(msg) < 400:
        return True
    return any(
        marker in msg
        for marker in (
            "failed to write prefs",
            "user data directory",
            "session not created",
            "chrome failed to start",
            "unknown error",
        )
    )


def _kill_stale_chromium() -> None:
    """Terminate orphaned Chromium/chromedriver from prior crashes (profile lock)."""
    patterns = (
        "chromium.*elitedate_chrome_profile",
        "chrome.*elitedate_chrome_profile",
        "chromedriver",
    )
    for pattern in patterns:
        try:
            subprocess.run(
                ["pkill", "-f", pattern],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception:  # noqa: BLE001
            pass


def is_dead_session_error(exc: BaseException) -> bool:
    if isinstance(exc, InvalidSessionIdException):
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _DEAD_SESSION_MARKERS)


def session_alive(client: EliteDateClient | None) -> bool:
    if client is None:
        return False
    try:
        _ = client.driver.current_url
        return True
    except Exception:  # noqa: BLE001
        return False


async def rebuild_session() -> EliteDateClient:
    """Quit the dead driver, start a new one, and log back into Elite Date."""
    old = shared_state.client
    if old is not None:
        try:
            await asyncio.to_thread(old.driver.quit)
        except Exception:  # noqa: BLE001
            pass
    shared_state.client = None

    _kill_stale_chromium()
    await asyncio.sleep(3)

    profile = Path("/data/elitedate_chrome_profile")
    if profile.exists():
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock = profile / name
            try:
                if lock.exists() or lock.is_symlink():
                    lock.unlink(missing_ok=True)
                    print(f"[elitedate_bot] Removed stale {name}")
            except OSError as exc:
                print(f"[elitedate_bot] Profile lock cleanup failed ({name}): {exc}")

    last_exc: Exception | None = None
    driver = None
    for attempt in range(5):
        try:
            driver = await asyncio.to_thread(build_driver)
            client = EliteDateClient(driver)
            await asyncio.to_thread(client.login)
            shared_state.client = client
            print("[elitedate_bot] Selenium session rebuilt and re-logged in.")
            return client
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < 4:
                print(
                    f"[elitedate_bot] Chrome startup failed on rebuild attempt {attempt + 1} "
                    f"({type(exc).__name__}: {exc!r}); retrying..."
                )
                if driver is not None:
                    try:
                        await asyncio.to_thread(driver.quit)
                    except Exception:  # noqa: BLE001
                        pass
                    driver = None
                _kill_stale_chromium()
                if attempt >= 1:
                    await asyncio.to_thread(reset_chrome_profile)
                await asyncio.sleep(6 + attempt * 6)
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
                print(f"[elitedate_bot] Dead session ({exc}); rebuilding...")
                await rebuild_session()
                await asyncio.sleep(1.5)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("run_with_recovery failed without an exception")


async def run_client_method(method_name: str, /, *args: Any, **kwargs: Any) -> T:
    """Call a client method using the current shared_state.client after rebuilds."""

    def _call() -> T:
        client = shared_state.client
        if client is None:
            raise RuntimeError("client is not initialized")
        return getattr(client, method_name)(*args, **kwargs)

    return await run_with_recovery(_call)
