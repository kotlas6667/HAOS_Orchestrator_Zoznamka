from app.tools.base import Tool
from app.tools.calendar_tool import CalendarTool
from app.tools.chat_tool import ChatTool
from app.tools.gmail_tool import GmailTool
from app.tools.homeassistant_tool import HomeAssistantTool
from app.tools.messages_tool import MessagesTool
from app.tools.todo_tool import TodoTool
from app.tools.weather_tool import WeatherTool


def build_tool_registry() -> dict[str, Tool]:
    tools: list[Tool] = [
        CalendarTool(),
        GmailTool(),
        HomeAssistantTool(),
        MessagesTool(),
        TodoTool(),
        WeatherTool(),
        ChatTool(),
    ]
    return {tool.name: tool for tool in tools}
