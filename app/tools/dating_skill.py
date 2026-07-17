"""Shared Elite Date + Tinder reply skill (persona / tone for AI drafts)."""

from __future__ import annotations

from pathlib import Path

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
