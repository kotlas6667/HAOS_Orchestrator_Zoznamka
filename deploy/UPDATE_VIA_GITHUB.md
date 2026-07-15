# Aktualizácia add-onov cez GitHub

Repo: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`

## DNS medzi add-onmi — automaticky

**Nenastavuj ručne žiadne `local-haos-*` ani hashe typu `8c003d88-…`.**

V Nastaveniach nechaj polia URL **prázdne**. Pri štarte si každý add-on
spýta Supervisor (`GET /addons`) a doplní správny hostname peer add-onu
(v závislosti od toho, či bežíš z Obchodu alebo lokálne).

Po štarte v logu orchestrátora:

```
[orchestrator/ed] supervisor discover: (empty) → http://…-haos-elitedate:8600
[orchestrator/tinder] supervisor discover: (empty) → http://…-haos-tinder:8601
[dating] Elite Date OK …
[dating] Tinder OK …
```

Ak discovery zlyhá: peer add-on nie je nainštalovaný / beží, alebo chýba
`hassio_api`. Vtedy výnimka: Info peer add-onu → **Hostname** → doplň do URL.

## Aktuálne verzie (`main`)

| Add-on | Verzia |
|--------|--------|
| Orchestrátor | **1.2.6** |
| Elite Date | **1.2.5** |
| Tinder | **1.2.8** |

## Ako vynútiť update z Obchodu

1. Obchod → ⋮ → Skontrolovať aktualizácie / `ha store reload`
2. Ak nepomôže: Repositories → odober repo → pridaj znova → Skontrolovať aktualizácie
