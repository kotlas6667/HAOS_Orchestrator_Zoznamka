# Tinder bot — návod na spustenie a obnovu

Tento bot (samostatný proces, `tinder_bot/`) drží prihlásenú Selenium session
na Tinderi, sleduje nové správy a odosiela vybrané odpovede. Komunikuje s
hlavným orchestrátorom cez HTTP (`ORCHESTRATOR_URL` / `TINDER_BOT_URL`), presne
ako `elitedate_bot/`.

## Prvé spustenie (manuálne prihlásenie)

Tinder sa väčšinou neprihlasuje heslom, ale telefónom+OTP alebo cez
Google/Facebook/Apple — to sa nedá spoľahlivo automatizovať. Preto:

1. V `.env` nastav `TINDER_HEADLESS=false` a `TINDER_USER_DATA_DIR` na priečinok,
   kam sa uloží prihlásený profil (už je predpripravené v `.env`).
2. Spusti bota ručne:
   ```
   python -m tinder_bot.main
   ```
3. Otvorí sa viditeľné okno Chrome. V ňom sa prihlás na Tinder presne tak, ako
   by si to urobil na telefóne/PC (OTP kód, Google, atď.).
4. Bot čaká až 10 minút na prihlásenie (pozri konzolu — vypíše
   `[tinder_bot] No saved session found...`). Po úspešnom prihlásení vypíše
   `[tinder_bot] Login detected, session saved...` a spustí sa normálne
   (poll loop + lokálny server na `TINDER_BOT_PORT`, default 8601).
5. Session sa uložila do `TINDER_USER_DATA_DIR` (priečinok s Chrome profilom).
   Odteraz už nie je potrebné prihlasovať sa znova — ani po reštarte, ani v
   headless režime.
6. Keď je session overená, môžeš v `.env` prepnúť späť na
   `TINDER_HEADLESS=true` pre bežnú prevádzku na pozadí.

## Bežné spustenie (po prvom prihlásení)

```
python -m tinder_bot.main
```

Bez GUI okna (headless), bot sa prihlási automaticky pomocou uloženej session
v `TINDER_USER_DATA_DIR` a začne pollovať nové správy (`TINDER_POLL_INTERVAL_MIN_SEC`
/ `TINDER_POLL_INTERVAL_MAX_SEC`, default 90–180s).

Zdravie bota over na: `http://127.0.0.1:8601/health` (vráti
`{"status": "ok", "logged_in": true}` keď je prihlásený).

Na Home Assistant add-one (Docker) sa spúšťa automaticky cez `run.sh`, pokiaľ
je `TINDER_BOT_ENABLED=true` (default). Nastavením `TINDER_BOT_ENABLED=false`
sa bot v kontajneri nespustí.

## Zadné vrátka — čo robiť keď sa niečo pokazí

**Session/token vypršal alebo Tinder vyžaduje nové prihlásenie** (bot hlási
chyby pri `check_new_messages`/`/send`, alebo `/health` vracia
`logged_in: false` a nezotaví sa):

1. Zastav bota (Ctrl+C, alebo v Dockeri príslušný proces/add-on restart).
2. V `.env` prepni `TINDER_HEADLESS=false`.
3. Spusti znova `python -m tinder_bot.main` — otvorí sa viditeľné okno, kde sa
   znova prihlásiš ručne (rovnaký postup ako "Prvé spustenie" vyššie).
   Existujúci `TINDER_USER_DATA_DIR` sa prepíše novou platnou session.
4. Po úspešnom prihlásení prepni `TINDER_HEADLESS` späť na `true`.

**Úplný reset (profil je poškodený / chceš sa prihlásiť iným účtom):**

- Vymaž priečinok `TINDER_USER_DATA_DIR` (v `.env` nastavený na
  `tinder_bot/chrome-profile` resp. cestu, ktorú si zadal).
- Spusti znova s `TINDER_HEADLESS=false` — bot sa zachová ako pri prvom
  spustení a založí nový profil.

**Bot spadne / Chrome crashuje opakovane (Docker/Pi):**

- `run.sh` má vlastný supervízor — automaticky restartuje `tinder_bot` (max 5×
  za 10 minút), potom sa vzdá a treba to vyriešiť ručne (pozri logy add-onu,
  hľadaj prefix `[tinder_bot]`).

**Chceš bota úplne vypnúť bez zásahu do kódu:**

- Lokálne: bota jednoducho nepúšťaj (`python -m tinder_bot.main`).
- V Dockeri/HA add-one: `TINDER_BOT_ENABLED=false` v `.env`.

## Kde čo je (rýchly prehľad env premenných)

| Premenná | Účel |
|---|---|
| `TINDER_EMAIL` / `TINDER_PASSWORD` / `TINDER_PHONE` | Prihlasovacie údaje — vyplň len ak ich reálne používaš (email+heslo login je na Tinderi zriedkavý) |
| `TINDER_USER_DATA_DIR` | Priečinok s trvalým Chrome profilom = uložená prihlásená session |
| `TINDER_HEADLESS` | `false` pre ručné prihlásenie / debug, `true` pre bežnú prevádzku |
| `TINDER_BOT_HOST` / `TINDER_BOT_PORT` | Kde beží lokálny HTTP server bota (orchestrátor naň volá `/send`) |
| `ORCHESTRATOR_URL` | Kde beží hlavný orchestrátor (bot naň volá `/api/tinder/incoming`) |
| `TINDER_AUTO_SEND` | `true` = vybraná odpoveď sa v Tinderi aj reálne odošle; `false` = len sa vloží do textového poľa |
| `TINDER_BOT_ENABLED` | Docker/HA add-on: či sa bot spúšťa automaticky (`run.sh`) |

Selektory v `tinder_client.py` sú placeholder — ak Tinder zmení svoje UI a bot
prestane nachádzať konverzácie/vstupné pole, treba ich prekontrolovať cez
DevTools (F12) a opraviť v tomto súbore.
