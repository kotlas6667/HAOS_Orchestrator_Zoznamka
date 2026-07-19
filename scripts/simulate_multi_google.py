#!/usr/bin/env python3
"""Simulácia stavov pre viac Google účtov (Gmail + Calendar).

Nepotrebuje reálne OAuth — fake registry + mock providery.
Spustenie: python3 scripts/simulate_multi_google.py
"""
from __future__ import annotations

import asyncio
import json
import pickle
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@dataclass
class FakeCreds:
    token: str = "fake"
    valid: bool = True
    expired: bool = False
    refresh_token: str | None = "refresh"


@dataclass
class FakeMail:
    message_id: str
    subject: str
    sender: str
    body: str = ""


@dataclass
class FakeEvent:
    summary: str
    start: str
    start_time: str
    all_day: bool = False


@dataclass
class FakeAccountBox:
    email: str
    label: str
    mails: list[FakeMail] = field(default_factory=list)
    events: list[FakeEvent] = field(default_factory=list)
    broken: bool = False


class FakeGmailProvider:
    def __init__(self, box: FakeAccountBox, account_id: str) -> None:
        self._box = box
        self._account_id = account_id
        self._account_email = box.email
        self.account_email = box.email
        self.account_id = account_id

    async def get_emails(self, query: str = "is:unread", max_results: int = 5) -> dict[str, Any]:
        if self._box.broken:
            raise RuntimeError(f"Token neplatný pre {self._box.email}")
        emails = [
            {
                "message_id": m.message_id,
                "subject": m.subject,
                "from": m.sender,
                "date": "2026-07-19",
                "body": m.body,
                "status": "success",
            }
            for m in self._box.mails[:max_results]
        ]
        return {"status": "success", "emails": emails, "total": len(emails), "query": query}

    async def send_email(self, recipient: str, subject: str, body: str) -> dict[str, Any]:
        if self._box.broken:
            return {"status": "error", "error": "token invalid"}
        return {
            "status": "success",
            "action": "send",
            "message_id": f"sent-{self._box.email}",
            "recipient": recipient,
            "subject": subject,
            "account": self._box.email,
        }


class FakeCalendarProvider:
    def __init__(self, box: FakeAccountBox, account_id: str) -> None:
        self._box = box
        self._account_id = account_id
        self.account_email = box.email
        self.account_id = account_id

    async def get_today_events(self) -> dict[str, Any]:
        if self._box.broken:
            return {"status": "error", "error": "token invalid", "events": []}
        # Len „dnes“ = 2026-07-19
        events = []
        for e in self._box.events:
            if e.start.startswith("2026-07-19"):
                events.append(
                    {
                        "summary": e.summary,
                        "start": e.start,
                        "start_time": e.start_time,
                        "end": e.start,
                        "location": "",
                        "description": "",
                        "all_day": e.all_day,
                    }
                )
        return {"status": "success", "action": "today", "events": events, "total": len(events)}

    async def get_events(self, days: int = 7, max_results: int = 10) -> dict[str, Any]:
        if self._box.broken:
            return {"status": "error", "error": "token invalid", "events": []}
        events = [
            {
                "summary": e.summary,
                "start": e.start,
                "start_time": e.start_time,
                "end": e.start,
                "location": "",
                "description": "",
                "all_day": e.all_day,
            }
            for e in self._box.events[:max_results]
        ]
        return {
            "status": "success",
            "action": "upcoming",
            "events": events,
            "total": len(events),
            "days": days,
        }

    async def create_event(self, summary: str, start: str, end: str, description: str = "") -> dict[str, Any]:
        return {
            "status": "success",
            "action": "create",
            "summary": summary,
            "start": start,
            "end": end,
            "account": self._box.email,
        }

    async def get_events_on_date(self, date_str: str) -> dict[str, Any]:
        return await self.get_today_events()

    async def delete_event(self, event_id: str) -> dict[str, Any]:
        return {"status": "success", "action": "delete", "event_id": event_id}

    async def delete_events_on_date(self, date_str: str) -> dict[str, Any]:
        return {"status": "success", "action": "delete", "count": 0, "deleted": []}

    async def update_event(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "success", "action": "update"}


def _seed_registry(tmpdir: Path, boxes: list[FakeAccountBox]) -> list[dict[str, Any]]:
    import app.tools.google_accounts as ga

    ga._config_dir = lambda: tmpdir  # type: ignore[method-assign]
    tokens = tmpdir / "google_tokens"
    tokens.mkdir(parents=True, exist_ok=True)
    accounts = []
    for i, box in enumerate(boxes):
        aid = f"acc{i+1:02d}"
        tp = tokens / f"{aid}.pickle"
        with open(tp, "wb") as fh:
            pickle.dump(FakeCreds(), fh)
        accounts.append(
            {
                "id": aid,
                "email": box.email,
                "label": box.label,
                "token_path": str(tp),
                "connected_at": "2026-07-19T07:00:00+00:00",
                "scopes": list(ga.GOOGLE_SCOPES),
            }
        )
    ga.save_state({"enabled": True, "default_account_id": accounts[0]["id"], "accounts": accounts})
    return accounts


def _wire_tools(boxes: list[FakeAccountBox], accounts: list[dict[str, Any]]):
    from app.tools.gmail_tool import GmailTool
    from app.tools.calendar_tool import CalendarTool

    with patch.object(GmailTool, "__init__", lambda self: None):
        gmail = GmailTool()
    gmail._providers = {}
    gmail.discord = None  # type: ignore
    for acc, box in zip(accounts, boxes):
        gmail._providers[acc["id"]] = FakeGmailProvider(box, acc["id"])  # type: ignore
    gmail.provider = gmail._providers[accounts[0]["id"]]

    with patch.object(CalendarTool, "__init__", lambda self: None):
        calendar = CalendarTool()
    calendar._providers = {}
    for acc, box in zip(accounts, boxes):
        calendar._providers[acc["id"]] = FakeCalendarProvider(box, acc["id"])  # type: ignore
    calendar.provider = calendar._providers[accounts[0]["id"]]
    return gmail, calendar


failures = 0


def _ok(name: str, cond: bool, detail: str = "") -> None:
    global failures
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures += 1


async def run_scenarios() -> int:
    global failures
    failures = 0

    boxes = [
        FakeAccountBox(
            email="osobny@gmail.com",
            label="osobny",
            mails=[
                FakeMail("m1", "Účet z banky", "banka@sk", "Zostatok…"),
                FakeMail("m2", "Rodina", "mama@example.com", "Ahoj"),
            ],
            events=[
                FakeEvent("Zubár", "2026-07-19T09:00:00", "09:00"),
                FakeEvent("Nákup", "2026-07-19T17:00:00", "17:00"),
            ],
        ),
        FakeAccountBox(
            email="praca@firma.sk",
            label="praca",
            mails=[FakeMail("w1", "Standup notes", "boss@firma.sk", "Dnes 10:00")],
            events=[
                FakeEvent("Standup", "2026-07-19T10:00:00", "10:00"),
                FakeEvent("1:1", "2026-07-19T14:00:00", "14:00"),
            ],
        ),
        FakeAccountBox(
            email="projekt@gmail.com",
            label="projekt",
            mails=[],
            events=[FakeEvent("Deadline", "2026-07-20T12:00:00", "12:00")],
        ),
    ]

    print("=== Simulácia: 3 Google účty (Gmail + Calendar) ===\n")

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        accounts = _seed_registry(tmpdir, boxes)
        from app.tools import google_accounts as ga

        print("A) Registry / default účet")
        listed = ga.list_accounts()
        _ok("3 účty v registri", len(listed) == 3, str([a["email"] for a in listed]))
        _ok("default = osobny", ga.get_account()["email"] == "osobny@gmail.com")
        ga.set_default_account(accounts[1]["id"])
        _ok("default → praca", ga.get_account()["email"] == "praca@firma.sk")
        ga.set_default_account(accounts[0]["id"])

        gmail, calendar = _wire_tools(boxes, accounts)

        print("\nB) Gmail — všetky účty naraz")
        count = await gmail.run("koľko mailov", context={"action": "count", "query": "is:unread"})
        _ok("count account=all", count.get("account") == "all")
        _ok("count súčet 3", count.get("count") == 3, json.dumps(count.get("per_account"), ensure_ascii=False))
        fetch = await gmail.run("ukáž maily", context={"action": "fetch", "query": "in:inbox", "max_results": 10})
        _ok("fetch account=all", fetch.get("account") == "all")
        _ok("fetch total 3", fetch.get("total") == 3, f"returned={fetch.get('returned')}")
        sources = {e.get("account") for e in (fetch.get("emails") or [])}
        _ok("maily z osobny+praca", sources == {"osobny@gmail.com", "praca@firma.sk"}, str(sources))

        print("\nC) Gmail — konkrétny účet / fuzzy label")
        one = await gmail.run(
            "emaily z praca",
            context={"action": "fetch", "query": "in:inbox", "account": "praca@firma.sk", "max_results": 5},
        )
        _ok("account=praca", one.get("account") == "praca@firma.sk")
        _ok("len 1 mail z práce", one.get("total") == 1)
        fuzzy = await gmail.run(
            "inbox projekt",
            context={"action": "count", "query": "is:unread", "account": "projekt"},
        )
        _ok("fuzzy label projekt → 0", fuzzy.get("count") == 0 and fuzzy.get("account") == "projekt@gmail.com")
        accs = await gmail.run("aké mám účty", context={"action": "accounts"})
        _ok("action accounts → 3", accs.get("total") == 3)

        print("\nD) Kalendár — merge zo všetkých")
        today = await calendar.run("čo mám dnes", context={"action": "today", "max_results": 20})
        _ok("calendar account=all", today.get("account") == "all")
        _ok(
            "dnes 4 eventy (2+2; Deadline je zajtra)",
            today.get("total") == 4,
            json.dumps(today.get("per_account"), ensure_ascii=False),
        )
        upcoming = await calendar.run("týždeň", context={"action": "upcoming", "days": 7, "max_results": 20})
        _ok("upcoming account=all", upcoming.get("account") == "all")
        _ok("upcoming 5 eventov", upcoming.get("total") == 5, f"total={upcoming.get('total')}")
        cal_sources = {e.get("account") for e in upcoming.get("events", [])}
        _ok(
            "eventy zo všetkých 3 účtov",
            cal_sources == {"osobny@gmail.com", "praca@firma.sk", "projekt@gmail.com"},
            str(cal_sources),
        )

        print("\nE) Kalendár — konkrétny účet + create")
        work_cal = await calendar.run(
            "kalendár práca",
            context={"action": "today", "account": "praca@firma.sk"},
        )
        _ok("today len práca", work_cal.get("account") == "praca@firma.sk" and work_cal.get("total") == 2)
        created = await calendar.run(
            "pridaj meeting",
            context={
                "action": "create",
                "account": "osobny@gmail.com",
                "summary": "Test",
                "start": "2026-07-20T11:00:00",
                "end": "2026-07-20T12:00:00",
            },
        )
        _ok("create na osobny", created.get("status") == "success" and created.get("account") == "osobny@gmail.com")

        print("\nF) Jeden účet s neplatným tokenom — ostatné bežia")
        boxes[1].broken = True
        gmail, calendar = _wire_tools(boxes, accounts)
        count_partial = await gmail.run("count", context={"action": "count", "query": "is:unread"})
        _ok(
            "count prežije broken účet",
            count_partial.get("count") == 2 and count_partial.get("account") == "all",
            json.dumps(count_partial.get("per_account"), ensure_ascii=False),
        )
        broken_row = next(
            (p for p in count_partial.get("per_account", []) if p.get("account") == "praca@firma.sk"),
            {},
        )
        _ok("praca status=error", broken_row.get("status") == "error")
        today_partial = await calendar.run("dnes", context={"action": "today", "max_results": 20})
        _ok(
            "calendar merge bez práce (2 eventy)",
            today_partial.get("account") == "all" and today_partial.get("total") == 2,
            json.dumps(today_partial.get("per_account"), ensure_ascii=False),
        )

        print("\nG) VNC switch OFF — účty ostanú")
        boxes[1].broken = False
        ga.set_enabled(False)
        st = ga.load_state()
        _ok("enabled=false", st.get("enabled") is False)
        _ok("stále 3 účty", len(st.get("accounts") or []) == 3)
        _ok("has_connected_accounts", ga.has_connected_accounts())

        print("\nH) Odpojiť jeden účet")
        ga.set_enabled(True)
        ga.remove_account(accounts[2]["id"])
        left = ga.list_accounts()
        _ok("zostali 2 účty", len(left) == 2, str([a["email"] for a in left]))
        _ok("projekt preč", all(a["email"] != "projekt@gmail.com" for a in left))

        print("\nI) Background poll cez všetky inboxy")
        # re-add projekt for poll with current 2 + we use left accounts
        gmail, _ = _wire_tools(boxes[:2], left)
        seen: set[str] = set()
        notified: list[str] = []
        for prov in gmail.all_real_providers():
            try:
                resp = await prov.get_emails(query="is:unread", max_results=10)
            except Exception as exc:
                print(f"  [INFO] poll skip: {exc}")
                continue
            for mail in resp.get("emails", []):
                mid = mail["message_id"]
                if mid in seen:
                    continue
                seen.add(mid)
                notified.append(f"{mail['subject']}@{getattr(prov, 'account_email', '?')}")
        _ok("poll 3 nové maily (2+1)", len(notified) == 3, str(notified))

        print("\nJ) Prázdny inbox + kalendár na tom istom účte")
        aid = "acc03"
        tp = tmpdir / "google_tokens" / f"{aid}.pickle"
        with open(tp, "wb") as fh:
            pickle.dump(FakeCreds(), fh)
        state = ga.load_state()
        state["accounts"].append(
            {
                "id": aid,
                "email": "projekt@gmail.com",
                "label": "projekt",
                "token_path": str(tp),
                "connected_at": "2026-07-19T08:00:00+00:00",
            }
        )
        ga.save_state(state)
        accounts = ga.list_accounts()
        gmail, calendar = _wire_tools(boxes, accounts)
        empty_fetch = await gmail.run(
            "projekt maily",
            context={"action": "fetch", "account": "projekt@gmail.com", "max_results": 5},
        )
        _ok("prázdny inbox OK", (empty_fetch.get("emails") or []) == [] or empty_fetch.get("total") == 0)
        proj_cal = await calendar.run(
            "kalendár projekt",
            context={"action": "upcoming", "account": "projekt", "days": 7},
        )
        _ok(
            "projekt kalendár má Deadline",
            any(e.get("summary") == "Deadline" for e in proj_cal.get("events", [])),
        )

        print("\nK) Send ide na predvolený / vybraný účet")
        sent = await gmail.run(
            "pošli mail",
            context={
                "action": "send",
                "account": "praca@firma.sk",
                "recipient": "kolega@firma.sk",
                "subject": "Hi",
                "body": "test",
            },
        )
        _ok("send z práce", sent.get("status") == "success" and sent.get("account") == "praca@firma.sk")

    print("\n=== Hotovo ===")
    print(f"Výsledok: {failures} FAIL" if failures else "Výsledok: všetky scenáre PASS")
    print(
        """
Správanie pri ~3 účtoch:
  • Gmail fetch/count bez mena   → všetky inboxy naraz (account=all, per_account)
  • Gmail s account=…            → len ten účet (aj fuzzy label)
  • Calendar today/upcoming      → merge zo všetkých kalendárov (tag account)
  • Calendar create + account    → event do konkrétneho kalendára
  • Discord/ranný poll           → prejde všetky účty
  • 1 broken token               → ostatné účty pokračujú
  • VNC switch OFF               → tokeny ostanú
"""
    )
    return failures


if __name__ == "__main__":
    code = asyncio.run(run_scenarios())
    sys.exit(1 if code else 0)
