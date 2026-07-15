from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from elitedate_bot.config import settings

# Per-thread inbox preview + last bubble — same idea as tinder_bot/.conversation_previews.json
_PREVIEW_CACHE_FILE = Path(settings.seen_messages_file).parent / ".conversation_previews.json"


class EliteDateClient:
    """Wraps a single logged-in Selenium session against Elite Date.

    The site has no public API, so every method here drives the real DOM. The
    CSS selectors below are placeholders — open the site in a real browser,
    use DevTools (F12 -> Inspect) on the login form / message list / message
    input, and replace the `By.CSS_SELECTOR, "..."` values with the real ones.
    """

    def __init__(self, driver) -> None:
        self.driver = driver
        self._wait = WebDriverWait(driver, 20)

    def _click_if_present(self, by: By, selector: str) -> bool:
        try:
            self.driver.find_element(by, selector).click()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _dismiss_cookie_banner(self) -> None:
        # The consent banner is present on first load and blocks the form.
        for by, selector in (
            (By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"),
            (By.XPATH, "//button[normalize-space()='Povoliť všetko']"),
            (By.XPATH, "//button[contains(., 'Povoliť')]"),
        ):
            if self._click_if_present(by, selector):
                break

        # If present, wait until overlay is gone to avoid click interception.
        for by, selector in (
            (By.ID, "CybotCookiebotDialog"),
            (By.ID, "CybotCookiebotDialogBody"),
        ):
            try:
                WebDriverWait(self.driver, 5).until(EC.invisibility_of_element_located((by, selector)))
            except TimeoutException:
                pass

    def _wait_for_login_form(self) -> tuple[Any, Any, Any]:
        email_input = self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='vas@email.sk']")))
        password_input = self._wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='zadajte, prosím, vaše heslo']"))
        )
        submit_button = self._wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Prihlásiť sa']")))
        return email_input, password_input, submit_button

    def _messages_url(self) -> str:
        base = settings.elitedate_login_url.rstrip("/")
        if base.endswith("/prihlaseni"):
            return base.removesuffix("/prihlaseni") + "/ucet/zpravy"
        return base + "/ucet/zpravy"

    def _conversation_profile_id(self, item) -> str:
        try:
            href = item.find_element(By.CSS_SELECTOR, "a[href*='/profil/']").get_attribute("href") or ""
            profile_id = href.split("/profil/")[-1].split("?")[0].strip("/")
            return profile_id or href
        except Exception:  # noqa: BLE001
            return ""

    def _conversation_sender_name(self, item) -> str:
        try:
            return (item.find_element(By.CSS_SELECTOR, "h5").text or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _date_hint_matches(self, text: str, date_hint: str) -> bool:
        if not date_hint.strip():
            return True
        normalized_text = (text or "").replace(" ", "").lower()
        normalized_hint = date_hint.replace(" ", "").lower().rstrip(".")
        candidates: set[str] = set()
        if "." in normalized_hint:
            parts = [part for part in normalized_hint.split(".") if part]
            if len(parts) >= 2:
                day = parts[0].lstrip("0") or "0"
                month = parts[1].lstrip("0") or "0"
                candidates.update(
                    {
                        f"{day}.{month}",
                        f"{day}.{month}.",
                        f"{int(day):02d}.{int(month):02d}",
                        f"{int(day):02d}.{int(month):02d}.",
                    }
                )
        else:
            candidates.add(normalized_hint)

        for candidate in candidates:
            if not candidate:
                continue
            pattern = rf"(?<!\d){re.escape(candidate.rstrip('.'))}\.?(?!\d)"
            if re.search(pattern, normalized_text):
                return True
        return False

    def _is_bold(self, element) -> bool:
        try:
            font_weight = self.driver.execute_script("return window.getComputedStyle(arguments[0]).fontWeight;", element)
            if isinstance(font_weight, str) and font_weight.isdigit():
                return int(font_weight) >= 600
            return str(font_weight).lower() in {"bold", "bolder"}
        except Exception:  # noqa: BLE001
            return False

    def _click_conversation(self, item) -> None:
        try:
            item.click()
        except Exception:  # noqa: BLE001
            self.driver.execute_script("arguments[0].click();", item)

    def _latest_received_message(self) -> str:
        messages = self.driver.find_elements(By.CSS_SELECTOR, "section.conversation-section-message .message.message-receiver")
        if not messages:
            return ""
        return self._clean_chat_message_text(messages[-1].text)

    def _clean_chat_message_text(self, text: str) -> str:
        """Remove timestamp/date lines from a message bubble's visible text."""
        cleaned_lines: list[str] = []
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.fullmatch(r"\d{1,2}\.\s*\d{1,2}\.?\s*(\d{1,2}:\d{2})?", line):
                continue
            if re.fullmatch(r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\s+\d{1,2}:\d{2}", line):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _conversation_scroll_container(self):
        """Return the actual scroll owner for conversation list.

        In ReactVirtualized UIs, `.conversation-section-list` often wraps an
        inner grid that owns `scrollTop`.
        """
        for selector in (
            ".conversation-section-list .ReactVirtualized__Grid",
            ".conversation-section-list",
            ".ReactVirtualized__Grid",
        ):
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                scroll_h = self.driver.execute_script("return arguments[0].scrollHeight || 0;", elem)
                client_h = self.driver.execute_script("return arguments[0].clientHeight || 0;", elem)
                if isinstance(scroll_h, (int, float)) and isinstance(client_h, (int, float)) and scroll_h > client_h + 5:
                    return elem
            except Exception:  # noqa: BLE001
                continue
        return None

    def _find_conversation_item(self, conversation_id: str, max_scroll_steps: int = 25):
        """Find conversation card by profile id, scrolling list container when needed.

        Elite Date uses a virtualized list, so older threads may not be present
        in the initial DOM snapshot.
        """
        conv_id = (conversation_id or "").strip()
        if not conv_id:
            return None

        list_container = self._conversation_scroll_container()

        if list_container is not None:
            try:
                self.driver.execute_script("arguments[0].scrollTop = 0;", list_container)
                time.sleep(0.2)
            except Exception:  # noqa: BLE001
                pass

        for _ in range(max_scroll_steps):
            items = self.driver.find_elements(By.CSS_SELECTOR, ".conversation-section-list .col-message")
            for item in items:
                profile_id = self._conversation_profile_id(item)
                if profile_id == conv_id or (conv_id and conv_id in profile_id):
                    return item

            if list_container is None:
                break

            try:
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollTop + Math.max(200, arguments[0].clientHeight * 0.8);",
                    list_container,
                )
            except Exception:  # noqa: BLE001
                break

            time.sleep(0.15)

        return None

    def _find_conversation_by_sender(self, sender: str, max_scroll_steps: int = 60):
        wanted = (sender or "").strip().lower()
        if not wanted:
            return None

        list_container = self._conversation_scroll_container()

        if list_container is not None:
            try:
                self.driver.execute_script("arguments[0].scrollTop = 0;", list_container)
                time.sleep(0.2)
            except Exception:  # noqa: BLE001
                pass

        for _ in range(max_scroll_steps):
            items = self.driver.find_elements(By.CSS_SELECTOR, ".conversation-section-list .col-message")
            for item in items:
                current_name = self._conversation_sender_name(item).lower()
                if not current_name:
                    continue
                if wanted in current_name or current_name in wanted:
                    return item

            if list_container is None:
                break

            try:
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollTop + Math.max(200, arguments[0].clientHeight * 0.8);",
                    list_container,
                )
            except Exception:  # noqa: BLE001
                break

            time.sleep(0.4)  # wait for ReactVirtualized to re-render new items

        return None

    def find_conversation_snapshot(
        self,
        sender: str,
        date_hint: str = "",
        max_scroll_steps: int = 60,
    ) -> dict[str, Any]:
        """Find a visible/scrollable conversation and return its current context."""
        wanted = (sender or "").strip().lower()
        if not wanted:
            raise RuntimeError("sender is required")

        self.driver.get(self._messages_url())
        list_container = self._conversation_scroll_container()

        if list_container is not None:
            try:
                self.driver.execute_script("arguments[0].scrollTop = 0;", list_container)
                time.sleep(0.2)
            except Exception:  # noqa: BLE001
                pass

        sender_candidates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for _ in range(max_scroll_steps):
            items = self.driver.find_elements(By.CSS_SELECTOR, ".conversation-section-list .col-message")
            for item in items:
                current_name = self._conversation_sender_name(item)
                if not current_name:
                    continue
                current_lower = current_name.lower()
                if wanted not in current_lower and current_lower not in wanted:
                    continue

                profile_id = self._conversation_profile_id(item)
                card_text = (item.text or "").strip()
                candidate_key = profile_id or card_text
                if candidate_key in seen_ids:
                    continue
                seen_ids.add(candidate_key)

                candidate = {
                    "conversation_id": profile_id,
                    "sender": current_name,
                    "card_text": card_text,
                    "date_match": self._date_hint_matches(card_text, date_hint),
                }
                sender_candidates.append(candidate)
                if candidate["date_match"]:
                    self._click_conversation(item)
                    time.sleep(0.5)
                    return {
                        **candidate,
                        "message": self._latest_received_message(),
                        "my_last_message": self._latest_sent_message(),
                    }

            if list_container is None:
                break

            try:
                previous_top = self.driver.execute_script("return arguments[0].scrollTop || 0;", list_container)
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollTop + Math.max(220, arguments[0].clientHeight * 0.85);",
                    list_container,
                )
                time.sleep(0.15)
                current_top = self.driver.execute_script("return arguments[0].scrollTop || 0;", list_container)
                if current_top == previous_top:
                    break
            except Exception:  # noqa: BLE001
                break

        if len(sender_candidates) == 1 and not date_hint.strip():
            item = self._find_conversation_by_sender(sender)
            if item is not None:
                self._click_conversation(item)
                time.sleep(0.5)
                return {
                    **sender_candidates[0],
                    "message": self._latest_received_message(),
                    "my_last_message": self._latest_sent_message(),
                }

        raise RuntimeError(
            "Conversation not found for "
            f"sender={sender!r}, date_hint={date_hint!r}, candidates={sender_candidates[:5]!r}"
        )

    def _find_conversation_by_latest_message(self, expected_message: str, max_scroll_steps: int = 12):
        wanted = (expected_message or "").strip()
        if not wanted:
            return None

        list_container = self._conversation_scroll_container()

        if list_container is not None:
            try:
                self.driver.execute_script("arguments[0].scrollTop = 0;", list_container)
                time.sleep(0.2)
            except Exception:  # noqa: BLE001
                pass

        wanted_short = wanted[:120]

        for _ in range(max_scroll_steps):
            items = self.driver.find_elements(By.CSS_SELECTOR, ".conversation-section-list .col-message")
            for item in items:
                try:
                    self._click_conversation(item)
                    time.sleep(0.12)
                    latest = self._latest_received_message()
                    if not latest:
                        continue
                    if latest == wanted or wanted_short in latest or latest[:120] in wanted:
                        return item
                except Exception:  # noqa: BLE001
                    continue

            if list_container is None:
                break

            try:
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollTop + Math.max(220, arguments[0].clientHeight * 0.9);",
                    list_container,
                )
            except Exception:  # noqa: BLE001
                break

            time.sleep(0.15)

        return None

    def _latest_sent_message(self) -> str:
        messages = self.driver.find_elements(By.CSS_SELECTOR, "section.conversation-section-message .message.message-sender")
        if not messages:
            return ""
        return self._clean_chat_message_text(messages[-1].text)

    def _last_message_is_received(self) -> bool:
        bubbles = self.driver.find_elements(By.CSS_SELECTOR, "section.conversation-section-message .message")
        if not bubbles:
            return False
        cls = bubbles[-1].get_attribute("class") or ""
        return "message-receiver" in cls

    def _load_preview_cache(self) -> dict[str, Any]:
        if _PREVIEW_CACHE_FILE.exists():
            try:
                data = json.loads(_PREVIEW_CACHE_FILE.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _save_preview_cache(self, cache: dict[str, Any]) -> None:
        _PREVIEW_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PREVIEW_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _conversation_inbox_preview(self, card) -> str:
        """Stable-ish text snapshot of the inbox row (name + preview snippet)."""
        return (card.text or "").strip()

    def _collect_conversation_cards(self, *, scroll_all: bool = False) -> list:
        """Return inbox cards; optionally scroll virtualized list to seed every thread."""
        self.driver.get(self._messages_url())
        try:
            self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".conversation-section-list")))
        except TimeoutException:
            pass
        try:
            self._wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".conversation-section-list .col-message"))
            )
        except TimeoutException:
            pass
        time.sleep(0.3)

        seen_ids: set[str] = set()
        collected: list = []
        list_container = self._conversation_scroll_container()
        max_steps = 40 if scroll_all else 1

        if list_container is not None:
            try:
                self.driver.execute_script("arguments[0].scrollTop = 0;", list_container)
                time.sleep(0.2)
            except Exception:  # noqa: BLE001
                pass

        for _ in range(max_steps):
            items = self.driver.find_elements(By.CSS_SELECTOR, ".conversation-section-list .col-message")
            for item in items:
                profile_id = self._conversation_profile_id(item)
                key = profile_id or (item.text or "").strip()
                if not key or key in seen_ids:
                    continue
                seen_ids.add(key)
                collected.append(item)

            if not scroll_all or list_container is None:
                break

            try:
                previous_top = self.driver.execute_script("return arguments[0].scrollTop || 0;", list_container)
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollTop + Math.max(220, arguments[0].clientHeight * 0.85);",
                    list_container,
                )
                time.sleep(0.15)
                current_top = self.driver.execute_script("return arguments[0].scrollTop || 0;", list_container)
                if current_top == previous_top:
                    break
            except Exception:  # noqa: BLE001
                break

        return collected

    def _snapshot_conversation(self, sender: str, inbox_preview: str) -> dict[str, Any]:
        from_them = self._last_message_is_received()
        received = self._latest_received_message()
        sent = self._latest_sent_message()
        return {
            "sender": sender,
            "inbox_preview": inbox_preview,
            "last_message": received if from_them else sent,
            "from_them": from_them,
            "my_last_message": sent,
        }

    def login(self) -> None:
        """Log in using credentials from environment variables (never hardcode them)."""
        if not settings.elitedate_email or not settings.elitedate_password:
            raise RuntimeError("ELITEDATE_EMAIL / ELITEDATE_PASSWORD not set in .env")

        self.driver.get(settings.elitedate_login_url)
        self._dismiss_cookie_banner()

        email_input, password_input, submit_button = self._wait_for_login_form()

        email_input.clear()
        email_input.send_keys(settings.elitedate_email)

        password_input.clear()
        password_input.send_keys(settings.elitedate_password)
        password_input.send_keys(Keys.TAB)
        self._dismiss_cookie_banner()
        try:
            submit_button.click()
        except ElementClickInterceptedException:
            self._dismiss_cookie_banner()
            self.driver.execute_script("arguments[0].click();", submit_button)

        # Logged-in state varies, so wait for a stable post-login marker.
        try:
            self._wait.until(
                EC.any_of(
                    EC.url_contains("/profil"),
                    EC.url_contains("/ucet"),
                    EC.url_contains("/messages"),
                    EC.presence_of_element_located((By.XPATH, "//*[contains(., 'Odhlásiť sa') or contains(., 'Logout') or contains(., 'Prihlásený')]")),
                )
            )
        except TimeoutException:
            # Some successful logins stay on a page without the old marker.
            # Verify the session by opening the inbox before treating it as failed.
            self.driver.get(self._messages_url())
            self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".conversation-section-list")))

    def check_new_messages(self) -> list[dict[str, Any]]:
        """Return conversations whose inbox preview changed and last bubble is from them.

        Persists per-thread state in `.conversation_previews.json` (same idea as Tinder):
        - first sight (or empty cache after restart): seed preview + last bubble, **no** notify
        - later polls: inbox preview changed → open chat → notify only if their new message
        """
        cache = self._load_preview_cache()
        seeding = not cache
        cards = self._collect_conversation_cards(scroll_all=seeding)
        updated_cache = dict(cache)
        results: list[dict[str, Any]] = []

        for card in cards:
            conversation_id = self._conversation_profile_id(card)
            if not conversation_id:
                continue

            sender = self._conversation_sender_name(card) or "Neznámy"
            inbox_preview = self._conversation_inbox_preview(card)
            previous = cache.get(conversation_id)

            # Unchanged preview — skip without opening the chat.
            if isinstance(previous, dict) and previous.get("inbox_preview") == inbox_preview:
                continue
            # Backward compatible: older cache stored plain preview strings.
            if isinstance(previous, str) and previous == inbox_preview:
                continue

            self._click_conversation(card)
            time.sleep(0.5)
            snapshot = self._snapshot_conversation(sender, inbox_preview)

            if previous is None:
                # Seed only — never spam Discord with the whole inbox after restart.
                updated_cache[conversation_id] = snapshot
                continue

            if snapshot.get("from_them"):
                message_text = str(snapshot.get("last_message") or "").strip()
                if isinstance(previous, dict):
                    old_message = str(previous.get("last_message") or "").strip()
                else:
                    old_message = ""
                if message_text and message_text != old_message:
                    results.append(
                        {
                            "conversation_id": conversation_id,
                            "sender": sender,
                            "message": message_text,
                            "my_last_message": snapshot.get("my_last_message", ""),
                        }
                    )
                    print(f"[elitedate_bot] New message from {sender}")

            updated_cache[conversation_id] = snapshot

        self._save_preview_cache(updated_cache)
        return results

    def send_reply(
        self,
        conversation_id: str,
        text: str,
        *,
        submit: bool = True,
        sender: str = "",
        expected_message: str = "",
    ) -> bool:
        """Open conversation, put `text` into input, and optionally submit it."""
        self.driver.get(self._messages_url())
        # Wait for conversation list AND at least one card to render before searching.
        try:
            self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".conversation-section-list")))
        except TimeoutException:
            pass
        try:
            self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".conversation-section-list .col-message")))
        except TimeoutException:
            pass
        time.sleep(0.3)  # let ReactVirtualized finish first batch render

        # Skip fake/manual IDs — they will never match real DOM profile ids.
        is_manual_id = (conversation_id or "").startswith("manual:")
        target = None if is_manual_id else self._find_conversation_item(conversation_id)

        # For manual lookups, the DOM may not expose a stable profile id.
        # Prefer sender name (fast, single-scroll) over iterating every message.
        if target is None and sender.strip():
            target = self._find_conversation_by_sender(sender)

        # Last resort: scan conversations by expected last received message.
        if target is None and expected_message.strip():
            self.driver.get(self._messages_url())
            target = self._find_conversation_by_latest_message(expected_message)

        if target is None:
            raise RuntimeError(f"Conversation {conversation_id} not found in inbox")

        self._click_conversation(target)

        message_input = self._wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "textarea.message-send-input")
            )
        )
        # Use JS to set value — send_keys() does not support non-BMP characters (emoji).
        self.driver.execute_script(
            "var setter = Object.getOwnPropertyDescriptor("
            "window.HTMLTextAreaElement.prototype, 'value').set;"
            "setter.call(arguments[0], arguments[1]);"
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            message_input,
            text,
        )

        if submit:
            send_button = self._wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-send-message")))
            send_button.click()
        return True
