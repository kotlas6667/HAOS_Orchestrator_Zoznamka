# Elite Date bot — samostatný HA add-on

Selenium bot pre Elite Date. Beží **mimo** hlavného orchestrátora (vlastný
Chromium), aby Pi 5 nemuselo ťahať dva browsery + FastAPI v jednom kontajneri.

## Inštalácia

```bash
cp -a /addons/haos_orchestrator/elitedate_bot /addons/haos_elitedate
# Supervisor → Local add-ons → HAOS Elite Date Bot → Install / Start
```

1. Po prvom boote vyplň `/data/.env` (`ELITEDATE_EMAIL`, `ELITEDATE_PASSWORD`).
2. Over `ORCHESTRATOR_URL=http://haos_orchestrator:8000`.
3. V orchestrátore: `ELITEDATE_BOT_URL=http://haos_elitedate:8600`.

## Lokálny / systemd beh

Pozri `elitedate-bot.service.example`. Pre localhost nastav
`BOT_HOST=127.0.0.1` a `ORCHESTRATOR_URL=http://127.0.0.1:8000`.

```
python -m elitedate_bot.main
```

Health: `http://<host>:8600/health`
