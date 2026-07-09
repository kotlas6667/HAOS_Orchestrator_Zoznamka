from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings

_ROUTER_SYSTEM_PROMPT = """\
You are a routing assistant. Given a user message and conversation history, decide which tool to call and extract the necessary parameters.

Available tools:
- weather: Get current weather or multi-day forecast for a city. Params: {"city": "<city name>", "action": "current|forecast", "days": <number 1-5, default 3>}
- gmail: Read or search emails. Params: {"action": "fetch|count|send", "query": "<gmail search query>", "max_results": <number, default 5>, "recipient": "<email if sending>", "subject": "<subject if sending>", "body": "<body if sending>"}
- calendar: Google Calendar — view and create events. Params: {"action": "today|upcoming|create|update|delete", "days": <number for upcoming, default 7>, "summary": "<event title>", "start": "<ISO datetime>", "end": "<ISO datetime>", "description": "<optional>", "date": "<YYYY-MM-DD for delete/update>", "old_time": "<HH:MM original time for update>"}
- homeassistant: Control smart home devices and automations. Params: {"action": "get_state|list_entities|turn_on|turn_off|toggle|call_service|list_automations|trigger_automation", "search": "<room/device keywords, e.g. 'svetlo pracovna'>", "domain": "<domain, only for call_service>", "service": "<service name, only for call_service>"}
- todo: Personal task/TODO list. Params: {"action": "add|list|complete|remove|clear_done", "task": "<task text for add>", "id": <task number for complete/remove>}
- messages: Send a message via Discord/Slack/webhook. Params: {"destination": "<channel>", "message": "<text>"}
- chat: General conversation, questions, help. Params: {}

Rules:
- USE CONVERSATION HISTORY to understand context. If the user says "show them", "summarize them", "zhrň ich" etc. — look at what was discussed before and route to the appropriate tool. For example if the previous message was about emails, route to gmail.
- If the user asks about temperature, weather, forecast, or conditions in any location — use "weather" and extract the city name.
- If the user asks about weather WITHOUT specifying a city (e.g. just "aké je počasie?" or "koľko je stupňov?"), use "weather" with params: {"city": ""} — do NOT guess or invent a city name.
- If the user asks for a forecast/prediction for multiple days (e.g. "predpoveď na 3 dni", "počasie na zajtra a pozajtra", "zobraz +3 dni", "počasie na týždeň"), use action: "forecast" with the appropriate number of days. Keywords: predpoveď, forecast, +Xdní, nasledujúce dni, tento týždeň (weather context).
- If the user just asks "aké je počasie?" or "koľko stupňov?" without mentioning multiple days, use action: "current".
- If the user asks about emails, inbox, or wants to send email — use "gmail".
- If the user asks about calendar, schedule, meetings, events, "čo mám dnes", "kedy mám meeting", or wants to create/add an event — use "calendar".
  - "čo mám dnes v kalendári?" → action: "today"
  - "čo mám tento týždeň?" → action: "upcoming", days: 7
  - "pridaj meeting zajtra o 10:00 s názvom X" → action: "create", summary: "X", start: "<ISO date>", end: "<ISO date +1h>"
  - "uprav udalosť X z 3.7.2026 z 16:00 na 15:00" → action: "update", summary: "X", date: "2026-07-03", start: "2026-07-03T15:00:00", old_time: "16:00"
  - "vymaž udalosti z 3.7.2026" → action: "delete", date: "2026-07-03"
  - IMPORTANT for update/delete: If the user does NOT provide ALL of (summary, date, time), still route to calendar with action "update" or "delete" and fill in what you know. Calendar tool will ask for missing details. Do NOT use "upcoming" as a workaround.
  - When creating/updating events, ALWAYS convert relative dates to ISO format based on current date.
  - If the user wants to create an event but did NOT provide enough details (time or name), ask for them using "chat" tool instead of routing to calendar with empty params.
- IMPORTANT: Only add query filters that the user EXPLICITLY mentioned. Do NOT invent or assume filters.
  - "dnes/today" → "newer_than:1d"
  - "tento tyždeň/this week" → "newer_than:7d"
  - "neprečítané/unread" → "is:unread"
  - "od X / from X" → "from:X"
  - If the user says "show me the first/latest email" without any time/filter reference, use query: "in:inbox" with max_results: 1.
  - If the user asks to show/list emails without specifying a folder, always default to query: "in:inbox".
  - Do NOT add "newer_than", "is:unread", or any other filter unless the user explicitly asks for it.
  - If the user references previous context (e.g. "summarize them" after asking about today's emails), reuse the same query from context.
- If the user wants to send a message or notification somewhere — use "messages".
- If the user wants to add a task, remember something, check their TODO list, mark something as done, or manage tasks — use "todo".
  - "zapamätaj si: kúpiť mlieko" → action: "add", task: "kúpiť mlieko"
  - If the user provides MULTIPLE items (e.g. "mlieko a chleba", "mlieko, chleba, maslo"), create SEPARATE tasks for each item using a comma-separated list in the task field: action: "add", task: "mlieko|chleba|maslo" — use | as separator between individual items. Each item is a separate task.
  - "čo mám na zozname?" / "ukáž úlohy" → action: "list"
  - "hotovo 3" / "splnené 3" → action: "complete", id: 3
  - "vymaž 2" → action: "remove", id: 2
  - "vyčisti dokončené" → action: "clear_done"
- If the user asks about smart home devices, lights, switches, sensors, temperature in the house/room (e.g. "teplota v obývačke", "teplota v dome"), automations, or wants to control something at home — use "homeassistant".
  - IMPORTANT: "počasie v [meste]" or "teplota v [meste]" where the location is a CITY or TOWN → use "weather", NOT homeassistant.
  - Only use "homeassistant" when the user refers to a ROOM in their house (obývačka, spálňa, kuchyňa, garáž) or specific devices (svetlo, klíma, termostat).
  - "zapni/turn on svetlo v kuchyni" → action: "turn_on", search: "svetlo kuchyna"
  - "vypni/turn off X" → action: "turn_off", search: "<room/device keywords>"
  - "prepni/toggle X" → action: "toggle", search: "<room/device keywords>"
  - "aká je teplota v obývačke" → action: "get_state", search: "teplota obyvacka"
  - "ukáž zariadenia/list devices" → action: "list_entities", search: "<optional filter>"
  - "aké mám automatizácie" → action: "list_automations"
  - "spusti automatizáciu X" → action: "trigger_automation", search: "<automation name keywords>"
  - If the user refers to a device with a pronoun or vague reference instead of naming it (e.g. "zapni ho", "vypni ju",
    "zapni to znova", "teraz ho zapni", "spusti ešte raz"), look at the CONVERSATION HISTORY for the most recent
    homeassistant device/room mentioned and reuse those same keywords as "search" — do NOT set search to the pronoun
    itself (e.g. never search: "ho" or search: "teraz").
  - NEVER invent or guess an entity_id yourself (e.g. do NOT write "light.living_room"). The app resolves the
    real entity_id from the "search" keywords against the actual Home Assistant entity list, and will ask the
    user to clarify if the device name is ambiguous.
- For everything else — use "chat".
- Always extract the city name from the prompt if tool is "weather", even if the city is in a locative/genitive Slovak form (e.g. "Smrdakoch" → "Smrdaky", "Bratislave" → "Bratislava").

Respond ONLY with a valid JSON object, no explanation, no markdown:
{"tool": "<tool_name>", "params": {<extracted params>}, "reason": "<short reason>"}
"""


async def llm_route(prompt: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
  """Ask GPT to decide which tool to call and what params to pass."""
  if not settings.openai_api_key:
    return {"tool": "chat", "params": {}, "reason": "No OpenAI API key configured."}

    from datetime import datetime
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    system_with_date = _ROUTER_SYSTEM_PROMPT + f"\n\nCurrent date and time: {current_date}"

    headers = {
      "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    messages = [{"role": "system", "content": system_with_date}]
    # Include last 4 exchanges for routing context (enough to understand references)
    if history:
        messages.extend(history[-8:])
    messages.append({"role": "user", "content": prompt})

    data = {
      "model": settings.openai_model,
        "messages": messages,
        "temperature": 0.0,
    }

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.post(
          "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
        )
        response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"].strip()

    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())

    return {"tool": "chat", "params": {}, "reason": "Router returned unparseable response."}
