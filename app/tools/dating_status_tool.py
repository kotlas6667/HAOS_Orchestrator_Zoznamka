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


class DatingStatusTool(Tool):
    name = "dating_status"
    description = (
        "Check Elite Date / Tinder bot connectivity and pending reply queues. "
        "Use when the user asks about ED/Elite Date/Tinder messages or whether bots are online."
    )

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        wanted = str(ctx.get("service") or "both").strip().lower()
        if wanted in {"ed", "elite", "elitedate", "elite date", "elite dáte"}:
            wanted = "elitedate"
        elif wanted in {"tinder"}:
            wanted = "tinder"
        else:
            wanted = "both"

        elitedate_url = settings.elitedate_bot_url
        tinder_url = settings.tinder_bot_url
        ed_queue = _queue_len(_ROOT / "elitedate_state.json")
        tinder_queue = _queue_len(_ROOT / "tinder_state.json")

        result: dict[str, Any] = {
            "status": "ok",
            "service": wanted,
            "elitedate_url": elitedate_url,
            "tinder_url": tinder_url,
        }

        lines: list[str] = []

        if wanted in {"elitedate", "both"}:
            ed = await _probe(elitedate_url)
            result["elitedate"] = {**ed, "pending_replies": ed_queue}
            if not ed.get("reachable"):
                lines.append(
                    f"❌ **Elite Date:** nedostupný ({elitedate_url}) — {ed.get('error', '?')}"
                )
            elif not ed.get("logged_in"):
                lines.append("❌ **Elite Date:** beží, ale nie je prihlásený")
            elif not ed.get("session_alive"):
                lines.append("⚠️ **Elite Date:** prihlásený, ale Selenium session je mŕtva")
            else:
                lines.append(
                    f"✅ **Elite Date:** online (fronta odpovedí: {ed_queue})"
                )

        if wanted in {"tinder", "both"}:
            td = await _probe(tinder_url)
            result["tinder"] = {**td, "pending_replies": tinder_queue}
            if not td.get("reachable"):
                lines.append(
                    f"❌ **Tinder:** nedostupný ({tinder_url}) — {td.get('error', '?')}"
                )
            elif not td.get("logged_in"):
                lines.append("❌ **Tinder:** beží, ale nie je prihlásený")
            elif not td.get("session_alive"):
                lines.append("⚠️ **Tinder:** prihlásený, ale Selenium session je mŕtva")
            else:
                lines.append(f"✅ **Tinder:** online (fronta odpovedí: {tinder_queue})")

        if wanted == "elitedate" and ed_queue == 0 and result.get("elitedate", {}).get("reachable"):
            lines.append("Žiadne nové správy na Elite Date nečakajú na výber odpovede.")
        if wanted == "tinder" and tinder_queue == 0 and result.get("tinder", {}).get("reachable"):
            lines.append("Žiadne nové správy na Tinderi nečakajú na výber odpovede.")

        result["reply"] = "\n".join(lines) if lines else "Žiadny stav na zobrazenie."
        return result
