from __future__ import annotations

import re
import time
from typing import Any

from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tinder_bot.config import settings


class TinderClient:
    """Wraps a single logged-in Selenium session against Tinder's web app
    (tinder.com/app/...).

    Tinder has no public messaging API, so every method here drives the real
    DOM. The CSS selectors below are placeholders — open tinder.com/app in a
    real browser, use DevTools (F12 -> Inspect) on the login form / matches
    list / message input, and replace the `By.CSS_SELECTOR, "..."` values
    with the real ones. Tinder's login also usually requires a phone-OTP or
    captcha step Selenium cannot drive; see `tinder_user_data_dir` in
    config.py for the recommended workaround (log in manually once with a
    persistent Chrome profile, then run headless).
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
        for by, selector in (
            (By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"),
            (By.XPATH, "//button[normalize-space()='Accept' or normalize-space()='Prijať všetky']"),
            (By.XPATH, "//button[contains(., 'Accept') or contains(., 'Prijať')]"),
        ):
            if self._click_if_present(by, selector):
                break

    def _dismiss_popups(self) -> None:
        # Tinder frequently shows "Add A Photo" / "Top Picks" / notification
        # permission modals right after login that block the rest of the UI.
        for by, selector in (
            (By.XPATH, "//button[contains(., 'Not interested') or contains(., 'Nie, ďakujem')]"),
            (By.XPATH, "//button[@aria-label='Close' or @aria-label='Zavrieť']"),
        ):
            self._click_if_present(by, selector)

    def _wait_for_login_form(self) -> tuple[Any, Any, Any] | None:
        """Only applicable if the account uses Tinder's legacy email+password
        form (`https://tinder.com/app/login?is_email=true`, if still exposed).
        Returns None when no such form is present (phone/OTP or SSO flow)."""
        try:
            email_input = self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
            password_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            return email_input, password_input, submit_button
        except TimeoutException:
            return None

    def _messages_url(self) -> str:
        return "https://tinder.com/app/messages"

    def _conversation_url(self, item) -> str:
        try:
            href = item.get_attribute("href") or ""
            return href
        except Exception:  # noqa: BLE001
            return ""

    def _conversation_match_id(self, item) -> str:
        href = self._conversation_url(item)
        return href.rstrip("/").split("/")[-1] if href else ""

    def _conversation_sender_name(self, item) -> str:
        try:
            return (item.find_element(By.CSS_SELECTOR, "[class*='matchListName']").text or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _is_unread(self, item) -> bool:
        try:
            return bool(item.find_elements(By.CSS_SELECTOR, "[class*='unread'], [data-unread='true']"))
        except Exception:  # noqa: BLE001
            return False

    def _clean_chat_message_text(self, text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}\s*(AM|PM)?", line, flags=re.IGNORECASE):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _latest_received_message(self) -> str:
        messages = self.driver.find_elements(By.CSS_SELECTOR, "[class*='msg'][class*='receiver'], [class*='messageRow--received']")
        if not messages:
            return ""
        return self._clean_chat_message_text(messages[-1].text)

    def _latest_sent_message(self) -> str:
        messages = self.driver.find_elements(By.CSS_SELECTOR, "[class*='msg'][class*='sender'], [class*='messageRow--sent']")
        if not messages:
            return ""
        return self._clean_chat_message_text(messages[-1].text)

    def _click_conversation(self, item) -> None:
        try:
            item.click()
        except Exception:  # noqa: BLE001
            self.driver.execute_script("arguments[0].click();", item)

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

    def login(self) -> None:
        """Log in using credentials from environment variables (never hardcode them).

        Tinder's actual login flow depends on the account: phone-number OTP,
        Google/Facebook/Apple SSO, or (in some regions) email+password. If
        `tinder_user_data_dir` is configured and the profile already has a
        valid session cookie, this just needs to land on the app and confirm
        we're logged in — no form submission required.
        """
        self.driver.get(self._messages_url())
        self._dismiss_cookie_banner()

        # We requested a /app/... URL ourselves, so `url_contains("/app/")`
        # would trivially pass even before any redirect kicks in. An
        # unauthenticated session gets bounced to the public marketing page
        # (tinder.com/, no "/app/" in the path — not the login page either),
        # so the only reliable "logged in" signal is that we're still on an
        # /app/... URL once navigation has settled.
        time.sleep(3)
        if "/app/" in self.driver.current_url:
            self._dismiss_popups()
            return  # Already logged in via a persisted session (user_data_dir).

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
            self._dismiss_popups()
            return

        if settings.headless:
            raise RuntimeError(
                "No email+password login form detected and no persisted session found. "
                "Set TINDER_USER_DATA_DIR, run once with TINDER_HEADLESS=false, and log in "
                "manually (phone OTP / Google / Facebook / Apple) so the session persists."
            )

        # First-run, no saved session: wait for the user to complete login by
        # hand (phone OTP / Google / Facebook / Apple) in the visible window,
        # then keep going once the app has actually loaded.
        print(
            "[tinder_bot] No saved session found. A Chrome window has opened — "
            "log in to Tinder there manually (phone OTP / Google / Facebook / Apple). "
            "Waiting up to 10 minutes for login to complete..."
        )
        WebDriverWait(self.driver, 600).until(EC.url_contains("/app/"))
        print("[tinder_bot] Login detected, session saved to TINDER_USER_DATA_DIR.")
        self._dismiss_popups()

    def check_new_messages(self) -> list[dict[str, Any]]:
        """Return newly-arrived messages as a list of
        {"conversation_id": str, "sender": str, "message": str, "my_last_message": str}.

        Dedup against previously-seen messages happens in poller.py — this
        method should just return whatever is currently visible/unread.
        """
        self.driver.get(self._messages_url())
        self._dismiss_popups()

        conversation_cards = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/app/messages/']")
        results: list[dict[str, Any]] = []

        for card in conversation_cards:
            if not self._is_unread(card):
                continue

            match_id = self._conversation_match_id(card)
            sender = self._conversation_sender_name(card) or "Neznámy"

            self._click_conversation(card)
            time.sleep(0.3)
            message_text = self._latest_received_message()
            my_last_message = self._latest_sent_message()

            if match_id and message_text:
                results.append(
                    {
                        "conversation_id": match_id,
                        "sender": sender,
                        "message": message_text,
                        "my_last_message": my_last_message,
                    }
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
        self._dismiss_popups()
        time.sleep(0.3)

        is_manual_id = (conversation_id or "").startswith("manual:")
        target = None if is_manual_id else self._find_conversation_item(conversation_id)

        if target is None and sender.strip():
            target = self._find_conversation_by_sender(sender)

        if target is None:
            raise RuntimeError(f"Conversation {conversation_id} not found in inbox")

        self._click_conversation(target)
        time.sleep(0.3)

        message_input = self._wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[name='matchMessage']"))
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
            send_button = self._wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
            send_button.click()
        return True
