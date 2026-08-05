"""Shared Discord prompt layout for dating-app reply handoff (ED / Tinder / Badoo)."""

from __future__ import annotations

from typing import Any

# DiscordNotifier also caps at 1900; keep choices block inside the limit.
DISCORD_CONTENT_LIMIT = 1900


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _discord_quote(text: str) -> str:
    lines = (text or "").splitlines() or [""]
    return "\n".join(f"> {line}" if line else ">" for line in lines)


def format_dating_prompt(entry: dict[str, Any], *, app_emoji: str, app_name: str) -> str:
    """Build Discord text with AI choices first so truncation never hides 1–4."""
    options = list(entry.get("options") or [])
    while len(options) < 4:
        options.append("(prázdna odpoveď)")
    opt1, opt2, opt3, opt4 = options[0], options[1], options[2], options[3]

    conv_short = str(entry.get("conversation_id", ""))[:8]
    sender = str(entry.get("sender") or "Neznámy").strip()
    my_last_message = str(entry.get("my_last_message") or "").strip()
    their_last_message = str(entry.get("message") or "").strip()

    queue_note = ""
    if entry.get("status") != "awaiting_selection":
        queue_note = (
            "⏳ Táto konverzácia je momentálne vo fronte. Odpovedz priamo na túto správu, "
            "ak chceš vybrať odpoveď práve pre ňu.\n"
        )

    choices_block = (
        "**AI návrhy (vyber 1–4):**\n"
        f"1️⃣ {opt1}\n"
        f"2️⃣ {opt2}\n"
        f"3️⃣ {opt3}\n"
        f"4️⃣ {opt4}\n\n"
        f"5️⃣ voľná odpoveď — pošli ju ako `5 Tvoj text`\n"
        f"6️⃣ nové návrhy od AI\n\n"
        f"Tip: Reply na túto správu a pošli `1`–`6`."
    )

    headline = f"{app_emoji} **Nová správa na {app_name} od {sender}**"
    header = f"{headline}\n🔒 Vlákno: `{sender} | {conv_short}`\n\n{choices_block}\n"

    context_intro = "**Kontext:**\n"
    footer = ""
    fixed_len = len(header) + len(context_intro) + len(footer)
    budget = max(200, DISCORD_CONTENT_LIMIT - fixed_len)

    my_block = ""
    if my_last_message:
        my_block = f"👤 Tvoja posledná otázka/správa:\n{_discord_quote(my_last_message)}\n\n"
    their_block = f"👥 Posledná odpoveď od {sender}:\n{_discord_quote(their_last_message)}\n"
    queue_block = f"\n{queue_note}" if queue_note else ""

    context = my_block + their_block + queue_block
    if len(context) > budget:
        # Shrink quoted messages proportionally; never truncate the choice block above.
        if my_block:
            my_budget = min(len(my_block), budget // 2)
            my_block = (
                f"👤 Tvoja posledná otázka/správa:\n"
                f"{_discord_quote(_truncate(my_last_message, my_budget))}\n\n"
            )
        remaining = max(80, budget - len(my_block) - len(queue_block))
        their_block = (
            f"👥 Posledná odpoveď od {sender}:\n"
            f"{_discord_quote(_truncate(their_last_message, remaining))}\n"
        )
        context = my_block + their_block + queue_block

    text = header + context_intro + context
    return text[:DISCORD_CONTENT_LIMIT]
