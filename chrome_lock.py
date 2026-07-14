"""Backward-compatible re-export.

Prefer importing from elitedate_bot.chrome_lock / tinder_bot.chrome_lock.
Kept so older local scripts that did ``from chrome_lock import ...`` still work.
"""

from __future__ import annotations

try:
    from elitedate_bot.chrome_lock import chrome_startup_lock
except ImportError:  # pragma: no cover
    from tinder_bot.chrome_lock import chrome_startup_lock

__all__ = ["chrome_startup_lock"]
