"""Google OAuth cez noVNC — Chromium na DISPLAY=:99 (ako Tinder login).

Keď je zapnutý switch google_accounts_enabled, run.sh spustí Xvfb + noVNC.
Tento modul otvorí Chromium v tom displeji, používateľ sa prihlási cez
http://<IP_HA>:6082/vnc.html a stiahnu sa tokeny (Gmail + Calendar).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from google_auth_oauthlib.flow import InstalledAppFlow

from app.tools import google_accounts

_VNC_STATUS: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "email": None,
    "message": None,
}
_VNC_LOCK = threading.Lock()
_OAUTH_LOCAL_PORT = 8099


def vnc_login_status() -> dict[str, Any]:
    return {
        "status": "success",
        **_VNC_STATUS,
        "novnc_listening": _port_open(6082),
        "display": os.environ.get("DISPLAY", ""),
        "vnc_url_hint": "http://<IP_HA>:6082/vnc.html",
    }


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _chromium_bin() -> str:
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    for path in ("/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if Path(path).is_file():
            return path
    raise FileNotFoundError(
        "Chromium nie je v image — rebuild add-onu (Dockerfile musí obsahovať chromium + noVNC)."
    )


def _chrome_profile_dir() -> Path:
    base = google_accounts._config_dir() / "chrome-google"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _chromium_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "chromium.*chrome-google"],
            capture_output=True,
            timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


def show_vnc_welcome(*, force: bool = False) -> None:
    """Zobrazí návod v Chromiu na VNC displeji (nie čierna obrazovka)."""
    if not force and _chromium_running():
        return
    welcome = Path(__file__).resolve().parent.parent / "static" / "google_vnc_welcome.html"
    url = welcome.as_uri() if welcome.is_file() else "about:blank"
    try:
        _open_chromium(url)
    except Exception as exc:
        print(f"[google-vnc] welcome screen failed: {exc}")
        # Fallback: aspoň farba pozadia cez xsetroot
        display = os.environ.get("DISPLAY") or ":99"
        subprocess.run(
            ["xsetroot", "-solid", "#1a2332"],
            env={**os.environ, "DISPLAY": display},
            capture_output=True,
            timeout=3,
        )


def _open_chromium(url: str) -> None:
    display = os.environ.get("DISPLAY") or ":99"
    os.environ["DISPLAY"] = display
    binary = _chromium_bin()
    profile = _chrome_profile_dir()
    log_path = google_accounts._config_dir() / "chrome-google.log"
    cmd = [
        binary,
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-setuid-sandbox",
        "--window-size=1280,800",
        "--start-maximized",
        "--password-store=basic",
        f"--user-data-dir={profile}",
        "--new-window",
        url,
    ]
    print(f"[google-vnc] Opening Chromium on DISPLAY={display}: {url[:80]}…")
    log_fh = open(log_path, "a", encoding="utf-8")
    subprocess.Popen(
        cmd,
        env={**os.environ, "DISPLAY": display},
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


class _ChromiumVncBrowser(webbrowser.BaseBrowser):
    name = "chromium-vnc"

    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:  # noqa: ARG002
        try:
            _open_chromium(url)
            return True
        except Exception as exc:
            print(f"[google-vnc] browser open failed: {exc}")
            return False


def _register_vnc_browser() -> None:
    webbrowser.register("chromium-vnc", None, _ChromiumVncBrowser("chromium-vnc"), preferred=True)
    os.environ["BROWSER"] = "chromium-vnc"


def _persist_creds(creds: Any, label: str = "") -> dict[str, Any]:
    return google_accounts.save_account_from_credentials(creds, label=label)


def run_vnc_oauth_login(*, label: str = "", timeout_sec: int = 600) -> dict[str, Any]:
    """Blocking: open Chromium on VNC display, wait for Google consent, save tokens."""
    with _VNC_LOCK:
        if _VNC_STATUS.get("running"):
            raise RuntimeError("Google VNC prihlásenie už beží — dokonči ho v noVNC alebo počkaj.")
        _VNC_STATUS.update(
            {
                "running": True,
                "started_at": time.time(),
                "finished_at": None,
                "error": None,
                "email": None,
                "message": "Čakám na prihlásenie v noVNC (Chromium)…",
            }
        )

    try:
        if not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = ":99"
        if not _port_open(6082):
            raise RuntimeError(
                "noVNC nebeží na porte 6082. Zapni switch „Google účty“, Uložiť → Reštart add-onu, "
                "potom otvor http://<IP_HA>:6082/vnc.html"
            )

        cred_path = google_accounts.find_credentials_path()
        if cred_path is None:
            raise FileNotFoundError(
                "Chýba OAuth client JSON (Desktop typ). Ulož gmailSecret.json do "
                "/data/orchestrator/config/ (Google Cloud → OAuth client ID → Desktop app)."
            )

        _register_vnc_browser()
        os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

        # Desktop/installed client — localhost callback v kontajneri
        config = google_accounts._client_config(cred_path)
        if "installed" not in config and "web" in config:
            # Web client: použi web sekciu cez InstalledAppFlow hack — radšej Flow localhost
            from google_auth_oauthlib.flow import Flow

            redirect = f"http://127.0.0.1:{_OAUTH_LOCAL_PORT}/"
            flow = Flow.from_client_config(
                config, scopes=google_accounts.GOOGLE_SCOPES, redirect_uri=redirect
            )
            auth_url, _state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            print("[google-vnc] ==============================================")
            print("[google-vnc] Otvor noVNC a prihlás Google účet:")
            print("[google-vnc]   http://<IP_HA>:6082/vnc.html")
            print("[google-vnc] Chromium sa otvorí automaticky na VNC displeji.")
            print("[google-vnc] ==============================================")
            _open_chromium(auth_url)
            # run_local_server nie je na Flow — použijeme InstalledAppFlow-style helper
            # google_auth_oauthlib.flow.Flow has no run_local_server; use InstalledAppFlow
            # by wrapping web as installed for localhost-only redirect
            raise RuntimeError(
                "OAuth client je typu Web. Pre VNC login vytvor v Google Cloud "
                "OAuth client ID typu **Desktop app**, stiahni JSON a ulož ako gmailSecret.json."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(cred_path), google_accounts.GOOGLE_SCOPES
        )
        print("[google-vnc] ==============================================")
        print("[google-vnc] PRIHLÁSENIE Google cez noVNC:")
        print("[google-vnc]   http://<IP_HA>:6082/vnc.html")
        print("[google-vnc] V Chromiu dokonči Google účet (Gmail + Kalendár).")
        print(f"[google-vnc] Timeout {timeout_sec}s")
        print("[google-vnc] ==============================================")

        # run_local_server otvorí BROWSER=chromium-vnc na DISPLAY
        kwargs = dict(
            port=_OAUTH_LOCAL_PORT,
            prompt="consent",
            open_browser=True,
            authorization_prompt_message=(
                "[google-vnc] Otvor http://<IP_HA>:6082/vnc.html a dokonči prihlásenie v Chromiu.\n"
            ),
            success_message=(
                "Google účet pripojený (Gmail + Kalendár). Môžeš zatvoriť toto okno."
            ),
        )
        # timeout_seconds je len v novších google-auth-oauthlib
        try:
            creds = flow.run_local_server(**kwargs, timeout_seconds=timeout_sec)
        except TypeError:
            creds = flow.run_local_server(**kwargs)
        entry = _persist_creds(creds, label=label)
        with _VNC_LOCK:
            _VNC_STATUS.update(
                {
                    "running": False,
                    "finished_at": time.time(),
                    "email": entry.get("email"),
                    "message": f"Pripojené: {entry.get('email')}",
                    "error": None,
                }
            )
        print(f"[google-vnc] Account connected: {entry.get('email')}")
        return entry
    except Exception as exc:
        with _VNC_LOCK:
            _VNC_STATUS.update(
                {
                    "running": False,
                    "finished_at": time.time(),
                    "error": str(exc),
                    "message": "Prihlásenie zlyhalo",
                }
            )
        print(f"[google-vnc] FAILED: {exc}")
        raise


def start_vnc_oauth_background(*, label: str = "", timeout_sec: int = 600) -> dict[str, Any]:
    """Non-blocking wrapper for FastAPI — Chromium + wait in a daemon thread."""
    with _VNC_LOCK:
        if _VNC_STATUS.get("running"):
            return {
                "status": "error",
                "error": "Prihlásenie už beží — otvor noVNC a dokonči Google login.",
                **vnc_login_status(),
            }

    def _worker() -> None:
        try:
            run_vnc_oauth_login(label=label, timeout_sec=timeout_sec)
        except Exception:
            pass  # status already stored

    threading.Thread(target=_worker, name="google-vnc-oauth", daemon=True).start()
    # Give thread a moment to flip running=True
    time.sleep(0.15)
    return {
        "status": "started",
        "message": (
            "Chromium sa otvára na VNC displeji. "
            "Otvor http://<IP_HA>:6082/vnc.html a prihlás Google účet "
            "(stiahnu sa práva na Gmail aj Kalendár)."
        ),
        **vnc_login_status(),
    }
