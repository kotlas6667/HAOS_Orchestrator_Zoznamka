from __future__ import annotations

import os
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]

_LOCK_PATH = Path(os.environ.get("SELENIUM_CHROME_LOCK", "/tmp/selenium_chrome.lock"))
if sys.platform == "win32":
    _LOCK_PATH = Path(os.environ.get("SELENIUM_CHROME_LOCK", str(Path.cwd() / ".selenium_chrome.lock")))


class chrome_startup_lock:
    """Serialize Chromium startups when multiple processes share one host.

    Uses fcntl on Linux (HAOS add-ons) and msvcrt on Windows (local capture).
    """

    def __init__(self, owner: str, timeout_sec: float = 180.0) -> None:
        self.owner = owner
        self.timeout_sec = timeout_sec
        self._fd = None

    def __enter__(self) -> chrome_startup_lock:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(_LOCK_PATH, "a+", encoding="utf-8")
        deadline = time.time() + self.timeout_sec
        while True:
            try:
                self._acquire()
                self._fd.seek(0)
                self._fd.truncate()
                self._fd.write(self.owner)
                self._fd.flush()
                return self
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"Timed out waiting for Chrome startup lock ({self.timeout_sec}s)"
                    ) from None
                time.sleep(0.5)

    def _acquire(self) -> None:
        assert self._fd is not None
        if fcntl is not None:
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        if msvcrt is not None:
            self._fd.seek(0)
            if self._fd.read(1) == "":
                self._fd.write("0")
                self._fd.flush()
            self._fd.seek(0)
            msvcrt.locking(self._fd.fileno(), msvcrt.LK_NBLCK, 1)
            return
        return

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None:
            try:
                if fcntl is not None:
                    fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:
                    try:
                        self._fd.seek(0)
                        msvcrt.locking(self._fd.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
            finally:
                self._fd.close()
                self._fd = None
