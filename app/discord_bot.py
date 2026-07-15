from __future__ import annotations

import asyncio
import logging
import re
import ssl
import sys
import time
from typing import Any

import aiohttp
import discord

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.config import Settings
from app.discord_chat import build_discord_reply, normalize_discord_prompt
from app.orchestrator import Orchestrator
from app.schemas import PromptResponse, ToolExecution

LOGGER = logging.getLogger("orchestrator.discord_bot")

_ELITEDATE_CHOICE_RE = re.compile(r"^\s*[123](?:[.):,]|\uFE0F\u20E3|\u20E3|\uFE0F)?(?:\s.*)?\s*$")
_ELITE_DATE_RE = re.compile(r"elite\s*d[aáä]te|elitedate", re.IGNORECASE)
# "správy na ed", "ed?", "stav ed" — nie bežné slová obsahujúce "ed"
_ED_WORD_RE = re.compile(
    r"(?:^|[\s,.;:])(?:na\s+)?ed(?:[\s?!.:,]|$)|(?:^|[\s])ed(?:\?|$)",
    re.IGNORECASE,
)


def _dating_status_service(prompt: str) -> str | None:
    """Ak prompt hovorí o Elite Date / ED / Tinder, vráť service pre dating_status."""
    lowered = prompt.lower().strip()
    has_elite = bool(_ELITE_DATE_RE.search(lowered))
    has_ed = bool(_ED_WORD_RE.search(lowered))
    has_tinder = "tinder" in lowered
    if has_elite or has_ed:
        return "both" if has_tinder else "elitedate"
    if has_tinder:
        return "tinder"
    return None


def _looks_like_numeric_fallback(text: str) -> bool:
    lowered = text.lower()
    return (
        ("gmail" in lowered or "todo" in lowered)
        and (
            "číslo" in lowered
            or "2. bod" in lowered
            or "druh" in lowered
            or "už to máme" in lowered
            or "tak do toho" in lowered
        )
    )


class OrchestratorDiscordClient(discord.Client):
    def __init__(self, *, settings: Settings, orchestrator: Orchestrator, ssl_context: ssl.SSLContext | None = None) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        
        connector = None
        if ssl_context:
            connector = aiohttp.TCPConnector(ssl=ssl_context)
        else:
            # Fallback: disable SSL verification for corporate networks
            fallback_ctx = ssl.create_default_context()
            fallback_ctx.check_hostname = False
            fallback_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=fallback_ctx)
        
        super().__init__(intents=intents, connector=connector)

        self._settings = settings
        self._orchestrator = orchestrator
        # Per-user email browsing state: {user_id: {"offset": int, "query": str}}
        self._email_state: dict[int, dict[str, Any]] = {}
        # Per-user conversation history: {user_id: [{"role": "user"|"assistant", "content": "..."}]}
        # Keep last 10 exchanges (20 messages) per user for context
        self._conversation_history: dict[int, list[dict[str, str]]] = {}
        self._max_history_pairs = 10  # 10 user+assistant pairs = 20 messages
        self._numeric_fallback_suppression_until: dict[int, float] = {}

    async def on_ready(self) -> None:
        LOGGER.info("Discord bot is online as %s", self.user)
        print(f"[OK] Discord bot online: {self.user}")

    def _is_navigation_request(self, prompt: str) -> str | None:
        """Detect navigation commands like 'next', 'previous', 'back'."""
        lowered = prompt.lower().strip()
        next_keywords = ["nasledujuci", "nasledujúci", "dalsi", "ďalší", "next", "dalej", "ďalej"]
        prev_keywords = ["predchadzajuci", "predchádzajúci", "predosly", "predošlý", "previous", "prev", "spat", "späť", "naspat", "naspäť"]
        
        for kw in next_keywords:
            if kw in lowered:
                return "next"
        for kw in prev_keywords:
            if kw in lowered:
                return "prev"
        return None

    async def on_message(self, message: discord.Message) -> None:
        print(f"[Discord] Message from {message.author} in #{message.channel}: {message.content}")
        LOGGER.info(f"Message from {message.author}: {message.content}")
        
        if message.author.bot:
            suppress_until = self._numeric_fallback_suppression_until.get(message.channel.id, 0)
            if (
                self.user
                and message.author.id == self.user.id
                and time.monotonic() <= suppress_until
                and _looks_like_numeric_fallback(message.content)
            ):
                try:
                    await message.delete()
                    LOGGER.info("Deleted stale numeric fallback message from duplicate bot session")
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("Failed to delete stale numeric fallback message: %s", exc)
            LOGGER.info(f"Ignoring bot message from {message.author}")
            return

        # User whitelist — if configured, only allowed users can interact
        allowed = self._settings.discord_bot_allowed_users
        if allowed:
            allowed_ids = {int(uid.strip()) for uid in allowed.split(",") if uid.strip()}
            if message.author.id not in allowed_ids:
                LOGGER.warning(f"Unauthorized user {message.author} ({message.author.id}) — ignoring")
                return

        channel_id = self._settings.discord_bot_channel_id
        if channel_id and message.channel.id != channel_id:
            LOGGER.info(f"Message in wrong channel: {message.channel.id} != {channel_id}")
            return

        prompt = self._extract_prompt(message)
        LOGGER.info(f"Extracted prompt: {prompt}")
        if not prompt:
            LOGGER.info("No prompt extracted, ignoring")
            return

        if _ELITEDATE_CHOICE_RE.match(prompt):
            self._numeric_fallback_suppression_until[message.channel.id] = time.monotonic() + 12

        try:
            # Dating-app intercept — ONLY when the user is replying to a message
            # that contains a known dating-app keyword (e.g. "Elite Date", "Tinder").
            # This prevents any standalone "1"/"2"/"3" message from accidentally
            # hijacking normal LLM routing.
            from app.tools import elitedate_dispatch, tinder_dispatch

            replied_to_message_id: str | None = None
            _is_dating_reply = False
            _dating_dispatchers = (elitedate_dispatch,)
            if message.reference and message.reference.message_id:
                replied_to_message_id = str(message.reference.message_id)
                try:
                    # Fetch the referenced message to get its content
                    # (message.reference.resolved may be None if not already cached)
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    ref_content: str = ref_msg.content or ""
                    _DATING_KEYWORDS = ("Elite Date", "Tinder", "Badoo", "Bumble", "Hinge", "Vlákno:")
                    _is_dating_reply = any(kw in ref_content for kw in _DATING_KEYWORDS)
                    LOGGER.info(f"Reply detected to message: {ref_content[:100]}... -> is_dating={_is_dating_reply}")
                    # Prefer the dispatcher for the specific app named in the
                    # referenced message; fall back to trying both when the
                    # reference only matched the generic "Vlákno:" marker.
                    if "Tinder" in ref_content:
                        _dating_dispatchers = (tinder_dispatch,)
                    elif "Elite Date" in ref_content:
                        _dating_dispatchers = (elitedate_dispatch,)
                    elif _is_dating_reply:
                        _dating_dispatchers = (elitedate_dispatch, tinder_dispatch)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning(f"Could not fetch referenced message: {exc}")

            if _is_dating_reply:
                LOGGER.info(f"Processing dating-app selection: {prompt}")
                for dispatcher in _dating_dispatchers:
                    dating_reply = await dispatcher.handle_selection(
                        prompt,
                        replied_to_message_id=replied_to_message_id,
                    )
                    if dating_reply is not None:
                        await message.channel.send(dating_reply)
                        self._add_to_history(message.author.id, prompt, dating_reply)
                        return
                # Replied to a dating-app message but no matching entry — stay silent.
                LOGGER.info("Reply to dating-app message had no actionable selection context; suppressing")
                return

            # Safety guard: suppress bare 1/2/3 inputs that were NOT dating replies
            # so they never fall through into the LLM and produce nonsense responses.
            if _ELITEDATE_CHOICE_RE.match(prompt):
                LOGGER.info("Bare numeric choice without dating-app Reply context; suppressing generic fallback")
                return

            # Check if this is a navigation request (next/previous email)
            nav = self._is_navigation_request(prompt)
            dating_service = _dating_status_service(prompt)
            if nav:
                result = await self._handle_email_navigation(message.author.id, nav)
                reply = build_discord_reply(prompt, result)
            elif dating_service:
                # Intercept pred LLM — inak GPT často mapuje "správy na ed" na Gmail.
                from app.tools.dating_status_tool import DatingStatusTool

                LOGGER.info("Dating-status intercept (service=%s): %s", dating_service, prompt)
                tool_result = await DatingStatusTool().run(
                    prompt, context={"service": dating_service}
                )
                result = PromptResponse(
                    route="dating_status",
                    summary=str(tool_result.get("reply") or ""),
                    executions=[
                        ToolExecution(
                            tool="dating_status",
                            reason="discord dating-status keyword intercept",
                            result=tool_result,
                        )
                    ],
                )
                reply = build_discord_reply(prompt, result)
            else:
                # Get conversation history for this user
                user_history = self._conversation_history.get(message.author.id, [])
                result = await self._orchestrator.handle_prompt(prompt, history=user_history)
                reply = build_discord_reply(prompt, result)
                if not reply.strip():
                    return
                # Track email state if this was a gmail fetch
                if result.route == "gmail" and result.executions:
                    exec_result = result.executions[0].result
                    action = exec_result.get("action", "")
                    if action == "fetch":
                        query = exec_result.get("query", "in:inbox")
                        self._email_state[message.author.id] = {"offset": 0, "query": query}

            # Save to conversation history
            self._add_to_history(message.author.id, prompt, reply)

        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to process Discord message")
            reply = f"Error while processing request: {exc}"

        await message.channel.send(reply)

    def _add_to_history(self, user_id: int, user_msg: str, bot_reply: str) -> None:
        """Add a user/assistant exchange to conversation history, keeping last N pairs."""
        if user_id not in self._conversation_history:
            self._conversation_history[user_id] = []

        history = self._conversation_history[user_id]
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": bot_reply})

        # Trim to max pairs (each pair = 2 messages)
        max_messages = self._max_history_pairs * 2
        if len(history) > max_messages:
            self._conversation_history[user_id] = history[-max_messages:]

    async def _handle_email_navigation(self, user_id: int, direction: str) -> PromptResponse:
        """Handle next/previous email navigation."""
        from app.tools.gmail_tool import GmailTool

        state = self._email_state.get(user_id)
        if not state:
            # No previous state, start from inbox
            state = {"offset": 0, "query": "in:inbox"}

        if direction == "next":
            state["offset"] += 1
        elif direction == "prev" and state["offset"] > 0:
            state["offset"] -= 1

        self._email_state[user_id] = state

        # Fetch email at offset
        gmail_tool = self._orchestrator.tools.get("gmail")
        if not gmail_tool:
            gmail_tool = GmailTool()

        result = await gmail_tool.run(
            "fetch email",
            context={"action": "fetch", "query": state["query"], "max_results": state["offset"] + 1},
        )

        # Extract only the last email (at offset position)
        emails = result.get("emails", [])
        if emails and len(emails) > state["offset"]:
            email = emails[state["offset"]]
            result = {
                "status": "success",
                "action": "fetch",
                "from": email.get("from", "Neznámy"),
                "subject": email.get("subject", "Bez predmetu"),
                "date": email.get("date", ""),
                "body_preview": email.get("body", "")[:500],
                "position": state["offset"] + 1,
            }
        elif emails:
            # Offset beyond available emails, stay at last
            state["offset"] = len(emails) - 1
            self._email_state[user_id] = state
            email = emails[-1]
            result = {
                "status": "success",
                "action": "fetch",
                "from": email.get("from", "Neznámy"),
                "subject": email.get("subject", "Bez predmetu"),
                "date": email.get("date", ""),
                "body_preview": email.get("body", "")[:500],
                "position": state["offset"] + 1,
            }
        else:
            result = {"status": "success", "action": "fetch", "emails": []}

        execution = ToolExecution(tool="gmail", reason="email navigation", result=result)
        return PromptResponse(route="gmail", summary="gmail:navigate", executions=[execution])

    def _extract_prompt(self, message: discord.Message) -> str:
        content = message.content.strip()

        if self._settings.discord_bot_require_mention:
            if not self.user:
                return ""
            mention_tags = {f"<@{self.user.id}>", f"<@!{self.user.id}>"}
            if not any(tag in content for tag in mention_tags):
                return ""
            for tag in mention_tags:
                content = content.replace(tag, "")

        return normalize_discord_prompt(content, prefix=self._settings.discord_bot_prefix)


async def start_discord_bot() -> None:
    settings = Settings()

    if not settings.discord_bot_enabled:
        raise RuntimeError("DISCORD_BOT_ENABLED is false. Enable it in .env before running the bot.")

    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is missing in .env.")

    logging.basicConfig(level=logging.INFO)
    orchestrator = Orchestrator()
    
    # SSL verification workaround for corporate networks
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    client = OrchestratorDiscordClient(settings=settings, orchestrator=orchestrator, ssl_context=ssl_context)
    await client.start(settings.discord_bot_token)


def main() -> None:
    asyncio.run(start_discord_bot())


if __name__ == "__main__":
    main()
