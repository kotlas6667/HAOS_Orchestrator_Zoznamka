from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from tinder_bot.config import settings


def build_driver() -> webdriver.Chrome | webdriver.Edge:
    """Build a browser driver for Tinder.

    Supports Chrome/Chromium and Edge. Tuned for Raspberry Pi (limited RAM/CPU,
    small /dev/shm) but works the same way on a regular desktop. Tinder's login
    usually requires solving a phone-OTP or captcha challenge that Selenium
    cannot drive reliably — see the note on `tinder_user_data_dir` in config.py.
    """
    browser_name = settings.browser.strip().lower()
    if browser_name == "edge":
        options = EdgeOptions()
    else:
        options = Options()

    if settings.headless:
        # Legacy --headless (not --headless=new): --single-process is only
        # reliably honored in this mode and cuts memory drastically by
        # running the renderer inside the browser process instead of a
        # separate one that can get OOM-killed ("tab crashed").
        options.add_argument("--headless")

        # Raspberry Pi essentials: /dev/shm is tiny by default and Chrome will
        # crash without --disable-dev-shm-usage; --single-process/--no-zygote
        # cut memory further. These are unstable for a *visible* desktop Chrome
        # window (crashes on Windows), so only apply them in headless mode —
        # headed mode is for the one-time manual login, run on a normal desktop.
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        options.add_argument("--mute-audio")
        options.add_argument("--no-zygote")
        options.add_argument("--single-process")
        options.add_argument("--renderer-process-limit=1")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-features=VizDisplayCompositor")

    options.add_argument("--disable-extensions")
    options.add_argument(f"--window-size={settings.window_size}")

    # Skip loading images: cuts per-page memory a lot and this bot only reads
    # text (messages, sender names), never needs rendered images.
    options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2}
    )

    if settings.user_data_dir:
        # Persistent profile so a manually-solved login/OTP/captcha survives
        # across restarts instead of re-triggering every time.
        options.add_argument(f"--user-data-dir={settings.user_data_dir}")

    if settings.user_agent:
        options.add_argument(f"--user-agent={settings.user_agent}")

    if settings.browser_binary:
        options.binary_location = settings.browser_binary

    if browser_name == "edge":
        service = EdgeService(executable_path=settings.webdriver_path) if settings.webdriver_path else EdgeService()
        driver = webdriver.Edge(service=service, options=options)
    else:
        service = Service(executable_path=settings.webdriver_path) if settings.webdriver_path else Service()
        driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(30)
    return driver
