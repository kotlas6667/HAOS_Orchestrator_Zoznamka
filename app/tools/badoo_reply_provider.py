from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.config import settings
from app.tools.dating_skill import (
    DATING_REPLY_RETRY_TEMPERATURE,
    SLOVAK_REPLY_GRAMMAR_RULES,
    dating_reply_temperature,
    format_chat_history_for_prompt,
    load_reply_skill,
    parse_dating_reply_json,
    resolve_dating_reply_model,
)

_SKILL_FILE = Path(__file__).resolve().with_name("badoo_reply_skill.md")

_REPLY_SYSTEM_PROMPT_BASE = """\
Si ghostwriter pre chat na Badoo. Píšeš v mene používateľa — ako by to napísal on sám v telefone, nie ako AI asistent.

Dostaneš predchádzajúcu konverzáciu (transcript) a jej poslednú správu. Vráť ŠTYRI odlišné odpovede.

Ako písať (kvalita ako dobrý ľudský draft, nie generický dating bot):
- Čítaj CELÚ históriu: nadviaž na témy, vtipy, plány a detaily z predchádzajúcich správ — nielen na posledný riadok.
- Zachyť KONKRÉTNY detail z jej poslednej správy v kontexte histórie — nie všeobecné „to znie fajn“.
- Prispôsob dĺžku a energiu jej správe: krátka správa → krátka odpoveď; dlhšia/hravá → môžeš trochu viac.
- Zniej ako reálny chlap v chate: hovorový slovenčina (alebo jazyk správy), prirodzené skratky OK, žiadne firemné / coachingové frázy.
- Vyhni sa klišé: „cením si úprimnosť“, „to je skvelé“, „som rád že…“, „chápem ťa“, „nech sa ti darí“, „nájdeš to čo hľadáš“.
- Jedna prirodzená otázka alebo ľahký next-step (kava / prechádzka / termín) len keď to sedí — nie vždy.
- Nevymýšľaj fakty o ňom (práca, deti, mesto…), ktoré nie sú v kontexte histórie.
- Emoji max 0–1; žiadne zoznamy, žiadne úvodzovky okolo celej odpovede.
- option_1 až option_4 musia mať rôzny tón/uhol (napr. hravý, vecný, zvedavý, ľahký next-step), nie parafrázy.

Personalizovaný skill nižšie má prioritu pri persona, tóne a hraniciach.

Odpovedz IBA validným JSON, nič iné:
{"option_1": "<text>", "option_2": "<text>", "option_3": "<text>", "option_4": "<text>"}
"""

_FALLBACK_SKILL = (
    "Ton: prirodzeny, sebavedomy, slusny.\n"
    "Komunikacia: kratke odpovede 1-2 vety, bez tlaku, bez needy stylu.\n"
    "Obsah: bud zvedavy, navrhni konkretny dalsi krok, ked to dava zmysel.\n"
    "Hranice: nevymyslaj osobne fakty, nebud manipulativny ani vulgarne sexualny."
)


def _build_system_prompt() -> str:
    skill = load_reply_skill(bundled_path=_SKILL_FILE, fallback=_FALLBACK_SKILL)
    return (
        f"{_REPLY_SYSTEM_PROMPT_BASE}\n\n"
        f"{SLOVAK_REPLY_GRAMMAR_RULES}\n"
        "Dodrž tento personalizovaný profil štýlu "
        "(skill z dashboardu Orchestrátora / súboru):\n"
        f"{skill}"
    )


async def generate_reply_options(
    message: str,
    sender: str,
    my_last_message: str = "",
    previous_options: list[str] | None = None,
    history: list | None = None,
    provider: str = "",
) -> list[str]:
    """Ask the configured LLM for four reply drafts using full chat history."""
    chosen_provider = (provider or settings.dating_reply_provider or "openai").strip().lower()

    previous = [str(o).strip() for o in (previous_options or []) if str(o).strip()]
    avoid_block = ""
    if previous:
        listed = "\n".join(f"- {opt}" for opt in previous)
        avoid_block = (
            "\n\nPredchádzajúce návrhy (NEPOUŽÍVAJ ich a nenapodobňuj ich — "
            "vymysli úplne iné varianty):\n"
            f"{listed}"
        )

    transcript = format_chat_history_for_prompt(history, sender=sender)
    if transcript:
        context_block = (
            f"Predchádzajúca konverzácia (od najstaršej po najnovšiu):\n"
            f"{transcript}\n\n"
            f"Jej posledná správa (na ktorú máš reagovať):\n{message}\n\n"
            "Napíš **štyri** možné odpovede ako reálny chat — zohľadni celú históriu, "
            "nielen posledný riadok, a dodrž skill. Každá musí mať iný tón/uhol."
        )
    else:
        context_block = (
            f"Tvoja posledná otázka/správa:\n{my_last_message or '(nie je známa)'}\n\n"
            f"Jej posledná odpoveď:\n{message}\n\n"
            "Napíš **štyri** možné odpovede ako reálny chat — nadviaž na konkrétny "
            "detail z jej správy a dodrž skill. Každá musí mať iný tón/uhol."
        )

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": resolve_dating_reply_model(),
        "messages": [
            {"role": "system", "content": _build_system_prompt()},
            {
                "role": "user",
                "content": (
                    f"Druhá osoba: {sender}\n\n"
                    f"{context_block}"
                    f"{avoid_block}"
                ),
            },
        ],
        "temperature": dating_reply_temperature(regenerate=bool(previous)),
    }

    fallback = [
        "Hej, super — a čo ty, ako sa máš dnes?",
        "Znie dobre. Keď budeš mať chuť, daj vedieť a nájdeme termín na kávu.",
        "Cool, vďaka za info — čo plánuješ dnes večer?",
        "Máš pravdu. Keď ti to vyhovuje, môžeme to posunúť na konkrétny termín.",
    ]

    if chosen_provider == "gemini":
        if not settings.gemini_api_key:
            msg = "(GEMINI_API_KEY nie je nastavený — doplň vlastnú odpoveď ručne.)"
            return [msg, msg, msg, msg]
        try:
            return await _generate_with_gemini(
                sender=sender,
                context_block=context_block,
                avoid_block=avoid_block,
                fallback=fallback,
            )
        except Exception:
            return fallback

    if not settings.openai_api_key:
        msg = "(OPENAI_API_KEY nie je nastavený — doplň vlastnú odpoveď ručne.)"
        return [msg, msg, msg, msg]

    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
            )
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"].strip()
        options = parse_dating_reply_json(content, fallback)
        unique = {o for o in options if o != "(prázdna odpoveď)"}
        if len(unique) < 4:
            retry_data = {
                **data,
                "messages": data["messages"]
                + [
                    {
                        "role": "user",
                        "content": (
                            "Predchádzajúca odpoveď nemala 4 rôzne varianty. "
                            "Vráť IBA JSON s option_1, option_2, option_3, option_4."
                        ),
                    }
                ],
                "temperature": DATING_REPLY_RETRY_TEMPERATURE,
            }
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                retry_resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=retry_data,
                )
                retry_resp.raise_for_status()
            retry_content = retry_resp.json()["choices"][0]["message"]["content"].strip()
            options = parse_dating_reply_json(retry_content, fallback)
        return options[:4]
    except Exception:
        return fallback


async def _generate_with_gemini(
    *,
    sender: str,
    context_block: str,
    avoid_block: str,
    fallback: list[str],
) -> list[str]:
    model = (settings.dating_reply_gemini_model or "gemini-2.5-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {
            "parts": [{"text": _build_system_prompt()}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"Druhá osoba: {sender}\n\n"
                            f"{context_block}"
                            f"{avoid_block}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": dating_reply_temperature(regenerate=bool(avoid_block)),
            "responseMimeType": "application/json",
        },
    }

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
        response.raise_for_status()
        content = _extract_gemini_text(response.json())

    options = parse_dating_reply_json(content, fallback)
    unique = {o for o in options if o != "(prázdna odpoveď)"}
    if len(unique) >= 4:
        return options[:4]

    retry_payload = {
        **payload,
        "contents": payload["contents"]
        + [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Predchádzajúca odpoveď nemala 4 rôzne varianty. "
                            "Vráť IBA JSON s option_1, option_2, option_3, option_4."
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            **payload["generationConfig"],
            "temperature": DATING_REPLY_RETRY_TEMPERATURE,
        },
    }
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        retry_resp = await client.post(
            url,
            params={"key": settings.gemini_api_key},
            json=retry_payload,
        )
        retry_resp.raise_for_status()
        retry_content = _extract_gemini_text(retry_resp.json())
    return parse_dating_reply_json(retry_content, fallback)[:4]


def _extract_gemini_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini nevrátil žiadnych kandidátov: {json.dumps(payload)[:500]}")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
    text = "\n".join(str(part.get("text") or "").strip() for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise RuntimeError("Gemini vrátil prázdny obsah.")
    return text
