"""Resolve HA add-on DNS hostnames for GitHub-store and local installs.

HA DNS hostname = {REPO}_{SLUG} with underscores → dashes.
- local install: local-haos-elitedate
- GitHub store:  {sha1(exact_store_repo_url)[:8]}-haos-elitedate

The repo hash depends on the EXACT URL string used when adding the store
repository — so we never trust a hardcoded hash. Prefer Supervisor discovery
(installed add-on slug → hostname).

This module is copied into each add-on image and also used by run.sh.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request

# Only a last-resort guess when Supervisor is unavailable.
REPO_URL = "https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka"
REPO_HASH = hashlib.sha1(REPO_URL.lower().encode()).hexdigest()[:8]

# Hosts that NEVER work (bare slug / wrong family).
_BROKEN_HOSTS = {
    "haos_orchestrator",
    "haos_elitedate",
    "haos_tinder",
    "haos_badoo",
    "haos-orchestrator",
    "haos-elitedate",
    "haos-tinder",
    "haos-badoo",
    "local-haos-orchestrator",
    "local-haos-elitedate",
    "local-haos-tinder",
    "local-haos-badoo",
}

_HASH_PREFIX_RE = re.compile(r"^([0-9a-f]{8})-haos-", re.IGNORECASE)


def dns_host_for_slug(addon_slug: str, *, repo_hash: str | None = None) -> str:
    """addon_slug like haos_elitedate → {hash}-haos-elitedate."""
    prefix = repo_hash if repo_hash is not None else (live_repo_hash() or REPO_HASH)
    return f"{prefix}-{addon_slug.replace('_', '-')}"


def default_url(addon_slug: str, port: int, *, repo_hash: str | None = None) -> str:
    return f"http://{dns_host_for_slug(addon_slug, repo_hash=repo_hash)}:{port}"


def extract_host(url: str) -> str:
    s = (url or "").strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    return s.split("/", 1)[0].split(":", 1)[0].strip().lower()


def is_broken_url(url: str) -> bool:
    host = extract_host(url)
    if not host:
        return True
    if host in _BROKEN_HOSTS:
        return True
    if host.startswith("haos_") or host.startswith("haos-"):
        # valid form: <8hex>-haos-elitedate
        if len(host) >= 14 and host[8] == "-" and all(c in "0123456789abcdef" for c in host[:8].lower()):
            return False
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
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else None


def list_installed_addons(timeout: float = 5.0) -> list[dict]:
    data = _supervisor_get("/addons", timeout=timeout)
    if not data:
        return []
    addons = data.get("addons")
    return addons if isinstance(addons, list) else []


def live_repo_hash() -> str | None:
    """Read hash prefix from this add-on's own Supervisor slug (e.g. 03146090)."""
    info = _supervisor_get("/addons/self/info")
    if not info:
        return None
    slug = str(info.get("slug") or "")
    # 03146090_haos_elitedate → 03146090
    if "_" in slug:
        prefix = slug.split("_", 1)[0]
        if len(prefix) == 8 and all(c in "0123456789abcdef" for c in prefix.lower()):
            return prefix.lower()
    if slug.startswith("local_"):
        return "local"
    return None


def discover_url(slug_suffix: str, port: int) -> str | None:
    """Find installed add-on whose slug ends with the wanted haos_* suffix."""
    wanted = slug_suffix if slug_suffix.startswith("haos_") else f"haos_{slug_suffix}"
    for addon in list_installed_addons():
        slug = str(addon.get("slug") or "")
        if slug == wanted or slug.endswith("_" + wanted):
            host = slug.replace("_", "-")
            return f"http://{host}:{port}"
    return None


def persist_self_options(options_patch: dict) -> bool:
    """Write corrected options into Supervisor (HA UI), not only /data/options.json."""
    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token or not options_patch:
        return False
    body = json.dumps({"options": options_patch}).encode("utf-8")
    req = urllib.request.Request(
        "http://supervisor/addons/self/options",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            resp.read()
        print(f"[addon_dns] Supervisor options updated: {list(options_patch.keys())}")
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[addon_dns] Supervisor options update failed: {exc}")
        return False


def resolve_url(
    current: str,
    *,
    slug_suffix: str,
    port: int,
    label: str = "",
) -> str:
    """Prefer Supervisor discovery; never keep a wrong hash like 8c003d88 vs 03146090."""
    cur = (current or "").strip()
    prefix = f"[{label}] " if label else ""
    slug = slug_suffix if slug_suffix.startswith("haos_") else f"haos_{slug_suffix}"

    discovered = discover_url(slug_suffix, port)
    if discovered:
        if cur and extract_host(cur) == extract_host(discovered):
            print(f"{prefix}keep URL (matches Supervisor): {cur}")
            return cur
        print(f"{prefix}supervisor discover: {cur or '(empty)'} → {discovered}")
        return discovered

    live = live_repo_hash()
    if cur and not is_broken_url(cur):
        host = extract_host(cur)
        m = _HASH_PREFIX_RE.match(host)
        # Default/options often ship with REPO_HASH (8c003d88) while this HA
        # install uses a different store URL hash (e.g. 03146090) — rewrite.
        if live and m and m.group(1).lower() != live.lower():
            fixed = default_url(slug, port, repo_hash=live)
            print(f"{prefix}repo-hash rewrite {m.group(1)}→{live}: {cur} → {fixed}")
            return fixed
        print(f"{prefix}keep URL (no Supervisor discovery): {cur}")
        return cur

    if cur:
        print(f"{prefix}BROKEN URL detected: {cur}")

    fallback = default_url(slug, port, repo_hash=live)
    print(f"{prefix}fallback DNS: {cur or '(empty)'} → {fallback} (hash={live or REPO_HASH})")
    return fallback
