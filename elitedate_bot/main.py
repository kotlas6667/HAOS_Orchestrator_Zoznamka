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


@asynccontextmanager
async def lifespan(app: FastAPI):
    driver = await asyncio.to_thread(build_driver)
    client = EliteDateClient(driver)
    await asyncio.to_thread(client.login)
    shared_state.client = client
    print("[elitedate_bot] Logged in, starting poll loop.")

    poll_task = asyncio.create_task(poll_loop())

    yield

    poll_task.cancel()
    await asyncio.to_thread(driver.quit)


inner_app.router.lifespan_context = lifespan


def main() -> None:
    uvicorn.run(inner_app, host=settings.bot_host, port=settings.bot_port, log_level="info")


if __name__ == "__main__":
    main()
