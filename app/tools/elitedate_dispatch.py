from __future__ import annotations

import re
import unicodedata
from typing import Any

import httpx

from app.config import settings
from app.tools import elitedate_state
from app.tools.elitedate_reply_provider import generate_reply_options
from app.tools.discord_notifier import DiscordNotifier

LOGGER_PREFIX = "[elitedate]"


def _format_prompt(entry: dict[str, Any]) -> str:
    opt1, opt2 = entry["options"][0], entry["options"][1]
    conv_short = entry.get("conversation_id", "")[:8]
    my_last_message = str(entry.get("my_last_message") or "").strip()
    sender = str(entry.get("sender") or "Neznámy").strip()
    their_last_message = str(entry.get("message") or "").strip()
    queue_note = ""
    if entry.get("status") != "awaiting_selection":
        queue_note = "⏳ Táto konverzácia je momentálne vo fronte. Odpovedz priamo na túto správu, ak chceš vybrať odpoveď práve pre ňu.\n"
    my_context = ""
    if my_last_message:
        my_context = f"👤 Tvoja posledná otázka/správa:\n> {my_last_message}\n\n"
    their_context = f"👥 Posledná odpoveď od {sender}:\n> {their_last_message}\n\n"
    return (
        f"💌 **Nová správa na Elite Date od {sender}**\n"
        f"🔒 Vlákno: `{sender} | {conv_short}`\n"
        f"{my_context}"
        f"{their_context}"
        f"{queue_note}"
        f"1️⃣ {opt1}\n"
        f"2️⃣ {opt2}\n\n"
        f"3️⃣ vlastný text - pošli ho ako `3 Tvoj text`\n\n"
        f"Tip: najbezpečnejšie je kliknúť Reply na túto správu a poslať `1/2/3`."
    )


async def _notify_discord(text: str) -> str | None:
    try:
        result = await DiscordNotifier().send_message(text)
        message_id = result.get("message_id")
        if message_id is None:
            return None
        return str(message_id)
    except Exception as exc:  # noqa: BLE001
        print(f"{LOGGER_PREFIX} Failed to notify Discord: {exc}")
        return None


async def handle_incoming(
    conversation_id: str,
    sender: str,
    message: str,
    my_last_message: str = "",
    submit: bool = False,
) -> dict[str, Any]:
    """Called by POST /api/elitedate/incoming when the bot finds a new message."""
    options = await generate_reply_options(message, sender, my_last_message=my_last_message)
    entry = elitedate_state.enqueue(
        conversation_id,
        sender,
        message,
        options,
        my_last_message=my_last_message,
        submit=submit,
    )

    # Do not spam Discord with the same queued entry repeatedly.
    # Duplicate polls can update metadata (e.g. my_last_message), but if a prompt
    # was already posted for this entry, keep using that original message.
    if entry.get("prompt_message_id"):
        return entry

    prompt_message_id = await _notify_discord(_format_prompt(entry))
    if prompt_message_id:
        elitedate_state.set_prompt_message_id(entry, prompt_message_id)

    return entry


async def _send_via_bot(
    conversation_id: str,
    text: str,
    sender: str = "",
    expected_message: str = "",
    submit: bool | None = None,
) -> str:
    """Insert chosen reply into EliteDate input, optionally submit by config."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.elitedate_bot_url}/send",
            json={
                "conversation_id": conversation_id,
                "sender": sender,
                "expected_message": expected_message,
                "text": text,
                "submit": bool(settings.elitedate_auto_send if submit is None else submit),
            },
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            error = str(data.get("error") or "unknown error")
            return f"error:{error}"
        return str(data.get("mode") or "inserted")


def _parse_choice(choice_text: str) -> tuple[str, str | None] | None:
    choice = unicodedata.normalize("NFKC", choice_text or "").strip().strip("`")

    # Accept plain numeric picks and common Discord variants like "2.", "2)", "2️⃣".
    simple_match = re.match(r"^([123])(?:[.)]|\uFE0F\u20E3|\u20E3|\uFE0F)?$", choice)
    if simple_match:
        picked = simple_match.group(1)
        if picked == "1":
            return ("1", None)
        if picked == "2":
            return ("2", None)
        return ("3", None)

    custom_match = re.match(r"^3(?:[.)]|\uFE0F\u20E3|\u20E3|\uFE0F)?\s*[:\-]?\s+(.+)$", choice, flags=re.DOTALL)
    if custom_match:
        return ("3custom", custom_match.group(1).strip())

    if choice.startswith("3:"):
        return ("3custom", choice[2:].strip())
    if choice.startswith("3 "):
        return ("3custom", choice[2:].strip())
    return None


async def handle_selection(choice_text: str, replied_to_message_id: str | None = None) -> str | None:
    """Called from the Discord bot when a message arrives while a conversation is
    awaiting_selection. Returns the reply to send back to Discord, or None if there
    is nothing pending (caller should fall back to normal LLM routing)."""
    parsed = _parse_choice(choice_text)
    if parsed is None:
        return None

    entry = None
    if replied_to_message_id:
        entry = elitedate_state.find_by_prompt_message_id(replied_to_message_id)

    if entry is None:
        entry = elitedate_state.current()

    if entry is None:
        return None

    choice_kind, custom_text = parsed
    if choice_kind == "1":
        chosen_text = entry["options"][0]
    elif choice_kind == "2":
        chosen_text = entry["options"][1]
    elif choice_kind == "3":
        return "📝 Pošli vlastný text ako `3 tvoj text`, napr. `3 Ahoj, dnes sa mi hodí o 19:00`"
    else:
        chosen_text = (custom_text or "").strip()

    if not chosen_text:
        return "⚠️ Vlastný text je prázdny. Pošli napr. `3 Ahoj, ...`"

    try:
        send_mode = await _send_via_bot(
            entry["conversation_id"],
            chosen_text,
            sender=str(entry.get("sender") or ""),
            expected_message=str(entry.get("message") or ""),
            submit=bool(entry.get("submit", settings.elitedate_auto_send)),
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"⚠️ Nepodarilo sa vložiť odpoveď cez bota: {exc}\n"
            f"Posledná zvolená odpoveď: \"{chosen_text}\""
        )

    if send_mode.startswith("error:"):
        detail = send_mode.split(":", 1)[1].strip() or "unknown error"
        return (
            f"⚠️ Bot nahlásil, že vloženie textu zlyhalo: {detail}. Skús to znova alebo over Selenium session.\n"
            f"Posledná zvolená odpoveď: \"{chosen_text}\""
        )

    conv_short = entry.get("conversation_id", "")[:8]
    if send_mode == "sent":
        reply = f"✅ Odoslané do vlákna {entry['sender']} | {conv_short}: \"{chosen_text}\""
    else:
        reply = (
            f"✅ Vložené do textboxu (bez odoslania) pre vlákno {entry['sender']} | {conv_short}: "
            f"\"{chosen_text}\""
        )

    sent_entry, next_entry = elitedate_state.resolve_selected(entry, chosen_text)
    if sent_entry is None:
        return reply

    if next_entry:
        next_prompt_message_id = await _notify_discord(_format_prompt(next_entry))
        if next_prompt_message_id:
            elitedate_state.set_prompt_message_id(next_entry, next_prompt_message_id)

    return reply
