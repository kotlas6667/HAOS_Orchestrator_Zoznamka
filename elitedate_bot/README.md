# Elite Date bot — samostatný HA add-on

Selenium bot pre Elite Date. Beží **mimo** hlavného orchestrátora (vlastný
Chromium) — izolovaný crash/reštart bez pádu FastAPI.

## Inštalácia

```bash
cp -a /addons/haos_orchestrator/elitedate_bot /addons/haos_elitedate
# Supervisor → Local add-ons → HAOS Elite Date Bot → Install / Start
```

1. V **Nastaveniach** add-onu vyplň `elitedate_email` a `elitedate_password`.
2. Over `orchestrator_url` (default `http://local-haos-orchestrator:8000`).
3. V orchestrátore nastav `ELITEDATE_BOT_URL=http://local-haos-elitedate:8600`.

## Nastavenia (HA UI)

| Možnosť | Popis |
|--------|--------|
| `elitedate_email` | Prihlasovací e-mail na Elite Date |
| `elitedate_password` | Heslo (skryté pole) |
| `orchestrator_url` | URL hlavného orchestrátora |
| `elitedate_login_url` | Login stránka (default SK) |
| `headless` | `true` pre bežnú prevádzku na pozadí |

## Lokálny / systemd beh

Pozri `elitedate-bot.service.example`. Pre localhost nastav
`BOT_HOST=127.0.0.1` a `ORCHESTRATOR_URL=http://127.0.0.1:8000`.

```
python -m elitedate_bot.main
```

Health: `http://<host>:8600/health`
