from __future__ import annotations

import functools
import time

from selenium.webdriver.common.by import By

from tinder_bot.browser import build_driver

print = functools.partial(print, flush=True)  # noqa: A001


def describe(el):
    tag = el.tag_name
    cls = el.get_attribute("class") or ""
    return f"<{tag} class='{cls}'>"


def main():
    driver = build_driver()
    driver.get("https://tinder.com/app/recs")
    time.sleep(4)
    print("[inspect] url:", driver.current_url, "title:", driver.title)

    # Find message-row anchors (we know href pattern from a real example).
    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/app/messages/']")
    print(f"[inspect] found {len(anchors)} message-row anchors")
    for a in anchors[:6]:
        print("----")
        print("href:", a.get_attribute("href"))
        print("anchor:", describe(a))
        print("text:", repr(a.text)[:200])
        # Walk a couple of descendant levels to find name/preview sub-elements.
        children = a.find_elements(By.XPATH, ".//*")
        for c in children[:12]:
            txt = (c.text or "").strip()
            if txt:
                print("  child:", describe(c), "text:", repr(txt)[:80])

    print("\n[inspect] Opening first conversation to inspect chat DOM...")
    if anchors:
        driver.execute_script("arguments[0].click();", anchors[0])
        time.sleep(2)
        print("[inspect] url after click:", driver.current_url)

        msg_candidates = driver.find_elements(By.CSS_SELECTOR, "[class*='msg' i], [class*='message' i], [class*='bubble' i]")
        print(f"[inspect] found {len(msg_candidates)} message-ish elements")
        seen_classes = set()
        for m in msg_candidates[:30]:
            cls = m.get_attribute("class") or ""
            if cls in seen_classes:
                continue
            seen_classes.add(cls)
            txt = (m.text or "").strip().replace("\n", " | ")
            print(f"  {describe(m)} text={txt[:80]!r}")

        inputs = driver.find_elements(By.CSS_SELECTOR, "textarea, input[type='text'], [contenteditable='true']")
        print(f"[inspect] found {len(inputs)} text-input-ish elements")
        for i in inputs[:10]:
            print("  ", describe(i), "name=", i.get_attribute("name"), "placeholder=", i.get_attribute("placeholder"))

    print("[inspect] Done. Sleeping 60s in case you want to look at the window.")
    time.sleep(60)


if __name__ == "__main__":
    main()
