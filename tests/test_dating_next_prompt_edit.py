"""After send, promote the next queued dating prompt by edit — not a duplicate post."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.tools import badoo_state, tinder_state


class DatingNextPromptEditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._badoo_file = badoo_state._STATE_FILE
        self._tinder_file = tinder_state._STATE_FILE
        self._badoo_orig = self._badoo_file.read_text(encoding="utf-8") if self._badoo_file.exists() else None
        self._tinder_orig = self._tinder_file.read_text(encoding="utf-8") if self._tinder_file.exists() else None
        badoo_state._save({"queue": []})
        tinder_state._save({"queue": []})

    async def asyncTearDown(self) -> None:
        if self._badoo_orig is None:
            if self._badoo_file.exists():
                self._badoo_file.unlink()
        else:
            self._badoo_file.write_text(self._badoo_orig, encoding="utf-8")
        if self._tinder_orig is None:
            if self._tinder_file.exists():
                self._tinder_file.unlink()
        else:
            self._tinder_file.write_text(self._tinder_orig, encoding="utf-8")

    async def test_badoo_selection_edits_existing_next_prompt(self) -> None:
        from app.tools import badoo_dispatch

        first = badoo_state.enqueue("c1", "Anna", "ahoj", ["A1", "A2", "A3", "A4"])
        second = badoo_state.enqueue("c2", "Bea", "cau", ["B1", "B2", "B3", "B4"])
        badoo_state.set_prompt_message_id(first, "msg-first")
        badoo_state.set_prompt_message_id(second, "msg-second")
        first = badoo_state.find_by_prompt_message_id("msg-first")
        assert first is not None

        with (
            patch.object(badoo_dispatch, "_send_via_bot", new=AsyncMock(return_value="sent")),
            patch.object(badoo_dispatch, "_post_prompt", new=AsyncMock(return_value="msg-second")) as post,
        ):
            reply = await badoo_dispatch.handle_selection("1", replied_to_message_id="msg-first")

        self.assertIsNotNone(reply)
        self.assertTrue(str(reply).startswith("✅"))
        post.assert_awaited_once()
        args, kwargs = post.await_args
        self.assertEqual(args[0]["conversation_id"], "c2")
        self.assertTrue(kwargs.get("edit_existing"))

    async def test_tinder_selection_edits_existing_next_prompt(self) -> None:
        from app.tools import tinder_dispatch

        first = tinder_state.enqueue("c1", "Anna", "ahoj", ["A1", "A2", "A3", "A4"])
        second = tinder_state.enqueue("c2", "Bea", "cau", ["B1", "B2", "B3", "B4"])
        tinder_state.set_prompt_message_id(first, "msg-first")
        tinder_state.set_prompt_message_id(second, "msg-second")

        with (
            patch.object(tinder_dispatch, "_send_via_bot", new=AsyncMock(return_value="sent")),
            patch.object(tinder_dispatch, "_post_prompt", new=AsyncMock(return_value="msg-second")) as post,
        ):
            reply = await tinder_dispatch.handle_selection("1", replied_to_message_id="msg-first")

        self.assertIsNotNone(reply)
        self.assertTrue(str(reply).startswith("✅"))
        post.assert_awaited_once()
        args, kwargs = post.await_args
        self.assertEqual(args[0]["conversation_id"], "c2")
        self.assertTrue(kwargs.get("edit_existing"))


if __name__ == "__main__":
    unittest.main()
