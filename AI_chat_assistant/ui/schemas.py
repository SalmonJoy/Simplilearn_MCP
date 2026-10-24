"""Validate the UI's view of the existing response without changing the API."""

from typing import Any
from pydantic import BaseModel


class ToolTrace(BaseModel):
    tool: str
    arguments: dict[str, Any]
    is_error: bool
    result: Any


class ChatResult(BaseModel):
    answer: str
    trace: list[ToolTrace]
