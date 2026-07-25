# HAOS Elite Date Bot

Separate Selenium bot for Elite Date. Talks to **HAOS Orchestrator** over HTTP (inbox → Discord drafts → `/send`).

## Full documentation

https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka  
Elite Date notes: https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka/blob/main/elitedate_bot/README.md

## Quick setup

1. Fill `elitedate_email` and `elitedate_password`
2. Set `orchestrator_url` from Orchestrator → **Info → Hostname**  
   Example: `http://{hash}-haos-orchestrator:8000`
3. In Orchestrator Settings set `elitedate_bot_url` to this add-on’s hostname:  
   `http://{hash}-haos-elitedate:8600`
4. Start with `poll_enabled=true` (default)

**Do not** open Elite Date in a normal browser while this bot is running — a second session often kills the Selenium login.

### Optional morning greets

Enable `morning_greet_enabled` for a daily ~07:00 run on new members. Limits: `morning_greet_max_profiles` (sent), `morning_greet_max_opens` (opened).

## Buy me a coffee

Optional tip: https://www.paypal.me/Kotlas6667

## Support

https://github.com/kotlas6667/HAOS_Orchestrator_Zoznamka/issues
