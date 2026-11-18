"""Regression: noVNC login must allow images so CAPTCHA puzzles render."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class NovncImagesPrefTests(unittest.TestCase):
    def test_badoo_allows_images_when_not_headless(self) -> None:
        import badoo_bot.browser as browser_mod

        fake_settings = MagicMock()
        fake_settings.browser = "chrome"
        fake_settings.headless = False
        fake_settings.window_size = "1366,768"
        fake_settings.geolocation_enabled = False
        fake_settings.user_data_dir = None
        fake_settings.user_agent = None
        fake_settings.browser_binary = None
        fake_settings.webdriver_path = None
        fake_settings.wait_timeout_sec = 30.0

        captured: dict = {}

        class FakeOptions:
            def add_argument(self, *_a, **_k):
                return None

            def add_experimental_option(self, name, value):
                captured[name] = value

        with (
            patch.object(browser_mod, "settings", fake_settings),
            patch.object(browser_mod, "Options", FakeOptions),
            patch.object(browser_mod, "Service"),
            patch.object(browser_mod, "chrome_startup_lock", lambda *_a, **_k: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: False)),
            patch.object(browser_mod.webdriver, "Chrome", return_value=MagicMock()),
        ):
            browser_mod.build_driver()

        prefs = captured.get("prefs") or {}
        self.assertEqual(prefs.get("profile.managed_default_content_settings.images"), 1)

    def test_badoo_blocks_images_when_headless(self) -> None:
        import badoo_bot.browser as browser_mod

        fake_settings = MagicMock()
        fake_settings.browser = "chrome"
        fake_settings.headless = True
        fake_settings.window_size = "1366,768"
        fake_settings.geolocation_enabled = False
        fake_settings.user_data_dir = None
        fake_settings.user_agent = None
        fake_settings.browser_binary = None
        fake_settings.webdriver_path = None
        fake_settings.wait_timeout_sec = 30.0

        captured: dict = {}

        class FakeOptions:
            def add_argument(self, *_a, **_k):
                return None

            def add_experimental_option(self, name, value):
                captured[name] = value

        with (
            patch.object(browser_mod, "settings", fake_settings),
            patch.object(browser_mod, "Options", FakeOptions),
            patch.object(browser_mod, "Service"),
            patch.object(browser_mod, "chrome_startup_lock", lambda *_a, **_k: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: False)),
            patch.object(browser_mod.webdriver, "Chrome", return_value=MagicMock()),
        ):
            browser_mod.build_driver()

        prefs = captured.get("prefs") or {}
        self.assertEqual(prefs.get("profile.managed_default_content_settings.images"), 2)


if __name__ == "__main__":
    unittest.main()
