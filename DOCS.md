# HAOS Orchestrator

AI orchestrator for Home Assistant — natural-language control of smart home, Gmail/Calendar, weather, Discord, TODO, and optional dating bots.

**This add-on is not a built-in voice assistant.** It has no STT/TTS. Optional Assist integration can send text to `/api/voice`; audio is handled by Home Assistant Assist outside this add-on.

## Full documentation

Public GitHub (install guide, all options, known issues):

https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka

## Related add-ons (same store repository)

| Add-on | Port |
|--------|------|
| **HAOS Orchestrator** (this one) | `8000`, Google noVNC `6082` |
| **HAOS Elite Date Bot** | `8600` |
| **HAOS Tinder Bot** | `8601`, Tinder noVNC `6080` |
| **HAOS Badoo Bot** | `8602`, Badoo noVNC `6081` |

## Quick setup

1. Set at least `openai_api_key` and `ha_token`
2. Optional: Discord bot/webhook, OpenWeather key, peer bot URLs
3. Start → open the **Orchestrator** panel (ingress) or `http://<HA_IP>:8000/`

### Peer DNS (GitHub store)

Use **Info → Hostname** for each add-on, e.g. `http://{hash}-haos-elitedate:8600`.  
Do **not** use `local-haos-*` or bare `haos_*` on GitHub-store installs.

### Google Gmail + Calendar

1. Desktop OAuth JSON → `/data/orchestrator/config/gmailSecret.json`
2. Enable **Google VNC login** → Save → Restart
3. Open `http://<HA_IP>:6082/vnc.html` → dashboard **Sign in via VNC**

## Buy me a coffee

Optional tip if this project helped you:

https://www.paypal.me/Kotlas6667

## Support

- Issues: https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka/issues
- Updates: https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka/blob/main/deploy/UPDATE_VIA_GITHUB.md
