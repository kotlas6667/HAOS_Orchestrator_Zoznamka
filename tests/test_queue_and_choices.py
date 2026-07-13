"""Discord reply-choice parsing and FIFO queue state under various inputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools import elitedate_dispatch, elitedate_state
from app.tools import tinder_dispatch, tinder_state


@pytest.fixture
def ed_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "elitedate_state.json"
    path.write_text('{"queue": []}', encoding="utf-8")
    monkeypatch.setattr(elitedate_state, "_STATE_FILE", path)
    return path


@pytest.fixture
def td_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tinder_state.json"
    path.write_text('{"queue": []}', encoding="utf-8")
    monkeypatch.setattr(tinder_state, "_STATE_FILE", path)
    return path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", ("1", None)),
        ("2", ("2", None)),
        ("3", ("3", None)),
        ("1.", ("1", None)),
        ("2)", ("2", None)),
        ("2️⃣", ("2", None)),
        ("3 Ahoj, idem o 19:00", ("3custom", "Ahoj, idem o 19:00")),
        ("3: Ahoj", ("3custom", "Ahoj")),
        ("   1   ", ("1", None)),
        ("`2`", ("2", None)),
        ("ahoj", None),
        ("", None),
        ("12", None),
        ("4", None),
    ],
)
def test_elitedate_parse_choice_variants(text, expected):
    assert elitedate_dispatch._parse_choice(text) == expected


@pytest.mark.parametrize(
    ("text", "expected_kind"),
    [
        ("1", "1"),
        ("2", "2"),
        ("3", "3"),
        ("1️⃣", "1"),
        ("3 vlastný text", "3custom"),
        ("nezmysel", None),
    ],
)
def test_tinder_parse_choice_variants(text, expected_kind):
    parsed = tinder_dispatch._parse_choice(text)
    if expected_kind is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert parsed[0] == expected_kind


def test_enqueue_promotes_first_to_awaiting(ed_state_file):
    first = elitedate_state.enqueue("c1", "Eva", "Ahoj", ["o1", "o2"])
    second = elitedate_state.enqueue("c2", "Jana", "Čau", ["a", "b"])
    assert first["status"] == "awaiting_selection"
    assert second["status"] == "queued"
    assert elitedate_state.current()["conversation_id"] == "c1"


def test_enqueue_deduplicates_same_message(ed_state_file):
    a = elitedate_state.enqueue("c1", "Eva", "Ahoj", ["o1", "o2"], my_last_message="Q1")
    b = elitedate_state.enqueue("c1", "Eva", "Ahoj", ["x", "y"], my_last_message="Q2")
    assert a["id"] == b["id"]
    assert b["my_last_message"] == "Q2"
    assert len(elitedate_state._load()["queue"]) == 1


def test_resolve_selected_promotes_next(td_state_file):
    e1 = tinder_state.enqueue("c1", "A", "hi", ["1a", "1b"])
    e2 = tinder_state.enqueue("c2", "B", "yo", ["2a", "2b"])
    sent, nxt = tinder_state.resolve_selected(e1, "1a")
    assert sent["status"] == "sent"
    assert sent["chosen_text"] == "1a"
    assert nxt is not None
    assert nxt["conversation_id"] == "c2"
    assert nxt["status"] == "awaiting_selection"
    assert tinder_state.current()["id"] == e2["id"]


def test_resolve_by_prompt_message_id(ed_state_file):
    e1 = elitedate_state.enqueue("c1", "Eva", "Ahoj", ["o1", "o2"])
    e2 = elitedate_state.enqueue("c2", "Jana", "Čau", ["a", "b"])
    elitedate_state.set_prompt_message_id(e2, "msg-222")
    found = elitedate_state.find_by_prompt_message_id("msg-222")
    assert found is not None
    assert found["conversation_id"] == "c2"
    # Head is still e1 awaiting; reply-to e2 should still resolve e2
    sent, nxt = elitedate_state.resolve_selected(found, "custom")
    assert sent["conversation_id"] == "c2"
    assert nxt["conversation_id"] == "c1"


@pytest.mark.asyncio
async def test_handle_selection_option_1(ed_state_file, monkeypatch):
    entry = elitedate_state.enqueue("c1", "Eva", "Ahoj", ["prvá", "druhá"])
    elitedate_state.set_prompt_message_id(entry, "discord-1")

    async def fake_send(*args, **kwargs):
        # Positional: conversation_id, text, ...
        text = kwargs.get("text", args[1] if len(args) > 1 else None)
        assert text == "prvá"
        return "inserted"

    monkeypatch.setattr(elitedate_dispatch, "_send_via_bot", fake_send)
    reply = await elitedate_dispatch.handle_selection("1", replied_to_message_id="discord-1")
    assert reply is not None
    assert "prvá" in reply
    assert "Vložené" in reply or "Odoslané" in reply
    assert elitedate_state.current() is None


@pytest.mark.asyncio
async def test_handle_selection_returns_none_when_idle(ed_state_file):
    assert await elitedate_dispatch.handle_selection("1") is None


@pytest.mark.asyncio
async def test_handle_selection_invalid_when_waiting(ed_state_file):
    elitedate_state.enqueue("c1", "Eva", "Ahoj", ["o1", "o2"])
    assert await elitedate_dispatch.handle_selection("ahoj svete") is None
