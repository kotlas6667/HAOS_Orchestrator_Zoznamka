"""Regression: Discord Kontext must not glue older Badoo bubbles into the latest reply."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.tools.badoo_dispatch import _format_prompt, _primary_bubble_text
from badoo_bot.badoo_client import BadooClient


class _FakeSettings:
    wait_timeout_sec = 1.0
    page_settle_sec = 0.6
    poll_interval_sec = 0.05


class PrimaryBubbleTextTests(unittest.TestCase):
    def test_keeps_single_message(self) -> None:
        self.assertEqual(_primary_bubble_text("No chladim sa sprcha"), "No chladim sa sprcha")

    def test_keeps_only_first_glued_bubble(self) -> None:
        # Old bot joined oldest-first; trailing block was the leftover "past" line.
        glued = (
            "No chladim sa sprcha vaňa ako sa len dá katastrofa\n\n"
            "Dnes sme mali tú 37stupnou ale isto bolo aj..."
        )
        self.assertEqual(
            _primary_bubble_text(glued),
            "No chladim sa sprcha vaňa ako sa len dá katastrofa",
        )

    def test_discord_prompt_hides_older_glued_message(self) -> None:
        text = _format_prompt(
            {
                "conversation_id": "abc-6d61bce",
                "sender": "Lucia",
                "status": "awaiting_selection",
                "options": ["A", "B", "C", "D"],
                "my_last_message": "Presne tak, ako prežívaš tieto hice 🥵",
                "message": (
                    "No chladim sa sprcha vaňa ako sa len dá katastrofa\n\n"
                    "Dnes sme mali tú 37stupnou ale isto bolo aj..."
                ),
            }
        )
        self.assertIn("No chladim sa sprcha vaňa ako sa len dá katastrofa", text)
        self.assertNotIn("37stupnou", text)
        self.assertIn("Presne tak, ako prežívaš tieto hice", text)


class BadooLatestMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        import badoo_bot.badoo_client as mod

        self._mod = mod
        self._real_settings = mod.settings
        mod.settings = _FakeSettings()  # type: ignore[assignment]

    def tearDown(self) -> None:
        self._mod.settings = self._real_settings

    def _bubble(self, direction: str) -> MagicMock:
        bubble = MagicMock()
        bubble.get_attribute.side_effect = lambda name: {
            "data-qa-message-direction": direction,
            "data-message-direction": direction,
            "class": "",
        }.get(name, "")
        return bubble

    def test_latest_received_prefers_inbox_preview_among_consecutive(self) -> None:
        driver = MagicMock()
        client = BadooClient(driver)
        older = self._bubble("in")
        newer_junk = self._bubble("in")
        mine = self._bubble("out")

        real = "No chladim sa sprcha vaňa ako sa len dá katastrofa"
        junk = "Dnes sme mali tú 37stupnou ale isto bolo aj..."

        client._iter_chat_bubbles = MagicMock(return_value=[mine, older, newer_junk])  # type: ignore[method-assign]
        client._bubble_message_payload = MagicMock(  # type: ignore[method-assign]
            side_effect=lambda b: {
                "type": "text",
                "text": {
                    id(older): real,
                    id(newer_junk): junk,
                    id(mine): "Presne tak, ako prežívaš tieto hice 🥵",
                }[id(b)],
            }
        )

        payload = client._latest_received_message_payload(preview=real[:40])
        self.assertEqual(payload["message"], real)
        self.assertNotIn("37stupnou", payload["message"])

    def test_latest_received_falls_back_to_newest_without_preview(self) -> None:
        driver = MagicMock()
        client = BadooClient(driver)
        older = self._bubble("in")
        newer = self._bubble("in")
        mine = self._bubble("out")

        client._iter_chat_bubbles = MagicMock(return_value=[mine, older, newer])  # type: ignore[method-assign]
        client._bubble_message_payload = MagicMock(  # type: ignore[method-assign]
            side_effect=lambda b: {
                "type": "text",
                "text": {
                    id(older): "staršia správa",
                    id(newer): "najnovšia správa",
                    id(mine): "moja",
                }[id(b)],
            }
        )

        payload = client._latest_received_message_payload()
        self.assertEqual(payload["message"], "najnovšia správa")

    def test_latest_sent_ignores_older_consecutive_bubbles(self) -> None:
        driver = MagicMock()
        client = BadooClient(driver)
        older_mine = self._bubble("out")
        newer_mine = self._bubble("out")
        theirs = self._bubble("in")

        client._iter_chat_bubbles = MagicMock(  # type: ignore[method-assign]
            return_value=[older_mine, newer_mine, theirs]
        )
        client._bubble_text = MagicMock(  # type: ignore[method-assign]
            side_effect=lambda b: {
                id(older_mine): "Ahoj",
                id(newer_mine): "Presne tak, ako prežívaš tieto hice 🥵",
                id(theirs): "No chladim sa sprcha",
            }[id(b)]
        )

        self.assertEqual(
            client._latest_sent_message(),
            "Presne tak, ako prežívaš tieto hice 🥵",
        )

    def test_outermost_elements_drops_nested_nodes(self) -> None:
        driver = MagicMock()
        outer = MagicMock(name="outer")
        inner = MagicMock(name="inner")
        driver.execute_script.return_value = [outer]
        client = BadooClient(driver)
        self.assertEqual(client._outermost_elements([outer, inner]), [outer])
        driver.execute_script.assert_called_once()


if __name__ == "__main__":
    unittest.main()
