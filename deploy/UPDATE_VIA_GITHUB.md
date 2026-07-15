# Aktualizácia add-onov cez GitHub (jediný podporovaný spôsob)

Add-ony sú v Obchode Home Assistant z repozitára:

`https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`

| Add-on | Cesta v gite | Očakávaná verzia (aktuálny `main`) |
|--------|--------------|-------------------------------------|
| HAOS Orchestrator | `config.json` (koreň) | **1.2.4** |
| HAOS Elite Date Bot | `elitedate_bot/` | **1.2.3** |
| HAOS Tinder Bot | `tinder_bot/` | **1.2.6** |

Po štarte orchestrátora **musí** byť v logu:

```
[orchestrator] image version=1.2.4
[orchestrator] DNS fix ELITEDATE_BOT_URL: … → http://local-haos-elitedate:8600
[dating] Elite Date …
```

Ak vidíš stále `ELITEDATE_BOT_URL=http://haos_elitedate:8600` **bez** riadku `image version=`,
beží ešte starý image — Obchod neaktualizoval (⋮ → Skontrolovať aktualizácie → Aktualizovať).

## Prečo UI neponúka aktualizáciu

Obchod **neťahá GitHub pri každom otvorení stránky**. Cache môže byť stará
niekoľko hodín (v UI: „Aktualizovať pred X hodinami“).

Ak máš na Tinderi nainštalované **1.2.4** a „Dostupná verzia“ je stále **1.2.4**,
store ešte nemal refresh — na GitHube medzičasom už je **1.2.6**.

**Netreba čakať dni** — stačí vynútiť obnovu obchodu.

## Postup (UI — odporúčané)

1. Home Assistant → **Nastavenia → Doplnky → Obchod doplnkov**
2. Vpravo hore **⋮ (tri bodky) → Skontrolovať aktualizácie** / Check for updates
3. Počkaj kým dobehne (pár desiatok sekúnd)
4. **Obnov stránku** v prehliadači (pull-to-refresh / F5)
5. Otvor **HAOS Tinder Bot → Informácie**
   - **Dostupná verzia** má byť **1.2.6**
   - Tlačidlo **Aktualizovať** má byť aktívne → klepni ho
6. To isté pre **Elite Date** (→ **1.2.3**) a **Orchestrator** (→ **1.2.3**)

Ak po refreshi stále „Aktuálne“ na starej verzii:

1. **Nastavenia → Systém → Opraviť** (alebo reštart Supervisora)
2. Znova **Obchod → ⋮ → Skontrolovať aktualizácie**
3. SSH (voliteľné):
   ```bash
   ha apps reload
   # alebo staršie: ha supervisor reload
   ha store reload
   ```

## Overenie po aktualizácii

V Informáciách add-onu:

- Tinder: nainštalovaná **1.2.6**
- Elite Date: **1.2.3**
- Orchestrator: **1.2.3**

V logu orchestrátora:

```
DNS fix … → http://local-haos-…
[dating] Elite Date OK …
[dating] Tinder OK …
```

## DNS hostname (stále platí)

Medzi add-onmi používaj:

- `http://local-haos-orchestrator:8000`
- `http://local-haos-elitedate:8600`
- `http://local-haos-tinder:8601`

(nie staré `haos_orchestrator` / `haos_tinder` bez `local-`)

## Poznámka k CLI

`ha apps rebuild local_haos_*` funguje **len** pre Local add-ony v `/addons`.
Pri inštalácii z GitHub Obchodu máš iný slug (hash + `haos_tinder`) —
`local_haos_*` teda „does not exist“. Pri GitHub flow stačí **Aktualizovať** v UI.
