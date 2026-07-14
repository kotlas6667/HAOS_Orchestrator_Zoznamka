# HAOS — nasadenie a aktualizácia add-onov

Podrobný návod pre **HAOS Orchestrator**, **Elite Date** a **Tinder** ako samostatné local add-ony na Home Assistant OS.

---

## Architektúra

```
┌─────────────────────┐     HTTP      ┌─────────────────────┐
│  haos_orchestrator  │◄─────────────►│   haos_elitedate    │
│  port 8000          │               │   port 8600         │
│  (bez Chromium)     │               │   (Selenium)        │
└─────────┬───────────┘               └─────────────────────┘
          │
          │ HTTP
          ▼
┌─────────────────────┐
│    haos_tinder      │
│    port 8601        │
│    port 6080 noVNC  │  ← len pri tinder_headless=false
└─────────────────────┘
```

Komunikácia cez **HA Docker DNS** (názvy služieb, nie `127.0.0.1` medzi add-onmi):

| Odkiaľ | Kam | URL |
|--------|-----|-----|
| Orchestrátor | Elite Date | `http://haos_elitedate:8600` |
| Orchestrátor | Tinder | `http://haos_tinder:8601` |
| Bot add-ony | Orchestrátor | `http://haos_orchestrator:8000` |

---

## Priečinky na HAOS

| Účel | Cesta |
|------|-------|
| Git repozitár (Samba `\\IP\addons\`) | `/addons/haos_orchestrator` |
| Local add-on zdrojáky | `/addons/haos_orchestrator`, `/addons/haos_elitedate`, `/addons/haos_tinder` |
| Trvalé dáta orchestrátora | `/mnt/data/supervisor/addons/data/local_haos_orchestrator/` |
| Trvalé dáta Tinder (profil!) | `/mnt/data/supervisor/addons/data/local_haos_tinder/` |
| Tinder Chrome session | `.../local_haos_tinder/chrome-profile/` |
| Tinder Možnosti (UI) | `.../local_haos_tinder/options.json` |

**Dôležité:** Local add-ony **nie sú git repá**. Po `git pull` v `haos_orchestrator` vždy treba **skopírovať** priečinky do `/addons/haos_*`.

---

## Prvá inštalácia (jednorazovo)

### 1. Klon git repa

```bash
cd /addons
git clone https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka.git haos_orchestrator
cd haos_orchestrator
git checkout cursor/separate-ed-tinder-addons-687c   # kým nie je merged do main
```

### 2. Sync add-onov na disk

```bash
bash /addons/haos_orchestrator/deploy/sync_local_addons.sh
```

### 3. HA UI — nainštaluj add-ony

1. **Obchod doplnkov → ⋮ → Skontrolovať aktualizácie**
2. Nainštaluj a spusti (poradie odporúčané):
   - **HAOS Orchestrator**
   - **HAOS Elite Date Bot** (ak potrebuješ)
   - **HAOS Tinder Bot**

### 4. Orchestrátor — `.env`

Súbor: `/mnt/data/supervisor/addons/data/local_haos_orchestrator/orchestrator/config/.env`

Vzor: `deploy/haos_orchestrator.env.example`

Minimálne pre dating boty:

```env
ELITEDATE_BOT_URL=http://haos_elitedate:8600
TINDER_BOT_URL=http://haos_tinder:8601
HA_URL=http://supervisor/core:8123
DISCORD_WEBHOOK_URL=...
```

Reštart orchestrátora po úprave.

---

## Tinder — prvé prihlásenie (noVNC)

**Nekopíruj Windows/WSL Chrome profil** — na Linux Chromium cookies nedešifruje.

### Automatický postup (odporúčané)

Na HA cez SSH:

```bash
cd /addons/haos_orchestrator

# 1) Režim prihlásenia (headless=false, rebuild, vypíše URL)
bash deploy/tinder_session.sh begin-login 192.168.1.109

# 2) V prehliadači: http://192.168.1.109:6080/vnc.html → telefón + OTP

# 3) Počkaj na úspešný login (health API)
bash deploy/tinder_session.sh wait-login

# 4) Prepnutie do bežnej prevádzky
bash deploy/tinder_session.sh finish-login
```

### Ručný postup (HA UI)

1. **Doplnky → HAOS Tinder Bot → Nastavenia → Možnosti**
   - `tinder_headless` = **false**
   - `orchestrator_url` = `http://haos_orchestrator:8000`
   - **Sieť:** porty `8601` + `6080` → **Uložiť**
2. **Info → ⋮ → Rebuild → Spustiť**
3. Prehliadač: `http://<IP_HA>:6080/vnc.html`
4. Log add-onu: `Login detected, session saved...`
5. **Nastavenia → `tinder_headless` = true → Uložiť → Reštart**

### Overenie

```bash
bash deploy/tinder_session.sh status
curl -s http://127.0.0.1:8601/health
# {"status":"ok","logged_in":true,"session_alive":true}
```

---

## Aktualizácia po `git pull`

Local add-ony **neaktualizujú samy**. Reštart Supervisor-a nestačí.

### Jedn príkaz (sync + rebuild)

```bash
bash /addons/haos_orchestrator/deploy/update_addons.sh
```

Len Tinder:

```bash
bash deploy/update_addons.sh --only tinder
```

Len sync bez rebuildu:

```bash
bash deploy/update_addons.sh --sync-only
```

### Prečo nie „Aktualizovať“ v UI?

Pri **local add-onoch** dialóg Aktualizovať často ukazuje rovnakú verziu (1.1.0 = 1.1.0) aj keď na disku je novší `config.json`. **Rebuild** vždy funguje:

- **UI:** Info → ⋮ → **Rebuild**
- **SSH:** `ha addons rebuild local_haos_tinder`

---

## Čo sa stane pri odinštalovaní

| Akcia | Chrome profil | `.env` / options |
|-------|---------------|------------------|
| Odinštalovať **bez** vymazania dát | **Ostáva** | Ostáva |
| Odinštalovať **s** vymazaním dát | **Zmizne** | Zmizne |

Záloha pred experimentom:

```bash
cp -a /mnt/data/supervisor/addons/data/local_haos_tinder/chrome-profile ~/tinder-chrome-backup
cp /mnt/data/supervisor/addons/data/local_haos_tinder/options.json ~/tinder-options-backup.json
```

---

## Riešenie problémov

### Profil na hoste existuje, kontajner ho nevidí

Log: `WARNING: no Cookies in container`

```bash
docker exec addon_local_haos_tinder ls -la /data/chrome-profile/Default/Network/
docker inspect addon_local_haos_tinder --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

Oprava: **Stop → Rebuild → Start**. Ak nepomôže, `ha supervisor reload` a znova Rebuild.

### Headless zlyhá hneď po noVNC

Príčina: prepnutie na `tinder_headless=true` **pred** riadkom `Login detected` v logu.

Oprava: `bash deploy/tinder_session.sh begin-login` a login znova.

### Session vypršala

```bash
bash deploy/tinder_session.sh begin-login
# noVNC login
bash deploy/tinder_session.sh wait-login
bash deploy/tinder_session.sh finish-login
```

### Port 6080 nefunguje

```bash
docker ps --filter name=tinder --format '{{.Ports}}'
# musí byť: 0.0.0.0:6080->6080/tcp
```

Ak chýba: sync add-onu (verzia ≥ 1.1.0 v config.json) → Supervisor reštart → Rebuild.

---

## Deploy skripty — prehľad

| Skript | Účel |
|--------|------|
| `deploy/sync_local_addons.sh` | `git pull` + `cp` do `/addons/haos_*` |
| `deploy/update_addons.sh` | sync + Rebuild + health check |
| `deploy/tinder_session.sh` | noVNC login workflow |
| `deploy/haos_*.env.example` | vzory `.env` pre jednotlivé add-ony |

Premenné prostredia:

```bash
REPO=/addons/haos_orchestrator
BRANCH=cursor/separate-ed-tinder-addons-687c   # po merge: main
SUPERVISOR_DATA=/mnt/data/supervisor/addons/data
```

---

## Bežná prevádzka Tinder

| Nastavenie | Hodnota |
|------------|---------|
| `tinder_headless` | **true** |
| `poll_enabled` | **true** |
| `orchestrator_url` | `http://haos_orchestrator:8000` |
| Port 6080 | netreba (noVNC sa nespúšťa) |

Discord handoff (1/2/vlastný text) rieši orchestrátor — Tinder bot len posiela správy cez Selenium.

---

## Súvisiace súbory v repozitári

- `tinder_bot/HAOS_LOGIN.md` — skrátený noVNC návod
- `tinder_bot/README.md` — technický popis bota
- `tinder_bot/translations/sk.yaml` — popisy polí v Nastaveniach HA
- `tinder_bot/CHANGELOG.md` — verzie add-onu
