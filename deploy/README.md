# Deploy skripty (HAOS)

Spúšťaj **na Home Assistant hoste cez SSH** (nie na Windows dev PC).

| Skript | Príkaz |
|--------|--------|
| **Kompletný návod** | [`HAOS_DEPLOY.md`](HAOS_DEPLOY.md) |
| Sync git → `/addons/*` | `bash deploy/sync_local_addons.sh` |
| Sync + Rebuild + check | `bash deploy/update_addons.sh` |
| Tinder noVNC workflow | `bash deploy/tinder_session.sh status` |

Rýchla aktualizácia po zmene kódu:

```bash
cd /addons/haos_orchestrator && git pull
bash deploy/update_addons.sh --only tinder
```

Prvé Tinder prihlásenie:

```bash
bash deploy/tinder_session.sh begin-login 192.168.1.109
# → noVNC v prehliadači
bash deploy/tinder_session.sh wait-login
bash deploy/tinder_session.sh finish-login
```

Vzory `.env`: `haos_orchestrator.env.example`, `haos_elitedate.env.example`, `haos_tinder.env.example`.
