# Tinder bot — návod na spustenie a obnovu

Tento bot (`tinder_bot/`) je **samostatný HA add-on / proces**. Drží prihlásenú
Selenium session na Tinderi, sleduje nové správy a odosiela vybrané odpovede.
S orchestrátorom sa rozpráva cez HTTP (`ORCHESTRATOR_URL` / `TINDER_BOT_URL`).

Beží ako **samostatný HA add-on** (vlastný Chromium, slug `haos_tinder`).
Na i3 / 16 GB môže bežať naraz s Elite Date add-onom — oddelenie je kvôli
izolácii, nie kvôli RAM.

## Inštalácia ako HA add-on

```bash
cp -a /addons/haos_orchestrator/tinder_bot /addons/haos_tinder
# Supervisor → Local add-ons → HAOS Tinder Bot → Install
```

### 1) Nastavenia (prvý krok — ešte pred Start)

**Doplnky → HAOS Tinder Bot → Nastavenia → Možnosti** (popisy pri každom poli, jazyk HA = sk):

| Pole | Prvé prihlásenie | Bežná prevádzka |
|------|------------------|-----------------|
| `tinder_headless` | **false** (noVNC) | **true** |
| `orchestrator_url` | `http://haos_orchestrator:8000` | rovnako |
| `poll_enabled` | true | true |
| `login_wait_sec` | 600 | 600 |
| `tinder_phone` | voliteľné | voliteľné |

**Sieť:** porty `8601` (API) a `6080` (noVNC) nechaj predvolené → **Uložiť**.

Tieto Možnosti sa pri štarte syncnú do `/data/.env` (majú prednosť pred ručnou editáciou `.env`).

### 2) Orchestrátor

V orchestrátore (`.env`):
```env
TINDER_BOT_URL=http://haos_tinder:8601
```

### 3) Prvé prihlásenie cez noVNC

1. V **Nastaveniach** maj `tinder_headless = false` → Start add-onu.
2. V prehliadači na PC otvor: `http://<IP_HA>:6080/vnc.html`
3. Prihlás sa **telefónom + OTP** (nie Google).
4. V logu počkaj: `Login detected, session saved...`
5. **Nastavenia** → `tinder_headless = true` → **Uložiť** → Reštart.

Chrome profil (session) je v `/data/chrome-profile`.

Zdravie: `http://<host>:8601/health` → `{"status":"ok","logged_in":true}`

Lokálne (dev):
```
python -m tinder_bot.main
```

## Bežné spustenie

Headless (`tinder_headless=true`), session z `/data/chrome-profile`.
Poll interval `TINDER_POLL_INTERVAL_MIN_SEC` / `MAX` (default 90–180s) — v `.env`.

## Keď sa niečo pokazí

**Session vypršala:** Nastavenia → `tinder_headless=false` → noVNC login → späť `true`.

**Reset profilu:** zmaž `/data/chrome-profile`.

**Chrome crash loop:** add-on `run.sh` restartuje proces (max 8× / 10 min).
Ak nestačí, pozri logy add-onu — často treba väčší `shm_size`.

**Vypnúť bota:** stop/uninstall add-onu `haos_tinder`. Orchestrátor beží ďalej.

## Env / Možnosti

| Nastavenie (UI) / ENV | Účel |
|---|---|
| `tinder_headless` / `TINDER_HEADLESS` | `false` = noVNC prihlásenie, `true` = prevádzka |
| `orchestrator_url` / `ORCHESTRATOR_URL` | Hlavný add-on |
| `poll_enabled` / `TINDER_POLL_ENABLED` | Periodické čítanie správ |
| `login_wait_sec` / `TINDER_LOGIN_WAIT_SEC` | Timeout čakania na login |
| `tinder_phone` / `TINDER_PHONE` | Voliteľné predvyplnenie |
| `/data/chrome-profile` | Trvalý Chrome profil = session |
| `TINDER_BOT_HOST` / `TINDER_BOT_PORT` | HTTP server (default `0.0.0.0:8601`) |
