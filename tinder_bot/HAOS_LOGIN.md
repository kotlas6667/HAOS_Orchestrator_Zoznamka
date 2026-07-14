# Prvé prihlásenie Tinder session na HAOS (Linux profil — funguje v add-one)

Windows/WSL profil **nefunguje** na HAOS (iné šifrovanie cookies). Prihlás sa priamo v add-one cez **noVNC**. Konfigurácia je v **Nastaveniach** add-onu (nie treba SSH do `.env`).

## Kroky

### 1) Nastavenia (prvý bod)

**Doplnky → HAOS Tinder Bot → Nastavenia → Možnosti:**

- `tinder_headless` = **false**
- `orchestrator_url` = `http://haos_orchestrator:8000`
- `login_wait_sec` = `600`

**Sieť:** nechaj `8601` a `6080` → **Uložiť**.

### 2) Rebuild / Start add-onu (verzia ≥ 1.2.0)

### 3) V prehliadači na PC otvor:
```
http://192.168.1.109:6080/vnc.html
```
alebo Tailscale: `http://100.82.143.35:6080/vnc.html`

Uvidíš Chromium s Tinderom. Prihlás sa **telefónom + OTP** (nie Google).

### 4) V logu add-onu počkaj:
```
[tinder_bot] Login detected, session saved...
```

### 5) Prepnúť na bežnú prevádzku

**Nastavenia → Možnosti → `tinder_headless` = true → Uložiť → Reštart.**

Port 6080 / noVNC sa už nespustí. Session ostáva v `/data/chrome-profile`.

## Overenie
```bash
curl http://127.0.0.1:8601/health
# {"status":"ok","logged_in":true}
```
