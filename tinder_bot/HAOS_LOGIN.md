# Prvé prihlásenie Tinder session na HAOS (Linux profil — funguje v add-one)

Windows/WSL profil **nefunguje** na HAOS (iné šifrovanie cookies). Prihlás sa priamo v add-one cez **noVNC**.

## Kroky

### 1) Rebuild add-onu (po `git pull` v `/addons/haos_tinder`)

### 2) V `.env` add-onu (`local_haos_tinder/.env` na HAOS):
```env
TINDER_HEADLESS=false
TINDER_USER_DATA_DIR=/data/chrome-profile
TINDER_LOGIN_WAIT_SEC=600
ORCHESTRATOR_URL=http://haos_orchestrator:8000
```

### 3) Start add-onu

### 4) V prehliadači na PC otvor:
```
http://192.168.1.109:6080/vnc.html
```
alebo Tailscale: `http://100.82.143.35:6080/vnc.html`

Uvidíš Chromium s Tinderom. Prihlás sa **telefónom + OTP** (nie Google).

### 5) V logu add-onu počkaj:
```
[tinder_bot] Login detected, session saved...
```

### 6) Prepnúť na bežnú prevádzku:
```env
TINDER_HEADLESS=true
```
Restart add-onu. Port 6080 už nepotrebuješ.

## Overenie
```bash
curl http://127.0.0.1:8601/health
# {"status":"ok","logged_in":true}
```
