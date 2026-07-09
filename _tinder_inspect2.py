from __future__ import annotations

import functools
import time

from selenium.webdriver.common.by import By

from tinder_bot.browser import build_driver

print = functools.partial(print, flush=True)  # noqa: A001


def describe(el):
    tag = el.tag_name
    cls = el.get_attribute("class") or ""
    testid = el.get_attribute("data-testid") or ""
    return f"<{tag} class='{cls}' data-testid='{testid}'>"


def main():
    driver = build_driver()
    driver.get("https://tinder.com/app/recs")
    time.sleep(4)

    # Dump every element with a data-testid anywhere on the messages list page.
    testid_els = driver.find_elements(By.CSS_SELECTOR, "[data-testid]")
    print(f"[inspect2] {len(testid_els)} elements with data-testid on /app/recs")
    seen = set()
    for el in testid_els:
        tid = el.get_attribute("data-testid")
        if tid in seen:
            continue
        seen.add(tid)
        txt = (el.text or "").strip().replace("\n", " | ")
        print(f"  data-testid='{tid}' tag={el.tag_name} text={txt[:60]!r}")

    # Find the anchor for "Barbora" specifically (known unread from the
    # screenshot) and dump its full ancestor chain / siblings for an unread marker.
    anchors = driver.find_elements(By.CSS_SELECTOR, "a.matchListItem")
    print(f"\n[inspect2] {len(anchors)} matchListItem anchors")
    target = None
    for a in anchors:
        if "Barbora" in (a.text or ""):
            target = a
            break
    if target is not None:
        print("[inspect2] Found Barbora anchor. Full outerHTML:")
        print(driver.execute_script("return arguments[0].outerHTML;", target)[:3000])
    else:
        print("[inspect2] Could not find Barbora in current list (may have scrolled off).")
        if anchors:
            print("[inspect2] Dumping first anchor outerHTML instead:")
            print(driver.execute_script("return arguments[0].outerHTML;", anchors[0])[:3000])

    print("\n[inspect2] Opening a conversation to inspect message bubbles...")
    if anchors:
        driver.execute_script("arguments[0].click();", anchors[0])
        time.sleep(2)
        print("[inspect2] url:", driver.current_url)

        chat_testids = driver.find_elements(By.CSS_SELECTOR, "[data-testid]")
        seen2 = set()
        for el in chat_testids:
            tid = el.get_attribute("data-testid")
            if tid in seen2:
                continue
            seen2.add(tid)
            txt = (el.text or "").strip().replace("\n", " | ")
            print(f"  data-testid='{tid}' tag={el.tag_name} text={txt[:60]!r}")

        # Dump the main chat column's outerHTML around any element containing
        # a decent chunk of text (likely a message bubble).
        candidates = driver.find_elements(By.XPATH, "//div[string-length(normalize-space(text())) > 3]")
        print(f"\n[inspect2] {len(candidates)} leaf divs with direct text; showing up to 15")
        for c in candidates[:15]:
            print("  ", describe(c), "text=", repr((c.text or "")[:60]))

    print("[inspect2] Done. Sleeping 45s.")
    time.sleep(45)


if __name__ == "__main__":
    main()
