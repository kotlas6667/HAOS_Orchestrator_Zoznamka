from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from datetime import datetime
from uuid import uuid4

_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "tinder_state.json"


def _load() -> dict[str, Any]:
    if _STATE_FILE.exists():
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    return {"queue": []}


def _save(state: dict[str, Any]) -> None:
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("conversation_id", "")),
        str(entry.get("message", "")),
        str(entry.get("created", "")),
    )


def enqueue(
    conversation_id: str,
    sender: str,
    message: str,
    options: list[str],
    my_last_message: str = "",
    submit: bool = False,
) -> dict[str, Any]:
    """Add a new incoming message to the queue. Returns the queue entry."""
    state = _load()

    # Ignore duplicates (bot may re-poll the same message before it's marked seen).
    for entry in state["queue"]:
        if entry["conversation_id"] == conversation_id and entry["message"] == message:
            incoming_last = (my_last_message or "").strip()
            existing_last = str(entry.get("my_last_message") or "").strip()
            if incoming_last and incoming_last != existing_last:
                entry["my_last_message"] = incoming_last
            if submit and not entry.get("submit"):
                entry["submit"] = True
            if incoming_last or submit:
                _save(state)
            return entry

    entry = {
        "id": str(uuid4()),
        "conversation_id": conversation_id,
        "sender": sender,
        "message": message,
        "my_last_message": my_last_message,
        "options": options,
        "status": "queued",
        "submit": submit,
        "prompt_message_id": None,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    state["queue"].append(entry)
    if len(state["queue"]) == 1:
        entry["status"] = "awaiting_selection"
    _save(state)
    return entry


def current() -> dict[str, Any] | None:
    """Return the conversation currently awaiting the user's 1/2 selection, if any."""
    state = _load()
    if state["queue"] and state["queue"][0]["status"] == "awaiting_selection":
        return state["queue"][0]
    return None


def find_by_prompt_message_id(prompt_message_id: str) -> dict[str, Any] | None:
    """Return queued entry mapped to a Discord prompt message id, if any."""
    state = _load()
    target = str(prompt_message_id)
    for entry in state["queue"]:
        if str(entry.get("prompt_message_id") or "") == target:
            return entry
    return None


def set_prompt_message_id(entry: dict[str, Any], prompt_message_id: str) -> bool:
    """Attach Discord prompt message id to a queued entry."""
    state = _load()
    target_identity = _entry_identity(entry)
    for queued in state["queue"]:
        if _entry_identity(queued) == target_identity:
            queued["prompt_message_id"] = str(prompt_message_id)
            _save(state)
            return True
    return False


def update_options(entry: dict[str, Any], options: list[str]) -> dict[str, Any] | None:
    """Replace reply options on a queued entry and return the updated entry."""
    state = _load()
    target_identity = _entry_identity(entry)
    for queued in state["queue"]:
        if _entry_identity(queued) == target_identity:
            queued["options"] = list(options)
            _save(state)
            return queued
    return None


def resolve_selected(entry: dict[str, Any], chosen_text: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve a specific queued entry (not only head), promote head as awaiting_selection."""
    state = _load()
    target_identity = _entry_identity(entry)
    idx = -1

    for i, queued in enumerate(state["queue"]):
        if _entry_identity(queued) == target_identity:
            idx = i
            break

    if idx < 0:
        return None, None

    sent_entry = state["queue"].pop(idx)
    sent_entry["status"] = "sent"
    sent_entry["chosen_text"] = chosen_text

    next_entry = None
    if state["queue"]:
        for queued in state["queue"]:
            queued["status"] = "queued"
        state["queue"][0]["status"] = "awaiting_selection"
        next_entry = state["queue"][0]

    _save(state)
    return sent_entry, next_entry
