# Aktualizácia add-onov cez GitHub

Repo: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`

## Správne DNS hostname (dôležité!)

Pri inštalácii z **GitHub Obchodu** HA DNS **nie je** `local-haos-*` ani holý `haos_*`.

Hostname = `{repo_hash}-{slug s pomlčkami}`

`repo_hash` = prvých 8 znakov SHA1 z **presnej** URL, ktorú si pridal do Obchodu.
Rôzne tvary (`.git`, trailing `/`, …) = **iný hash**. Preto vždy ber hodnotu z HA:

**Add-on → Info → Hostname** (napr. `03146090-haos-elitedate` alebo `8c003d88-haos-elitedate`).

| Add-on | URL |
|--------|-----|
| Orchestrátor | `http://{hash}-haos-orchestrator:8000` |
| Elite Date | `http://{hash}-haos-elitedate:8600` |
| Tinder | `http://{hash}-haos-tinder:8601` |

Od Orchestrátor **1.2.9** / ED **1.2.8** / Tinder **1.2.11** sa peer URL berie zo **Supervisor** (skutočný nainštalovaný slug) — hardcoded hash v defaultoch sa opraví pri štarte.

## Aktuálne verzie (`main`)

| Add-on | Verzia |
|--------|--------|
| Orchestrátor | **1.2.36** |
| Elite Date | **1.3.17** |
| Tinder | **1.2.20** |
| Badoo | **1.1.6** |

## Súbeh s webom (Elite Date / Tinder)

**Neotváraj** Elite Date / Tinder vo webovom prehliadači naraz so zapnutým botom.
Server často vyhodí druhú session → Selenium stratí login a poller neuvidí nové správy.

Ak chceš ísť na web ručne: najprv **zastav** príslušný bot add-on, potom znova spusti.

## Okamžitý workaround

Do Nastavení daj Hostname z **Info** (nie tip z dokumentácie, ak sa líši). Ulož → reštart všetkých troch.

## Ako vynútiť novú verziu z Obchodu

Pozri `deploy/FORCE_STORE_REFRESH.md` (odobrať/pridať repo, `ha store reload`).
