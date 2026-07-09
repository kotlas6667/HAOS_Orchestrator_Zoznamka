from typing import Any

from pydantic import BaseModel, Field


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)


class ToolExecution(BaseModel):
    tool: str
    reason: str
    result: dict[str, Any]


class PromptResponse(BaseModel):
    route: str
    summary: str
    executions: list[ToolExecution]


class WeatherRequest(BaseModel):
    city: str = Field(min_length=1, max_length=120)


class WeatherResponse(BaseModel):
    result: dict[str, Any]


class MessageRequest(BaseModel):
    destination: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    result: dict[str, Any]
