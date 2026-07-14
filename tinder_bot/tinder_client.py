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

from tinder_bot.config import settings

_PREVIEW_CACHE_FILE = Path(settings.seen_messages_file).parent / ".conversation_previews.json"
_NEW_MATCH_LABEL = "Nová zhoda"


_INBOX_ROW_JS = """
function inboxRowFromAnchor(a) {
    const h3 = a.querySelector('h3');
    let name = h3 ? h3.innerText.trim() : '';
    let preview = '';
    const previewEl = a.querySelector('[class*="body-2"]') ||
                      a.querySelector('[class*="subtitle"]') ||
                      a.querySelector('p');
    if (previewEl) preview = previewEl.innerText.trim();
    if (!preview) {
        const lines = (a.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
        if (!name && lines.length) name = lines[0];
        if (lines.length > 1) preview = lines.slice(1).join(' ').trim();
    }
    return { name, preview };
}
function isRealInboxRow(name, preview) {
    if (!preview || name === 'Nová zhoda') return false;
    if (preview.startsWith('Klikni a začni chatovať')) return false;
    const pl = preview.toLowerCase();
    if (pl.includes('vytvor zhodu') || pl.includes('vytvoř zhodu')) return false;
    if (pl.includes('nedávno aktívny') || pl.includes('nedavno aktivny')) return false;
    return true;
}
"""


class TinderClient:
    """Wraps a single logged-in Selenium session against Tinder's web app."""

    def __init__(self, driver) -> None:
        self.driver = driver
        self._wait = WebDriverWait(driver, int(settings.wait_timeout_sec))

    def _wait_timeout(self) -> float:
        return settings.wait_timeout_sec

    def _settle(self, multiplier: float = 1.0) -> None:
        """Wait for Tinder's SPA to finish rendering after a navigation or click."""
        time.sleep(settings.page_settle_sec * multiplier)

    def _poll_interval(self) -> float:
        """Shorter sleep used inside wait loops (fraction of page settle)."""
        return max(0.5, settings.page_settle_sec / 6)

    def _wait_for_document_ready(self, timeout: float | None = None) -> None:
        deadline = time.time() + (timeout if timeout is not None else self._wait_timeout())
        while time.time() < deadline:
            try:
                if self.driver.execute_script("return document.readyState") == "complete":
                    return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(self._poll_interval())

    def _wait_for_app_route(self, timeout: float | None = None) -> None:
        """Wait until Tinder's logged-in SPA finished loading the current route."""
        deadline = time.time() + (timeout if timeout is not None else self._wait_timeout())
        while time.time() < deadline:
            try:
                url = self.driver.current_url or ""
                ready = self.driver.execute_script("return document.readyState") == "complete"
                if ready and "/app/" in url:
                    return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(self._poll_interval())

    def _count_conversation_previews(self) -> int:
        count = self.driver.execute_script(
            _INBOX_ROW_JS
            + """
            return Array.from(document.querySelectorAll("a[href*='/app/messages/']")).filter(a => {
                const row = inboxRowFromAnchor(a);
                return isRealInboxRow(row.name, row.preview);
            }).length;
            """
        )
        return int(count or 0)

    def _wait_for_inbox_rows(self, timeout: float | None = None) -> None:
        """Wait until Správy rows with message previews are rendered."""
        deadline = time.time() + (timeout if timeout is not None else self._wait_timeout())
        while time.time() < deadline:
            if self._count_conversation_previews() > 0:
                self._settle(multiplier=0.5)
                return
            time.sleep(self._poll_interval())

    def _wait_for_chat_messages(self, timeout: float | None = None) -> None:
        """Wait until the open chat shows at least one non-empty message bubble."""
        deadline = time.time() + (timeout if timeout is not None else self._wait_timeout())
        while time.time() < deadline:
            self._dismiss_popups()
            count = self.driver.execute_script(
                """
                return Array.from(document.querySelectorAll('div.msg')).filter(el => {
                    const text = (el.innerText || '').trim();
                    return text && text !== 'Ty:' && text !== 'Ty';
                }).length;
                """
            )
            if int(count or 0) > 0:
                self._settle(multiplier=0.5)
                return
            time.sleep(self._poll_interval())

    def _click_if_present(self, by: By, selector: str) -> bool:
        try:
            self.driver.find_element(by, selector).click()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _dismiss_cookie_banner(self) -> None:
        for by, selector in (
            (By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"),
            (By.XPATH, "//button[normalize-space()='Accept' or normalize-space()='Prijať všetky']"),
            (By.XPATH, "//button[contains(., 'Accept') or contains(., 'Prijať')]"),
        ):
            if self._click_if_present(by, selector):
                break

    def _dismiss_popups(self) -> None:
        for by, selector in (
            # Onboarding "Nedá sa pripojiť" (location sharing) — click "Pripomenúť neskôr".
            (By.CSS_SELECTOR, 'button[data-testid="onboarding_dismiss"]'),
            (By.CSS_SELECTOR, 'button[aria-label="Pripomenúť neskôr"]'),
            (By.XPATH, "//button[normalize-space()='Pripomenúť neskôr']"),
            (By.XPATH, "//div[contains(@class,'onboarding__modal') and @role='alertdialog']//button[normalize-space()='Pripomenúť neskôr']"),
            (By.XPATH, "//button[contains(., 'Not interested') or contains(., 'Nie, ďakujem')]"),
            (By.XPATH, "//button[@aria-label='Close' or @aria-label='Zavrieť']"),
            (By.XPATH, "//button[contains(., 'Neskôr') or contains(., 'Later')]"),
            # Chrome / Tinder notification permission prompt (see screenshot).
            (By.XPATH, "//button[normalize-space()='Blokovať' or normalize-space()='Block']"),
            (By.XPATH, "//button[normalize-space()='Povoliť' or normalize-space()='Allow']/following-sibling::button"),
            # Chrome "restore pages?" bubble after an unclean shutdown.
            (By.XPATH, "//button[contains(., 'Obnoviť stránky')]/ancestor::*[@role='alert' or contains(@class,'infobar')]//button[@aria-label='Zavrieť' or @aria-label='Close']"),
        ):
            self._click_if_present(by, selector)
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:  # noqa: BLE001
            pass

    def _is_messages_list_visible(self) -> bool:
        """True when the left panel shows the Správy list (rows with message previews)."""
        return self._count_conversation_previews() > 0

    def _spravy_tab_active(self) -> bool:
        return bool(
            self.driver.execute_script(
                """
                const wanted = new Set(['Správy', 'Spravy', 'Messages']);
                const tabs = Array.from(document.querySelectorAll('button[role="tab"]'));
                const spravy = tabs.find(tab => wanted.has((tab.innerText || '').split('\\n')[0].trim()));
                return spravy ? spravy.getAttribute('aria-selected') === 'true' : false;
                """
            )
        )

    def _wait_after_spravy_tab(self) -> None:
        """Wait until Správy inbox rows are visible — first row = top of screen."""
        deadline = time.time() + settings.spravy_settle_sec
        while time.time() < deadline:
            if self._count_conversation_previews() > 0:
                return
            time.sleep(0.5)

    def _click_messages_tab(self, *, fast: bool = False) -> bool:
        """Click the 'Správy' tab in the left sidebar (Tinder defaults to Zhody on /app/recs)."""
        clicked = self.driver.execute_script(
            """
            const wanted = new Set(['Správy', 'Spravy', 'Messages']);
            const tablist =
                document.querySelector('[role="tablist"][aria-labelledby="desktop-message-list-tablist-label"]') ||
                document.querySelector('[role="tablist"]');
            if (tablist) {
                const tabs = Array.from(tablist.querySelectorAll('button[role="tab"]'));
                for (const tab of tabs) {
                    const label = (tab.innerText || '').split('\\n')[0].trim();
                    if (wanted.has(label)) {
                        tab.click();
                        return label;
                    }
                }
                // Zhody = first tab, Správy = second tab in current Tinder UI.
                if (tabs.length >= 2) {
                    tabs[1].click();
                    return (tabs[1].innerText || '').split('\\n')[0].trim();
                }
            }
            return '';
            """
        )
        if clicked:
            self._wait_after_spravy_tab()
            if not fast:
                self._wait_for_inbox_rows()
            return True

        for xpath in (
            "//div[@role='tablist']//button[@role='tab' and (normalize-space()='Správy' or normalize-space()='Spravy' or normalize-space()='Messages')]",
            "//div[@role='tablist']//button[@role='tab'][2]",
            "//button[@role='tab' and normalize-space()='Správy']",
        ):
            for tab in self.driver.find_elements(By.XPATH, xpath):
                try:
                    self.driver.execute_script("arguments[0].click();", tab)
                    self._wait_after_spravy_tab()
                    if not fast:
                        self._wait_for_inbox_rows()
                    return True
                except Exception:  # noqa: BLE001
                    continue
        return False

    def _navigate_to_inbox(self, *, fast: bool = False) -> None:
        """Open inbox and switch to Správy tab.

        Zhody match tiles also use a[href*='/app/messages/'] but have no preview —
        click Správy before reading the list. Fall back to /app/recs when the
        messages URL renders an empty shell.

        fast=True: click Správy, wait ~10s for list to render, then read top row.
        """
        if fast:
            self.driver.get("https://tinder.com/app/recs")
            self._dismiss_cookie_banner()
            self._dismiss_popups()
            for attempt in range(2):
                self._click_messages_tab(fast=True)
                if self._spravy_tab_active() and self._count_conversation_previews() > 0:
                    break
                if attempt == 0:
                    time.sleep(1)
            return

        self.driver.get("https://tinder.com/app/recs")
        self._wait_for_app_route()
        self._dismiss_cookie_banner()
        self._dismiss_popups()
        self._settle()
        self._click_messages_tab()
        self._wait_for_inbox_rows()

        self._wait_for_conversation_list()

    def _scroll_conversation_list_to_top(self) -> None:
        """Scroll the Správy virtual list to the top so row order matches recency."""
        self.driver.execute_script(
            """
            const grid = document.querySelector('.ReactVirtualized__Grid') ||
                         document.querySelector('[class*="messageList"]') ||
                         document.querySelector('main');
            if (grid) grid.scrollTop = 0;
            """
        )

    def _wait_for_login_form(self) -> tuple[Any, Any, Any] | None:
        try:
            email_input = self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
            password_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            return email_input, password_input, submit_button
        except TimeoutException:
            return None

    def _messages_url(self) -> str:
        return "https://tinder.com/app/messages"

    def _conversation_url(self, match_id: str) -> str:
        return f"https://tinder.com/app/messages/{match_id.strip()}"

    def _conversation_match_id(self, item) -> str:
        try:
            href = self.driver.execute_script("return arguments[0].href || '';", item) or ""
        except Exception:  # noqa: BLE001
            href = self._conversation_url_from_item(item)
        return href.rstrip("/").split("/")[-1] if href else ""

    def _conversation_url_from_item(self, item) -> str:
        try:
            return item.get_attribute("href") or ""
        except Exception:  # noqa: BLE001
            return ""

    def _conversation_sender_name(self, item) -> str:
        try:
            name = self.driver.execute_script(
                "const h3 = arguments[0].querySelector('h3'); return h3 ? h3.innerText.trim() : '';",
                item,
            )
            return (name or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _conversation_preview(self, item) -> str:
        try:
            preview = self.driver.execute_script(
                "const el = arguments[0].querySelector('[class*=\"body-2\"]');"
                "return el ? el.innerText.trim() : '';",
                item,
            )
            return (preview or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _is_new_match(self, item) -> bool:
        name = self._conversation_sender_name(item)
        preview = self._conversation_preview(item)
        if name == _NEW_MATCH_LABEL:
            return True
        return preview.startswith("Klikni a začni chatovať")

    def _load_preview_cache(self) -> dict[str, str]:
        if _PREVIEW_CACHE_FILE.exists():
            try:
                return json.loads(_PREVIEW_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _save_preview_cache(self, cache: dict[str, str]) -> None:
        _PREVIEW_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PREVIEW_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _clean_chat_message_text(self, text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}\s*(AM|PM)?", line, flags=re.IGNORECASE):
                continue
            if line.lower().startswith("odoslané"):
                continue
            if line in {"Ty:", "Ty"}:
                continue
            if re.fullmatch(r"[^:]+:", line):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _latest_received_message(self) -> str:
        messages = self.driver.find_elements(By.CSS_SELECTOR, "div.msg.msg--received")
        if not messages:
            messages = self.driver.find_elements(By.CSS_SELECTOR, "div.msg[class*='chat-bubble-receive']")
        if not messages:
            return ""
        return self._clean_chat_message_text(messages[-1].text)

    def _latest_sent_message(self) -> str:
        messages = self.driver.find_elements(By.CSS_SELECTOR, "div.msg[class*='chat-bubble-send']:not(.msg--received)")
        if not messages:
            return ""
        return self._clean_chat_message_text(messages[-1].text)

    def _last_message_is_received(self) -> bool:
        bubbles = self.driver.find_elements(By.CSS_SELECTOR, "div.msg[class*='chat-bubble']")
        if not bubbles:
            bubbles = self.driver.find_elements(By.CSS_SELECTOR, "div.msg")
        if not bubbles:
            return False
        last = bubbles[-1]
        cls = last.get_attribute("class") or ""
        return "msg--received" in cls or "chat-bubble-receive" in cls

    def _click_conversation(self, item) -> None:
        try:
            item.click()
        except Exception:  # noqa: BLE001
            self.driver.execute_script("arguments[0].click();", item)

    def _open_conversation(self, match_id: str) -> None:
        self.driver.get(self._conversation_url(match_id))
        self._wait_for_app_route()
        self._dismiss_popups()
        self._settle()
        self._wait_for_chat_loaded()

    def _wait_for_chat_loaded(self, timeout: float | None = None) -> None:
        self._wait_for_chat_messages(timeout=timeout)

    def _wait_for_conversation_list(self, timeout: float | None = None) -> None:
        """Wait until the Správy tab list is showing rows with message previews."""
        self._wait_for_inbox_rows(timeout=timeout)

    def _find_conversation_item(self, match_id: str):
        target = (match_id or "").strip()
        if not target:
            return None
        items = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/app/messages/']")
        for item in items:
            if self._conversation_match_id(item) == target:
                return item
        return None

    def _find_conversation_by_sender(self, sender: str):
        wanted = (sender or "").strip().lower()
        if not wanted:
            return None
        items = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/app/messages/']")
        for item in items:
            name = self._conversation_sender_name(item).lower()
            if name and (wanted in name or name in wanted):
                return item
        return None

    def _is_logged_in_app(self) -> bool:
        url = self.driver.current_url or ""
        title = self.driver.title or ""
        if "/app/" not in url:
            return False
        if "Ups" in title or "neexistuje" in (self.driver.execute_script(
            "return (document.body.innerText||'').slice(0,200);"
        ) or ""):
            return False
        return True

    def _cookie_file_path(self) -> "Path | None":
        from pathlib import Path

        if not settings.user_data_dir:
            return None
        base = Path(settings.user_data_dir) / "Default"
        for name in ("Network/Cookies", "Cookies"):
            p = base / name
            if p.is_file():
                return p
        return None

    def _headless_session_error(self) -> RuntimeError:
        cookie = self._cookie_file_path()
        if cookie is None:
            return RuntimeError(
                "V kontajneri chýba Chrome profil (/data/chrome-profile). "
                "Over: docker exec addon_local_haos_tinder ls -la /data/chrome-profile/Default/Network/ "
                "Host path: /mnt/data/supervisor/addons/data/local_haos_tinder/chrome-profile/ "
                "Ak je profil na hoste ale nie v kontajneri, reštartuj add-on alebo Rebuild. "
                "Prvé prihlásenie: Nastavenia → tinder_headless=false → noVNC :6080."
            )
        return RuntimeError(
            f"Cookie súbor existuje ({cookie}, {cookie.stat().st_size} B), "
            "ale Tinder session nie je aktívna v headless režime. "
            "Pravdepodobne neúplné prihlásenie alebo expirovaná session. "
            "Nastavenia → tinder_headless=false → Rebuild → noVNC login znova → "
            "počkaj 'Login detected' v logu → tinder_headless=true → Reštart."
        )

    def login(self) -> None:
        self.driver.get("https://tinder.com/app/recs")
        self._wait_for_document_ready()
        self._dismiss_cookie_banner()

        self._settle()
        if self._is_logged_in_app():
            self._navigate_to_inbox(fast=True)
            return

        self.driver.get(settings.tinder_login_url)
        self._dismiss_cookie_banner()

        form = self._wait_for_login_form()
        if form is not None and settings.tinder_email and settings.tinder_password:
            email_input, password_input, submit_button = form
            email_input.clear()
            email_input.send_keys(settings.tinder_email)
            password_input.clear()
            password_input.send_keys(settings.tinder_password)
            password_input.send_keys(Keys.TAB)
            try:
                submit_button.click()
            except ElementClickInterceptedException:
                self.driver.execute_script("arguments[0].click();", submit_button)
            self._wait.until(EC.url_contains("/app/"))
            self._navigate_to_inbox(fast=True)
            return

        if settings.headless:
            raise self._headless_session_error()

        # Manual OTP / Google / Facebook login needs far more than the normal
        # Selenium step timeout (default 10s). Allow up to 10 minutes unless
        # TINDER_LOGIN_WAIT_SEC overrides it.
        login_wait = float(
            __import__("os").environ.get("TINDER_LOGIN_WAIT_SEC", "600")
        )
        print(
            "[tinder_bot] No saved session found. A Chrome window has opened — "
            "log in to Tinder there manually (phone OTP / Google / Facebook / Apple). "
            f"Waiting up to {int(login_wait)}s for login to complete..."
        )
        WebDriverWait(self.driver, login_wait).until(EC.url_contains("/app/"))
        print("[tinder_bot] Login detected, session saved to TINDER_USER_DATA_DIR.")
        self._navigate_to_inbox(fast=True)

    def _is_inbox_suggestion(self, name: str, preview: str) -> bool:
        """Skip match ads / Top Picks — not real chat threads (e.g. MISHA row)."""
        label = (name or "").strip()
        text = (preview or "").strip().lower()
        if label == "Nová zhoda":
            return True
        if text.startswith("klikni a začni chatovať"):
            return True
        if "vytvor zhodu" in text or "vytvoř zhodu" in text:
            return True
        if "nedávno aktívny" in text or "nedavno aktivny" in text:
            return True
        if "recently active" in text and "match" in text:
            return True
        return False

    def _preview_looks_sent_by_me(self, preview: str) -> bool:
        """Inbox preview with ← / <- means the last bubble in that chat is ours."""
        text = (preview or "").strip()
        return text.startswith("←") or text.startswith("<-") or text.startswith("↩")

    def find_latest_received_conversation(self, *, max_checks: int = 8) -> dict[str, str]:
        """First real Správy row from the top (Tinder recency order) with any received message.

        Inbox preview with ← only means *you* sent last — not that there is no incoming
        message. Barbora can be #2 with ← while still being the thread we want.
        """
        self._navigate_to_inbox(fast=True)
        seen_ids: set[str] = set()
        checks = 0

        for _ in range(3):
            for row in self._list_conversations():
                match_id = (row.get("match_id") or "").strip()
                name = (row.get("name") or "").strip()
                preview = (row.get("preview") or "").strip()
                if not match_id or match_id in seen_ids:
                    continue
                seen_ids.add(match_id)
                if self._is_inbox_suggestion(name, preview):
                    continue

                checks += 1
                self._open_conversation(match_id)
                if self._latest_received_message():
                    return row
                if checks >= max_checks:
                    break
            if checks >= max_checks:
                break

            scrolled = self.driver.execute_script(
                """
                const grid = document.querySelector('.ReactVirtualized__Grid') ||
                             document.querySelector('[class*="messageList"]') ||
                             document.querySelector('main');
                if (!grid) return false;
                const before = grid.scrollTop;
                grid.scrollTop = before + Math.max(300, grid.clientHeight * 0.8);
                return grid.scrollTop > before;
                """
            )
            if not scrolled:
                break
            time.sleep(0.4)

        raise RuntimeError(
            "No conversation with a received (incoming) message found in Správy list."
        )

    def _list_conversations(self, *, scroll_top: bool = False) -> list[dict[str, str]]:
        """Snapshot Správy rows — sorted by vertical position (top of screen first).

        Do NOT scroll to top by default: Tinder's virtual list at scrollTop=0 is not
        the recency-sorted view the user sees when opening Správy (Barbora would
        become Veronca from the head of the full list).
        """
        if scroll_top:
            self._scroll_conversation_list_to_top()
            time.sleep(0.5)
        rows = self.driver.execute_script(
            _INBOX_ROW_JS
            + """
            return Array.from(document.querySelectorAll("a[href*='/app/messages/']")).map(a => {
                const row = inboxRowFromAnchor(a);
                const href = a.href || '';
                const matchId = href.replace(/\\/$/, '').split('/').pop();
                const top = a.getBoundingClientRect().top;
                return { match_id: matchId || '', name: row.name, preview: row.preview, top };
            }).filter(row => isRealInboxRow(row.name, row.preview))
              .sort((a, b) => a.top - b.top)
              .map(({ top, ...row }) => row);
            """
        )
        return rows if isinstance(rows, list) else []

    def check_new_messages(self) -> list[dict[str, Any]]:
        """Return conversations whose preview changed and whose last message is from them.

        Reads Správy list via JS only. Opens a chat ONLY when preview changed
        from a cached value — never on first sighting (seeding).
        """
        self._navigate_to_inbox()

        preview_cache = self._load_preview_cache()
        results: list[dict[str, Any]] = []
        updated_cache = dict(preview_cache)

        for row in self._list_conversations():
            match_id = (row.get("match_id") or "").strip()
            sender = (row.get("name") or "").strip() or "Neznámy"
            preview = (row.get("preview") or "").strip()
            if not match_id or not preview:
                continue

            previous_preview = preview_cache.get(match_id)
            updated_cache[match_id] = preview

            # First sighting or unchanged preview — seed/update only, no notification.
            if previous_preview is None or previous_preview == preview:
                continue

            self._open_conversation(match_id)
            if not self._last_message_is_received():
                continue

            message_text = self._latest_received_message() or preview
            my_last_message = self._latest_sent_message()

            if message_text:
                results.append(
                    {
                        "conversation_id": match_id,
                        "sender": sender,
                        "message": message_text,
                        "my_last_message": my_last_message,
                    }
                )

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
        is_manual_id = (conversation_id or "").startswith("manual:")
        if is_manual_id:
            self._navigate_to_inbox()
            target = self._find_conversation_by_sender(sender) if sender.strip() else None
        else:
            self._open_conversation(conversation_id)
            target = None

        if target is not None:
            self._click_conversation(target)
            self._settle()
            self._wait_for_chat_loaded()
        elif not is_manual_id:
            if not self._find_conversation_item(conversation_id):
                raise RuntimeError(f"Conversation {conversation_id} not found in inbox")

        message_input = self._wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "textarea[placeholder='Napíš správu'], textarea[placeholder*='správu']")
            )
        )
        self.driver.execute_script(
            "var setter = Object.getOwnPropertyDescriptor("
            "window.HTMLTextAreaElement.prototype, 'value').set;"
            "setter.call(arguments[0], arguments[1]);"
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            message_input,
            text,
        )

        if submit:
            send_button = self._wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button[aria-label='Odoslať správu'], button[type='submit']")
                )
            )
            send_button.click()
        return True
