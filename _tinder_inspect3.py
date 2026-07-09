from __future__ import annotations

import functools
import time

from selenium.webdriver.common.by import By

from tinder_bot.browser import build_driver

print = functools.partial(print, flush=True)  # noqa: A001


def main():
    driver = build_driver()
    driver.get("https://tinder.com/app/recs")
    time.sleep(4)

    # Explicitly switch to the "Spravy" (messages) tab — a fresh navigation
    # may default to "Zhody" (matches grid), which uses the same anchor class
    # but without message previews.
    try:
        tab = driver.find_element(By.XPATH, "//*[contains(., 'Správy') or contains(., 'Spravy')][self::button or self::a or @role='tab']")
        driver.execute_script("arguments[0].click();", tab)
        print("[inspect3] Clicked Spravy tab.")
        time.sleep(2)
    except Exception as exc:  # noqa: BLE001
        print(f"[inspect3] Could not find/click Spravy tab: {exc}")

    anchors = driver.find_elements(By.CSS_SELECTOR, "a.matchListItem")
    print(f"[inspect3] {len(anchors)} matchListItem anchors after switching tab")

    # Grab everything we need in ONE pass per anchor (outerHTML, text) to avoid
    # stale-element issues from the virtualized list re-rendering between calls.
    rows = []
    for a in anchors[:15]:
        try:
            html = driver.execute_script("return arguments[0].outerHTML;", a)
            rows.append((a.get_attribute("href"), a.text, html))
        except Exception as exc:  # noqa: BLE001
            rows.append((None, None, f"<error: {exc}>"))

    for href, text, html in rows:
        print("----")
        print("href:", href)
        print("text:", repr(text))
        print("html:", html[:1500])


if __name__ == "__main__":
    main()
