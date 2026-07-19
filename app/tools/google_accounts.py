"""Multi-account Google (Gmail + Calendar) registry and OAuth helpers.

Persists connected accounts in google_accounts.json. Each account stores one
OAuth token with combined Gmail + Calendar scopes so a single login unlocks
both mail reading and calendar.
"""
from __future__ import annotations

import json
import os
import pickle
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import Flow

from app.config import settings

# Combined scopes — one consent = Gmail read/send + Calendar
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_FILENAME = "google_accounts.json"
_TOKENS_DIRNAME = "google_tokens"
_PENDING_OAUTH: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()


def _config_dir() -> Path:
    """Prefer HA persistent config; fall back to project root."""
    for candidate in (
        Path("/data/orchestrator/config"),
        _PROJECT_ROOT / "data" / "orchestrator" / "config",
        _PROJECT_ROOT,
    ):
        if candidate.exists() or str(candidate).startswith("/data/"):
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate
            except OSError:
                continue
    return _PROJECT_ROOT


def state_path() -> Path:
    return _config_dir() / _STATE_FILENAME


def tokens_dir() -> Path:
    path = _config_dir() / _TOKENS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def credentials_candidates() -> list[Path]:
    """Ordered list of possible OAuth client-secrets JSON paths."""
    candidates: list[Path] = []
    configured = (settings.gmail_credentials_json or "").strip()
    if configured:
        candidates.append(Path(configured))
    cfg = _config_dir()
    for name in ("gmailSecret.json", "credentials.json", "client_secret.json"):
        candidates.append(cfg / name)
        candidates.append(_PROJECT_ROOT / name)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[Path] = []
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def find_credentials_path() -> Path | None:
    for path in credentials_candidates():
        if path.is_file():
            return path
    return None


def _default_state() -> dict[str, Any]:
    return {
        "enabled": False,
        "default_account_id": None,
        "accounts": [],
    }


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_state()
    if not isinstance(data, dict):
        return _default_state()
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        accounts = []
    return {
        "enabled": bool(data.get("enabled", False)),
        "default_account_id": data.get("default_account_id"),
        "accounts": [a for a in accounts if isinstance(a, dict) and a.get("id")],
    }


def save_state(state: dict[str, Any]) -> Path:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    # Also symlink/copy into /app for local tooling when on HA
    app_copy = _PROJECT_ROOT / _STATE_FILENAME
    try:
        if app_copy.resolve() != path.resolve():
            if not app_copy.exists() and not app_copy.is_symlink():
                app_copy.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            elif app_copy.is_symlink() or app_copy.exists():
                pass
    except OSError:
        pass
    return path


def is_enabled() -> bool:
    """VNC login switch on (HA / dashboard) — spúšťa noVNC, nie nutne Gmail runtime."""
    state = load_state()
    if state.get("enabled"):
        return True
    return bool(settings.google_accounts_enabled)


def has_connected_accounts() -> bool:
    return bool(load_state().get("accounts"))


def set_enabled(enabled: bool) -> dict[str, Any]:
    """Zapni/vypni VNC režim. Tokeny ostávajú; oauth provider ostane ak sú účty."""
    with _LOCK:
        state = load_state()
        state["enabled"] = bool(enabled)
        save_state(state)
        # VNC off ≠ mock: ak už máme účty, Gmail/Calendar ostanú oauth
        use_oauth = bool(enabled) or bool(state.get("accounts"))
        _sync_env_providers(use_oauth, vnc_enabled=bool(enabled))
        return state


def _sync_env_providers(use_oauth: bool, *, vnc_enabled: bool | None = None) -> None:
    """Best-effort: keep runtime settings + .env in sync."""
    value = "oauth" if use_oauth else "mock"
    try:
        settings.gmail_provider = value
        settings.calendar_provider = value
        if vnc_enabled is not None:
            settings.google_accounts_enabled = bool(vnc_enabled)
    except Exception:
        pass
    env_path = _config_dir() / ".env"
    app_env = _PROJECT_ROOT / ".env"
    for path in (env_path, app_env):
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            updates = {
                "GMAIL_PROVIDER": value,
                "CALENDAR_PROVIDER": value,
            }
            if vnc_enabled is not None:
                updates["GOOGLE_ACCOUNTS_ENABLED"] = "true" if vnc_enabled else "false"
            out: list[str] = []
            seen: set[str] = set()
            for line in lines:
                if "=" not in line or line.lstrip().startswith("#"):
                    out.append(line)
                    continue
                key = line.split("=", 1)[0].strip()
                if key in updates:
                    out.append(f"{key}={updates[key]}")
                    seen.add(key)
                else:
                    out.append(line)
            for key, val in updates.items():
                if key not in seen:
                    out.append(f"{key}={val}")
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
        except OSError:
            continue


def list_accounts() -> list[dict[str, Any]]:
    state = load_state()
    default_id = state.get("default_account_id")
    result = []
    for acc in state.get("accounts", []):
        item = dict(acc)
        item["is_default"] = item.get("id") == default_id
        item["token_ok"] = Path(item.get("token_path", "")).is_file()
        result.append(item)
    return result


def get_account(account_id: str | None = None, email: str | None = None) -> dict[str, Any] | None:
    """Return matching account, or default when neither id nor email was given.

    If account_id / email is provided but not found → None (no silent default).
    """
    state = load_state()
    accounts = state.get("accounts", [])
    if account_id:
        for acc in accounts:
            if acc.get("id") == account_id:
                return acc
        return None
    if email:
        needle = email.strip().lower()
        for acc in accounts:
            if (acc.get("email") or "").strip().lower() == needle:
                return acc
        return None
    default_id = state.get("default_account_id")
    if default_id:
        for acc in accounts:
            if acc.get("id") == default_id:
                return acc
    if accounts:
        return accounts[0]
    return None


def find_account_fuzzy(needle: str) -> dict[str, Any] | None:
    """Match by exact email, exact label, then substring on email/label."""
    text = (needle or "").strip().lower()
    if not text:
        return None
    accounts = load_state().get("accounts", [])
    for acc in accounts:
        if text == (acc.get("email") or "").lower() or text == (acc.get("label") or "").lower():
            return acc
    for acc in accounts:
        if text in (acc.get("email") or "").lower() or text in (acc.get("label") or "").lower():
            return acc
    return None


def set_default_account(account_id: str) -> dict[str, Any]:
    with _LOCK:
        state = load_state()
        ids = {a.get("id") for a in state.get("accounts", [])}
        if account_id not in ids:
            raise ValueError(f"Účet {account_id} neexistuje")
        state["default_account_id"] = account_id
        save_state(state)
        return state


def remove_account(account_id: str) -> dict[str, Any]:
    with _LOCK:
        state = load_state()
        accounts = state.get("accounts", [])
        removed = None
        kept = []
        for acc in accounts:
            if acc.get("id") == account_id:
                removed = acc
            else:
                kept.append(acc)
        if removed is None:
            raise ValueError(f"Účet {account_id} neexistuje")
        token_path = Path(removed.get("token_path") or "")
        if token_path.is_file():
            try:
                token_path.unlink()
            except OSError:
                pass
        state["accounts"] = kept
        if state.get("default_account_id") == account_id:
            state["default_account_id"] = kept[0]["id"] if kept else None
        save_state(state)
        return state


def _client_config(credentials_path: Path) -> dict[str, Any]:
    data = json.loads(credentials_path.read_text(encoding="utf-8"))
    if "web" in data or "installed" in data:
        return data
    # Bare client fields → wrap as installed
    return {"installed": data}


def _client_type(config: dict[str, Any]) -> str:
    if "web" in config:
        return "web"
    return "installed"


def start_oauth(redirect_uri: str, label: str = "") -> dict[str, Any]:
    """Begin OAuth; returns auth_url + state for the browser redirect."""
    cred_path = find_credentials_path()
    if cred_path is None:
        raise FileNotFoundError(
            "Chýba OAuth client JSON (gmailSecret.json / credentials.json). "
            "Stiahni ho z Google Cloud Console → APIs & Services → Credentials "
            "a ulož do /data/orchestrator/config/."
        )

    config = _client_config(cred_path)
    ctype = _client_type(config)
    # Flow needs the matching section key
    flow = Flow.from_client_config(config, scopes=GOOGLE_SCOPES, redirect_uri=redirect_uri)
    state = secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    with _LOCK:
        _PENDING_OAUTH[state] = {
            "redirect_uri": redirect_uri,
            "credentials_path": str(cred_path),
            "client_type": ctype,
            "label": (label or "").strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    return {
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": redirect_uri,
        "credentials_path": str(cred_path),
        "client_type": ctype,
    }


def _fetch_profile_email(creds: OAuth2Credentials) -> str:
    """Resolve the Google account email via userinfo or Gmail profile."""
    try:
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build

        http = httplib2.Http(disable_ssl_certificate_validation=True)
        authorized = AuthorizedHttp(creds, http)
        # Prefer oauth2 userinfo
        try:
            oauth2 = build("oauth2", "v2", http=authorized, cache_discovery=False)
            info = oauth2.userinfo().get().execute()
            email = (info.get("email") or "").strip()
            if email:
                return email
        except Exception:
            pass
        gmail = build("gmail", "v1", http=authorized, cache_discovery=False, static_discovery=False)
        profile = gmail.users().getProfile(userId="me").execute()
        return (profile.get("emailAddress") or "").strip()
    except Exception as exc:
        print(f"[google_accounts] profile email lookup failed: {exc}")
        return ""


def save_account_from_credentials(creds: OAuth2Credentials, *, label: str = "") -> dict[str, Any]:
    """Persist OAuth2 credentials as a multi-account entry (Gmail + Calendar scopes)."""
    if not isinstance(creds, OAuth2Credentials):
        raise TypeError("Očakávam OAuth2Credentials")
    email = _fetch_profile_email(creds) or f"account-{uuid.uuid4().hex[:8]}@unknown"
    account_id = uuid.uuid4().hex[:12]
    token_path = tokens_dir() / f"{account_id}.pickle"
    with open(token_path, "wb") as fh:
        pickle.dump(creds, fh)

    entry_label = (label or "").strip() or email.split("@")[0]
    with _LOCK:
        state_data = load_state()
        accounts = [
            a for a in state_data.get("accounts", [])
            if (a.get("email") or "").lower() != email.lower()
        ]
        entry = {
            "id": account_id,
            "email": email,
            "label": entry_label,
            "token_path": str(token_path),
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "scopes": list(GOOGLE_SCOPES),
        }
        accounts.append(entry)
        state_data["accounts"] = accounts
        state_data["enabled"] = True
        if not state_data.get("default_account_id"):
            state_data["default_account_id"] = account_id
        save_state(state_data)
        _sync_env_providers(True)
    return entry


def complete_oauth(state: str, code: str) -> dict[str, Any]:
    """Exchange authorization code; persist token + account entry."""
    with _LOCK:
        pending = _PENDING_OAUTH.pop(state, None)
    if not pending:
        raise ValueError("Neplatný alebo expirovaný OAuth state — spusti prihlásenie znova.")

    cred_path = Path(pending["credentials_path"])
    redirect_uri = pending["redirect_uri"]
    config = _client_config(cred_path)
    flow = Flow.from_client_config(config, scopes=GOOGLE_SCOPES, redirect_uri=redirect_uri)
    # google-auth may warn on scope changes; allow
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    flow.fetch_token(code=code)
    creds = flow.credentials
    if not isinstance(creds, OAuth2Credentials):
        raise RuntimeError("OAuth nevrátil OAuth2 credentials")

    return save_account_from_credentials(creds, label=pending.get("label") or "")


def load_credentials(token_path: str | Path) -> OAuth2Credentials:
    """Load + refresh token from pickle; never starts interactive OAuth."""
    path = Path(token_path)
    if not path.is_file():
        raise FileNotFoundError(f"Token súbor neexistuje: {path}")
    with open(path, "rb") as fh:
        creds = pickle.load(fh)
    if not isinstance(creds, OAuth2Credentials):
        raise TypeError("Neplatný token pickle")
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(path, "wb") as fh:
            pickle.dump(creds, fh)
        return creds
    raise RuntimeError(
        f"Token pre {path.name} je neplatný — znova pripoj účet v nastaveniach Google."
    )


def migrate_legacy_single_account() -> dict[str, Any] | None:
    """If old token.pickle exists and registry is empty, import it as one account."""
    state = load_state()
    if state.get("accounts"):
        return None

    legacy_token = settings.gmail_token_pickle or "token.pickle"
    candidates = [
        Path(legacy_token),
        _config_dir() / "token.pickle",
        _PROJECT_ROOT / "token.pickle",
    ]
    token_file = next((p for p in candidates if p.is_file()), None)
    if token_file is None:
        return None

    try:
        creds = load_credentials(token_file)
    except Exception as exc:
        print(f"[google_accounts] legacy token unusable: {exc}")
        return None

    email = _fetch_profile_email(creds) or "legacy@gmail.com"
    account_id = uuid.uuid4().hex[:12]
    dest = tokens_dir() / f"{account_id}.pickle"
    with open(dest, "wb") as fh:
        pickle.dump(creds, fh)

    # Also try calendar token — if present, prefer combined scopes already on gmail token
    entry = {
        "id": account_id,
        "email": email,
        "label": email.split("@")[0],
        "token_path": str(dest),
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "scopes": list(GOOGLE_SCOPES),
        "migrated_from": str(token_file),
    }
    state["accounts"] = [entry]
    state["default_account_id"] = account_id
    if (settings.gmail_provider or "").lower() == "oauth":
        state["enabled"] = True
    save_state(state)
    print(f"[google_accounts] Migrated legacy token → {email}")
    return entry


def _novnc_listening() -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 6082), timeout=0.3):
            return True
    except OSError:
        return False


def status_payload() -> dict[str, Any]:
    migrate_legacy_single_account()
    state = load_state()
    cred = find_credentials_path()
    accounts = list_accounts()
    enabled = bool(state.get("enabled")) or bool(settings.google_accounts_enabled)
    novnc = _novnc_listening()
    hint = None
    if not cred:
        hint = (
            "Nahraj OAuth client JSON typu **Desktop** ako gmailSecret.json "
            "do /data/orchestrator/config/ (Google Cloud → OAuth client ID)."
        )
    elif enabled and not novnc:
        hint = (
            "Switch je zapnutý, ale noVNC ešte nebeží — Uložiť Nastavenia a "
            "Reštartuj add-on. Potom otvor http://<IP_HA>:6082/vnc.html"
        )
    elif enabled and novnc:
        hint = (
            "noVNC beží. Otvor http://<IP_HA>:6082/vnc.html a klikni "
            "„Prihlásiť cez VNC“ — v Chromiu sa stiahnu práva na Gmail aj Kalendár."
        )
    return {
        "status": "success",
        "enabled": enabled,
        "novnc_listening": novnc,
        "vnc_url_hint": "http://<IP_HA>:6082/vnc.html",
        "credentials_present": cred is not None,
        "credentials_path": str(cred) if cred else None,
        "default_account_id": state.get("default_account_id"),
        "accounts": accounts,
        "account_count": len(accounts),
        "providers": {
            "gmail": settings.gmail_provider,
            "calendar": settings.calendar_provider,
        },
        "hint": hint,
    }


def build_callback_uri(request_base: str) -> str:
    """Normalize public base URL + callback path for OAuth redirect_uri."""
    base = request_base.rstrip("/")
    return f"{base}/api/google/oauth/callback"


def oauth_error_html(message: str) -> str:
    return (
        "<!doctype html><html lang='sk'><head><meta charset='utf-8'>"
        "<title>Google OAuth</title></head><body style='font-family:sans-serif;padding:2rem'>"
        f"<h1>Prihlásenie zlyhalo</h1><p>{message}</p>"
        "<p><a href='/'>Späť na dashboard</a></p></body></html>"
    )


def oauth_success_html(email: str) -> str:
    return (
        "<!doctype html><html lang='sk'><head><meta charset='utf-8'>"
        "<title>Google pripojený</title>"
        "<meta http-equiv='refresh' content='2;url=/'>"
        "</head><body style='font-family:sans-serif;padding:2rem'>"
        f"<h1>Účet pripojený</h1><p><strong>{email}</strong> — Gmail + Kalendár sú pripravené.</p>"
        "<p>Presmerovávam na dashboard…</p>"
        "<p><a href='/'>Späť na dashboard</a></p></body></html>"
    )
