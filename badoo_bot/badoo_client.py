from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from badoo_bot.config import settings

_PREVIEW_CACHE_FILE = Path(settings.seen_messages_file).parent / ".conversation_previews.json"
_CACHE_META_KEY = "__meta__"

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

# Real DOM (user-verified):
# - logged-in: https://fr1.badoo.com/en/encounters
# - Chats tab: button[data-qa=connections]
# - list: ul.csms-connections-list > li[data-qa=connections-list-item]
# - user row: [data-qa=connections-item][data-qa-connections-item-type=user]
# - name: [data-qa=profile-info__name] .csms-profile-info__name-inner
# - preview: [data-qa=csms-connections-item__message]
# - open chat: button[data-qa=connections-item-content]
# - skip promo + swipe-menu ("Unmatch & Block")
_INBOX_ROW_JS = r"""
function reactUserId(el) {
    const key = Object.keys(el || {}).find(k =>
        k.startsWith('__reactFiber') ||
        k.startsWith('__reactInternalInstance') ||
        k.startsWith('__reactProps')
    );
    if (!key) return '';
    let fiber = el[key];
    if (fiber && fiber.item && fiber.item.user_id) return String(fiber.item.user_id);
    if (fiber && fiber.user && (fiber.user.id || fiber.user.user_id)) {
        return String(fiber.user.id || fiber.user.user_id);
    }
    if (fiber && fiber.userId) return String(fiber.userId);
    for (let i = 0; i < 50 && fiber; i++) {
        const p = fiber.memoizedProps || fiber.pendingProps || fiber;
        if (!p || typeof p !== 'object') { fiber = fiber.return; continue; }
        if (p.item && (p.item.user_id || (p.item.user && p.item.user.user_id))) {
            return String(p.item.user_id || p.item.user.user_id);
        }
        if (p.user && (p.user.id || p.user.user_id)) return String(p.user.id || p.user.user_id);
        if (p.userId) return String(p.userId);
        if (p.id && /^\d{5,}$/.test(String(p.id))) return String(p.id);
        fiber = fiber.return;
    }
    return '';
}
function isJunkName(name) {
    const n = (name || '').trim().toLowerCase();
    if (!n) return true;
    if (n === 'badoo') return true; // system / tips account
    if (n.includes('unmatch') || n.includes('block') || n.includes('report')) return true;
    if (n.includes('odblok') || n.includes('odpojiť') || n.includes('odpojit')) return true;
    if (n.includes('liked you') || n.includes('páčiš sa') || n.includes('pacis sa')) return true;
    if (n.includes('matter of time') || n.includes('someone new likes')) return true;
    return false;
}
function isUserConnection(el) {
    const type = (el.getAttribute('data-qa-connections-item-type') || '').toLowerCase();
    if (type && type !== 'user') return false;
    if (el.getAttribute('data-qa-feature-card') !== null) return false;
    const cls = String(el.className || '');
    if (cls.includes('csms-connections-item--promo') || cls.includes('--promo')) return false;
    return type === 'user' || cls.includes('csms-connections-item--user');
}
function inboxRowFromItem(el) {
    const nameEl = el.querySelector(
        '[data-qa="profile-info__name"] .csms-profile-info__name-inner, '
        + '[data-qa="profile-info__name"], .csms-profile-info__name-inner'
    );
    let name = nameEl ? (nameEl.innerText || nameEl.textContent || '').trim() : '';
    if (name.includes(',')) {
        const left = name.split(',')[0].trim();
        if (left) name = left;
    }
    const msgEl = el.querySelector('[data-qa="csms-connections-item__message"], .csms-connections-item__message');
    let preview = msgEl ? (msgEl.innerText || msgEl.textContent || '').trim() : '';
    preview = preview.replace(/\b\d{1,2}:\d{2}\b\s*$/, '').trim();
    if (/^\d{1,2}$/.test(preview) || isJunkName(preview)) preview = '';

    const openBtn = el.querySelector('button[data-qa="connections-item-content"], .csms-connections-item__user');
    const domId = (
        (openBtn && openBtn.getAttribute('aria-describedby')) ||
        (msgEl && msgEl.id) ||
        ''
    ).trim();
    const numericId = reactUserId(el);
    // Prefer numeric user_id for /messages/{id}; else stable DOM id for preview cache + click.
    let matchId = numericId || domId;
    if (!matchId && name && !isJunkName(name)) {
        matchId = 'name:' + name.toLowerCase().replace(/\s+/g, '_').slice(0, 64);
    }
    return { name, preview, match_id: matchId, numeric_id: numericId || '', dom_id: domId };
}
function isRealInboxRow(name, preview) {
    if (!name || !preview) return false;
    if (isJunkName(name)) return false;
    const pl = preview.toLowerCase();
    if (/^\d{1,2}$/.test(preview)) return false;
    if (pl.includes('start chatting') || pl.includes('začni chat') || pl.includes('zacni chat')) return false;
    if (pl.includes('liked you') || pl.includes('páčiš sa') || pl.includes('pacis sa')) return false;
    if (pl.includes('welcome back') && name.toLowerCase() === 'badoo') return false;
    return true;
}
function listConnectionItems() {
    const fromList = Array.from(document.querySelectorAll(
        'ul.csms-connections-list [data-qa="connections-item"][data-qa-connections-item-type="user"], '
        + 'li[data-qa="connections-list-item"] [data-qa="connections-item"][data-qa-connections-item-type="user"]'
    ));
    if (fromList.length) return fromList.filter(isUserConnection);
    return Array.from(document.querySelectorAll(
        '[data-qa="connections-item"][data-qa-connections-item-type="user"]'
    )).filter(isUserConnection);
}
function clickConnectionItem(el) {
    if (!el) return false;
    const target = el.querySelector(
        'button[data-qa="connections-item-content"], .csms-connections-item__user'
    );
    if (target) { target.click(); return true; }
    const content = el.querySelector('.csms-connections-item__content');
    if (content) { content.click(); return true; }
    el.click();
    return true;
}
"""


class BadooClient:
    """Selenium client for Badoo — login, inbox poll, send (mirrors Tinder)."""

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver
        self._wait = WebDriverWait(driver, settings.wait_timeout_sec)

    def _settle(self, sec: float | None = None) -> None:
        time.sleep(sec if sec is not None else settings.page_settle_sec)

    def _poll_interval(self) -> float:
        return max(0.5, settings.page_settle_sec / 6)

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

    def _click_if_present(self, by: By, selector: str) -> bool:
        try:
            el = self.driver.find_element(by, selector)
            if el.is_displayed():
                el.click()
                return True
        except Exception:  # noqa: BLE001
            return False
        return False

    def _dismiss_cookie_banner(self) -> None:
        selectors = [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
            "[data-qa='cookie-banner-accept']",
            "button[data-testid='cookie-policy-dialog-accept-button']",
            "button.js-cookie-accept",
        ]
        for css in selectors:
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, css):
                    if el.is_displayed():
                        el.click()
                        self._settle(1.0)
                        return
            except (StaleElementReferenceException, ElementClickInterceptedException, WebDriverException):
                continue
        try:
            clicked = self.driver.execute_script(
                """
                const texts = [
                  'accept all', 'accept', 'agree', 'i agree',
                  'prijať všetko', 'prijat vsetko', 'súhlasím', 'suhlasim',
                  'povoliť všetko', 'povolit vsetko', 'souhlasím', 'prijmout vše'
                ];
                const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                for (const el of buttons) {
                  const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                  if (!t || t.length > 40) continue;
                  if (texts.some(x => t === x || t.includes(x))) { el.click(); return true; }
                }
                return false;
                """
            )
            if clicked:
                self._settle(1.0)
        except WebDriverException:
            pass

    def _dismiss_popups(self) -> None:
        # Rate-app drawer: Close (X) or Cancel — do not interact with stars.
        for css in (
            '[data-qa="rate-app"] button[data-qa="modal-close"]',
            'button[data-qa="modal-close"]',
            'button[data-qa="modal-action-cancel"]',
            '[data-qa="rate-app"] button[data-qa="modal-action-cancel"]',
        ):
            if self._click_if_present(By.CSS_SELECTOR, css):
                self._settle(0.6)
                break
        for by, selector in (
            (By.CSS_SELECTOR, "button[aria-label='Close']"),
            (By.CSS_SELECTOR, "button[aria-label='Zavrieť']"),
            (By.XPATH, "//button[contains(., 'Neskôr') or contains(., 'Later') or contains(., 'Not now')]"),
            (By.XPATH, "//button[contains(., 'Nie, ďakujem') or contains(., 'No thanks') or contains(., 'Cancel')]"),
            (By.CSS_SELECTOR, "[data-qa='close']"),
        ):
            self._click_if_present(by, selector)
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:  # noqa: BLE001
            pass

    def _site_base(self) -> str:
        """Preserve regional host + locale, e.g. https://fr1.badoo.com/en."""
        raw = self._current_url() or settings.badoo_home_url
        try:
            parsed = urlparse(raw)
        except Exception:  # noqa: BLE001
            return "https://badoo.com"
        if not parsed.scheme or not parsed.netloc or "badoo.com" not in parsed.netloc.lower():
            return "https://badoo.com"
        locale = ""
        parts = [p for p in (parsed.path or "/").split("/") if p]
        if parts and re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", parts[0], flags=re.I):
            locale = "/" + parts[0].lower()
        return f"{parsed.scheme}://{parsed.netloc}{locale}"

    def _click_chats_tab(self) -> bool:
        """Open Connections/Chats via bottom tabbar (data-qa=connections)."""
        try:
            clicked = self.driver.execute_script(
                """
                const tab = document.querySelector('button[data-qa="connections"], [data-qa="connections"]');
                if (!tab) return false;
                tab.click();
                return true;
                """
            )
            if clicked:
                print("[badoo_bot] Clicked Chats tab (data-qa=connections).")
                self._settle(1.2)
                return True
        except WebDriverException:
            pass
        return False

    def _is_logged_in(self) -> bool:
        url = self._current_url().lower()
        if not url or "badoo.com" not in url:
            if any(m in url for m in ("accounts.google.com", "accounts.youtube.com")):
                return False
            return False
        if any(m in url for m in _LOGGED_OUT_PATH_MARKERS):
            return False
        if any(m in url for m in _LOGGED_IN_PATH_MARKERS):
            return True
        body = self._body_snippet(800).lower()
        logged_out_hints = (
            "sign in", "sign up", "prihlásiť", "prihlasit", "vytvoriť účet",
            "continue with google", "pokračovať cez google", "pokracovat cez google",
        )
        logged_in_hints = (
            "encounters", "connections", "messages", "správy", "spravy",
            "people nearby", "ľudia nablízku", "ludia nablizku", "likes you",
        )
        if any(h in body for h in logged_in_hints) and not any(h in body for h in logged_out_hints):
            return True
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
                "→ prihlás sa cez Google → počkaj 'Login detected' → "
                "badoo_headless=true → Reštart."
            )
        return RuntimeError(
            f"Cookie súbor existuje ({cookie}, {cookie.stat().st_size} B), "
            "ale Badoo session nie je aktívna v headless režime. "
            "Nastavenia → badoo_headless=false → Rebuild → noVNC Google login znova → "
            "počkaj 'Login detected' → badoo_headless=true → Reštart."
        )

    def _click_google_login(self) -> bool:
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
                  'google', 'continue with google', 'continue via google',
                  'pokračovať cez google', 'pokracovat cez google',
                  'prihlásiť cez google', 'prihlasit cez google'
                ];
                const els = Array.from(document.querySelectorAll('a, button, [role="button"]'));
                for (const el of els) {
                  const t = ((el.innerText || el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
                  if (!t.trim()) continue;
                  if (needles.some(n => t.includes(n))) { el.click(); return true; }
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
        self._dismiss_popups()
        self._settle()

        if self._is_logged_in():
            print(f"[badoo_bot] Existing Badoo session detected: {self._current_url()}")
            self._dismiss_cookie_banner()
            self._dismiss_popups()
            self._navigate_to_inbox(fast=True)
            return

        self.driver.get(settings.badoo_login_url)
        self._wait_for_document_ready()
        self._dismiss_cookie_banner()
        self._dismiss_popups()
        self._settle()

        if self._is_logged_in():
            print(f"[badoo_bot] Existing Badoo session after signin URL: {self._current_url()}")
            self._dismiss_cookie_banner()
            self._dismiss_popups()
            self._navigate_to_inbox(fast=True)
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
            self._dismiss_popups()
            if self._is_logged_in():
                print(f"[badoo_bot] Login detected: {self._current_url()}")
                self._dismiss_cookie_banner()
                self._dismiss_popups()
                self._navigate_to_inbox(fast=True)
                return
            time.sleep(2.0)

        raise TimeoutException(
            f"Badoo login not completed within {int(login_wait)}s. "
            "Dokonči Google prihlásenie v noVNC (:6081) a skús znova."
        )

    # --- Inbox / chat ---

    def _inbox_url(self) -> str:
        return f"{self._site_base()}/connections"

    def _conversation_url(self, match_id: str) -> str:
        cid = (match_id or "").strip().lstrip("/")
        if cid.startswith("http"):
            return cid
        # Only numeric Badoo user ids deep-link to /messages/{id}.
        if not re.fullmatch(r"\d{5,}", cid):
            return ""
        return f"{self._site_base()}/messages/{cid}"

    def _on_connections_list(self) -> bool:
        url = self._current_url().lower()
        if "/messages/" in url:
            return False
        try:
            return bool(
                self.driver.execute_script(
                    """
                    return !!document.querySelector(
                      'ul.csms-connections-list, [data-qa="connections-item"][data-qa-connections-item-type="user"]'
                    );
                    """
                )
            )
        except WebDriverException:
            return "/connections" in url

    def _navigate_to_inbox(self, *, fast: bool = False) -> None:
        self._dismiss_cookie_banner()
        self._dismiss_popups()

        if self._on_connections_list() and not fast:
            if self._count_conversation_previews() > 0:
                return

        # Prefer Chats tab from encounters (same SPA session / regional host).
        if not self._on_connections_list():
            if not self._click_chats_tab():
                self.driver.get(self._inbox_url())
                self._wait_for_document_ready()

        self._dismiss_cookie_banner()
        self._dismiss_popups()
        self._settle(1.5 if fast else settings.page_settle_sec)

        if not self._on_connections_list():
            # Tab may need a second click after encounters hydrate.
            self._click_chats_tab()
            self._settle(1.0)
            if not self._on_connections_list():
                self.driver.get(self._inbox_url())
                self._wait_for_document_ready()
                self._dismiss_cookie_banner()
                self._dismiss_popups()
                self._settle(1.5)

        self._wait_for_inbox_rows(timeout=20.0 if fast else settings.wait_timeout_sec)
        print(
            f"[badoo_bot] Inbox ready url={self._current_url()} "
            f"rows={self._count_conversation_previews()}"
        )

    def _count_conversation_previews(self) -> int:
        count = self.driver.execute_script(
            _INBOX_ROW_JS
            + """
            return listConnectionItems().filter(el => {
                const row = inboxRowFromItem(el);
                return isRealInboxRow(row.name, row.preview);
            }).length;
            """
        )
        return int(count or 0)

    def _wait_for_inbox_rows(self, timeout: float | None = None) -> None:
        deadline = time.time() + (timeout if timeout is not None else settings.wait_timeout_sec)
        while time.time() < deadline:
            if self._count_conversation_previews() > 0:
                self._settle(0.5)
                return
            time.sleep(self._poll_interval())

    def _list_conversations(self) -> list[dict[str, str]]:
        rows = self.driver.execute_script(
            _INBOX_ROW_JS
            + """
            return listConnectionItems().map(el => {
                const row = inboxRowFromItem(el);
                const top = el.getBoundingClientRect().top;
                return {
                  match_id: row.match_id,
                  name: row.name,
                  preview: row.preview,
                  top
                };
            }).filter(row => isRealInboxRow(row.name, row.preview))
              .sort((a, b) => a.top - b.top)
              .map(({ top, ...row }) => row);
            """
        )
        return rows if isinstance(rows, list) else []

    def _scroll_inbox_down(self) -> bool:
        return bool(
            self.driver.execute_script(
                """
                const sels = [
                  'ul.csms-connections-list',
                  '.connections__items',
                  '.connections-items',
                  '[class*="connections__items"]',
                  '[class*="connections-items"]',
                  'main',
                  '[role="main"]',
                ];
                let grid = null;
                for (const sel of sels) {
                  const el = document.querySelector(sel);
                  if (!el) continue;
                  const scrollParent = el.closest('[class*="scroll"], .csms-modal__scrollable, main') || el.parentElement || el;
                  const candidate = (scrollParent.scrollHeight > scrollParent.clientHeight + 40)
                    ? scrollParent
                    : (el.scrollHeight > el.clientHeight + 40 ? el : null);
                  if (candidate) { grid = candidate; break; }
                }
                if (!grid) grid = document.scrollingElement;
                if (!grid) return false;
                const before = grid.scrollTop || 0;
                grid.scrollTop = before + Math.max(300, (grid.clientHeight || 600) * 0.8);
                return (grid.scrollTop || 0) > before;
                """
            )
        )

    def _list_conversations_scrolled(self, *, max_steps: int = 5) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for step in range(max(1, max_steps)):
            for row in self._list_conversations():
                match_id = (row.get("match_id") or "").strip()
                if not match_id or match_id in seen_ids:
                    continue
                seen_ids.add(match_id)
                merged.append(row)
            if step + 1 >= max_steps:
                break
            if not self._scroll_inbox_down():
                break
            time.sleep(0.35)
        return merged

    def _click_connection_item(self, match_id: str) -> bool:
        return bool(
            self.driver.execute_script(
                _INBOX_ROW_JS
                + """
                const want = String(arguments[0] || '');
                for (const el of listConnectionItems()) {
                  const row = inboxRowFromItem(el);
                  if (row && row.match_id === want) {
                    return clickConnectionItem(el);
                  }
                }
                return false;
                """,
                match_id,
            )
        )

    def _open_conversation(self, match_id: str) -> None:
        cid = (match_id or "").strip()
        if not cid:
            raise RuntimeError("Empty Badoo conversation_id")

        # Prefer clicking the Connections row (stable for DOM ids like user-5104cb9d).
        self._navigate_to_inbox()
        if self._click_connection_item(cid):
            self._settle()
            self._dismiss_popups()
            self._wait_for_chat_messages()
            return

        deep = self._conversation_url(cid)
        if deep:
            self.driver.get(deep)
            self._wait_for_document_ready()
            self._dismiss_popups()
            self._settle()
            if "/messages/" in self._current_url().lower():
                self._wait_for_chat_messages()
                return

        raise RuntimeError(f"Badoo conversation not found in connections: {cid}")

    def _wait_for_chat_messages(self, timeout: float | None = None) -> None:
        deadline = time.time() + (timeout if timeout is not None else settings.wait_timeout_sec)
        while time.time() < deadline:
            self._dismiss_popups()
            count = self.driver.execute_script(
                """
                return document.querySelectorAll(
                  '[data-qa="message"], [data-qa="chat-message"], '
                  + '[data-qa-message-direction], [data-message-direction], '
                  + '.csms-chat-message-content-text__message, '
                  + '[class*="message-bubble"], [class*="chat-message"]'
                ).length;
                """
            )
            if int(count or 0) > 0:
                self._settle(0.5)
                return
            # Composer present = chat open even if empty
            if self.driver.execute_script(
                "return !!document.querySelector("
                "'#chat-composer-input-message, [data-qa=\"messenger-chat-input\"], "
                "textarea[placeholder*=\"message\" i], [contenteditable=\"true\"]');"
            ):
                return
            time.sleep(self._poll_interval())

    def _iter_chat_bubbles(self) -> list[Any]:
        for css in (
            '[data-qa="message"]',
            '[data-qa="chat-message"]',
            "[data-qa-message-direction]",
            "[data-message-direction]",
            ".csms-chat-messages [class*='message']",
            "[class*='message-bubble']",
        ):
            bubbles = self.driver.find_elements(By.CSS_SELECTOR, css)
            if bubbles:
                return bubbles
        return []

    def _bubble_direction(self, bubble) -> str:
        try:
            direction = (
                bubble.get_attribute("data-qa-message-direction")
                or bubble.get_attribute("data-message-direction")
                or ""
            ).strip().lower()
            if direction in {"out", "outgoing", "sent", "self", "me"}:
                return "out"
            if direction in {"in", "incoming", "received", "them"}:
                return "in"
        except Exception:  # noqa: BLE001
            pass
        try:
            cls = (bubble.get_attribute("class") or "").lower()
            if any(x in cls for x in ("out", "sent", "self", "own")):
                return "out"
            if any(x in cls for x in ("in", "received", "other")):
                return "in"
        except Exception:  # noqa: BLE001
            pass
        try:
            mid = self.driver.execute_script(
                """
                const r = arguments[0].getBoundingClientRect();
                return r.left + r.width / 2;
                """,
                bubble,
            )
            width = self.driver.execute_script("return window.innerWidth;") or 1366
            return "out" if float(mid) > float(width) / 2 else "in"
        except Exception:  # noqa: BLE001
            return ""

    def _bubble_text(self, bubble) -> str:
        try:
            text = self.driver.execute_script(
                """
                const el = arguments[0];
                const preferred = el.querySelector(
                  '.csms-chat-message-content-text__message, [data-qa-message-content-type="text"], [dir="auto"]'
                );
                const raw = (preferred && preferred.innerText) || el.innerText || '';
                return (raw || '').trim();
                """,
                bubble,
            )
            return (text or "").strip()
        except Exception:  # noqa: BLE001
            return (bubble.text or "").strip()

    def _is_received_bubble(self, bubble) -> bool:
        return self._bubble_direction(bubble) == "in"

    def _is_sent_bubble(self, bubble) -> bool:
        return self._bubble_direction(bubble) == "out"

    def _latest_received_message(self) -> str:
        bubbles = self._iter_chat_bubbles()
        parts: list[str] = []
        for bubble in reversed(bubbles):
            if not self._is_received_bubble(bubble):
                if parts:
                    break
                continue
            text = self._bubble_text(bubble)
            if text:
                parts.append(text)
        if not parts:
            return ""
        parts.reverse()
        return "\n\n".join(parts).strip()

    def _latest_sent_message(self) -> str:
        bubbles = self._iter_chat_bubbles()
        parts: list[str] = []
        for bubble in reversed(bubbles):
            if self._is_received_bubble(bubble):
                if parts:
                    break
                continue
            if not self._is_sent_bubble(bubble):
                if parts:
                    break
                continue
            text = self._bubble_text(bubble)
            if text:
                parts.append(text)
        if not parts:
            return ""
        parts.reverse()
        return "\n\n".join(parts).strip()

    def _last_message_is_received(self) -> bool:
        bubbles = self._iter_chat_bubbles()
        if not bubbles:
            return False
        return self._is_received_bubble(bubbles[-1])

    def _extract_chat_history(self, *, max_messages: int = 24) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for bubble in self._iter_chat_bubbles():
            text = self._bubble_text(bubble)
            if not text:
                continue
            role = "them" if self._is_received_bubble(bubble) else "me"
            history.append({"role": role, "text": text})
        if len(history) > max_messages:
            history = history[-max_messages:]
        return history

    def _preview_looks_sent_by_me(self, preview: str) -> bool:
        text = (preview or "").strip().lower()
        if text.startswith("←") or text.startswith("<-") or text.startswith("↩"):
            return True
        if text.startswith("you:") or text.startswith("ty:") or text.startswith("vy:"):
            return True
        return False

    def _load_preview_cache(self) -> dict[str, Any]:
        if _PREVIEW_CACHE_FILE.exists():
            try:
                data = json.loads(_PREVIEW_CACHE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _save_preview_cache(self, cache: dict[str, Any]) -> None:
        _PREVIEW_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PREVIEW_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _preview_cache_bootstrapped(self, cache: dict[str, Any]) -> bool:
        meta = cache.get(_CACHE_META_KEY)
        if isinstance(meta, dict) and "bootstrapped" in meta:
            return bool(meta.get("bootstrapped"))
        return any(k != _CACHE_META_KEY for k in cache)

    def _thread_preview_cache(self, cache: dict[str, Any]) -> dict[str, str]:
        return {k: str(v) for k, v in cache.items() if k != _CACHE_META_KEY and v is not None}

    def commit_preview(self, conversation_id: str, preview: str) -> None:
        cid = (conversation_id or "").strip()
        text = (preview or "").strip()
        if not cid or not text:
            return
        cache = self._load_preview_cache()
        cache[cid] = text
        if _CACHE_META_KEY not in cache:
            cache[_CACHE_META_KEY] = {"bootstrapped": True}
        self._save_preview_cache(cache)

    def _build_message_result(
        self,
        match_id: str,
        sender: str,
        message_text: str,
        preview: str,
    ) -> dict[str, Any]:
        return {
            "conversation_id": match_id,
            "sender": sender,
            "message": message_text,
            "my_last_message": self._latest_sent_message(),
            "preview": preview,
            "history": self._extract_chat_history(max_messages=24),
        }

    def check_new_messages(self) -> list[dict[str, Any]]:
        """Return conversations whose preview changed and whose last message is from them."""
        self._navigate_to_inbox()

        raw_cache = self._load_preview_cache()
        bootstrapped = self._preview_cache_bootstrapped(raw_cache)
        preview_cache = self._thread_preview_cache(raw_cache)
        seeding = not bootstrapped
        scroll_steps = 20 if seeding else 5
        rows = self._list_conversations_scrolled(max_steps=scroll_steps)

        results: list[dict[str, Any]] = []
        updated_threads = dict(preview_cache)
        preview_changes = 0

        for row in rows:
            match_id = (row.get("match_id") or "").strip()
            sender = (row.get("name") or "").strip() or "Neznámy"
            preview = (row.get("preview") or "").strip()
            if not match_id or not preview:
                continue

            previous_preview = preview_cache.get(match_id)

            if seeding:
                if not self._preview_looks_sent_by_me(preview):
                    try:
                        self._open_conversation(match_id)
                        if self._last_message_is_received():
                            message_text = self._latest_received_message() or preview
                            if message_text:
                                results.append(
                                    self._build_message_result(
                                        match_id, sender, message_text, preview
                                    )
                                )
                                print(
                                    f"[badoo_bot] Bootstrap unread from {sender} "
                                    f"(preview seed + verify)"
                                )
                                continue
                    except Exception as exc:  # noqa: BLE001
                        print(f"[badoo_bot] bootstrap verify skip {match_id}: {exc}")
                updated_threads[match_id] = preview
                continue

            if previous_preview == preview:
                continue

            preview_changes += 1

            if previous_preview is None:
                if self._preview_looks_sent_by_me(preview):
                    updated_threads[match_id] = preview
                    continue

            try:
                self._open_conversation(match_id)
                if not self._last_message_is_received():
                    updated_threads[match_id] = preview
                    print(f"[badoo_bot] Preview changed but last bubble is ours: {sender}")
                    continue

                message_text = self._latest_received_message() or preview
                if not message_text:
                    continue

                results.append(
                    self._build_message_result(match_id, sender, message_text, preview)
                )
                print(
                    f"[badoo_bot] New message from {sender} "
                    f"(history_turns={len(results[-1].get('history') or [])})"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[badoo_bot] check_new_messages skip {match_id}: {exc}")
                continue

        save_cache: dict[str, Any] = dict(updated_threads)
        save_cache[_CACHE_META_KEY] = {"bootstrapped": True}
        self._save_preview_cache(save_cache)
        print(
            f"[badoo_bot] Poll done: rows={len(rows)} preview_changes={preview_changes} "
            f"new={len(results)} seeding={seeding}"
        )
        return results

    def _find_conversation_by_sender(self, sender: str):
        wanted = (sender or "").strip().lower()
        if not wanted:
            return None
        for row in self._list_conversations_scrolled(max_steps=8):
            name = (row.get("name") or "").strip().lower()
            if name and (wanted in name or name in wanted):
                return row
        return None

    def _find_message_input(self):
        selectors = (
            "#chat-composer-input-message",
            "textarea#chat-composer-input-message",
            "[data-qa='chat-input-textarea']",
            "[data-qa='chat-composer-input']",
            "textarea[placeholder*='message' i]",
            "textarea[placeholder*='správ' i]",
            "div[contenteditable='true']",
            "form textarea",
            "textarea",
        )
        last_exc: Exception | None = None
        for css in selectors:
            try:
                return self._wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        raise TimeoutException(
            f"Badoo message input not found. url={self._current_url()}"
        ) from last_exc

    def _find_send_button(self):
        selectors = (
            "button[data-qa='messenger-chat-send-circle']",
            "[data-qa='messenger-chat-send-circle']",
            "button[data-qa='action-send']",
            "[data-qa='action-send']",
            "button[data-qa='chat-composer-send']",
            "button[aria-label*='Send' i]",
            "button[aria-label*='Odoslať' i]",
            "button[type='submit']",
            "form button[type='submit']",
            "[class*='composer'] button[type='submit']",
        )
        last_exc: Exception | None = None
        for css in selectors:
            try:
                return self._wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        raise TimeoutException(
            f"Badoo send button not found. url={self._current_url()}"
        ) from last_exc

    def send_reply(
        self,
        conversation_id: str,
        text: str,
        *,
        submit: bool = True,
        sender: str = "",
        expected_message: str = "",
    ) -> bool:
        _ = expected_message
        is_manual_id = (conversation_id or "").startswith("manual:")
        if is_manual_id:
            self._navigate_to_inbox()
            row = self._find_conversation_by_sender(sender) if sender.strip() else None
            if row is None:
                raise RuntimeError(f"Conversation for sender={sender!r} not found in inbox")
            self._open_conversation(row["match_id"])
        else:
            self._open_conversation(conversation_id)

        message_input = self._find_message_input()
        tag = (message_input.tag_name or "").lower()
        if tag == "textarea" or tag == "input":
            self.driver.execute_script(
                "var el = arguments[0], val = arguments[1];"
                "var proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype"
                " : window.HTMLInputElement.prototype;"
                "var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;"
                "setter.call(el, val);"
                "el.dispatchEvent(new Event('input', { bubbles: true }));"
                "el.dispatchEvent(new Event('change', { bubbles: true }));",
                message_input,
                text,
            )
        else:
            self.driver.execute_script(
                "arguments[0].focus();"
                "arguments[0].textContent = arguments[1];"
                "arguments[0].dispatchEvent(new InputEvent('input', { bubbles: true, data: arguments[1] }));",
                message_input,
                text,
            )

        if submit:
            send_button = self._find_send_button()
            try:
                send_button.click()
            except Exception:  # noqa: BLE001
                self.driver.execute_script("arguments[0].click();", send_button)
        return True
