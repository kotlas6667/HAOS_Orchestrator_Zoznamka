# HAOS Tinder Bot

Separate Selenium bot for Tinder web. Talks to **HAOS Orchestrator** over HTTP (inbox → Discord drafts → `/send`).

## Full documentation

https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka  
Tinder notes: https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka/blob/main/tinder_bot/README.md  
First login: https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka/blob/main/tinder_bot/HAOS_LOGIN.md

## First login (noVNC)

1. Set `tinder_headless=false` → Save → Start
2. Open `http://<HA_IP>:6080/vnc.html`
3. Log in with **phone + OTP** (do not copy a Windows Chrome profile)
4. Wait for login/session saved in the log
5. Set `tinder_headless=true` → Save → Restart

Set `orchestrator_url` from Orchestrator → **Info → Hostname**.  
In Orchestrator set `tinder_bot_url` to this add-on’s hostname (`:8601`).

**Do not** use Tinder in a normal browser while the bot is running.

## Buy me a coffee

Optional tip: https://www.paypal.me/Kotlas6667

## Support

https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka/issues
