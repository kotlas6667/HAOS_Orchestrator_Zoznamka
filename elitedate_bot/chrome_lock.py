from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

_LOCK_PATH = Path(os.environ.get("SELENIUM_CHROME_LOCK", "/tmp/selenium_chrome.lock"))


class chrome_startup_lock:
    """Serialize Chromium startups when multiple processes share one host.

    In the dedicated HA add-on (one Chrome per container) this is effectively
    a no-op — still useful for local/systemd co-hosting with tinder_bot.
    """

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
