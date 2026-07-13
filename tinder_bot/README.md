# Tinder bot — návod na spustenie a obnovu

Tento bot (`tinder_bot/`) je **samostatný HA add-on / proces**. Drží prihlásenú
Selenium session na Tinderi, sleduje nové správy a odosiela vybrané odpovede.
S orchestrátorom sa rozpráva cez HTTP (`ORCHESTRATOR_URL` / `TINDER_BOT_URL`).

Na Pi 5 ho nespúšťaj v tom istom kontajneri ako Elite Date — každý bot má
vlastný Chromium a vlastný add-on (`slug: haos_tinder`).

## Inštalácia ako HA add-on

```bash
cp -a /addons/haos_orchestrator/tinder_bot /addons/haos_tinder
# Supervisor → Local add-ons → HAOS Tinder Bot → Install / Start
```

Konfig je v `/data/.env` add-onu (pri prvom boote sa seeduje zo šablóny).
Chrome profil (prihlásenie) je v `/data/chrome-profile`.

V orchestrátore nastav:
```env
TINDER_BOT_URL=http://haos_tinder:8601
```

V Tinder add-one:
```env
ORCHESTRATOR_URL=http://haos_orchestrator:8000
TINDER_BOT_HOST=0.0.0.0
```

## Prvé spustenie (manuálne prihlásenie)

Tinder sa väčšinou neprihlasuje heslom, ale telefónom+OTP alebo cez
Google/Facebook/Apple — to sa nedá spoľahlivo automatizovať. Preto:

1. V `/data/.env` nastav `TINDER_HEADLESS=false`.
2. Reštartuj add-on (alebo lokálne `python -m tinder_bot.main`).
3. Otvorí sa viditeľné okno Chrome — prihlás sa ručne.
4. Po úspechu prepni `TINDER_HEADLESS=true`.

Lokálne (dev):
```
python -m tinder_bot.main
```

Zdravie: `http://<host>:8601/health`

## Bežné spustenie

Headless, session z `TINDER_USER_DATA_DIR` (v add-one `/data/chrome-profile`).
Poll interval `TINDER_POLL_INTERVAL_MIN_SEC` / `MAX` (default 90–180s).

## Keď sa niečo pokazí

**Session vypršala:** `TINDER_HEADLESS=false`, prihlás znova, potom späť `true`.

**Reset profilu:** zmaž `/data/chrome-profile` (resp. `TINDER_USER_DATA_DIR`).

**Chrome crash loop:** add-on `run.sh` restartuje proces (max 8× / 10 min).
Ak nestačí, pozri logy add-onu — často treba väčší `shm_size` alebo vypnúť
druhý Selenium bot na tom istom Pi.

**Vypnúť bota:** jednoducho stop/uninstall add-onu `haos_tinder`. Orchestrátor
beží ďalej; `TINDER_BOT_URL` volania zlyhajú, kým bot znova nenabehne.

## Env premenné

| Premenná | Účel |
|---|---|
| `TINDER_USER_DATA_DIR` | Trvalý Chrome profil = session |
| `TINDER_HEADLESS` | `false` = ručné prihlásenie, `true` = prevádzka |
| `TINDER_BOT_HOST` / `TINDER_BOT_PORT` | HTTP server bota (default `0.0.0.0:8601`) |
| `ORCHESTRATOR_URL` | Hlavný add-on (`http://haos_orchestrator:8000`) |
| `TINDER_AUTO_SEND` | Na strane orchestrátora — či sa odpoveď aj odošle |
