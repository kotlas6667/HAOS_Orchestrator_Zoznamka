from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from elitedate_bot.chrome_lock import chrome_startup_lock
from elitedate_bot.config import settings

DEFAULT_PROFILE = Path("/data/elitedate_chrome_profile")
FALLBACK_PROFILE = Path("/tmp/elitedate_chrome_profile")


def reset_chrome_profile() -> None:
    """Wipe corrupted Chromium profile dirs (login is email/password — safe to reset)."""
    for path in (DEFAULT_PROFILE, FALLBACK_PROFILE):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
    print("[elitedate_bot] Chrome profile reset (fresh user-data-dir).")


def _log_browser_versions() -> None:
    for cmd in (
        ["/usr/bin/chromium", "--version"],
        ["/usr/bin/chromedriver", "--version"],
    ):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            line = (result.stdout or result.stderr or "").strip()
            if line:
                print(f"[elitedate_bot] {line}")
        except Exception:  # noqa: BLE001
            pass


def _chrome_options(user_data_dir: Path) -> Options:
    browser_name = settings.browser.strip().lower()
    options = EdgeOptions() if browser_name == "edge" else Options()

    if settings.headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-features=VizDisplayCompositor,TranslateUI")
    options.add_argument("--renderer-process-limit=2")
    options.add_argument("--js-flags=--max-old-space-size=256")
    options.add_argument("--password-store=basic")
    options.add_argument(f"--window-size={settings.window_size}")
    options.add_argument(f"--user-data-dir={user_data_dir}")

    options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2}
    )

    if settings.user_agent:
        options.add_argument(f"--user-agent={settings.user_agent}")

    browser_binary = settings.browser_binary or settings.chrome_binary
    if browser_binary:
        options.binary_location = browser_binary

    return options


def _start_driver(options: Options) -> webdriver.Chrome | webdriver.Edge:
    browser_name = settings.browser.strip().lower()
    webdriver_path = settings.webdriver_path or settings.chromedriver_path
    with chrome_startup_lock("elitedate_bot"):
        if browser_name == "edge":
            service = EdgeService(executable_path=webdriver_path) if webdriver_path else EdgeService()
            return webdriver.Edge(service=service, options=options)
        service = Service(executable_path=webdriver_path) if webdriver_path else Service()
        return webdriver.Chrome(service=service, options=options)


def build_driver(*, reset_profile: bool = False) -> webdriver.Chrome | webdriver.Edge:
    """Build headless Chromium — retry with wiped profile + /tmp fallback on crash."""
    if reset_profile:
        reset_chrome_profile()

    last_exc: Exception | None = None
    plans: list[tuple[Path, bool]] = [
        (DEFAULT_PROFILE, reset_profile),
        (DEFAULT_PROFILE, True),
        (FALLBACK_PROFILE, False),
    ]
    seen: set[str] = set()

    for profile_dir, do_reset in plans:
        key = f"{profile_dir}|{do_reset}"
        if key in seen:
            continue
        seen.add(key)
        if do_reset:
            reset_chrome_profile()

        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            driver = _start_driver(_chrome_options(profile_dir))
            driver.set_page_load_timeout(45)
            driver.set_script_timeout(45)
            try:
                driver.implicitly_wait(0)
            except Exception:  # noqa: BLE001
                pass
            if profile_dir != DEFAULT_PROFILE or do_reset:
                print(f"[elitedate_bot] Chrome started with profile: {profile_dir} (reset={do_reset})")
            return driver
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(
                f"[elitedate_bot] build_driver failed (profile={profile_dir}, reset={do_reset}): "
                f"{type(exc).__name__}: {exc!r}"
            )

    _log_browser_versions()
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("build_driver failed without an exception")
