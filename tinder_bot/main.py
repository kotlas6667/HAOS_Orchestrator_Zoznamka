from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from tinder_bot import shared_state
from tinder_bot.browser import build_driver
from tinder_bot.config import settings
from tinder_bot.tinder_client import TinderClient
from tinder_bot.poller import poll_loop
from tinder_bot.server import app as inner_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    driver = await asyncio.to_thread(build_driver)
    client = TinderClient(driver)
    await asyncio.to_thread(client.login)
    shared_state.client = client
    print("[tinder_bot] Logged in, starting poll loop.")

    poll_task = asyncio.create_task(poll_loop())

    yield

    poll_task.cancel()
    await asyncio.to_thread(driver.quit)


inner_app.router.lifespan_context = lifespan


def main() -> None:
    uvicorn.run(inner_app, host=settings.bot_host, port=settings.bot_port, log_level="info")


if __name__ == "__main__":
    main()
