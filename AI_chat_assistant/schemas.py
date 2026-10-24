from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from HRMS.schemas import Identifier


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=40)
    user_id: Identifier | None = None


class ChatResponse(BaseModel):
    answer: str
    trace: list[dict]
