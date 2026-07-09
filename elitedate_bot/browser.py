from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from elitedate_bot.config import settings


def build_driver() -> webdriver.Chrome | webdriver.Edge:
    """Build a headless browser driver.

    Supports Chrome/Chromium and Edge. Tuned for Raspberry Pi (limited RAM/CPU,
    small /dev/shm) but works the same way on a regular desktop.
    """
    browser_name = settings.browser.strip().lower()
    if browser_name == "edge":
        options = EdgeOptions()
    else:
        options = Options()

    if settings.headless:
        options.add_argument("--headless=new")

    # Raspberry Pi essentials: /dev/shm is tiny by default and Chrome will crash
    # without --disable-dev-shm-usage; --no-sandbox is required when running as
    # a non-root systemd service without extra sandboxing capabilities.
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={settings.window_size}")

    if settings.user_agent:
        options.add_argument(f"--user-agent={settings.user_agent}")

    browser_binary = settings.browser_binary or settings.chrome_binary
    if browser_binary:
        options.binary_location = browser_binary

    webdriver_path = settings.webdriver_path or settings.chromedriver_path
    if browser_name == "edge":
        service = EdgeService(executable_path=webdriver_path) if webdriver_path else EdgeService()
        driver = webdriver.Edge(service=service, options=options)
    else:
        service = Service(executable_path=webdriver_path) if webdriver_path else Service()
        driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(30)
    return driver
