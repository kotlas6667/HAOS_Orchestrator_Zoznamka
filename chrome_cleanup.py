from __future__ import annotations

import subprocess
import time


def kill_stale_chrome_for_profile(user_data_dir: str | None, *, grace_sec: float = 1.0) -> None:
    """Best-effort kill of orphaned Chromium processes tied to a profile.

    On Raspberry Pi, driver.quit() after --single-process Chrome often leaves
    zombie renderer processes that block the profile lock and exhaust RAM.
    """
    if not user_data_dir:
        return
    needle = f"--user-data-dir={user_data_dir}"
    try:
        subprocess.run(
            ["pkill", "-f", needle],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return
    if grace_sec > 0:
        time.sleep(grace_sec)
