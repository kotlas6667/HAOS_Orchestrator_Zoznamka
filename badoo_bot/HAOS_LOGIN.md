# Prvé prihlásenie Badoo session na HAOS (Linux profil — funguje v add-one)

Windows/WSL profil **nefunguje** na HAOS (iné šifrovanie cookies). Prihlás sa priamo v add-one cez **noVNC** a **Google**. Konfigurácia je v **Nastaveniach** add-onu.

## Kroky

### 1) Nastavenia (prvý bod)

**Doplnky → HAOS Badoo Bot → Nastavenia → Možnosti:**

- `badoo_headless` = **false**
- `orchestrator_url` = hostname orchestrátora (Info → Hostname)
- `login_wait_sec` = `600`
- `poll_enabled` = **false** (zatiaľ — inbox príde neskôr)

**Sieť:** nechaj `8602` a `6081` → **Uložiť**.

### 2) Rebuild / Start add-onu

### 3) V prehliadači na PC otvor:
```
http://<IP_HA>:6081/vnc.html
```

Uvidíš Chromium s Badoom. Prihlás sa **cez Google** (alebo telefón/email, ak preferuješ).

### 4) V logu add-onu počkaj:
```
[badoo_bot] Login detected, session saved...
```

### 5) Prepnúť na bežnú prevádzku

**Nastavenia → Možnosti → `badoo_headless` = true → Uložiť → Reštart.**

Port 6081 / noVNC sa už nespustí. Session ostáva v `/data/chrome-profile`.

## Overenie
```bash
curl http://127.0.0.1:8602/health
# {"status":"ok","logged_in":true,"session_alive":true,...}

curl http://127.0.0.1:8602/debug/page
# url by nemal obsahovať /signin
```

## Porty (konflikt s ostatnými add-onmi)

| Služba | noVNC | API |
|--------|-------|-----|
| Elite Date | — (bez noVNC) | 8600 |
| Tinder | 6080 | 8601 |
| **Badoo** | **6081** | **8602** |
| Google (orch) | 6082 | 8000 |

Elite Date, Tinder a Badoo bežia **paralelne** ako tri samostatné add-ony — Badoo nič z ED/Tinderu nenahrádza.
