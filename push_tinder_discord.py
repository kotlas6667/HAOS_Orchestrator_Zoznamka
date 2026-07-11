"""Push a Tinder thread to Discord (requires running tinder_bot + orchestrator).

Usage:
  python push_tinder_discord.py              # posledná PRIJATÁ správa (od kohokoľvek)
  python push_tinder_discord.py Barbora      # prvá Barbora v zozname
  python push_tinder_discord.py Barbora 2    # druhá Barbora (staršia duplicita)
"""
from __future__ import annotations

import json
import sys

import httpx

SENDER = (sys.argv[1] if len(sys.argv) > 1 else "latest").strip()
OCCURRENCE = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1
BOT = "http://127.0.0.1:8601"
ORCH = "http://127.0.0.1:8000"
TIMEOUT_SEC = 10
# Push volá Selenium (Správy ~10 s + navigácia) — 10 s HTTP by vždy spadlo.
PUSH_TIMEOUT_SEC = 25


def main() -> None:
    health = httpx.get(f"{BOT}/health", timeout=TIMEOUT_SEC).json()
    if not health.get("logged_in"):
        raise SystemExit(f"Tinder bot not logged in: {health}")

    if SENDER.lower() in {"latest", "last", "posledna", "posledná"}:
        label = "poslednej prijatej správy (od kohokoľvek)"
    elif OCCURRENCE > 1:
        label = f"{SENDER} (výskyt #{OCCURRENCE})"
    else:
        label = f"{SENDER} (prvá v zozname)"
    print(f"Fetching thread for {label!r} and posting to Discord (submit=false)...")
    response = httpx.post(
        f"{BOT}/debug/push-discord",
        json={"sender": SENDER, "submit": False, "occurrence": OCCURRENCE},
        timeout=PUSH_TIMEOUT_SEC,
    )
    data = response.json()
    print(json.dumps(data, ensure_ascii=False, indent=2))

    if data.get("status") != "ok":
        raise SystemExit(1)

    fetch = data.get("fetch") or {}
    print("\n--- Discord prompt sent ---")
    print(f"Ona: {fetch.get('message', '')}")
    print(f"Ty:  {fetch.get('my_last_message', '')}")
    print("Odpovedz na Discord správu: 1 / 2 / 3 tvoj text")
    print("(Text sa vloží do Tinderu bez odoslania — TINDER_AUTO_SEND=false)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
