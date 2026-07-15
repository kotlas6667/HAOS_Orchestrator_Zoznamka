"""Resolve HA add-on DNS hostnames for GitHub-store and local installs.

HA DNS hostname = {REPO}_{SLUG} with underscores → dashes.
- local install: local-haos-elitedate
- GitHub store:  {sha1(repo_url)[:8]}-haos-elitedate

This module is copied into each add-on image and also used by run.sh.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request

REPO_URL = "https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka"
REPO_HASH = hashlib.sha1(REPO_URL.lower().encode()).hexdigest()[:8]

# Bare slug (wrong) and mistaken "local-" for GitHub installs.
_BROKEN_HOSTS = {
    "haos_orchestrator",
    "haos_elitedate",
    "haos_tinder",
    "local-haos-orchestrator",
    "local-haos-elitedate",
    "local-haos-tinder",
}


def dns_host_for_slug(addon_slug: str, *, repo_hash: str | None = None) -> str:
    """addon_slug like haos_elitedate → 8c003d88-haos-elitedate (or local-…)."""
    prefix = repo_hash if repo_hash is not None else REPO_HASH
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
    # bare slug-style without repo prefix
    if host.startswith("haos-") and not host[0:8].isalnum():
        return True
    if host in {"haos-orchestrator", "haos-elitedate", "haos-tinder"}:
        return True
    return False


def list_installed_addons(timeout: float = 5.0) -> list[dict]:
    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        return []
    req = urllib.request.Request(
        "http://supervisor/addons",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    addons = data.get("addons") if isinstance(data, dict) else None
    return addons if isinstance(addons, list) else []


def discover_url(slug_suffix: str, port: int) -> str | None:
    """Find installed add-on whose slug ends with _{slug_suffix} and build http URL."""
    wanted = slug_suffix if slug_suffix.startswith("haos_") else f"haos_{slug_suffix}"
    for addon in list_installed_addons():
        slug = str(addon.get("slug") or "")
        if slug == wanted or slug.endswith("_" + wanted):
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
    """Return a usable URL: keep good current, else supervisor discover, else hash default."""
    cur = (current or "").strip()
    prefix = f"[{label}] " if label else ""

    if cur and not is_broken_url(cur):
        print(f"{prefix}keep URL: {cur}")
        return cur

    discovered = discover_url(slug_suffix, port)
    if discovered:
        print(f"{prefix}supervisor discover: {cur or '(empty)'} → {discovered}")
        return discovered

    fallback = default_url(slug_suffix if slug_suffix.startswith("haos_") else f"haos_{slug_suffix}", port)
    print(f"{prefix}fallback hash DNS: {cur or '(empty)'} → {fallback}")
    return fallback
