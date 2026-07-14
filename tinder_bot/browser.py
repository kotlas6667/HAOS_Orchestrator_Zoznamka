from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

from tinder_bot.chrome_lock import chrome_startup_lock
from tinder_bot.config import settings



def build_driver() -> webdriver.Chrome | webdriver.Edge:
    """Build a browser driver for Tinder.

    Supports Chrome/Chromium and Edge. Chrome flags are tuned for containers
    (limited /dev/shm) on the HAOS host (i3 / 16 GB). Tinder's login
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

        # Container essentials: /dev/shm is often tiny and Chrome will
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
    if settings.headless:
        options.add_argument(f"--window-size={settings.window_size}")
    else:
        # Tinder's desktop layout (Zhody/Správy tabs, message list) needs a wide window.
        options.add_argument("--start-maximized")

    # Headed mode (manual login / dev): still avoid tiny /dev/shm issues on some setups.
    # Also hide the most obvious Selenium fingerprints so Google/Tinder "Prihlásenie
    # sa nepodarilo / not secure" is less likely. Phone OTP still works best.
    if not settings.headless:
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

    # Skip loading images: cuts per-page memory a lot and this bot only reads
    # text (messages, sender names), never needs rendered images.
    prefs: dict[str, object] = {"profile.managed_default_content_settings.images": 2}
    if settings.geolocation_enabled:
        prefs["profile.default_content_setting_values.geolocation"] = 1
        prefs["profile.managed_default_content_settings.geolocation"] = 1
    options.add_experimental_option("prefs", prefs)

    if settings.user_data_dir:
        # Persistent profile so a manually-solved login/OTP/captcha survives
        # across restarts instead of re-triggering every time.
        options.add_argument(f"--user-data-dir={settings.user_data_dir}")

    # Portable profiles (WSL → HAOS): avoid OS keyring so cookies decrypt on both.
    password_store = __import__("os").environ.get("TINDER_CHROME_PASSWORD_STORE", "").strip()
    if password_store:
        options.add_argument(f"--password-store={password_store}")
    elif not settings.headless:
        # Headed capture sessions should also be portable to the Linux add-on.
        options.add_argument("--password-store=basic")

    if settings.user_agent:
        options.add_argument(f"--user-agent={settings.user_agent}")

    if settings.browser_binary:
        options.binary_location = settings.browser_binary

    with chrome_startup_lock("tinder_bot"):
        if browser_name == "edge":
            service = EdgeService(executable_path=settings.webdriver_path) if settings.webdriver_path else EdgeService()
            driver = webdriver.Edge(service=service, options=options)
        else:
            service = Service(executable_path=settings.webdriver_path) if settings.webdriver_path else Service()
            driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(int(settings.wait_timeout_sec))
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
    """Grant geolocation for Tinder and provide coordinates (CDP)."""
    try:
        driver.execute_cdp_cmd(
            "Browser.grantPermissions",
            {"origin": "https://tinder.com", "permissions": ["geolocation"]},
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
