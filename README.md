# HAOS Orchestrator

**AI Assistant for Home Assistant OS** - Natural language control for your smart home and external services.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2024.6+-41BDF5.svg)](https://www.home-assistant.io/)

---

## 🎯 What is HAOS Orchestrator?

HAOS Orchestrator is a **Home Assistant Add-on** that provides:

- **Natural Language Control** - Speak to your smart home: "Turn on the living room lights" or "What's the temperature in the bedroom?"
- **Multi-Service Integration** - Gmail, Google Calendar, Weather, Discord, and AI Chat
- **Deep Home Assistant Integration** - Direct access to all your HA entities, automations, and services
- **Real-time Updates** - WebSocket connection for live state changes
- **Web Dashboard** - Beautiful UI accessible through HA's ingress
- **Discord Bot** - Chat with your assistant directly in Discord
- **AI-Powered Routing** - Uses GPT to understand your intent and route to the right tool

---

## ✨ Features

### 🏠 Home Assistant Integration
- **Entity Control** - Turn on/off, toggle any device
- **State Reading** - Get current state of sensors, switches, lights
- **Service Calls** - Call any Home Assistant service
- **Automation Management** - List and trigger automations
- **Entity Discovery** - Auto-discover all your devices
- **Real-time Updates** - WebSocket connection for live events

### 🌤️ Weather
- Current weather conditions
- Multi-day forecasts
- Hourly predictions
- OpenWeather API support

### 📧 Gmail
- Read emails (unread, inbox, custom queries)
- Send emails
- Email count notifications
- OAuth 2.0 authentication

### 📅 Google Calendar
- Today's events
- Upcoming events
- Event creation
- Event management

### 💬 Discord
- Full bot with conversation history
- Webhook notifications
- User whitelist support
- Custom prefixes and mentions

### 💞 Elite Date (planned integration)
- Selenium-based background bot checks the inbox on a fixed/random interval
- New messages are forwarded to the orchestrator via `POST /api/elitedate/incoming`
- Orchestrator stores the conversation as pending, generates 2 reply options with GPT, and posts them to Discord
- Your Discord reply `1` / `2` is intercepted before normal LLM routing and sent to the local Selenium bot via `POST /send`
- The Selenium process remains the source of truth for login state and actual message delivery

### 📋 TODO
- Task management
- Persistent storage
- Mark tasks as done
- Clear completed tasks

### 🤖 AI Chat
- Natural language understanding
- OpenAI GPT integration
- Conversation history
- Fallback for unknown prompts

---

## 📦 Installation

### As a Home Assistant Add-on

1. **Copy this repository** to your HAOS add-ons directory:
   ```bash
   cd /addons
   git clone https://github.com/your-repo/haos_orchestrator.git haos_orchestrator
   ```

2. **Or copy the folder** `HAOS_Orchestrator` to your add-ons directory

3. **Restart Home Assistant** to discover the new add-on

4. **Install the add-on** through the Supervisor UI:
   - Go to Supervisor → Add-on Store
   - Find "HAOS Orchestrator" in the local add-ons
   - Click "Install"

5. **Configure the add-on**:
   - Set your `HA_TOKEN` (Long-lived access token from HA)
   - Configure other services (OpenAI API, OpenWeather, Discord, Gmail)
   - Enable/disable features as needed

6. **Start the add-on**

7. **Access the dashboard**:
   - Through HA's ingress: `http://your-ha-ip/api/orchestrator/dashboard`
   - Or directly on port 8000

---

## 🚀 Quick Start

### Access the Dashboard
1. Open your browser to `http://your-homeassistant:8000/dashboard`
2. Or through HA ingress at `/api/orchestrator/dashboard`

### Try These Commands

**Home Assistant Control:**
- "Zapni svetlo v obývačke" (Turn on the light in the living room)
- "Vypni klímu" (Turn off the AC)
- "Aká je teplota v spálni?" (What's the temperature in the bedroom?)
- "Ukáž všetky zariadenia" (Show all devices)

**Weather:**
- "Aké je počasie v Bratislave?" (What's the weather in Bratislava?)
- "Predpoveď na 3 dni" (3-day forecast)

**Gmail:**
- "Ukáž neprečítané emaily" (Show unread emails)
- "Pošli email na john@example.com: Ahoj!" (Send email)

**Calendar:**
- "Čo mám dnes?" (What do I have today?)
- "Udalosti tento týždeň" (Events this week)

**General:**
- "Ako sa volá hlavné mesto Slovenska?" (What's the capital of Slovakia?)
- "Akú má dnes meniny?" (Whose name day is it today?)

---

## 🔧 Configuration

Edit your `.env` file or configure through the Add-on UI:

### Required (for Home Assistant)
```env
HA_PROVIDER=real
HA_URL=http://supervisor/core:8123
HA_TOKEN=your_long_lived_access_token
```

### Optional Services

**AI (OpenAI GPT):**
```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
```

**Weather (OpenWeather):**
```env
WEATHER_PROVIDER=openweather
OPENWEATHER_API_KEY=your_openweather_api_key
WEATHER_DEFAULT_CITY=Senica
```

**Discord:**
```env
DISCORD_PROVIDER=discord_webhook
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_USERNAME=HAOS Orchestrator

# For Discord Bot
DISCORD_BOT_ENABLED=true
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_BOT_CHANNEL_ID=your_channel_id
DISCORD_BOT_PREFIX=!
DISCORD_BOT_REQUIRE_MENTION=false
```

**EliteDate:**
```env
ELITEDATE_BOT_URL=http://127.0.0.1:8600
ELITEDATE_AUTO_SEND=false
```

**Gmail:**
```env
GMAIL_PROVIDER=oauth
GMAIL_USER_EMAIL=your@email.com
GMAIL_CREDENTIALS_JSON=/data/orchestrator/config/credentials.json
GMAIL_TOKEN_PICKLE=/data/orchestrator/tokens/token.pickle
```

**Calendar:**
```env
CALENDAR_PROVIDER=oauth
CALENDAR_TOKEN_PICKLE=/data/orchestrator/tokens/token_calendar.pickle
```

---

## 📡 API Endpoints

### Core
- `GET /` - Health check
- `GET /health` - Health status
- `GET /status` - Detailed status
- `GET /dashboard` - Web dashboard

### Prompt Processing
- `POST /api/prompt` - Process natural language prompt

### Home Assistant (HAOS-specific)
- `GET /api/ha/entities` - List all entities (optional: `?domain=light&search=term`)
- `POST /api/ha/entities/{entity_id}` - Control entity (actions: turn_on, turn_off, toggle, call_service, get_state)
- `GET /api/ha/automations` - List automations
- `POST /api/ha/automations/{automation_id}` - Trigger automation
- `GET /api/ha/states` - Get all entity states

### Weather
- `POST /api/weather` - Get weather for city
- `GET /api/weather/hourly?city=...` - Hourly forecast

### Calendar
- `GET /api/calendar/today` - Today's events
- `GET /api/calendar/upcoming?days=7` - Upcoming events

### TODO
- `GET /api/todos` - Get all todos
- `POST /api/todos` - Add todo
- `PATCH /api/todos/{id}` - Toggle todo done status
- `DELETE /api/todos/{id}` - Delete todo

### Messages
- `POST /api/messages` - Send message to Discord

---

## 🎨 Dashboard Features

- **Real-time clock** with Slovak date format
- **Slovak namedays** display
- **Weather mini-card** with hourly forecast
- **Home Assistant connection status**
- **Uptime tracker**
- **Tool cards grid** with status indicators
- **Chat interface** for prompt testing
- **TODO widget** with add/complete/remove
- **Calendar widget** with upcoming events
- **HA Entities widget** showing device states
- **Responsive design** for mobile/tablet

---

## 🤖 Discord Bot

The Discord bot provides the same functionality as the web dashboard:

1. **Enable the bot** in configuration:
   ```env
   DISCORD_BOT_ENABLED=true
   DISCORD_BOT_TOKEN=your_token
   ```

2. **Set up permissions**:
   - Enable `Message Content Intent` in Discord Developer Portal
   - Add bot to your server with appropriate permissions

3. **Usage**:
   - Mention the bot: `@HAOS Orchestrator zapni svetlo`
   - Or use prefix: `!zapni svetlo` (if prefix is set)
   - Or just type in the channel (if prefix is empty)

4. **Features**:
   - Conversation history per user
   - All tools available (HA, Weather, Gmail, Calendar, TODO)
   - Formatted responses for Discord

---

## 📁 Project Structure

```
HAOS_Orchestrator/
├── config.json              # Home Assistant Add-on configuration
├── Dockerfile              # Container build instructions
├── run.sh                  # Add-on entrypoint
├── start.sh                # Development start script
├── requirements.txt        # Python dependencies
├── README.md
├── .env.example
└── app/
    ├── __init__.py
    ├── main.py              # FastAPI application
    ├── config.py           # Settings management
    ├── orchestrator.py     # Main orchestrator class
    ├── router.py           # LLM-based routing
    ├── ha_integration.py   # HAOS-specific integration
    ├── discord_bot.py      # Discord bot client
    ├── schemas.py          # Pydantic models
    ├── tools/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── registry.py
    │   ├── homeassistant_tool.py
    │   ├── homeassistant_provider.py
    │   ├── weather_tool.py
    │   ├── weather_provider.py
    │   ├── gmail_tool.py
    │   ├── gmail_provider.py
    │   ├── calendar_tool.py
    │   ├── calendar_provider.py
    │   ├── messages_tool.py
    │   ├── messages_provider.py
    │   ├── todo_tool.py
    │   ├── chat_tool.py
    │   ├── discord_notifier.py
    │   └── discord_chat.py
    └── templates/
        └── index.html        # Web dashboard
    └── static/
        └── styles.css       # Dashboard styles
```

---

## 🛠️ Development

### Run locally (for development)
```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.\.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Edit .env with your settings
nano .env  # or use any editor

# Start the server
python -m app.main
# or
python start.sh
```

The server will start on `http://localhost:8000`

### Build the Docker image
```bash
docker build -t haos-orchestrator .
docker run -p 8000:8000 haos-orchestrator
```

---

## 🐛 Troubleshooting

### Add-on won't start
- Check the logs in Supervisor
- Verify `HA_URL` and `HA_TOKEN` are set correctly
- Ensure your HA token has sufficient permissions

### Home Assistant connection fails
- Verify the token is valid (create a new long-lived token)
- Check that the URL is correct (in HAOS, it's typically `http://supervisor/core:8123`)
- Ensure the add-on has network access to Home Assistant

### Weather not working
- Set `OPENWEATHER_API_KEY` in configuration
- Verify the API key is valid
- Check that the city name is correct

### Discord bot not responding
- Verify `DISCORD_BOT_TOKEN` is set
- Ensure `Message Content Intent` is enabled
- Check that the bot has been added to the server

### Gmail not working
- Zapni **Google VNC prihlásenie** v HA Nastaveniach → Uložiť → **Reštart**
- Otvor `http://<IP_HA>:6082/vnc.html` (ako pri Tinderi)
- Desktop OAuth JSON: `/data/orchestrator/config/gmailSecret.json`
- Dashboard → **Prihlásiť cez VNC** → v Chromiu dokonči Google účet
- Viac schránok = zopakuj. Potom switch vypni + reštart (tokeny ostanú)

---

## 📄 Gmail / Calendar cez noVNC (multi-account)

Rovnaký model ako Tinder login:

1. [Google Cloud Console](https://console.cloud.google.com/) → zapni **Gmail API** + **Calendar API**
2. OAuth client ID typu **Desktop app** → stiahni JSON →
   `/data/orchestrator/config/gmailSecret.json`
3. HA Nastavenia → **Google VNC prihlásenie** = zapnuté → Uložiť → Reštart
4. Otvor `http://<IP_HA>:6082/vnc.html`
5. Dashboard Orchestrátora → **Prihlásiť cez VNC** (Chromium sa otvorí vo VNC)
6. Prihlás Google účet — stiahnu sa tokeny na maily aj kalendár
7. Ďalší účet = znova krok 5–6. Vypnutie switchu + reštart vypne noVNC.

---

## 📜 License

MIT License - See [LICENSE](LICENSE) file for details.

---

## 🙏 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📞 Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Check the documentation
- Review the configuration examples

---

**Made for Home Assistant OS** ❤️

*HAOS Orchestrator brings AI-powered natural language control to your smart home.*
