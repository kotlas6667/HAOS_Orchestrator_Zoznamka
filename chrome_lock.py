from __future__ import annotations

import fcntl
import time
from pathlib import Path

_LOCK_PATH = Path("/data/orchestrator/config/.selenium_chrome.lock")


class chrome_startup_lock:
    """Serialize Chromium startup across elitedate_bot and tinder_bot processes."""

    def __init__(self, owner: str, timeout_sec: float = 180.0) -> None:
        self.owner = owner
        self.timeout_sec = timeout_sec
        self._fd = None

    def __enter__(self) -> chrome_startup_lock:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(_LOCK_PATH, "w", encoding="utf-8")
        deadline = time.time() + self.timeout_sec
        while True:
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd.seek(0)
                self._fd.truncate()
                self._fd.write(self.owner)
                self._fd.flush()
                return self
            except BlockingIOError:
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"Timed out waiting for Chrome startup lock ({self.timeout_sec}s)"
                    ) from None
                time.sleep(2)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            finally:
                self._fd.close()
                self._fd = None
