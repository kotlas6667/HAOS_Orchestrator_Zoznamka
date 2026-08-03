from __future__ import annotations

import base64
import re
import unicodedata
from typing import Any

import httpx

from app.config import settings
from app.tools import badoo_state
from app.tools.badoo_reply_provider import generate_reply_options
from app.tools.discord_notifier import DiscordNotifier

LOGGER_PREFIX = "[badoo]"

_REGENERATE_RE = re.compile(
    r"(?:"
    r"^4(?:[.)]|️⃣|⃣|️)?$"
    r"|navrhni\s+(?:dalsie|ďalšie)(?:\s+odpovede?)?"
    r"|(?:dalsie|ďalšie)\s+(?:odpovede?|navrhy|návrhy)"
    r"|nove?\s+navrhy"
    r"|nové\s+návrhy"
    r"|regener(?:ate|uj)(?:\s+odpovede?)?"
    r")",
    re.IGNORECASE,
)


def _discord_quote(text: str) -> str:
    """Quote every line so multi-paragraph messages stay visible in Discord."""
    lines = (text or "").splitlines() or [""]
    return "\n".join(f"> {line}" if line else ">" for line in lines)


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
        my_context = f"👤 Tvoja posledná otázka/správa:\n{_discord_quote(my_last_message)}\n\n"
    their_context = f"👥 Posledná odpoveď od {sender}:\n{_discord_quote(their_last_message)}\n\n"
    return (
        f"💜 **Nová správa na Badoo od {sender}**\n"
        f"🔒 Vlákno: `{sender} | {conv_short}`\n"
        f"{my_context}"
        f"{their_context}"
        f"{queue_note}"
        f"1️⃣ {opt1}\n"
        f"2️⃣ {opt2}\n\n"
        f"3️⃣ vlastný text - pošli ho ako `3 Tvoj text`\n"
        f"4️⃣ nové návrhy odpovedí\n\n"
        f"Tip: najbezpečnejšie je kliknúť Reply na túto správu a poslať `1/2/3/4`."
    )


def _decode_photo_payload(
    photo_base64: str = "",
    photo_content_type: str = "",
    photo_url: str = "",
) -> tuple[bytes | None, str, str]:
    raw = (photo_base64 or "").strip()
    if raw:
        try:
            data = base64.b64decode(raw, validate=False)
        except Exception:  # noqa: BLE001
            data = b""
        if data:
            ctype = (photo_content_type or "image/jpeg").split(";")[0].strip() or "image/jpeg"
            ext = "jpg"
            if "png" in ctype:
                ext = "png"
            elif "webp" in ctype:
                ext = "webp"
            elif "gif" in ctype:
                ext = "gif"
            return data, f"profile.{ext}", ctype
    _ = photo_url
    return None, "profile.jpg", "image/jpeg"


async def _notify_discord(
    text: str,
    *,
    photo_base64: str = "",
    photo_content_type: str = "",
    photo_url: str = "",
) -> str | None:
    try:
        image_bytes, filename, ctype = _decode_photo_payload(
            photo_base64, photo_content_type, photo_url
        )
        content = text
        if image_bytes is None and (photo_url or "").strip():
            content = f"{text}\n{photo_url.strip()}"
        result = await DiscordNotifier().send_message(
            content,
            image_bytes=image_bytes,
            image_filename=filename,
            image_content_type=ctype,
        )
        message_id = result.get("message_id")
        if message_id is None:
            return None
        return str(message_id)
    except Exception as exc:  # noqa: BLE001
        print(f"{LOGGER_PREFIX} Failed to notify Discord: {exc}")
        if photo_base64 or photo_url:
            try:
                result = await DiscordNotifier().send_message(text)
                message_id = result.get("message_id")
                return str(message_id) if message_id else None
            except Exception as exc2:  # noqa: BLE001
                print(f"{LOGGER_PREFIX} Discord text fallback failed: {exc2}")
        return None


async def handle_incoming(
    conversation_id: str,
    sender: str,
    message: str,
    my_last_message: str = "",
    submit: bool = False,
    history: list[dict[str, Any]] | None = None,
    photo_url: str = "",
    photo_base64: str = "",
    photo_content_type: str = "",
) -> dict[str, Any]:
    """Called by POST /api/badoo/incoming when the bot finds a new message."""
    options = await generate_reply_options(
        message,
        sender,
        my_last_message=my_last_message,
        history=history,
    )
    entry = badoo_state.enqueue(
        conversation_id,
        sender,
        message,
        options,
        my_last_message=my_last_message,
        submit=submit,
        history=history,
    )
    if photo_url:
        entry["photo_url"] = photo_url

    # Do not spam Discord with the same queued entry repeatedly.
    # Duplicate polls can update metadata (e.g. my_last_message), but if a prompt
    # was already posted for this entry, keep using that original message.
    if entry.get("prompt_message_id"):
        return entry

    prompt_message_id = await _notify_discord(
        _format_prompt(entry),
        photo_base64=photo_base64,
        photo_content_type=photo_content_type,
        photo_url=photo_url or str(entry.get("photo_url") or ""),
    )
    if prompt_message_id:
        badoo_state.set_prompt_message_id(entry, prompt_message_id)

    return entry


async def _send_via_bot(
    conversation_id: str,
    text: str,
    sender: str = "",
    expected_message: str = "",
    submit: bool | None = None,
) -> str:
    """Insert chosen reply into Badoo input, optionally submit by config.

    Timeout must cover Selenium navigation + optional wait on driver_lock while
    the poller holds Chrome (10s was too short → empty httpx.ReadTimeout).
    """
    url = f"{settings.badoo_bot_url.rstrip('/')}/send"
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                url,
                json={
                    "conversation_id": conversation_id,
                    "sender": sender,
                    "expected_message": expected_message,
                    "text": text,
                    "submit": bool(settings.badoo_auto_send if submit is None else submit),
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        detail = str(exc).strip() or "ReadTimeout"
        raise RuntimeError(
            f"timeout po 90s pri volaní {url} ({detail}) — bot asi drží Chrome (poll) "
            "alebo Selenium dlho otvára chat"
        ) from exc
    except httpx.HTTPError as exc:
        detail = str(exc).strip() or type(exc).__name__
        raise RuntimeError(f"HTTP chyba pri {url}: {detail}") from exc

    if data.get("status") != "success":
        error = str(data.get("error") or "unknown error").strip() or "unknown error"
        return f"error:{error}"
    return str(data.get("mode") or "inserted")


def is_regenerate_request(choice_text: str) -> bool:
    """True when the user asks for fresh reply suggestions."""
    choice = unicodedata.normalize("NFKC", choice_text or "").strip().strip("`")
    if not choice:
        return False
    if re.match(r"^4(?:[.)]|️⃣|⃣|️)?$", choice):
        return True
    # Strip diacritics for fuzzy Slovak matching.
    ascii_choice = "".join(
        c for c in unicodedata.normalize("NFKD", choice.lower()) if not unicodedata.combining(c)
    )
    return bool(_REGENERATE_RE.search(choice) or _REGENERATE_RE.search(ascii_choice))


def _parse_choice(choice_text: str) -> tuple[str, str | None] | None:
    choice = unicodedata.normalize("NFKC", choice_text or "").strip().strip("`")

    if is_regenerate_request(choice):
        return ("regenerate", None)

    # Accept plain numeric picks and common Discord variants like "2.", "2)", "2️⃣".
    simple_match = re.match(r"^([123])(?:[.)]|️⃣|⃣|️)?$", choice)
    if simple_match:
        picked = simple_match.group(1)
        if picked == "1":
            return ("1", None)
        if picked == "2":
            return ("2", None)
        return ("3", None)

    custom_match = re.match(r"^3(?:[.)]|️⃣|⃣|️)?\s*[:\-]?\s+(.+)$", choice, flags=re.DOTALL)
    if custom_match:
        return ("3custom", custom_match.group(1).strip())

    if choice.startswith("3:"):
        return ("3custom", choice[2:].strip())
    if choice.startswith("3 "):
        return ("3custom", choice[2:].strip())
    return None


def _resolve_entry(replied_to_message_id: str | None = None) -> dict[str, Any] | None:
    entry = None
    if replied_to_message_id:
        entry = badoo_state.find_by_prompt_message_id(replied_to_message_id)
    if entry is None:
        entry = badoo_state.current()
    return entry


async def regenerate_suggestions(replied_to_message_id: str | None = None) -> str | None:
    """Generate fresh options and re-post the Discord prompt for the same thread."""
    entry = _resolve_entry(replied_to_message_id)
    if entry is None:
        return None

    previous_options = list(entry.get("options") or [])
    try:
        options = await generate_reply_options(
            str(entry.get("message") or ""),
            str(entry.get("sender") or ""),
            my_last_message=str(entry.get("my_last_message") or ""),
            previous_options=previous_options,
            history=list(entry.get("history") or []),
        )
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ Nepodarilo sa vygenerovať nové návrhy: {exc}"

    updated = badoo_state.update_options(entry, options)
    if updated is None:
        return "⚠️ Konverzácia už nie je vo fronte — nové návrhy sa nepodarilo uložiť."

    prompt_message_id = await _notify_discord(_format_prompt(updated))
    if prompt_message_id:
        badoo_state.set_prompt_message_id(updated, prompt_message_id)

    conv_short = str(updated.get("conversation_id") or "")[:8]
    sender = str(updated.get("sender") or "Neznámy")
    return f"🔄 Nové návrhy pre `{sender} | {conv_short}` sú vyššie. Vyber `1/2/3` alebo znova `4`."


async def handle_selection(choice_text: str, replied_to_message_id: str | None = None) -> str | None:
    """Called from the Discord bot when a message arrives while a conversation is
    awaiting_selection. Returns the reply to send back to Discord, or None if there
    is nothing pending (caller should fall back to normal LLM routing)."""
    parsed = _parse_choice(choice_text)
    if parsed is None:
        return None

    choice_kind, custom_text = parsed
    if choice_kind == "regenerate":
        return await regenerate_suggestions(replied_to_message_id)

    entry = _resolve_entry(replied_to_message_id)
    if entry is None:
        return None
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
            # entry.submit z pollera je často false — OR s Nastaveniami Orchestrátora
            submit=bool(entry.get("submit")) or bool(settings.badoo_auto_send),
        )
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or type(exc).__name__
        print(f"{LOGGER_PREFIX} /send failed: {detail}")
        return (
            f"⚠️ Nepodarilo sa vložiť odpoveď cez bota: {detail}\n"
            f"URL: `{settings.badoo_bot_url}` · auto_send={settings.badoo_auto_send}\n"
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
            f"\"{chosen_text}\"\n"
            f"ℹ️ Auto odoslanie je vypnuté — zapni **Auto odoslať odpoveď** v Nastaveniach "
            f"**Badoo bota** a/alebo **Badoo — auto odoslať** v Orchestrátore, potom reštartuj."
        )

    sent_entry, next_entry = badoo_state.resolve_selected(entry, chosen_text)
    if sent_entry is None:
        return reply

    if next_entry:
        next_prompt_message_id = await _notify_discord(_format_prompt(next_entry))
        if next_prompt_message_id:
            badoo_state.set_prompt_message_id(next_entry, next_prompt_message_id)

    return reply
