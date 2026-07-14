"""Session recovery scenarios — Chrome crash, dead session, rebuild retries."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from selenium.common.exceptions import InvalidSessionIdException

from elitedate_bot import shared_state as ed_state
from elitedate_bot import session as ed_session
from tinder_bot import shared_state as td_state
from tinder_bot import session as td_session


@pytest.fixture(autouse=True)
def _reset_shared_clients():
    ed_state.client = None
    td_state.client = None
    yield
    ed_state.client = None
    td_state.client = None


@pytest.mark.parametrize(
    "exc",
    [
        InvalidSessionIdException("invalid session id"),
        Exception("no such window"),
        Exception("chrome not reachable"),
        Exception("disconnected: not connected to DevTools"),
        Exception("Failed to establish a new connection"),
        Exception("Connection refused"),
        Exception("The target machine actively refused"),
    ],
)
@pytest.mark.parametrize("mod", [ed_session, td_session], ids=["elitedate", "tinder"])
def test_is_dead_session_error_true(mod, exc):
    assert mod.is_dead_session_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        Exception("element not found"),
        Exception("timeout waiting for selector"),
        ValueError("bad payload"),
        Exception("HTTP 429 rate limit"),
    ],
)
@pytest.mark.parametrize("mod", [ed_session, td_session], ids=["elitedate", "tinder"])
def test_is_dead_session_error_false(mod, exc):
    assert mod.is_dead_session_error(exc) is False


@pytest.mark.parametrize("mod", [ed_session, td_session], ids=["elitedate", "tinder"])
def test_session_alive_none(mod):
    assert mod.session_alive(None) is False


@pytest.mark.parametrize(
    ("mod", "state"),
    [(ed_session, ed_state), (td_session, td_state)],
    ids=["elitedate", "tinder"],
)
def test_session_alive_ok(mod, state, fake_driver):
    client = MagicMock()
    client.driver = fake_driver
    state.client = client
    assert mod.session_alive(client) is True


@pytest.mark.parametrize(
    ("mod", "state"),
    [(ed_session, ed_state), (td_session, td_state)],
    ids=["elitedate", "tinder"],
)
def test_session_alive_dead_driver(mod, state, dead_driver):
    client = MagicMock()
    client.driver = dead_driver
    state.client = client
    assert mod.session_alive(client) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mod", "state", "client_cls", "build_path", "client_path"),
    [
        (
            ed_session,
            ed_state,
            "EliteDateClient",
            "elitedate_bot.session.build_driver",
            "elitedate_bot.session.EliteDateClient",
        ),
        (
            td_session,
            td_state,
            "TinderClient",
            "tinder_bot.session.build_driver",
            "tinder_bot.session.TinderClient",
        ),
    ],
    ids=["elitedate", "tinder"],
)
async def test_run_with_recovery_succeeds_without_rebuild(
    mod, state, client_cls, build_path, client_path, fake_driver
):
    client = MagicMock()
    client.driver = fake_driver
    state.client = client

    def work():
        return "ok"

    with patch.object(mod, "rebuild_session", new_callable=AsyncMock) as rebuild:
        result = await mod.run_with_recovery(work)
    assert result == "ok"
    rebuild.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mod", "state"),
    [(ed_session, ed_state), (td_session, td_state)],
    ids=["elitedate", "tinder"],
)
async def test_run_with_recovery_rebuilds_on_dead_session(mod, state, fake_driver):
    dead = MagicMock()
    type(dead).current_url = property(
        lambda self: (_ for _ in ()).throw(Exception("chrome not reachable"))
    )
    dead_client = MagicMock()
    dead_client.driver = dead

    healthy = MagicMock()
    healthy.driver = fake_driver

    state.client = dead_client
    calls = {"n": 0}

    def work():
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("invalid session id")
        return "recovered"

    async def fake_rebuild():
        state.client = healthy
        return healthy

    with (
        patch.object(mod, "rebuild_session", side_effect=fake_rebuild) as rebuild,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await mod.run_with_recovery(work)

    assert result == "recovered"
    assert rebuild.await_count >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mod", "state"),
    [(ed_session, ed_state), (td_session, td_state)],
    ids=["elitedate", "tinder"],
)
async def test_run_with_recovery_non_dead_error_is_raised(mod, state, fake_driver):
    client = MagicMock()
    client.driver = fake_driver
    state.client = client

    def work():
        raise Exception("element not found")

    with patch.object(mod, "rebuild_session", new_callable=AsyncMock) as rebuild:
        with pytest.raises(Exception, match="element not found"):
            await mod.run_with_recovery(work)
    rebuild.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mod", "state", "build_path", "client_path"),
    [
        (
            ed_session,
            ed_state,
            "elitedate_bot.session.build_driver",
            "elitedate_bot.session.EliteDateClient",
        ),
        (
            td_session,
            td_state,
            "tinder_bot.session.build_driver",
            "tinder_bot.session.TinderClient",
        ),
    ],
    ids=["elitedate", "tinder"],
)
async def test_rebuild_session_retries_chrome_startup_then_succeeds(
    mod, state, build_path, client_path, fake_driver
):
    old = MagicMock()
    old.driver.quit = MagicMock(side_effect=Exception("already dead"))
    state.client = old

    build_attempts = {"n": 0}

    def build():
        build_attempts["n"] += 1
        if build_attempts["n"] < 2:
            raise Exception("chrome not reachable")
        return fake_driver

    fake_client = MagicMock()
    fake_client.driver = fake_driver
    fake_client.login = MagicMock()

    with (
        patch(build_path, side_effect=build),
        patch(client_path, return_value=fake_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await mod.rebuild_session()

    assert result is fake_client
    assert state.client is fake_client
    assert build_attempts["n"] == 2
    fake_client.login.assert_called_once()


@pytest.mark.asyncio
async def test_tinder_rebuild_retries_user_data_dir_lock(fake_driver):
    """Tinder-specific: Chrome profile lock / prefs write failures are retryable."""
    state = td_state
    state.client = None
    attempts = {"n": 0}

    def build():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise Exception("session not created: failed to write prefs")
        if attempts["n"] == 2:
            raise Exception("user data directory is already in use")
        return fake_driver

    fake_client = MagicMock()
    fake_client.login = MagicMock()

    with (
        patch("tinder_bot.session.build_driver", side_effect=build),
        patch("tinder_bot.session.TinderClient", return_value=fake_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await td_session.rebuild_session()

    assert result is fake_client
    assert attempts["n"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mod", "state"),
    [(ed_session, ed_state), (td_session, td_state)],
    ids=["elitedate", "tinder"],
)
async def test_run_client_method_uses_current_client_after_rebuild(mod, state, fake_driver):
    client = MagicMock()
    client.driver = fake_driver
    client.check_new_messages = MagicMock(return_value=[{"conversation_id": "c1"}])
    state.client = client

    with patch.object(mod, "rebuild_session", new_callable=AsyncMock):
        result = await mod.run_client_method("check_new_messages")

    assert result == [{"conversation_id": "c1"}]
    client.check_new_messages.assert_called_once()
