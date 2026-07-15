from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from elitedate_bot import shared_state
from elitedate_bot.browser import build_driver
from elitedate_bot.config import settings
from elitedate_bot.elitedate_client import EliteDateClient
from elitedate_bot.poller import poll_loop
from elitedate_bot.server import app as inner_app

# Exit code used by run.sh supervisor to stop retrying on static misconfiguration.
CONFIG_EXIT_CODE = 77


class ConfigurationError(RuntimeError):
    """Missing or invalid static configuration; retrying won't help."""


def credentials_configured() -> bool:
    return bool(settings.elitedate_email and settings.elitedate_password)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not credentials_configured():
        raise ConfigurationError("ELITEDATE_EMAIL / ELITEDATE_PASSWORD not set in .env")

    client = None
    driver = None
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            driver = await asyncio.to_thread(build_driver)
            client = EliteDateClient(driver)
            await asyncio.to_thread(client.login)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if driver is not None:
                try:
                    await asyncio.to_thread(driver.quit)
                except Exception:  # noqa: BLE001
                    pass
            driver = None
            wait_s = 5 + attempt * 5
            print(f"[elitedate_bot] Startup attempt {attempt + 1} failed ({exc}); retrying in {wait_s}s...")
            await asyncio.sleep(wait_s)
    else:
        raise last_exc or RuntimeError("elitedate_bot startup failed")

    shared_state.client = client
    poll_task = None
    if settings.poll_enabled:
        print("[elitedate_bot] Logged in, starting poll loop.")
        poll_task = asyncio.create_task(poll_loop())
    else:
        print("[elitedate_bot] Logged in, poll loop disabled (POLL_ENABLED=false).")

    yield

    if poll_task is not None:
        poll_task.cancel()
    if driver is not None:
        await asyncio.to_thread(driver.quit)


inner_app.router.lifespan_context = lifespan


def main() -> None:
    if not credentials_configured():
        print(
            "[elitedate_bot] ELITEDATE_EMAIL / ELITEDATE_PASSWORD not set — bot will not start. "
            "Configure credentials in .env or set ELITEDATE_BOT_ENABLED=false."
        )
        raise SystemExit(CONFIG_EXIT_CODE)

    uvicorn.run(inner_app, host=settings.bot_host, port=settings.bot_port, log_level="info")


if __name__ == "__main__":
    main()
