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
from selenium.webdriver.support.ui import Select, WebDriverWait

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
            el = self.driver.find_element(by, selector)
            return self._safe_click(el)
        except Exception:  # noqa: BLE001
            return False

    def _safe_click(self, element) -> bool:
        """Click with JS fallback when the normal click is intercepted/hidden."""
        try:
            element.click()
            return True
        except Exception:  # noqa: BLE001
            try:
                self.driver.execute_script("arguments[0].click();", element)
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

    def _site_base(self) -> str:
        base = settings.elitedate_login_url.rstrip("/")
        if base.endswith("/prihlaseni"):
            return base.removesuffix("/prihlaseni")
        return base

    def _messages_url(self) -> str:
        return self._site_base() + "/ucet/zpravy"

    def _new_members_url(self) -> str:
        return self._site_base() + "/ucet/novi-clenove"

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

    def _scroll_open_chat_up(self, steps: int = 5) -> None:
        """Scroll chat upward so React-virtualized history loads more bubbles."""
        for selector in (
            "section.conversation-section-message .ReactVirtualized__Grid",
            ".ReactVirtualized__Grid",
            "section.conversation-section-message",
        ):
            try:
                grid = self.driver.find_element(By.CSS_SELECTOR, selector)
            except Exception:  # noqa: BLE001
                continue
            for _ in range(max(1, steps)):
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollTop = Math.max(0, (arguments[0].scrollTop || 0) "
                        "- Math.max(280, arguments[0].clientHeight * 0.85));",
                        grid,
                    )
                except Exception:  # noqa: BLE001
                    break
                time.sleep(0.28)
            return

    def _extract_chat_history(self, *, max_messages: int = 24) -> list[dict[str, str]]:
        """Chronological [{role: me|them, text}] from the open chat (for AI drafts)."""
        self._scroll_open_chat_up(steps=5)
        bubbles = self.driver.find_elements(
            By.CSS_SELECTOR, "section.conversation-section-message .message"
        )
        if not bubbles:
            bubbles = self.driver.find_elements(
                By.CSS_SELECTOR, ".message.message-receiver, .message.message-sender"
            )
        history: list[dict[str, str]] = []
        for bubble in bubbles:
            cls = (bubble.get_attribute("class") or "").lower()
            try:
                p = bubble.find_element(By.CSS_SELECTOR, "p")
                text = self._clean_chat_message_text(p.text or "")
            except Exception:  # noqa: BLE001
                text = self._clean_chat_message_text(bubble.text or "")
            if not text:
                continue
            if "message-sender" in cls or "outgoing" in cls:
                role = "me"
            elif "message-receiver" in cls or "message-received" in cls or "incoming" in cls:
                role = "them"
            else:
                continue
            # Merge consecutive same-role bubbles (split paragraphs).
            if history and history[-1]["role"] == role:
                history[-1]["text"] = f"{history[-1]['text']}\n\n{text}".strip()
            else:
                history.append({"role": role, "text": text})
        if len(history) > max_messages:
            history = history[-max_messages:]
        return history

    def _latest_received_message(self) -> str:
        messages = self.driver.find_elements(
            By.CSS_SELECTOR, "section.conversation-section-message .message.message-receiver"
        )
        if not messages:
            messages = self.driver.find_elements(By.CSS_SELECTOR, ".message.message-receiver")
        if not messages:
            return ""
        # Join consecutive trailing received bubbles (full last turn, not only last paragraph).
        parts: list[str] = []
        all_msgs = self.driver.find_elements(By.CSS_SELECTOR, "section.conversation-section-message .message")
        if not all_msgs:
            all_msgs = messages
        for bubble in reversed(all_msgs):
            cls = (bubble.get_attribute("class") or "").lower()
            if "message-receiver" not in cls:
                if parts:
                    break
                continue
            text = self._clean_chat_message_text(bubble.text or "")
            if text:
                parts.append(text)
        if not parts:
            return self._clean_chat_message_text(messages[-1].text)
        parts.reverse()
        return "\n\n".join(parts).strip()

    def _latest_sent_message(self) -> str:
        messages = self.driver.find_elements(
            By.CSS_SELECTOR, "section.conversation-section-message .message.message-sender"
        )
        if not messages:
            return ""
        parts: list[str] = []
        all_msgs = self.driver.find_elements(By.CSS_SELECTOR, "section.conversation-section-message .message")
        if not all_msgs:
            all_msgs = messages
        for bubble in reversed(all_msgs):
            cls = (bubble.get_attribute("class") or "").lower()
            if "message-sender" not in cls:
                if parts:
                    break
                continue
            text = self._clean_chat_message_text(bubble.text or "")
            if text:
                parts.append(text)
        if not parts:
            return self._clean_chat_message_text(messages[-1].text)
        parts.reverse()
        return "\n\n".join(parts).strip()

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

    def _absolutize_url(self, url: str) -> str:
        href = (url or "").strip()
        if not href or href.startswith("data:"):
            return ""
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return self._site_base() + href
        return href

    def _extract_profile_photo_url(self) -> str:
        """Best-effort profile/chat avatar URL from the open conversation."""
        for selector in (
            "section.conversation-section-message img[src*='galerie']",
            "section.conversation-section-message img[src*='Image']",
            ".conversation-header img",
            ".message-header img",
            "img.profile-photo",
            "img.avatar",
            "a[href*='/profil/'] img",
            ".card-image",
        ):
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:  # noqa: BLE001
                continue
            for el in els:
                src = (el.get_attribute("src") or "").strip()
                if src and not src.startswith("data:"):
                    abs_url = self._absolutize_url(src)
                    if abs_url:
                        return abs_url
                style = (el.get_attribute("style") or "") + " " + (el.get_attribute("data-src") or "")
                match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style, flags=re.I)
                if match:
                    abs_url = self._absolutize_url(match.group(1))
                    if abs_url:
                        return abs_url
        return ""

    def _download_url_bytes(self, url: str, *, max_bytes: int = 4_000_000) -> tuple[bytes, str] | None:
        """Download URL using the logged-in Selenium cookie jar."""
        abs_url = self._absolutize_url(url)
        if not abs_url:
            return None
        try:
            import ssl
            import urllib.request

            req = urllib.request.Request(
                abs_url,
                headers={"User-Agent": self.driver.execute_script("return navigator.userAgent;") or "Mozilla/5.0"},
            )
            cookie_header = "; ".join(
                f"{c['name']}={c['value']}" for c in self.driver.get_cookies() if c.get("name")
            )
            if cookie_header:
                req.add_header("Cookie", cookie_header)
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:  # noqa: S310
                data = resp.read(max_bytes + 1)
                content_type = (resp.headers.get_content_type() or "image/jpeg").split(";")[0].strip()
            if not data or len(data) > max_bytes:
                return None
            if not content_type.startswith("image/"):
                # Guess from magic bytes
                if data[:3] == b"\xff\xd8\xff":
                    content_type = "image/jpeg"
                elif data[:8] == b"\x89PNG\r\n\x1a\n":
                    content_type = "image/png"
                elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                    content_type = "image/webp"
                else:
                    content_type = "image/jpeg"
            return data, content_type
        except Exception as exc:  # noqa: BLE001
            print(f"[elitedate_bot] photo download failed: {exc}")
            return None

    def _profile_photo_fields(self) -> dict[str, str]:
        """Return photo_url / photo_base64 / photo_content_type for Discord."""
        import base64

        url = self._extract_profile_photo_url()
        if not url:
            return {}
        out: dict[str, str] = {"photo_url": url}
        downloaded = self._download_url_bytes(url)
        if downloaded:
            data, content_type = downloaded
            out["photo_base64"] = base64.b64encode(data).decode("ascii")
            out["photo_content_type"] = content_type
        return out

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

    def _last_message_is_received(self) -> bool:
        bubbles = self.driver.find_elements(By.CSS_SELECTOR, "section.conversation-section-message .message")
        if not bubbles:
            bubbles = self.driver.find_elements(By.CSS_SELECTOR, ".message")
        if not bubbles:
            return False
        cls = (bubbles[-1].get_attribute("class") or "").lower()
        # Elite Date uses message-receiver for their bubbles; also accept common aliases.
        if "message-receiver" in cls or "message-received" in cls or "incoming" in cls:
            return True
        if "message-sender" in cls or "outgoing" in cls:
            return False
        # Unknown class: treat as theirs if we can read a received bubble text.
        return bool(self._latest_received_message())

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

    def commit_preview(self, conversation_id: str, preview: str) -> None:
        """Persist inbox preview only after Discord notify succeeded (retry-safe)."""
        cid = (conversation_id or "").strip()
        text = (preview or "").strip()
        if not cid or not text:
            return
        cache = self._load_preview_cache()
        cache[cid] = text
        self._save_preview_cache(cache)

    @staticmethod
    def _cached_preview_text(previous: Any) -> str | None:
        """Normalize cache entry → plain preview string (Tinder stores strings)."""
        if previous is None:
            return None
        if isinstance(previous, str):
            return previous
        if isinstance(previous, dict):
            return str(previous.get("inbox_preview") or "")
        return str(previous)

    def _conversation_inbox_preview(self, card) -> str:
        """Message preview snippet (Tinder-style) — not the whole card text.

        Full card.text also contains relative times ("pred 5 min") that change
        without a new message and used to cause stale/false opens.
        """
        name = self._conversation_sender_name(card).strip()
        for selector in (
            ".message-preview",
            ".col-message-text",
            ".conversation-preview",
            "p",
            "span",
        ):
            try:
                nodes = card.find_elements(By.CSS_SELECTOR, selector)
            except Exception:  # noqa: BLE001
                continue
            for node in nodes:
                snippet = (node.text or "").strip()
                if not snippet:
                    continue
                if name and snippet.lower() == name.lower():
                    continue
                if re.fullmatch(r"(pred\s+)?\d+\s*(min|h|hod|d|dňami|dni|minútami)?\.?", snippet, re.I):
                    continue
                if re.fullmatch(r"\d{1,2}\.\s*\d{1,2}\.?(?:\s*\d{1,2}:\d{2})?", snippet):
                    continue
                return snippet

        full = (card.text or "").strip()
        if name and full.lower().startswith(name.lower()):
            full = full[len(name) :].strip()
        lines = [ln.strip() for ln in full.splitlines() if ln.strip()]
        while lines and (
            re.fullmatch(r"(pred\s+)?\d+\s*(min|h|hod|d|dňami|dni|minútami)?\.?", lines[0], re.I)
            or re.fullmatch(r"\d{1,2}\.\s*\d{1,2}\.?(?:\s*\d{1,2}:\d{2})?", lines[0])
        ):
            lines.pop(0)
        return " ".join(lines).strip() or full

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

    def _list_inbox_rows(self, *, scroll_all: bool = False) -> list[dict[str, str]]:
        """Snapshot inbox as plain dicts (no live WebElements — avoids stale refs like Tinder)."""
        cards = self._collect_conversation_cards(scroll_all=scroll_all)
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for card in cards:
            conversation_id = self._conversation_profile_id(card)
            if not conversation_id or conversation_id in seen:
                continue
            seen.add(conversation_id)
            preview = self._conversation_inbox_preview(card)
            if not preview:
                continue
            rows.append(
                {
                    "conversation_id": conversation_id,
                    "sender": self._conversation_sender_name(card) or "Neznámy",
                    "preview": preview,
                }
            )
        return rows

    def _open_conversation_by_id(self, conversation_id: str) -> None:
        """Re-open inbox and click a fresh card for `conversation_id` (Tinder opens by URL)."""
        target = (conversation_id or "").strip()
        if not target:
            raise RuntimeError("empty conversation_id")
        # Always reload inbox so we never reuse a stale WebElement from the scan pass.
        self.driver.get(self._messages_url())
        time.sleep(0.4)
        item = self._find_conversation_item(target)
        if item is None:
            raise RuntimeError(f"conversation card not found for id={target!r}")
        self._click_conversation(item)
        time.sleep(0.5)
        try:
            self._wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "section.conversation-section-message .message, textarea.message-send-input")
                )
            )
        except TimeoutException:
            pass

    def check_new_messages(self) -> list[dict[str, Any]]:
        """Return conversations whose preview changed and last bubble is from them.

        Aligned with Tinder:
        - seed / unchanged preview → update cache only, never open chat
        - preview changed → open chat by id (fresh DOM), notify if last msg is from them
        - message text falls back to inbox preview if bubble text is empty

        Pending candidates keep the *old* preview in cache until
        ``commit_preview`` runs after a successful Discord notify — otherwise a
        timeout/Discord failure would permanently silence the conversation.
        """
        cache = self._load_preview_cache()
        seeding = not cache
        rows = self._list_inbox_rows(scroll_all=seeding)
        updated_cache: dict[str, Any] = dict(cache)
        results: list[dict[str, Any]] = []
        changed = 0

        for row in rows:
            conversation_id = row["conversation_id"]
            sender = row["sender"]
            preview = row["preview"]
            previous_preview = self._cached_preview_text(cache.get(conversation_id))

            # First sighting or unchanged — seed only (Tinder never opens on seed).
            if previous_preview is None or previous_preview == preview:
                updated_cache[conversation_id] = preview
                continue

            changed += 1
            try:
                self._open_conversation_by_id(conversation_id)
                if not self._last_message_is_received():
                    # Our own last bubble — advance cache so we do not reopen forever.
                    updated_cache[conversation_id] = preview
                    print(f"[elitedate_bot] Preview changed but last bubble is ours: {sender}")
                    continue

                message_text = self._latest_received_message() or preview
                my_last_message = self._latest_sent_message()
                if not message_text:
                    # Keep old preview so the next poll retries this conversation.
                    continue
                history = self._extract_chat_history(max_messages=24)
                photo = self._profile_photo_fields()

                results.append(
                    {
                        "conversation_id": conversation_id,
                        "sender": sender,
                        "message": message_text,
                        "my_last_message": my_last_message,
                        "preview": preview,
                        "history": history,
                        **photo,
                    }
                )
                print(
                    f"[elitedate_bot] New message from {sender} "
                    f"(history_turns={len(history)}, photo={'yes' if photo.get('photo_base64') else 'no'})"
                )
                # Do NOT write the new preview yet — poller commits after Discord OK.
            except Exception as exc:  # noqa: BLE001
                # One broken thread must not abort the whole poll (stale refs used to).
                # Keep old preview so we retry on the next cycle.
                print(f"[elitedate_bot] check_new_messages skip {conversation_id}: {exc}")
                continue

        self._save_preview_cache(updated_cache)
        print(
            f"[elitedate_bot] Poll done: rows={len(rows)} preview_changes={changed} "
            f"new={len(results)} seeding={seeding}"
        )
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

    # --- Morning greet („Noví členovia“) ---------------------------------
    # Real DOM (Elite Date SK):
    #   Filter toggle: button.btn-partner-filter (.active = panel open)
    #   Age: #search_filter_form_ageFrom / #search_filter_form_ageTo
    #   Height to: #search_filter_form_heightTo
    #   Distance: .noUi-handle[role=slider] (noUiSlider)
    #   Submit: #search_filter_form_submit (text in nested span)
    #   Cards: a.c-card[href*='/profil/']
    #   Write: a.send-message-btn

    def _filter_form_visible(self) -> bool:
        try:
            el = self.driver.find_element(By.ID, "search_filter_form_ageFrom")
            return el.is_displayed()
        except Exception:  # noqa: BLE001
            return False

    def _open_filter_panel(self) -> None:
        """Ensure the filter form on Noví členovia is visible — never toggle it closed."""
        if self._filter_form_visible():
            return

        toggle = None
        for by, selector in (
            (By.CSS_SELECTOR, "button.btn-partner-filter"),
            (By.XPATH, "//button[contains(@class,'btn-partner-filter')]"),
            (By.XPATH, "//button[contains(.,'Filter')]"),
        ):
            try:
                toggle = self.driver.find_element(by, selector)
                break
            except Exception:  # noqa: BLE001
                continue

        if toggle is None:
            raise RuntimeError("Filter toggle (btn-partner-filter) not found on Noví členovia")

        cls = (toggle.get_attribute("class") or "").lower()
        if "active" in cls and self._filter_form_visible():
            return

        if not self._safe_click(toggle):
            raise RuntimeError("Could not open Filter panel on Noví členovia")
        time.sleep(0.5)

        if not self._filter_form_visible():
            # Toggle may have closed an already-open panel — open once more.
            cls = (toggle.get_attribute("class") or "").lower()
            if "active" not in cls:
                self._safe_click(toggle)
                time.sleep(0.5)
        if not self._filter_form_visible():
            raise RuntimeError("Filter form inputs not visible after opening Filter panel")

    def _set_input_value(self, element, value: str | int) -> None:
        text = str(value)
        try:
            element.clear()
        except Exception:  # noqa: BLE001
            pass
        try:
            element.send_keys(Keys.CONTROL, "a")
            element.send_keys(Keys.BACKSPACE)
        except Exception:  # noqa: BLE001
            pass
        self.driver.execute_script(
            "var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
            "setter.call(arguments[0], arguments[1]);"
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
            element,
            text,
        )

    def _input_matches(self, element, expected: str | int | None) -> bool:
        if expected is None:
            return True
        current = (element.get_attribute("value") or "").strip()
        return current == str(expected)

    def _select_dropdown_near_label(self, label: str, option_text: str) -> bool:
        try:
            block = self.driver.find_element(
                By.XPATH,
                f"//*[normalize-space()='{label}' or starts-with(normalize-space(),'{label}')]"
                "/ancestor::*[.//select or .//button][1]",
            )
        except Exception:  # noqa: BLE001
            return False

        selects = block.find_elements(By.TAG_NAME, "select")
        for sel in selects:
            try:
                Select(sel).select_by_visible_text(option_text)
                return True
            except Exception:  # noqa: BLE001
                continue

        # Custom dropdowns: open and click the option.
        for btn in block.find_elements(By.CSS_SELECTOR, "button, [role='button'], .dropdown-toggle"):
            try:
                current = (btn.text or "").strip().lower()
                if option_text.lower() in current:
                    return True
                if not self._safe_click(btn):
                    continue
                time.sleep(0.2)
                opt = self.driver.find_element(
                    By.XPATH,
                    f"//*[normalize-space()='{option_text}' or contains(normalize-space(),'{option_text}')]",
                )
                self._safe_click(opt)
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _ensure_photo_only_toggle(self) -> None:
        """Activate „Iba s fotkou“ when it is not already on."""
        for xpath in (
            "//*[contains(normalize-space(),'Iba s fotkou')]",
            "//button[contains(.,'Iba s fotkou')]",
            "//label[contains(.,'Iba s fotkou')]",
        ):
            try:
                el = self.driver.find_element(By.XPATH, xpath)
            except Exception:  # noqa: BLE001
                continue
            cls = (el.get_attribute("class") or "").lower()
            aria = (el.get_attribute("aria-pressed") or "").lower()
            checked = (el.get_attribute("aria-checked") or "").lower()
            already_on = (
                "active" in cls
                or "checked" in cls
                or "selected" in cls
                or aria == "true"
                or checked == "true"
            )
            if already_on:
                return
            self._safe_click(el)
            return

    def _set_distance_km(self, km: int) -> bool:
        """Set noUiSlider (Vzdialenosť) / range input to `km` (e.g. 75)."""
        ok = self.driver.execute_script(
            """
            var km = arguments[0];
            var targets = document.querySelectorAll('.noUi-target');
            for (var i = 0; i < targets.length; i++) {
                if (targets[i].noUiSlider) {
                    try { targets[i].noUiSlider.set(km); return true; } catch (e) {}
                }
            }
            var handle = document.querySelector('.noUi-handle[role="slider"]');
            if (handle) {
                var now = parseFloat(handle.getAttribute('aria-valuenow') || '');
                if (!isNaN(now) && Math.abs(now - km) < 0.5) return true;
            }
            var ranges = document.querySelectorAll('input[type="range"]');
            for (var j = 0; j < ranges.length; j++) {
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(ranges[j], String(km));
                ranges[j].dispatchEvent(new Event('input', { bubbles: true }));
                ranges[j].dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
            return false;
            """,
            km,
        )
        return bool(ok)

    def _filter_already_matches(self) -> bool:
        try:
            age_from = self.driver.find_element(By.ID, "search_filter_form_ageFrom")
            age_to = self.driver.find_element(By.ID, "search_filter_form_ageTo")
            height_to = self.driver.find_element(By.ID, "search_filter_form_heightTo")
        except Exception:  # noqa: BLE001
            return False
        return (
            self._input_matches(age_from, settings.morning_greet_age_from)
            and self._input_matches(age_to, settings.morning_greet_age_to)
            and self._input_matches(height_to, settings.morning_greet_height_to)
        )

    def _click_filter_submit(self) -> None:
        """Click #search_filter_form_submit (text is inside a nested span)."""
        for by, selector in (
            (By.ID, "search_filter_form_submit"),
            (By.CSS_SELECTOR, "button.btn-search[type='submit']"),
            (By.CSS_SELECTOR, "button#search_filter_form_submit"),
            (By.XPATH, "//button[@type='submit'][.//span[contains(normalize-space(),'Filtrovať')]]"),
            (By.XPATH, "//button[contains(.,'Filtrovať')]"),
        ):
            try:
                el = self.driver.find_element(by, selector)
            except Exception:  # noqa: BLE001
                continue
            if self._safe_click(el):
                return
        raise RuntimeError("Filtrovať button (#search_filter_form_submit) not found on Noví členovia")

    def ensure_new_members_filter(self) -> bool:
        """Open Noví členovia, apply filter when needed, click Filtrovať.

        Returns True when Filtrovať was clicked (filter changed), False if already OK.
        """
        self.driver.get(self._new_members_url())
        time.sleep(1.0)
        self._dismiss_cookie_banner()
        self._open_filter_panel()
        time.sleep(0.3)

        if self._filter_already_matches():
            print("[elitedate_bot] Noví členovia filter already matches — skipping apply.")
            return False

        try:
            age_from = self.driver.find_element(By.ID, "search_filter_form_ageFrom")
            self._set_input_value(age_from, settings.morning_greet_age_from)
        except Exception as exc:  # noqa: BLE001
            print(f"[elitedate_bot] ageFrom not set: {exc}")
        try:
            age_to = self.driver.find_element(By.ID, "search_filter_form_ageTo")
            self._set_input_value(age_to, settings.morning_greet_age_to)
        except Exception as exc:  # noqa: BLE001
            print(f"[elitedate_bot] ageTo not set: {exc}")
        try:
            height_to = self.driver.find_element(By.ID, "search_filter_form_heightTo")
            self._set_input_value(height_to, settings.morning_greet_height_to)
        except Exception as exc:  # noqa: BLE001
            print(f"[elitedate_bot] heightTo not set: {exc}")

        for label in ("Minimálne vzdelanie", "Fajčiar", "Chce deti"):
            self._select_dropdown_near_label(label, "nezáleží")

        self._ensure_photo_only_toggle()
        if not self._set_distance_km(settings.morning_greet_distance_km):
            print("[elitedate_bot] Distance slider not set (continuing anyway).")

        self._click_filter_submit()
        time.sleep(1.2)
        # Wait for profile cards after filter apply.
        try:
            self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.c-card[href*='/profil/']")))
        except TimeoutException:
            pass
        print("[elitedate_bot] Noví členovia filter applied.")
        return True

    def _name_from_heading_text(self, raw: str) -> str:
        """„Natalia, 36“ → „Natalia“."""
        text = (raw or "").strip()
        if not text:
            return ""
        return text.split(",")[0].strip()

    def _profile_display_name(self) -> str:
        """Best-effort name from an open profile / card page."""
        for selector in (
            "h4.card-heading",
            ".card-heading",
            "h1.profile-name",
            ".profile-name",
            "h1",
        ):
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                name = self._name_from_heading_text(el.text or "")
                if name:
                    return name
            except Exception:  # noqa: BLE001
                continue
        return ""

    def _click_new_members_next_page(self) -> bool:
        """Click „Ďalšie“ on Noví členovia pagination. Returns True if navigated."""
        for by, selector in (
            (By.CSS_SELECTOR, "a.btn-success[href*='novi-clenove'][href*='listFrom=']"),
            (By.CSS_SELECTOR, "a.btn[href*='/ucet/novi-clenove?'][href*='listFrom=']"),
            (By.XPATH, "//a[contains(@href,'novi-clenove') and contains(@href,'listFrom=') and contains(.,'Ďalšie')]"),
            (By.XPATH, "//a[contains(@class,'btn-success') and contains(normalize-space(),'Ďalšie')]"),
        ):
            try:
                el = self.driver.find_element(by, selector)
            except Exception:  # noqa: BLE001
                continue
            href = (el.get_attribute("href") or "").strip()
            if not self._safe_click(el):
                if href:
                    self.driver.get(href)
                else:
                    continue
            time.sleep(1.0)
            try:
                self._wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "a.c-card[href*='/profil/'], a[href*='/profil/']")
                    )
                )
            except TimeoutException:
                pass
            print(f"[elitedate_bot] Noví členovia → Ďalšie ({href or 'click'})")
            return True
        return False

    def _harvest_visible_new_member_cards(
        self, seen: set[str], profiles: list[dict[str, str]], limit: int
    ) -> int:
        """Append newly visible profile cards; return how many were added."""
        links = self.driver.find_elements(By.CSS_SELECTOR, "a.c-card[href*='/profil/']")
        if not links:
            links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/profil/']")
        added = 0
        for link in links:
            if len(profiles) >= limit:
                break
            href = (link.get_attribute("href") or "").strip()
            if "/profil/" not in href:
                continue
            profile_id = href.split("/profil/")[-1].split("?")[0].strip("/")
            if not profile_id or profile_id in seen:
                continue
            name = ""
            try:
                name = self._name_from_heading_text(
                    link.find_element(By.CSS_SELECTOR, "h4.card-heading, .card-heading").text or ""
                )
            except Exception:  # noqa: BLE001
                pass
            seen.add(profile_id)
            profiles.append({"profile_id": profile_id, "url": href, "name": name})
            added += 1
        return added

    def _collect_new_member_profiles(self, limit: int = 40) -> list[dict[str, str]]:
        """Collect unique profile id/url(/name) across Noví členovia pages (Ďalšie)."""
        # Prefer staying on filtered results; only reload if cards are missing.
        if not self.driver.find_elements(By.CSS_SELECTOR, "a.c-card[href*='/profil/'], a[href*='/profil/']"):
            self.driver.get(self._new_members_url())
            time.sleep(1.0)
        try:
            self._wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.c-card[href*='/profil/'], a[href*='/profil/']"))
            )
        except TimeoutException:
            pass

        seen: set[str] = set()
        profiles: list[dict[str, str]] = []
        # ~16 kariet / stránka; hard cap stránok proti nekonečnému klikaniu.
        max_pages = max(3, min(25, (limit // 8) + 3))

        for page_idx in range(max_pages):
            stagnant = 0
            for _ in range(8):
                before = len(profiles)
                self._harvest_visible_new_member_cards(seen, profiles, limit)
                if len(profiles) >= limit:
                    print(
                        f"[elitedate_bot] Noví členovia collected {len(profiles)} "
                        f"(page {page_idx + 1}/{max_pages})"
                    )
                    return profiles

                if len(profiles) == before:
                    stagnant += 1
                    if stagnant >= 2:
                        break
                else:
                    stagnant = 0

                self.driver.execute_script("window.scrollBy(0, Math.max(400, window.innerHeight * 0.85));")
                time.sleep(0.35)

            if len(profiles) >= limit:
                break

            if not self._click_new_members_next_page():
                print(
                    f"[elitedate_bot] Noví členovia: no more Ďalšie "
                    f"(collected {len(profiles)} on page {page_idx + 1})"
                )
                break

        return profiles

    def _conversation_has_history(self) -> bool:
        """True when the open chat already contains any message bubbles."""
        # React-virtualized chat: .message.message-sender / .message-receiver with <p>
        bubbles = self.driver.find_elements(
            By.CSS_SELECTOR,
            ".message.message-receiver, .message.message-sender, "
            "section.conversation-section-message .message, "
            ".ReactVirtualized__Grid .message",
        )
        for bubble in bubbles:
            # Prefer inner <p> text; fall back to whole bubble (minus timestamp bar).
            try:
                p = bubble.find_element(By.CSS_SELECTOR, "p")
                text = self._clean_chat_message_text(p.text or "")
            except Exception:  # noqa: BLE001
                text = self._clean_chat_message_text(bubble.text or "")
            if text:
                return True
        # Fallback: non-empty textarea means draft — treat as history to avoid overwrite.
        try:
            ta = self.driver.find_element(By.CSS_SELECTOR, "textarea.message-send-input")
            if (ta.get_attribute("value") or "").strip():
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _open_write_message(self) -> None:
        for by, selector in (
            (By.CSS_SELECTOR, "a.send-message-btn"),
            (By.CSS_SELECTOR, "a.btn-profile.send-message-btn"),
            (By.CSS_SELECTOR, "a[href*='/ucet/zpravy?username=']"),
            (By.XPATH, "//a[contains(@class,'send-message-btn')]"),
            (By.XPATH, "//a[.//span[contains(normalize-space(),'Napísať správu')]]"),
            (By.XPATH, "//*[normalize-space()='Napísať správu']"),
        ):
            try:
                el = self._wait.until(EC.element_to_be_clickable((by, selector)))
                if self._safe_click(el):
                    return
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError("„Napísať správu“ button (a.send-message-btn) not found on profile")

    def _send_greeting_in_open_chat(self, text: str) -> None:
        message_input = self._wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea.message-send-input"))
        )
        self.driver.execute_script(
            "var setter = Object.getOwnPropertyDescriptor("
            "window.HTMLTextAreaElement.prototype, 'value').set;"
            "setter.call(arguments[0], arguments[1]);"
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            message_input,
            text,
        )
        send_button = self._wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-send-message")))
        send_button.click()
        time.sleep(0.5)

    def run_morning_greet(
        self,
        *,
        max_profiles: int = 10,
        max_opens: int = 20,
        already_greeted: set[str] | None = None,
        greeting_text: str = "Ahoj :-)",
    ) -> dict[str, Any]:
        """Apply Noví členovia filter and greet empty conversations.

        `max_profiles` = koľko prázdnych chatov má dostať pozdrav (odoslaných správ).
        `max_opens` = max. koľko profilov otvoriť/prehľadať (ochrana pred zacyklením).
        Profily s históriou sa len preskočia a nepočítajú do `max_profiles`.

        Anti-loop:
        - skip profile IDs in `already_greeted` (persisted across days),
        - mark each opened profile as processed (sent or skipped-with-history),
        - walk a pre-collected unique URL list instead of re-clicking the same card.
        """
        known = set(already_greeted or ())
        processed: list[str] = []
        sent_names: list[str] = []
        target_sent = max(1, int(max_profiles))
        open_cap = max(1, int(max_opens))
        stats = {
            "checked": 0,
            "sent": 0,
            "skipped_history": 0,
            "skipped_known": 0,
            "errors": 0,
            "processed_ids": processed,
            "sent_names": sent_names,
            "max_profiles": target_sent,
            "max_opens": open_cap,
        }

        self.ensure_new_members_filter()
        # Zbieraj aspoň toľko kariet, koľko smieme otvoriť (+ rezerva na known skip).
        collect_limit = max(open_cap + 10, target_sent * 3, 20)
        candidates = self._collect_new_member_profiles(limit=collect_limit)
        print(
            f"[elitedate_bot] Morning greet candidates: {len(candidates)} "
            f"(target_sent={target_sent}, max_opens={open_cap})"
        )

        for profile in candidates:
            if stats["sent"] >= target_sent:
                break
            if stats["checked"] >= open_cap:
                print(
                    f"[elitedate_bot] Morning greet stop: open cap {open_cap} "
                    f"(sent={stats['sent']}/{target_sent})"
                )
                break

            profile_id = profile["profile_id"]
            if profile_id in known or profile_id in processed:
                stats["skipped_known"] += 1
                continue

            stats["checked"] += 1
            display_name = (profile.get("name") or "").strip()
            try:
                self.driver.get(profile["url"])
                time.sleep(0.7)
                if not display_name:
                    display_name = self._profile_display_name()
                self._open_write_message()
                time.sleep(0.6)
                self._wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "textarea.message-send-input"))
                )

                if self._conversation_has_history():
                    stats["skipped_history"] += 1
                    processed.append(profile_id)
                    known.add(profile_id)
                    print(f"[elitedate_bot] Morning greet skip (has history): {profile_id}")
                    continue

                self._send_greeting_in_open_chat(greeting_text)
                stats["sent"] += 1
                processed.append(profile_id)
                known.add(profile_id)
                label = display_name or profile_id
                sent_names.append(label)
                print(
                    f"[elitedate_bot] Morning greet sent to {label} "
                    f"({stats['sent']}/{target_sent})"
                )
                time.sleep(0.8)
            except Exception as exc:  # noqa: BLE001
                stats["errors"] += 1
                # Still mark as processed so a broken profile cannot trap the loop.
                processed.append(profile_id)
                known.add(profile_id)
                print(f"[elitedate_bot] Morning greet error on {profile_id}: {exc}")

        return stats
