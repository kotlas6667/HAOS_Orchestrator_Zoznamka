# Aktualizácia add-onov cez GitHub (jediný podporovaný spôsob)

Repo:

`https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`

| Add-on | Cesta v gite | Očakávaná verzia (`main`) |
|--------|--------------|---------------------------|
| HAOS Orchestrator | `config.json` (koreň) | **1.2.4** |
| HAOS Elite Date Bot | `elitedate_bot/` | **1.2.3** |
| HAOS Tinder Bot | `tinder_bot/` | **1.2.6** |

Po štarte orchestrátora **musí** byť v logu:

```
[orchestrator] image version=1.2.4
[orchestrator] DNS fix … → http://local-haos-elitedate:8600
[dating] configured URLs: …
```

Ak stále vidíš `ELITEDATE_BOT_URL=http://haos_elitedate:8600` **bez** `image version=`,
beží starý image.

---

## 1) Soft refresh (skús najprv)

**UI:** Nastavenia → Doplnky → **Obchod doplnkov** → ⋮ → **Skontrolovať aktualizácie**
(alebo **Reload** / Obnoviť) → počkaj → pull-to-refresh stránky.

**SSH:**

```bash
ha store reload
ha apps reload
```

Potom znova otvor Informácie add-onu — „Dostupná verzia“ sa má zmeniť.

---

## 2) Tvrdý refresh (keď soft nestačí) — odporúčané

Supervízor má Git cache repa, ktoré sa niekedy „zasekne“. **Add-ony neodinstaluj** — len repo:

### A) UI

1. Nastavenia → Doplnky → Obchod doplnkov → ⋮ → **Repositories**
2. Nájdi `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`
3. **Odober** (Remove) — nainštalované add-ony ostanú
4. **Pridaj znova** rovnakú URL
5. ⋮ → **Skontrolovať aktualizácie**
6. Obnov stránku → otvor Orchestrátor → má ponúknuť **1.2.4**

### B) SSH (to isté)

```bash
# vypíš store / slug repa
ha store list

# nájdi riadok s HAOS_Orchestrator_Zoznamka (slug = hash, napr. ab12cd34)
ha store delete <SLUG_REPA>

# znova pridaj
ha store add https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka

ha store reload
```

Overenie:

```bash
# v git cache Supervisora — verzia z config.json musí byť 1.2.4
find /mnt/data/supervisor/addons/git -name config.json 2>/dev/null \
  | xargs grep -l haos_orchestrator 2>/dev/null \
  | head xargs grep '"version"'
```

Ak stále stará verzia, nútene pretiahni git (cestu nahraď svojou z `find`):

```bash
REPO_DIR=$(find /mnt/data/supervisor/addons/git -maxdepth 2 -type d -name .git \
  -exec grep -l HAOS_Orchestrator_Zoznamka {}/config 2>/dev/null \; \
  -printf '%h\n' | head -1)
# jednoduchší variant — prejdi adresáre a hľadaj:
ls /mnt/data/supervisor/addons/git
# potom:
cd /mnt/data/supervisor/addons/git/<HASH>
git fetch --all
git reset --hard origin/main
ha store reload
```

---

## 3) Kým store nejde — workaround bez novej verzie

Orchestrátor → **Nastavenia → Možnosti** manuálne:

- `elitedate_bot_url` = `http://local-haos-elitedate:8600`
- `tinder_bot_url` = `http://local-haos-tinder:8601`

Ulož → Reštart. DNS bude OK aj na starom image; nový image (1.2.4) to navyše opraví sám a napíše do logu `image version=`.

---

## Overenie po aktualizácii

| Add-on | Nainštalovaná |
|--------|----------------|
| Orchestrator | **1.2.4** |
| Elite Date | **1.2.3** |
| Tinder | **1.2.6** |

DNS medzi add-onmi: vždy `local-haos-*` (nie `haos_*` bez `local-`).
