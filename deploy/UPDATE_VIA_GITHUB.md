# Aktualizácia add-onov cez GitHub

Repo: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`

## Správne DNS hostname (dôležité!)

Pri inštalácii z **GitHub Obchodu** HA DNS **nie je** `local-haos-*`.

Hostname = `{repo_hash}-{slug s pomlčkami}`  
Pre toto repo je `repo_hash` = **`8c003d88`**.

| Add-on | URL |
|--------|-----|
| Orchestrátor | `http://8c003d88-haos-orchestrator:8000` |
| Elite Date | `http://8c003d88-haos-elitedate:8600` |
| Tinder | `http://8c003d88-haos-tinder:8601` |

Overenie: v HA otvor add-on → **Info** → pole **Hostname** (má vyzerať ako `8c003d88-haos-elitedate`).

Chyba `No address associated with hostname` pri `local-haos-*` = zlé DNS (tyčí sa lokálny slug namiesto GitHub hashu).

Od verzie Orchestrátor **1.2.5** / ED **1.2.4** / Tinder **1.2.7** sa URL opraví aj samo pri štarte (Supervisor discover + zápis do Nastavení).

## Aktuálne verzie (`main`)

| Add-on | Verzia |
|--------|--------|
| Orchestrátor | **1.2.5** |
| Elite Date | **1.2.4** |
| Tinder | **1.2.7** |

## Okamžitý workaround (bez čakania na update)

**Orchestrátor → Nastavenia:**

- Elite Date URL = `http://8c003d88-haos-elitedate:8600`
- Tinder URL = `http://8c003d88-haos-tinder:8601`

**Elite Date + Tinder → Nastavenia:**

- URL orchestrátora = `http://8c003d88-haos-orchestrator:8000`

Ulož → reštart všetkých troch. V logu orchestrátora:

```
[dating] Elite Date OK @ http://8c003d88-haos-elitedate:8600 …
[dating] Tinder OK @ http://8c003d88-haos-tinder:8601 …
```

## Ako vynútiť novú verziu z Obchodu

1. Soft: Obchod → ⋮ → Skontrolovať aktualizácie → `ha store reload`
2. Tvrdé: Obchod → ⋮ → Repositories → odober repo → pridaj znova → Skontrolovať aktualizácie
3. Núdzové: `git reset --hard origin/main` v `/mnt/data/supervisor/addons/git/<HASH>` + `ha store reload`
