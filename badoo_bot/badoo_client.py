from __future__ import annotations

import os
import time
from pathlib import Path

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from badoo_bot.config import settings

# Paths that usually mean the user is inside the logged-in web app.
_LOGGED_IN_PATH_MARKERS = (
    "/encounters",
    "/connections",
    "/messages",
    "/people",
    "/likes",
    "/profile",
    "/settings",
    "/premium",
    "/own_profile",
    "/page",
    "/photos",
    "/activity",
    "/visitors",
    "/credits",
)

_LOGGED_OUT_PATH_MARKERS = (
    "/signin",
    "/signup",
    "/landing",
    "/google/authorize",
    "/facebook/authorize",
    "accounts.google.com",
    "accounts.youtube.com",
)


class BadooClient:
    """Selenium client for Badoo — login first; inbox/send come later."""

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver
        self._wait = WebDriverWait(driver, settings.wait_timeout_sec)

    def _settle(self, sec: float | None = None) -> None:
        time.sleep(sec if sec is not None else settings.page_settle_sec)

    def _wait_for_document_ready(self, timeout: float | None = None) -> None:
        limit = timeout if timeout is not None else settings.wait_timeout_sec
        try:
            WebDriverWait(self.driver, limit).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            pass

    def _current_url(self) -> str:
        try:
            return (self.driver.current_url or "").strip()
        except WebDriverException:
            return ""

    def _body_snippet(self, n: int = 400) -> str:
        try:
            return (
                self.driver.execute_script(
                    f"return (document.body && document.body.innerText || '').slice(0,{n});"
                )
                or ""
            )
        except WebDriverException:
            return ""

    def _dismiss_cookie_banner(self) -> None:
        """Accept cookie / consent overlays common on Badoo."""
        selectors = [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
            "[data-qa='cookie-banner-accept']",
            "button[data-testid='cookie-policy-dialog-accept-button']",
            "button.js-cookie-accept",
        ]
        for css in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, css)
                for el in els:
                    if el.is_displayed():
                        el.click()
                        self._settle(1.0)
                        return
            except (StaleElementReferenceException, ElementClickInterceptedException, WebDriverException):
                continue

        # Text-based fallback (SK/EN/CS)
        try:
            clicked = self.driver.execute_script(
                """
                const texts = [
                  'accept all', 'accept', 'agree', 'i agree',
                  'prijať všetko', 'prijat vsetko', 'súhlasím', 'suhlasim',
                  'povoliť všetko', 'povolit vsetko',
                  'souhlasím', 'prijmout vše', 'rozumím'
                ];
                const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                for (const el of buttons) {
                  const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                  if (!t || t.length > 40) continue;
                  if (texts.some(x => t === x || t.includes(x))) {
                    el.click();
                    return true;
                  }
                }
                return false;
                """
            )
            if clicked:
                self._settle(1.0)
        except WebDriverException:
            pass

    def _is_logged_in(self) -> bool:
        url = self._current_url().lower()
        if not url or "badoo.com" not in url:
            # Google OAuth tab / blank — not logged into Badoo yet
            if any(m in url for m in ("accounts.google.com", "accounts.youtube.com")):
                return False
            return False

        if any(m in url for m in _LOGGED_OUT_PATH_MARKERS):
            return False

        if any(m in url for m in _LOGGED_IN_PATH_MARKERS):
            return True

        # Homepage while logged in often has nav / profile chrome without a special path.
        body = self._body_snippet(800).lower()
        logged_out_hints = (
            "sign in",
            "sign up",
            "prihlásiť",
            "prihlasit",
            "vytvoriť účet",
            "continue with google",
            "pokračovať cez google",
            "pokracovat cez google",
        )
        logged_in_hints = (
            "encounters",
            "connections",
            "messages",
            "správy",
            "spravy",
            "people nearby",
            "ľudia nablízku",
            "ludia nablizku",
            "likes you",
            "páčiš sa",
            "pacis sa",
        )
        if any(h in body for h in logged_in_hints) and not any(h in body for h in logged_out_hints):
            return True

        # Session cookie presence as weak signal (combined with not on signin)
        try:
            cookies = {c.get("name", "").lower() for c in self.driver.get_cookies()}
            sessionish = any(
                name.startswith("session") or name in {"device_id", "badoo_s", "sticky"}
                for name in cookies
            )
            if sessionish and "/signin" not in url and "/signup" not in url:
                # Prefer stronger signals — only accept if URL looks like app root
                path = url.split("badoo.com", 1)[-1]
                if path in ("", "/", "/en/", "/en", "/sk/", "/sk", "/cs/", "/cs"):
                    # Ambiguous landing — treat as not logged in unless nav present
                    return any(h in body for h in logged_in_hints)
        except WebDriverException:
            pass
        return False

    def _cookie_file_path(self) -> Path | None:
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
                "Prvé prihlásenie: Nastavenia → badoo_headless=false → noVNC :6081 "
                "→ prihlás sa cez Google → počkaj 'Login detected' v logu → "
                "badoo_headless=true → Reštart."
            )
        return RuntimeError(
            f"Cookie súbor existuje ({cookie}, {cookie.stat().st_size} B), "
            "ale Badoo session nie je aktívna v headless režime. "
            "Nastavenia → badoo_headless=false → Rebuild → noVNC Google login znova → "
            "počkaj 'Login detected' v logu → badoo_headless=true → Reštart."
        )

    def _click_google_login(self) -> bool:
        """Try to start Google OAuth from the Badoo sign-in UI."""
        css_candidates = [
            "a[href*='google/authorize']",
            "a[href*='google'][href*='authorize']",
            "[data-qa*='google']",
            "[data-testid*='google']",
            "button[aria-label*='Google' i]",
            "a[aria-label*='Google' i]",
        ]
        for css in css_candidates:
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, css):
                    if not el.is_displayed():
                        continue
                    try:
                        el.click()
                    except ElementClickInterceptedException:
                        self.driver.execute_script("arguments[0].click();", el)
                    print("[badoo_bot] Clicked Google login control.")
                    self._settle(2.0)
                    return True
            except (StaleElementReferenceException, WebDriverException):
                continue

        try:
            clicked = self.driver.execute_script(
                """
                const needles = [
                  'google', 'продолжить через google', 'continue with google',
                  'continue via google', 'pokračovať cez google', 'pokracovat cez google',
                  'prihlásiť cez google', 'prihlasit cez google'
                ];
                const els = Array.from(document.querySelectorAll('a, button, [role="button"], div[role="button"]'));
                for (const el of els) {
                  const t = ((el.innerText || el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
                  if (!t.trim()) continue;
                  if (needles.some(n => t.includes(n))) {
                    el.click();
                    return true;
                  }
                }
                return false;
                """
            )
            if clicked:
                print("[badoo_bot] Clicked Google login via text match.")
                self._settle(2.0)
                return True
        except WebDriverException:
            pass

        # Direct authorize endpoint (Badoo adds back= itself if missing)
        try:
            self.driver.get("https://badoo.com/google/authorize.phtml")
            self._wait_for_document_ready()
            print("[badoo_bot] Opened Badoo Google authorize URL.")
            return True
        except WebDriverException as exc:
            print(f"[badoo_bot] Google authorize navigation failed: {exc}")
            return False

    def login(self) -> None:
        self.driver.get(settings.badoo_home_url)
        self._wait_for_document_ready()
        self._dismiss_cookie_banner()
        self._settle()

        if self._is_logged_in():
            print("[badoo_bot] Existing Badoo session detected (profile cookies).")
            return

        self.driver.get(settings.badoo_login_url)
        self._wait_for_document_ready()
        self._dismiss_cookie_banner()
        self._settle()

        if self._is_logged_in():
            print("[badoo_bot] Existing Badoo session detected after signin URL.")
            return

        if settings.headless:
            raise self._headless_session_error()

        login_wait = float(os.environ.get("BADOO_LOGIN_WAIT_SEC", "600"))
        print(
            "[badoo_bot] No saved session. Open noVNC and finish Google login "
            f"(or phone/email). Waiting up to {int(login_wait)}s..."
        )
        print("[badoo_bot]   noVNC: http://<IP_HA>:6081/vnc.html")

        self._click_google_login()

        deadline = time.time() + login_wait
        last_url = ""
        while time.time() < deadline:
            url = self._current_url()
            if url != last_url:
                print(f"[badoo_bot] Login wait URL: {url[:120]}")
                last_url = url
            self._dismiss_cookie_banner()
            if self._is_logged_in():
                print("[badoo_bot] Login detected, session saved to BADOO_USER_DATA_DIR.")
                return
            time.sleep(2.0)

        raise TimeoutException(
            f"Badoo login not completed within {int(login_wait)}s. "
            "Dokonči Google prihlásenie v noVNC (:6081) a skús znova."
        )

    # --- Stubs for later inbox / send work ---

    def check_new_messages(self) -> list[dict]:
        """Inbox polling not implemented yet — login-only milestone."""
        print("[badoo_bot] check_new_messages: not implemented yet (login milestone).")
        return []

    def send_reply(self, conversation_id: str, text: str, *, submit: bool = True) -> dict:
        raise NotImplementedError(
            "Badoo send_reply ešte nie je implementované — najprv over login."
        )

    def commit_preview(self, conversation_id: str, preview: str) -> None:
        return
