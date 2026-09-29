"""Regression: sequential WebDriverWait per CSS burned 30s×N and exceeded /send timeout."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock

from selenium.common.exceptions import TimeoutException

from tinder_bot.tinder_client import TinderClient


class _FakeSettings:
    wait_timeout_sec = 1.0
    page_settle_sec = 0.6


class FindFirstMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = TinderClient.__init__.__globals__.get("settings")
        import tinder_bot.tinder_client as mod

        self._mod = mod
        self._real_settings = mod.settings
        mod.settings = _FakeSettings()  # type: ignore[assignment]

    def tearDown(self) -> None:
        self._mod.settings = self._real_settings

    def test_later_selector_wins_without_stacking_full_waits(self) -> None:
        hidden = MagicMock()
        hidden.is_displayed.return_value = False
        hidden.is_enabled.return_value = True

        visible = MagicMock()
        visible.is_displayed.return_value = True
        visible.is_enabled.return_value = True

        driver = MagicMock()

        def find_elements(_by, css):
            if css == "textarea[placeholder='Napíš správu']":
                return [hidden]
            if css == "textarea":
                return [visible]
            return []

        driver.find_elements.side_effect = find_elements
        client = TinderClient(driver)

        started = time.monotonic()
        found = client._find_first_matching(
            (
                "textarea[placeholder='Napíš správu']",
                "textarea[placeholder*='správu']",
                "textarea",
            ),
            timeout=1.0,
        )
        elapsed = time.monotonic() - started

        self.assertIs(found, visible)
        # Old bug: each miss used full WebDriverWait(30s). Must stay well under that.
        self.assertLess(elapsed, 0.5)

    def test_timeout_when_nothing_matches(self) -> None:
        driver = MagicMock()
        driver.find_elements.return_value = []
        driver.current_url = "https://tinder.com/app/messages/x"
        client = TinderClient(driver)

        with self.assertRaises(TimeoutException):
            client._find_first_matching(("textarea",), timeout=0.35)


if __name__ == "__main__":
    unittest.main()
