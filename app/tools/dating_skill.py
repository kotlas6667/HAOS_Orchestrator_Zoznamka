"""Shared Elite Date + Tinder reply skill (persona / tone for AI drafts)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings

# Writable HAOS path first; symlink targets /app/... after run.sh.
_USER_SKILL_CANDIDATES = (
    Path("/data/orchestrator/config/dating_reply_skill.md"),
    Path("/app/dating_reply_skill.user.md"),
    Path("dating_reply_skill.user.md"),
    # legacy split skills (pre 1.2.13)
    Path("/data/orchestrator/config/elitedate_reply_skill.md"),
    Path("/data/orchestrator/config/tinder_reply_skill.md"),
    Path("/app/elitedate_reply_skill.user.md"),
    Path("/app/tinder_reply_skill.user.md"),
)

_WRITE_PATH = Path("/data/orchestrator/config/dating_reply_skill.md")
_WRITE_FALLBACK = Path("dating_reply_skill.user.md")

# Keep drafts varied, but low enough that Slovak inflections stay stable.
DATING_REPLY_TEMPERATURE = 0.55
DATING_REPLY_REGENERATE_TEMPERATURE = 0.65
DATING_REPLY_RETRY_TEMPERATURE = 0.5

SLOVAK_REPLY_GRAMMAR_RULES = """\
Slovenčina (povinné, má prednosť pred „kreatívnym“ tónom):
- Správne skloňovanie: pád, rod, číslo a predložkové väzby (na + akuzatív, s + inštrumentál, v + lokál).
- Zakázané lámané tvary, napr. „na káva“, „ísť na kino“, „s tebou stretnúť“, „poď na pivo so mňa“.
- Hovorový jazyk a skratky OK, ale tvary musia byť ako od rodilého hovorcu.
- Ak si nie istý tvarom, napíš kratšiu vetu, ktorú vieš skloňovať správne.
- Skill z dashboardu dodrž presne (persona, hranice, fakty) — nevymýšľaj proti nemu.
"""


def dating_reply_temperature(*, regenerate: bool = False) -> float:
    return DATING_REPLY_REGENERATE_TEMPERATURE if regenerate else DATING_REPLY_TEMPERATURE


def resolve_dating_reply_model() -> str:
    """Prefer a stronger GPT for drafts; treat the old default gpt-4o as gpt-4.1."""
    raw = (settings.dating_reply_model or "").strip()
    if not raw or raw in {"gpt-4o", "gpt-4"}:
        return "gpt-4.1"
    return raw


def skill_write_path() -> Path:
    """Path used by dashboard PUT — prefer persistent HAOS config dir."""
    if Path("/data").exists():
        _WRITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        return _WRITE_PATH
    return _WRITE_FALLBACK


def read_user_skill_file() -> tuple[str, str | None]:
    """Return (content, path_str_or_None) from the first non-empty user skill file."""
    for path in _USER_SKILL_CANDIDATES:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                if text.strip():
                    return text, str(path)
        except Exception:  # noqa: BLE001
            continue
    # Empty primary file still counts as "loaded" for the editor.
    primary = skill_write_path()
    if primary.is_file():
        try:
            return primary.read_text(encoding="utf-8"), str(primary)
        except Exception:  # noqa: BLE001
            pass
    return "", None


def save_user_skill(content: str) -> str:
    """Persist multiline skill; returns path written."""
    path = skill_write_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Normalize: keep user's newlines; ensure trailing newline for editors.
    text = content.replace("\r\n", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return str(path)


def load_reply_skill(*, bundled_path: Path, fallback: str) -> str:
    """Priority: dashboard/sidecar file → HA/env one-liner → bundled md → fallback."""
    file_text, _ = read_user_skill_file()
    if file_text.strip():
        return file_text.strip()

    from_settings = (settings.dating_reply_skill or "").strip()
    if from_settings:
        return from_settings

    if bundled_path.is_file():
        bundled = bundled_path.read_text(encoding="utf-8").strip()
        if bundled:
            return bundled
    return fallback


def format_chat_history_for_prompt(
    history: list[dict[str, Any]] | None,
    *,
    sender: str = "Ona",
    max_turns: int = 24,
) -> str:
    """Format [{role: me|them, text}] into a readable transcript for GPT."""
    if not history:
        return ""
    lines: list[str] = []
    for turn in history[-max_turns:]:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        role = str(turn.get("role") or "").strip().lower()
        who = "Ty" if role in {"me", "user", "self", "sender"} else (sender or "Ona")
        lines.append(f"{who}: {text}")
    return "\n".join(lines).strip()


def parse_dating_reply_json(content: str, fallback: list[str]) -> list[str]:
    """Parse GPT JSON with option_1..option_4; pad missing slots from fallback."""
    import json
    import re

    empty = "(prázdna odpoveď)"
    json_match = re.search(r"\{.*\}", content or "", re.DOTALL)
    if not json_match:
        text = (content or "").strip() or (fallback[0] if fallback else empty)
        return [text, text, text, text]

    parsed = json.loads(json_match.group())
    options = [
        str(parsed.get(f"option_{i}", "") or "").strip() or empty for i in range(1, 5)
    ]
    filled = {o for o in options if o != empty}
    if len(filled) < 4 and fallback:
        for candidate in fallback:
            if len(filled) >= 4:
                break
            if candidate in filled:
                continue
            for idx, current in enumerate(options):
                if current == empty:
                    options[idx] = candidate
                    filled.add(candidate)
                    break
    return options[:4]
