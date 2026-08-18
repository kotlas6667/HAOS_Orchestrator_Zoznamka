# Vynútenie obnovy GitHub Obchodu v HA

Ak po pushi do `main` add-on **neukáže update**, HA ešte nevidí nové `version` v `config.json`
alebo má v cache starý manifest repozitára.

## 1. Skontroluj verziu v repozitári

V `main` musí byť vyššie číslo než nainštalované u teba:

| Add-on | Súbor | Slug |
|--------|-------|------|
| Orchestrátor | `config.json` | `haos_orchestrator` |
| Badoo | `badoo_bot/config.json` | `haos_badoo` |
| Tinder | `tinder_bot/config.json` | `haos_tinder` |
| Elite Date | `elitedate_bot/config.json` | `haos_elitedate` |

Pre audio/Gemini update treba **aspoň**:
- Orchestrátor **1.2.35**
- Badoo **1.1.6**

## 2. Obnov Obchod v HA

1. **Nastavenia → Add-ons → Add-on Obchod**
2. Klikni **tri bodky** (⋮) vpravo hore → **Skontrolovať aktualizácie**
3. Ak nič: odstráň repozitár a pridaj znova:
   - URL: `https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka`
4. Počkaj ~1–2 minúty a znova **Skontrolovať aktualizácie**

## 3. Aktualizuj oba add-ony

Audio + Gemini vyžaduje **obe**:
1. **HAOS Orchestrator** → Aktualizovať → Reštart
2. **HAOS Badoo Bot** → Aktualizovať → Reštart

Len orchestrátor bez Badoo bota nevie vytiahnuť audio z DOM.

## 4. Gemini (voliteľné)

V Nastaveniach orchestrátora:
- **Provider AI návrhov:** `gemini`
- **Gemini API kľúč:** z Google AI Studio
- Reštart orchestrátora

V Discorde pri Badoo vlákne: `6 gemini` alebo `6 gpt` pre nové návrhy.

## 5. Stále nič?

- Add-on → **Info** → over, že **Verzia** sa líši od GitHub `main`
- Supervisor → **Systém** → reštart Supervisor (až potom znova check updates)
- Posledná možnosť: add-on → **Rebuild** (nie len Reštart) po update
