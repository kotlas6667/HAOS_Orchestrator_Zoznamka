from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.tools.base import Tool

_ROOT = Path(__file__).resolve().parent.parent.parent


def _queue_len(state_file: Path) -> int:
    if not state_file.is_file():
        return 0
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return 0
    queue = data.get("queue") if isinstance(data, dict) else None
    return len(queue) if isinstance(queue, list) else 0


async def _probe(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url.rstrip('/')}/health")
            response.raise_for_status()
            body = response.json() if response.content else {}
            return {
                "reachable": True,
                "logged_in": bool(body.get("logged_in")),
                "session_alive": bool(body.get("session_alive")),
                "raw": body,
            }
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "error": str(exc)}


def _normalize_service(raw: str) -> str:
    wanted = (raw or "all").strip().lower()
    if wanted in {"ed", "elite", "elitedate", "elite date", "elite dáte"}:
        return "elitedate"
    if wanted in {"tinder"}:
        return "tinder"
    if wanted in {"badoo"}:
        return "badoo"
    if wanted in {"both", "all", ""}:
        return "all"
    return wanted


class DatingStatusTool(Tool):
    name = "dating_status"
    description = (
        "Check Elite Date / Tinder / Badoo bot connectivity and pending reply queues. "
        "Use when the user asks about ED/Elite Date/Tinder/Badoo messages or whether bots are online."
    )

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        wanted = _normalize_service(str(ctx.get("service") or "all"))

        elitedate_url = settings.elitedate_bot_url
        tinder_url = settings.tinder_bot_url
        badoo_url = settings.badoo_bot_url
        ed_queue = _queue_len(_ROOT / "elitedate_state.json")
        tinder_queue = _queue_len(_ROOT / "tinder_state.json")
        badoo_queue = _queue_len(_ROOT / "badoo_state.json")

        result: dict[str, Any] = {
            "status": "ok",
            "service": wanted,
            "elitedate_url": elitedate_url,
            "tinder_url": tinder_url,
            "badoo_url": badoo_url,
        }

        lines: list[str] = []

        def _append_status(label: str, probe: dict[str, Any], url: str, queue: int) -> None:
            if not probe.get("reachable"):
                lines.append(f"❌ **{label}:** nedostupný ({url}) — {probe.get('error', '?')}")
            elif not probe.get("logged_in"):
                lines.append(f"❌ **{label}:** beží, ale nie je prihlásený")
            elif not probe.get("session_alive"):
                lines.append(f"⚠️ **{label}:** prihlásený, ale Selenium session je mŕtva")
            else:
                poll_on = probe.get("raw", {}).get("poll_enabled", True)
                poll_note = "" if poll_on else " · poll vypnutý"
                lines.append(f"✅ **{label}:** online (fronta odpovedí: {queue}{poll_note})")

        if wanted in {"elitedate", "all"}:
            ed = await _probe(elitedate_url)
            result["elitedate"] = {**ed, "pending_replies": ed_queue}
            _append_status("Elite Date", ed, elitedate_url, ed_queue)

        if wanted in {"tinder", "all"}:
            td = await _probe(tinder_url)
            result["tinder"] = {**td, "pending_replies": tinder_queue}
            _append_status("Tinder", td, tinder_url, tinder_queue)

        if wanted in {"badoo", "all"}:
            bd = await _probe(badoo_url)
            result["badoo"] = {**bd, "pending_replies": badoo_queue}
            _append_status("Badoo", bd, badoo_url, badoo_queue)

        if wanted == "elitedate" and ed_queue == 0 and result.get("elitedate", {}).get("reachable"):
            lines.append("Žiadne nové správy na Elite Date nečakajú na výber odpovede.")
        if wanted == "tinder" and tinder_queue == 0 and result.get("tinder", {}).get("reachable"):
            lines.append("Žiadne nové správy na Tinderi nečakajú na výber odpovede.")
        if wanted == "badoo" and badoo_queue == 0 and result.get("badoo", {}).get("reachable"):
            lines.append("Žiadne nové správy na Badoo nečakajú na výber odpovede.")

        result["reply"] = "\n".join(lines) if lines else "Žiadny stav na zobrazenie."
        return result
