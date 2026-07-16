from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from app.config import settings

_SKILL_FILE = Path(__file__).resolve().with_name("elitedate_reply_skill.md")
_USER_SKILL_CANDIDATES = (
    Path("/data/orchestrator/config/dating_reply_skill.md"),
    Path("/app/dating_reply_skill.user.md"),
    Path("dating_reply_skill.user.md"),
    # legacy filenames from 1.2.12
    Path("/data/orchestrator/config/elitedate_reply_skill.md"),
    Path("/app/elitedate_reply_skill.user.md"),
)

_REPLY_SYSTEM_PROMPT_BASE = """\
Si asistent, ktorý pomáha používateľovi odpovedať na správy zo zoznamky. Dostaneš kontext poslednej výmeny: poslednú otázku/správu používateľa a poslednú odpoveď druhej osoby. Napíš DVE odlišné alternatívne odpovede v mene používateľa.

Pravidlá:
- Píš po slovensky (alebo v jazyku správy, ak je iný), prirodzene a konverzačne, nie formálne.
- Odpoveď 1 a odpoveď 2 sa majú štýlom líšiť (napr. jedna hravejšia/vtipnejšia, druhá vecnejšia/zvedavejšia) — nie len preformulovanie toho istého.
- Krátke, ako reálna správa v chate (1-3 vety), žiadne emoji balvany.
- Reaguj priamo na jej poslednú odpoveď a drž nadväznosť na používateľovu poslednú otázku/správu.
- Nikdy nevymýšľaj fakty o používateľovi, ktoré nepozná z kontextu správy.
- Personalizovaný skill nižšie má prioritu pri tóne, persona a hraniciach — dodrž ho.

Odpovedz IBA validným JSON objektom, žiadny iný text:
{"option_1": "<text>", "option_2": "<text>"}
"""

_FALLBACK_SKILL = (
    "Ton: prirodzeny, sebavedomy, slusny.\n"
    "Komunikacia: kratke odpovede 1-3 vety, bez tlaku, bez needy stylu.\n"
    "Obsah: bud zvedavy, navrhni konkretny dalsi krok, ked to dava zmysel.\n"
    "Hranice: nevymyslaj osobne fakty, nebud manipulativny ani vulgarne sexualny."
)


def _load_reply_skill() -> str:
    """Priority: HA Nastavenia / env → user sidecar .md → bundled skill → fallback."""
    from_settings = (settings.dating_reply_skill or "").strip()
    if from_settings:
        return from_settings

    for path in _USER_SKILL_CANDIDATES:
        try:
            if path.is_file():
                skill = path.read_text(encoding="utf-8").strip()
                if skill:
                    return skill
        except Exception:  # noqa: BLE001
            continue

    if _SKILL_FILE.exists():
        skill = _SKILL_FILE.read_text(encoding="utf-8").strip()
        if skill:
            return skill
    return _FALLBACK_SKILL


def _build_system_prompt() -> str:
    return (
        f"{_REPLY_SYSTEM_PROMPT_BASE}\n\n"
        "Dodrž aj tento personalizovaný profil štýlu pre odpovede "
        "(skill z Nastavení Orchestrátora / súboru):\n"
        f"{_load_reply_skill()}"
    )


async def generate_reply_options(message: str, sender: str, my_last_message: str = "") -> list[str]:
    """Ask GPT for two reply drafts using both sides of the latest exchange."""
    if not settings.openai_api_key:
        return [
            "(OPENAI_API_KEY nie je nastavený — doplň vlastnú odpoveď ručne.)",
            "(OPENAI_API_KEY nie je nastavený — doplň vlastnú odpoveď ručne.)",
        ]

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": _build_system_prompt()},
            {
                "role": "user",
                "content": (
                    f"Druhá osoba: {sender}\n\n"
                    f"Tvoja posledná otázka/správa:\n{my_last_message or '(nie je známa)'}\n\n"
                    f"Jej posledná odpoveď:\n{message}\n\n"
                    "Vygeneruj dve možné odpovede, ktoré nadväzujú na túto výmenu "
                    "a rešpektujú personalizovaný skill."
                ),
            },
        ],
        "temperature": 0.8,
    }

    fallback = [
        "Ďakujem za úprimnosť. Rozumiem a cením si, že si to napísala narovinu.",
        "Vďaka, že si to povedala otvorene. Prajem ti, nech sa ti darí a nájdeš to, čo hľadáš.",
    ]

    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
            )
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"].strip()
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            return [content, content]

        parsed = json.loads(json_match.group())
        return [
            parsed.get("option_1", "").strip() or "(prázdna odpoveď)",
            parsed.get("option_2", "").strip() or "(prázdna odpoveď)",
        ]
    except Exception:
        return fallback
