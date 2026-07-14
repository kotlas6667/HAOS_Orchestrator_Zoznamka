"""Poller notify / dedup behaviour under re-delivery and HTTP failures."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from elitedate_bot import poller as ed_poller
from tinder_bot import poller as td_poller


@pytest.mark.parametrize(
    ("msg_a", "msg_b", "same"),
    [
        (
            {"conversation_id": "c1", "sender": "Eva", "message": "Ahoj"},
            {"conversation_id": "c1", "sender": "Eva", "message": "Ahoj"},
            True,
        ),
        (
            {"conversation_id": "c1", "sender": "Eva", "message": "Ahoj"},
            {"conversation_id": "c1", "sender": "Eva", "message": "Ahoj!"},
            False,
        ),
        (
            {"conversation_id": "c1", "sender": "Eva", "message": "Ahoj"},
            {"conversation_id": "c2", "sender": "Eva", "message": "Ahoj"},
            False,
        ),
    ],
)
def test_message_key_stability(msg_a, msg_b, same):
    ka = ed_poller._message_key(msg_a)
    kb = ed_poller._message_key(msg_b)
    assert (ka == kb) is same
    # Same hashing for tinder
    assert (td_poller._message_key(msg_a) == td_poller._message_key(msg_b)) is same


@pytest.mark.asyncio
async def test_notify_orchestrator_posts_expected_payload(monkeypatch):
    calls = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            calls["url"] = url
            calls["json"] = json
            return FakeResponse()

    monkeypatch.setattr(ed_poller.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(ed_poller.settings, "orchestrator_url", "http://haos_orchestrator:8000")

    msg = {
        "conversation_id": "c1",
        "sender": "Eva",
        "message": "Ahoj",
        "my_last_message": "Čau",
    }
    await ed_poller._notify_orchestrator(msg)
    assert calls["url"] == "http://haos_orchestrator:8000/api/elitedate/incoming"
    assert calls["json"]["sender"] == "Eva"
    assert calls["json"]["my_last_message"] == "Čau"


@pytest.mark.asyncio
async def test_poll_loop_skips_seen_and_retries_failed_notify(tmp_path, monkeypatch):
    seen_file = tmp_path / ".seen.json"
    monkeypatch.setattr(ed_poller, "_SEEN_FILE", seen_file)

    msg = {"conversation_id": "c1", "sender": "Eva", "message": "Hi", "my_last_message": ""}
    key = ed_poller._message_key(msg)

    from elitedate_bot import shared_state

    client = MagicMock()
    shared_state.client = client

    notify_calls = {"n": 0}

    async def notify(m):
        notify_calls["n"] += 1
        if notify_calls["n"] == 1:
            raise RuntimeError("orchestrator down")

    poll_count = {"n": 0}

    async def fake_run(method_name):
        poll_count["n"] += 1
        if poll_count["n"] > 2:
            raise asyncio.CancelledError()
        return [msg]

    import asyncio

    monkeypatch.setattr(ed_poller, "_notify_orchestrator", notify)
    monkeypatch.setattr(ed_poller, "run_client_method", fake_run)
    monkeypatch.setattr(ed_poller.random, "uniform", lambda a, b: 0)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        await ed_poller.poll_loop()

    # First notify failed → key not persisted; second succeeded → persisted
    assert notify_calls["n"] == 2
    saved = set(json.loads(seen_file.read_text(encoding="utf-8")))
    assert key in saved
