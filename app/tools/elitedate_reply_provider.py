from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from app.config import settings
from app.tools.dating_skill import load_reply_skill

_SKILL_FILE = Path(__file__).resolve().with_name("elitedate_reply_skill.md")

_REPLY_SYSTEM_PROMPT_BASE = """\
Si ghostwriter pre chat na zoznamke (Elite Date). Píšeš v mene používateľa — ako by to napísal on sám, nie ako AI asistent.

Dostaneš poslednú výmenu (jeho správa + jej odpoveď). Vráť DVE odlišné odpovede.

Ako písať (kvalita ako dobrý ľudský draft, nie generický dating bot):
- Zachyť KONKRÉTNY detail z jej správy (slovo, vtip, plán, náladu) a nadviaž naň — nie všeobecné „to znie fajn“.
- Prispôsob dĺžku a energiu jej správe: krátka správa → kratšia odpoveď; dlhšia/vecná → 2–3 vety OK.
- Zniej ako reálny chlap v chate: hovorový slovenčina (alebo jazyk správy), prirodzené skratky OK, žiadne firemné / coachingové frázy.
- Vyhni sa klišé: „cením si úprimnosť“, „to je skvelé“, „som rád že…“, „chápem ťa“, „nech sa ti darí“, „nájdeš to čo hľadáš“.
- Jedna prirodzená otázka alebo ľahký next-step (kava / prechádzka / termín) len keď to sedí — nie vždy.
- Nevymýšľaj fakty o ňom (práca, deti, mesto…), ktoré nie sú v kontexte.
- Emoji max 0–1; žiadne zoznamy, žiadne úvodzovky okolo celej odpovede.
- option_1 a option_2 musia byť iný tón (napr. hravejší vs. vecnejší), nie parafráza.

Personalizovaný skill nižšie má prioritu pri persona, tóne a hraniciach.

Odpovedz IBA validným JSON, nič iné:
{"option_1": "<text>", "option_2": "<text>"}
"""

_FALLBACK_SKILL = (
    "Ton: prirodzeny, sebavedomy, slusny.\n"
    "Komunikacia: kratke odpovede 1-3 vety, bez tlaku, bez needy stylu.\n"
    "Obsah: bud zvedavy, navrhni konkretny dalsi krok, ked to dava zmysel.\n"
    "Hranice: nevymyslaj osobne fakty, nebud manipulativny ani vulgarne sexualny."
)


def _build_system_prompt() -> str:
    skill = load_reply_skill(bundled_path=_SKILL_FILE, fallback=_FALLBACK_SKILL)
    return (
        f"{_REPLY_SYSTEM_PROMPT_BASE}\n\n"
        "Dodrž tento personalizovaný profil štýlu "
        "(skill z dashboardu Orchestrátora / súboru):\n"
        f"{skill}"
    )


async def generate_reply_options(
    message: str,
    sender: str,
    my_last_message: str = "",
    previous_options: list[str] | None = None,
) -> list[str]:
    """Ask GPT for two reply drafts using both sides of the latest exchange."""
    if not settings.openai_api_key:
        return [
            "(OPENAI_API_KEY nie je nastavený — doplň vlastnú odpoveď ručne.)",
            "(OPENAI_API_KEY nie je nastavený — doplň vlastnú odpoveď ručne.)",
        ]

    previous = [str(o).strip() for o in (previous_options or []) if str(o).strip()]
    avoid_block = ""
    if previous:
        listed = "\n".join(f"- {opt}" for opt in previous)
        avoid_block = (
            "\n\nPredchádzajúce návrhy (NEPOUŽÍVAJ ich a nenapodobňuj ich — "
            "vymysli úplne iné varianty):\n"
            f"{listed}"
        )

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
                    "Napíš dve možné odpovede ako reálny chat — nadviaž na konkrétny "
                    "detail z jej správy a dodrž skill."
                    f"{avoid_block}"
                ),
            },
        ],
        "temperature": 0.95 if previous else 0.85,
    }

    fallback = [
        "Hej, super — a čo ty, ako sa máš dnes?",
        "Znie dobre. Keď budeš mať chuť, daj vedieť a nájdeme termín na kávu.",
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
