"""Daily morning greet on Elite Date „Noví členovia“.

When enabled in settings, once per day at the configured hour the bot:
1. opens /ucet/novi-clenove and applies the search filter if needed,
2. walks unique profile cards (up to morning_greet_max_profiles),
3. opens „Napísať správu“ and sends „Ahoj :-)“ only when the thread is empty.

Processed profile IDs are persisted so the same person is not re-opened forever.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from elitedate_bot import shared_state
from elitedate_bot.config import settings
from elitedate_bot.session import run_client_method

_GREETED_FILE = Path(settings.seen_messages_file).parent / ".morning_greeted.json"


def _load_state() -> dict:
    if _GREETED_FILE.exists():
        try:
            data = json.loads(_GREETED_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
    return {"profile_ids": [], "last_run_date": ""}


def _save_state(state: dict) -> None:
    _GREETED_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GREETED_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_greeted_ids() -> set[str]:
    state = _load_state()
    ids = state.get("profile_ids") or []
    return {str(x) for x in ids if x}


def mark_greeted(profile_ids: set[str], *, last_run_date: str | None = None) -> None:
    state = _load_state()
    existing = {str(x) for x in (state.get("profile_ids") or []) if x}
    existing.update(profile_ids)
    state["profile_ids"] = sorted(existing)
    if last_run_date is not None:
        state["last_run_date"] = last_run_date
    _save_state(state)


def already_ran_today(today: str | None = None) -> bool:
    day = today or datetime.now().strftime("%Y-%m-%d")
    return _load_state().get("last_run_date") == day


async def morning_greet_loop() -> None:
    """Wait until the configured morning hour, then run one greet cycle per day."""
    if not settings.morning_greet_enabled:
        print("[elitedate_bot] Morning greet disabled (MORNING_GREET_ENABLED=false).")
        return

    hour = max(0, min(23, int(settings.morning_greet_hour)))
    minute = max(0, min(59, int(settings.morning_greet_minute)))
    print(
        f"[elitedate_bot] Morning greet enabled — daily at {hour:02d}:{minute:02d}, "
        f"max {settings.morning_greet_max_profiles} profiles."
    )

    while True:
        if not settings.morning_greet_enabled:
            await asyncio.sleep(60)
            continue

        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_s = (target - now).total_seconds()
        print(f"[elitedate_bot] Morning greet next run in {wait_s / 3600:.1f}h ({target.isoformat(timespec='minutes')})")
        await asyncio.sleep(wait_s)

        if not settings.morning_greet_enabled:
            continue

        today = datetime.now().strftime("%Y-%m-%d")
        if already_ran_today(today):
            print(f"[elitedate_bot] Morning greet already ran on {today}, skipping.")
            continue

        if shared_state.client is None:
            print("[elitedate_bot] Morning greet skipped — client not ready.")
            continue

        try:
            result = await run_morning_greet_once()
            mark_greeted(set(result.get("processed_ids") or []), last_run_date=today)
            print(
                "[elitedate_bot] Morning greet done: "
                f"checked={result.get('checked', 0)} "
                f"sent={result.get('sent', 0)} "
                f"skipped_history={result.get('skipped_history', 0)} "
                f"skipped_known={result.get('skipped_known', 0)} "
                f"errors={result.get('errors', 0)}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[elitedate_bot] Morning greet failed: {exc}")


async def run_morning_greet_once() -> dict:
    """Run one greet cycle under the shared Selenium lock (for scheduler + debug)."""
    already = load_greeted_ids()
    max_profiles = max(1, int(settings.morning_greet_max_profiles))
    async with shared_state.driver_lock:
        result = await run_client_method(
            "run_morning_greet",
            max_profiles=max_profiles,
            already_greeted=already,
            greeting_text=settings.morning_greet_message,
        )
    # Persist IDs immediately even if caller forgets (debug endpoint).
    processed = set(result.get("processed_ids") or [])
    if processed:
        mark_greeted(processed)
    return result
