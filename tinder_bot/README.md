# Tinder bot — návod na spustenie a obnovu

Tento bot (`tinder_bot/`) je **samostatný HA add-on**. Drží prihlásenú
Selenium session na Tinderi, sleduje nové správy a odosiela vybrané odpovede.
S orchestrátorom sa rozpráva cez HTTP (`ORCHESTRATOR_URL` / `TINDER_BOT_URL`).

Beží ako **samostatný HA add-on** (vlastný Chromium, slug `haos_tinder`).

## Inštalácia / aktualizácia

Len cez **GitHub Obchod** — pozri [`deploy/UPDATE_VIA_GITHUB.md`](../deploy/UPDATE_VIA_GITHUB.md).

Repo: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`

### 1) Nastavenia (prvý krok — ešte pred Start)

**Doplnky → HAOS Tinder Bot → Nastavenia → Možnosti**:

| Pole | Prvé prihlásenie | Bežná prevádzka |
|------|------------------|-----------------|
| `tinder_headless` | **false** (noVNC) | **true** |
| `orchestrator_url` | `http://local-haos-orchestrator:8000` | rovnako |
| `poll_enabled` | true | true |
| `login_wait_sec` | 600 | 600 |
| `tinder_phone` | voliteľné | voliteľné |

**Sieť:** porty `8601` (API) a `6080` (noVNC) nechaj predvolené → **Uložiť**.

### 2) Orchestrátor

V Nastaveniach orchestrátora:

```
tinder_bot_url = http://local-haos-tinder:8601
```

### 3) Prvé prihlásenie cez noVNC

1. `tinder_headless=false` → Uložiť → Štart
2. Otvor `http://<IP_HA>:6080/vnc.html` — prihlás sa telefónom + OTP
3. V logu počkaj na `Login detected, session saved...`
4. `tinder_headless=true` → Uložiť → Reštart

Detail: [`tinder_bot/HAOS_LOGIN.md`](HAOS_LOGIN.md).

## Detekcia správ

Poller porovnáva preview v `/data/.conversation_previews.json`.
Seed po reštarte Discord nezahlcuje; notifikácia až pri zmene preview
a poslednej bunke od nich.

Debug: `POST http://local-haos-tinder:8601/debug/poll`
Manuálny push: `POST …/debug/push-discord` s `{"sender":"latest"}`.

## Env (referencia)

| Premenná | Význam |
|----------|--------|
| `TINDER_BOT_HOST` / `TINDER_BOT_PORT` | HTTP server (default `0.0.0.0:8601`) |
| `ORCHESTRATOR_URL` | `http://local-haos-orchestrator:8000` |
| `TINDER_USER_DATA_DIR` | Chrome profil (v add-one `/data/chrome-profile`) |
| `TINDER_HEADLESS` | `true` v bežnej prevádzke |

**Vypnúť bota:** Stop / Uninstall add-onu `haos_tinder`. Orchestrátor beží ďalej.
