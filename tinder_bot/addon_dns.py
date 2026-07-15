"""Resolve peer HA add-on URLs via Supervisor API (no hardcoded repo hashes).

HA DNS hostname = addon slug with underscores replaced by dashes, e.g.
``abcd1234_haos_elitedate`` → ``abcd1234-haos-elitedate``.

User-facing defaults must stay empty/auto — digests differ per install store
and must never be pasted manually into Nastavenia.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# Hostnames that are never valid between GitHub-store add-ons (or are bare slugs).
_BROKEN_HOSTS = {
    "haos_orchestrator",
    "haos_elitedate",
    "haos_tinder",
    "haos-orchestrator",
    "haos-elitedate",
    "haos-tinder",
    "local-haos-orchestrator",
    "local-haos-elitedate",
    "local-haos-tinder",
}


def extract_host(url: str) -> str:
    s = (url or "").strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    return s.split("/", 1)[0].split(":", 1)[0].strip().lower()


def is_broken_url(url: str) -> bool:
    """True if empty / placeholder / known-wrong host that should be rediscovered."""
    host = extract_host(url)
    if not host:
        return True
    if host in _BROKEN_HOSTS:
        return True
    if host in {"auto", "auto.discover", "localhost", "127.0.0.1"}:
        return True
    return False


def _supervisor_get(path: str, timeout: float = 5.0) -> dict | None:
    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        return None
    req = urllib.request.Request(
        f"http://supervisor{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"[addon_dns] supervisor GET {path} failed: {exc}")
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def list_installed_addons() -> list[dict]:
    data = _supervisor_get("/addons")
    if not data:
        return []
    addons = data.get("addons")
    if not isinstance(addons, list):
        return []
    out: list[dict] = []
    for addon in addons:
        if not isinstance(addon, dict):
            continue
        # Store list may include non-installed; prefer installed when field present.
        if "installed" in addon and not addon.get("installed"):
            continue
        out.append(addon)
    return out


def addon_info(slug: str) -> dict | None:
    return _supervisor_get(f"/addons/{slug}/info")


def discover_url(slug_suffix: str, port: int) -> str | None:
    """Find installed add-on by slug suffix and return http://{hostname}:{port}."""
    wanted = slug_suffix if slug_suffix.startswith("haos_") else f"haos_{slug_suffix}"
    for addon in list_installed_addons():
        slug = str(addon.get("slug") or "")
        if slug != wanted and not slug.endswith("_" + wanted):
            continue

        # Prefer official hostname from /addons/{slug}/info when available.
        info = addon_info(slug) or {}
        host = str(info.get("hostname") or "").strip()
        if not host:
            host = slug.replace("_", "-")
        return f"http://{host}:{port}"
    return None


def resolve_url(
    current: str,
    *,
    slug_suffix: str,
    port: int,
    label: str = "",
) -> str:
    """Return peer URL: keep non-broken current, else Supervisor discover.

    Never invents a repo-hash hostname — discovery must succeed via Supervisor.
    """
    cur = (current or "").strip()
    prefix = f"[{label}] " if label else ""

    discovered = discover_url(slug_suffix, port)

    if cur and not is_broken_url(cur):
        # If Supervisor sees a different live hostname, prefer discovery (store reinstall).
        if discovered and extract_host(discovered) != extract_host(cur):
            print(f"{prefix}supervisor updated host: {cur} → {discovered}")
            return discovered
        print(f"{prefix}keep URL: {cur}")
        return cur

    if discovered:
        print(f"{prefix}supervisor discover: {cur or '(empty)'} → {discovered}")
        return discovered

    print(
        f"{prefix}WARNING: could not discover {slug_suffix} via Supervisor "
        f"(current={cur or '(empty)'}). Is the peer add-on installed and hassio_api enabled?"
    )
    return cur
