# Elite Date bot — samostatný HA add-on

Selenium bot pre Elite Date. Beží **mimo** hlavného orchestrátora (vlastný
Chromium) — izolovaný crash/reštart bez pádu FastAPI.

## Inštalácia / aktualizácia

Len cez **GitHub Obchod** — pozri [`deploy/UPDATE_VIA_GITHUB.md`](../deploy/UPDATE_VIA_GITHUB.md).

Repo: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`

1. V **Nastaveniach** add-onu vyplň `elitedate_email` a `elitedate_password`.
2. Over `orchestrator_url` = `http://local-haos-orchestrator:8000`.
3. V orchestrátore nastav `elitedate_bot_url` = `http://local-haos-elitedate:8600`.

## Nové správy (JSON cache)

Poller porovnáva inbox preview v `/data/.conversation_previews.json`
(seed po reštarte neposiela Discord; notifikácia až pri zmene + posledná správa od nich).

Manuálny test: `POST http://local-haos-elitedate:8600/debug/poll`.

## Ranné pozdravy (Noví členovia)

Voliteľný denný cyklus o **07:00** (lokálny čas kontajnera):

1. Otvorí `https://www.elitedate.sk/ucet/novi-clenove`
2. Otvorí filter (`button.btn-partner-filter`) ak formulár nie je viditeľný
3. Nastaví filter (ak ešte nie je): `#search_filter_form_ageFrom/To` 34–41, `heightTo` 166, 75 km (noUiSlider), potvrdí `#search_filter_form_submit`
4. Prechádza karty `a.c-card`, kým neodošle `morning_greet_max_profiles` pozdravov
   (profily s históriou sa preskočia a do limitu sa nepočítajú)
5. Klikne `a.send-message-btn` — ak je chat prázdny, pošle `Ahoj :-)`; ak už sú `.message` bubliny, preskočí

Spracované profilové ID sú v `/data/.morning_greeted.json` (neopakujú sa).
Manuálny test: `POST http://local-haos-elitedate:8600/debug/morning_greet`.

## Nastavenia (HA UI)

| Možnosť | Popis |
|--------|--------|
| `elitedate_email` | Prihlasovací e-mail na Elite Date |
| `elitedate_password` | Heslo (skryté pole) |
| `orchestrator_url` | `http://local-haos-orchestrator:8000` |
| `elitedate_login_url` | Login stránka (default SK) |
| `headless` | `true` pre bežnú prevádzku na pozadí |
| `poll_enabled` | Automatické sledovanie inboxu (default `true`) |
| `morning_greet_enabled` | Zapnúť ranné pozdravy (default `false`) |
| `morning_greet_max_profiles` | Koľko **odoslaných** pozdravov za jeden beh (1–50, default 10) |

## Lokálny / systemd beh (bez HA)

Pozri `elitedate-bot.service.example`. Pre localhost nastav
`BOT_HOST=127.0.0.1` a `ORCHESTRATOR_URL=http://127.0.0.1:8000`.

```
python -m elitedate_bot.main
```

Health: `http://<host>:8600/health`
