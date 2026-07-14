"""chrome_startup_lock scenarios — concurrent startups and timeout."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from elitedate_bot.chrome_lock import chrome_startup_lock as ed_lock
from tinder_bot.chrome_lock import chrome_startup_lock as td_lock


@pytest.mark.parametrize("lock_cls", [ed_lock, td_lock], ids=["elitedate", "tinder"])
def test_lock_acquires_and_releases(lock_cls, tmp_path, monkeypatch):
    lock_path = tmp_path / "chrome.lock"
    monkeypatch.setenv("SELENIUM_CHROME_LOCK", str(lock_path))
    # Re-import path used by the class — patch module-level _LOCK_PATH
    import elitedate_bot.chrome_lock as ed_mod
    import tinder_bot.chrome_lock as td_mod

    mod = ed_mod if lock_cls is ed_lock else td_mod
    monkeypatch.setattr(mod, "_LOCK_PATH", lock_path)

    with lock_cls("bot-a", timeout_sec=2):
        assert lock_path.exists()
        assert lock_path.read_text(encoding="utf-8") == "bot-a"


def test_second_bot_waits_then_acquires(tmp_path, monkeypatch):
    lock_path = tmp_path / "shared.lock"
    import elitedate_bot.chrome_lock as ed_mod
    import tinder_bot.chrome_lock as td_mod

    monkeypatch.setattr(ed_mod, "_LOCK_PATH", lock_path)
    monkeypatch.setattr(td_mod, "_LOCK_PATH", lock_path)

    order: list[str] = []
    hold = threading.Event()
    first_has_lock = threading.Event()

    def holder():
        with ed_lock("elitedate", timeout_sec=10):
            order.append("ed-enter")
            first_has_lock.set()
            hold.wait(timeout=2)
            order.append("ed-exit")

    def waiter():
        first_has_lock.wait(timeout=2)
        with td_lock("tinder", timeout_sec=10):
            order.append("td-enter")

    t1 = threading.Thread(target=holder)
    t2 = threading.Thread(target=waiter)
    t1.start()
    assert first_has_lock.wait(timeout=2)
    t2.start()
    time.sleep(0.2)
    assert "td-enter" not in order
    hold.set()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert order == ["ed-enter", "ed-exit", "td-enter"]


def test_lock_timeout(tmp_path, monkeypatch):
    lock_path = tmp_path / "timeout.lock"
    import elitedate_bot.chrome_lock as ed_mod
    import tinder_bot.chrome_lock as td_mod

    monkeypatch.setattr(ed_mod, "_LOCK_PATH", lock_path)
    monkeypatch.setattr(td_mod, "_LOCK_PATH", lock_path)

    with ed_lock("holder", timeout_sec=5):
        with pytest.raises(TimeoutError, match="Timed out waiting"):
            with td_lock("waiter", timeout_sec=0.5):
                pass
