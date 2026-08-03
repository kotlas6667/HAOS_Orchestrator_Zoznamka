from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from badoo_bot.chrome_lock import chrome_startup_lock
from badoo_bot.config import settings


def build_driver() -> webdriver.Chrome | webdriver.Edge:
    """Build a browser driver for Badoo (same container flags as Tinder)."""
    browser_name = settings.browser.strip().lower()
    if browser_name == "edge":
        options = EdgeOptions()
    else:
        options = Options()

    if settings.headless:
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        options.add_argument("--mute-audio")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-features=VizDisplayCompositor,TranslateUI")
        options.add_argument("--renderer-process-limit=2")
        options.add_argument("--js-flags=--max-old-space-size=256")

    options.add_argument("--disable-extensions")
    if settings.headless:
        options.add_argument(f"--window-size={settings.window_size}")
    else:
        options.add_argument("--start-maximized")

    if not settings.headless:
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)
        if __import__("os").name == "posix":
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-software-rasterizer")

    prefs: dict[str, object] = {"profile.managed_default_content_settings.images": 2}
    if settings.geolocation_enabled:
        prefs["profile.default_content_setting_values.geolocation"] = 1
        prefs["profile.managed_default_content_settings.geolocation"] = 1
    options.add_experimental_option("prefs", prefs)

    if settings.user_data_dir:
        options.add_argument(f"--user-data-dir={settings.user_data_dir}")

    options.add_argument("--password-store=basic")

    if settings.user_agent:
        options.add_argument(f"--user-agent={settings.user_agent}")

    if settings.browser_binary:
        options.binary_location = settings.browser_binary

    with chrome_startup_lock("badoo_bot"):
        if browser_name == "edge":
            service = EdgeService(executable_path=settings.webdriver_path) if settings.webdriver_path else EdgeService()
            driver = webdriver.Edge(service=service, options=options)
        else:
            service = Service(executable_path=settings.webdriver_path) if settings.webdriver_path else Service()
            driver = webdriver.Chrome(service=service, options=options)

    page_timeout = max(30, int(settings.wait_timeout_sec))
    driver.set_page_load_timeout(page_timeout)
    driver.set_script_timeout(page_timeout)
    try:
        driver.implicitly_wait(0)
    except Exception:  # noqa: BLE001
        pass

    if not settings.headless:
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": (
                        "Object.defineProperty(navigator, 'webdriver', "
                        "{get: () => undefined});"
                    )
                },
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            driver.maximize_window()
        except Exception:  # noqa: BLE001
            pass
    if settings.geolocation_enabled:
        configure_geolocation(driver)
    return driver


def configure_geolocation(driver) -> None:
    """Grant geolocation for Badoo and provide coordinates (CDP)."""
    try:
        driver.execute_cdp_cmd(
            "Browser.grantPermissions",
            {"origin": "https://badoo.com", "permissions": ["geolocation"]},
        )
        driver.execute_cdp_cmd(
            "Emulation.setGeolocationOverride",
            {
                "latitude": settings.geolocation_latitude,
                "longitude": settings.geolocation_longitude,
                "accuracy": 100,
            },
        )
    except Exception:  # noqa: BLE001
        pass
