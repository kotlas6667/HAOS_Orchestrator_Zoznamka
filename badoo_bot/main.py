from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from badoo_bot import shared_state
from badoo_bot.badoo_client import BadooClient
from badoo_bot.browser import build_driver
from badoo_bot.config import settings
from badoo_bot.poller import poll_loop
from badoo_bot.server import app as inner_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = None
    driver = None
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            driver = await asyncio.to_thread(build_driver)
            client = BadooClient(driver)
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
            print(f"[badoo_bot] Startup attempt {attempt + 1} failed ({exc}); retrying in {wait_s}s...")
            await asyncio.sleep(wait_s)
    else:
        raise last_exc or RuntimeError("badoo_bot startup failed")

    shared_state.client = client
    poll_task = None
    if settings.poll_enabled:
        print("[badoo_bot] Logged in, starting poll loop.")
        poll_task = asyncio.create_task(poll_loop())
    else:
        print("[badoo_bot] Logged in, poll loop disabled (BADOO_POLL_ENABLED=false).")

    yield

    if poll_task is not None:
        poll_task.cancel()
    if driver is not None:
        await asyncio.to_thread(driver.quit)


inner_app.router.lifespan_context = lifespan


def main() -> None:
    uvicorn.run(inner_app, host=settings.bot_host, port=settings.bot_port, log_level="info")


if __name__ == "__main__":
    main()
