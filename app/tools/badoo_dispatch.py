from __future__ import annotations

import base64
import re
import unicodedata
from typing import Any

import httpx

from app.config import settings
from app.tools.audio_transcription import transcribe_audio
from app.tools import badoo_state
from app.tools.badoo_reply_provider import generate_reply_options
from app.tools.discord_notifier import DiscordNotifier
from app.tools.dating_discord_prompt import format_dating_prompt

LOGGER_PREFIX = "[badoo]"

_REGENERATE_RE = re.compile(
    r"(?:"
    r"^6(?:[.)]|️⃣|⃣|️)?$"
    r"|navrhni\s+(?:dalsie|ďalšie)(?:\s+odpovede?)?"
    r"|(?:dalsie|ďalšie)\s+(?:odpovede?|navrhy|návrhy)"
    r"|nove?\s+navrhy"
    r"|nové\s+návrhy"
    r"|regener(?:ate|uj)(?:\s+odpovede?)?"
    r")",
    re.IGNORECASE,
)


def _format_prompt(entry: dict[str, Any]) -> str:
    return format_dating_prompt(entry, app_emoji="💜", app_name="Badoo")


def _normalize_provider_name(provider: str) -> str:
    normalized = unicodedata.normalize("NFKC", provider or "").strip().lower()
    if normalized in {"gpt", "openai", "chatgpt"}:
        return "openai"
    if normalized in {"gemini", "google"}:
        return "gemini"
    return ""


def _default_provider() -> str:
    return _normalize_provider_name(settings.dating_reply_provider) or "openai"


def _provider_label(provider: str) -> str:
    normalized = _normalize_provider_name(provider)
    if normalized == "gemini":
        return "gemini"
    return "openai"


def _provider_model(provider: str) -> str:
    normalized = _normalize_provider_name(provider)
    if normalized == "gemini":
        return str(settings.dating_reply_gemini_model or "gemini-2.5-flash")
    return str(settings.dating_reply_model or settings.openai_model or "gpt-4o")


async def _post_prompt(
    entry: dict[str, Any],
    *,
    photo_base64: str = "",
    photo_content_type: str = "",
    photo_url: str = "",
    edit_existing: bool = False,
) -> str | None:
    text = _format_prompt(entry)
    existing_id = str(entry.get("prompt_message_id") or "").strip()
    if edit_existing and existing_id:
        try:
            await DiscordNotifier().edit_message(existing_id, text)
            return existing_id
        except Exception as exc:  # noqa: BLE001
            print(f"{LOGGER_PREFIX} Discord edit failed, posting new prompt: {exc}")

    return await _notify_discord(
        text,
        photo_base64=photo_base64,
        photo_content_type=photo_content_type,
        photo_url=photo_url or str(entry.get("photo_url") or ""),
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
    message_type: str = "text",
    audio_base64: str = "",
    audio_content_type: str = "",
) -> dict[str, Any]:
    """Called by POST /api/badoo/incoming when the bot finds a new message."""
    normalized_message_type = str(message_type or "text").strip().lower() or "text"
    effective_message = message
    transcribed_text = ""
    transcription_failed = False
    if normalized_message_type == "audio":
        if audio_base64.strip():
            try:
                transcript = await transcribe_audio(
                    audio_base64=audio_base64,
                    audio_content_type=audio_content_type,
                )
                transcribed_text = str(transcript.get("text") or "").strip()
                if transcribed_text:
                    effective_message = transcribed_text
            except Exception as exc:  # noqa: BLE001
                transcription_failed = True
                effective_message = f"[Audio správa — prepis zlyhal: {exc}]"
        else:
            transcription_failed = True
            effective_message = "[Audio správa — nepodarilo sa vytiahnuť audio súbor z Badoo DOM]"

    option_provider = _default_provider()
    if transcription_failed:
        options = [
            "Pošli `6 gemini` po doplnení API kľúča a skús nový návrh znova.",
            "Pošli `5` a napíš vlastnú odpoveď podľa obsahu audio správy.",
            "Otvor Badoo a vypočuj si správu ručne, potom pošli `5 tvoj text`.",
            "Skús preposlať túto správu znova cez debug flow, ak bol problém len pri prepise.",
        ]
    else:
        options = await generate_reply_options(
            effective_message,
            sender,
            my_last_message=my_last_message,
            history=history,
            provider=option_provider,
        )
    entry = badoo_state.enqueue(
        conversation_id,
        sender,
        effective_message,
        options,
        my_last_message=my_last_message,
        submit=submit,
        history=history,
        option_provider=option_provider,
        option_model=_provider_model(option_provider),
        message_type=normalized_message_type,
        transcribed_text=transcribed_text,
    )
    if photo_url:
        entry["photo_url"] = photo_url

    # Do not spam Discord with the same queued entry repeatedly.
    # Duplicate polls can update metadata (e.g. my_last_message), but if a prompt
    # was already posted for this entry, keep using that original message.
    if entry.get("prompt_message_id"):
        return entry

    prompt_message_id = await _post_prompt(
        entry,
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
    if re.match(r"^6(?:[.)]|️⃣|⃣|️)?$", choice):
        return True
    # Strip diacritics for fuzzy Slovak matching.
    ascii_choice = "".join(
        c for c in unicodedata.normalize("NFKD", choice.lower()) if not unicodedata.combining(c)
    )
    return bool(_REGENERATE_RE.search(choice) or _REGENERATE_RE.search(ascii_choice))


def _parse_choice(choice_text: str) -> tuple[str, str | None] | None:
    choice = unicodedata.normalize("NFKC", choice_text or "").strip().strip("`")
    lowered = choice.lower()

    provider_only = _normalize_provider_name(choice)
    if provider_only:
        return ("regenerate_provider", provider_only)

    if is_regenerate_request(choice):
        return ("regenerate", None)

    regen_provider_match = re.match(
        r"^6(?:[.)]|️⃣|⃣|️)?\s+(gemini|gpt|openai|chatgpt|google)$",
        lowered,
    )
    if regen_provider_match:
        return ("regenerate_provider", _normalize_provider_name(regen_provider_match.group(1)))

    # Accept plain numeric picks and common Discord variants like "2.", "2)", "2️⃣".
    simple_match = re.match(r"^([123456])(?:[.)]|️⃣|⃣|️)?$", choice)
    if simple_match:
        picked = simple_match.group(1)
        if picked in {"1", "2", "3", "4"}:
            return (picked, None)
        if picked == "5":
            return ("5", None)
        return ("regenerate", None)

    custom_match = re.match(r"^5(?:[.)]|️⃣|⃣|️)?\s*[:\-]?\s+(.+)$", choice, flags=re.DOTALL)
    if custom_match:
        return ("5custom", custom_match.group(1).strip())

    if choice.startswith("5:"):
        return ("5custom", choice[2:].strip())
    if choice.startswith("5 "):
        return ("5custom", choice[2:].strip())
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
    return await regenerate_suggestions_with_provider(replied_to_message_id=replied_to_message_id)


async def regenerate_suggestions_with_provider(
    replied_to_message_id: str | None = None,
    provider: str = "",
) -> str | None:
    """Generate fresh options and re-post the Discord prompt for the same thread."""
    entry = _resolve_entry(replied_to_message_id)
    if entry is None:
        return None

    previous_options = list(entry.get("options") or [])
    chosen_provider = _normalize_provider_name(provider) or _default_provider()
    try:
        options = await generate_reply_options(
            str(entry.get("message") or ""),
            str(entry.get("sender") or ""),
            my_last_message=str(entry.get("my_last_message") or ""),
            previous_options=previous_options,
            history=list(entry.get("history") or []),
            provider=chosen_provider,
        )
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ Nepodarilo sa vygenerovať nové návrhy: {exc}"

    updated = badoo_state.update_options(entry, options)
    if updated is None:
        return "⚠️ Konverzácia už nie je vo fronte — nové návrhy sa nepodarilo uložiť."

    updated = (
        badoo_state.update_metadata(
            updated,
            option_provider=_provider_label(chosen_provider),
            option_model=_provider_model(chosen_provider),
        )
        or updated
    )
    prompt_message_id = await _post_prompt(updated, edit_existing=True)
    if prompt_message_id:
        badoo_state.set_prompt_message_id(updated, prompt_message_id)

    conv_short = str(updated.get("conversation_id") or "")[:8]
    sender = str(updated.get("sender") or "Neznámy")
    return (
        f"🔄 Nové návrhy pre `{sender} | {conv_short}` boli aktualizované v pôvodnej správe "
        f"cez `{_provider_label(chosen_provider)}`. "
        f"Vyber `1/2/3/4`, voľnú `5 text`, alebo znova `6`."
    )


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
    if choice_kind == "regenerate_provider":
        return await regenerate_suggestions_with_provider(
            replied_to_message_id=replied_to_message_id,
            provider=custom_text or "",
        )

    entry = _resolve_entry(replied_to_message_id)
    if entry is None:
        return None
    if choice_kind in {"1", "2", "3", "4"}:
        idx = int(choice_kind) - 1
        options = list(entry.get("options") or [])
        if idx >= len(options):
            return "⚠️ Tento návrh nie je k dispozícii. Pošli `6` pre nové návrhy od AI."
        chosen_text = options[idx]
    elif choice_kind == "5":
        return "📝 Pošli voľnú odpoveď ako `5 tvoj text`, napr. `5 Ahoj, dnes sa mi hodí o 19:00`"
    else:
        chosen_text = (custom_text or "").strip()

    if not chosen_text:
        return "⚠️ Voľná odpoveď je prázdna. Pošli napr. `5 Ahoj, ...`"

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
        next_prompt_message_id = await _post_prompt(next_entry)
        if next_prompt_message_id:
            badoo_state.set_prompt_message_id(next_entry, next_prompt_message_id)

    return reply
