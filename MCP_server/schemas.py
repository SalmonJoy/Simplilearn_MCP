"""The MCP SDK generates wire schemas from the typed tool functions."""

from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Literal

__all__ = ["CallToolResult", "TextContent", "READ", "WRITE"]

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)


class UsageCounts(BaseModel):
    total_calls: int = Field(ge=0)
    successful_calls: int = Field(ge=0)
    failed_calls: int = Field(ge=0)
    cancelled_calls: int = Field(ge=0)
    avg_duration_ms: float = Field(ge=0)


class ToolUsageCounts(UsageCounts):
    tool_name: str


class UsageSummary(UsageCounts):
    by_tool: list[ToolUsageCounts]


class PerformanceCounts(UsageCounts):
    max_duration_ms: float = Field(ge=0)
    success_rate: float | None = Field(ge=0, le=100)
    error_rate: float | None = Field(ge=0, le=100)


class ToolPerformance(PerformanceCounts):
    tool_name: str
    usage_share: float = Field(ge=0, le=100)


class TimelineBucket(BaseModel):
    bucket: datetime
    total_calls: int = Field(ge=0)
    successful_calls: int = Field(ge=0)
    failed_calls: int = Field(ge=0)
    cancelled_calls: int = Field(ge=0)


class ClientUsage(BaseModel):
    client_app: str
    total_calls: int = Field(ge=0)


class UserUsage(BaseModel):
    user_id: str
    total_calls: int = Field(ge=0)


class ErrorUsage(BaseModel):
    error_code: int | str | None
    total_calls: int = Field(ge=0)


class UsageInsights(PerformanceCounts):
    date_from: date
    date_to: date
    granularity: Literal["day", "hour"]
    generated_at: datetime
    tools_called: int = Field(ge=0)
    identified_users: int = Field(ge=0)
    anonymous_calls: int = Field(ge=0)
    by_tool: list[ToolPerformance]
    timeline: list[TimelineBucket]
    by_client: list[ClientUsage]
    by_user: list[UserUsage]
    by_error_code: list[ErrorUsage]


class UsageEvent(BaseModel):
    event_id: str
    tool_name: str
    user_id: str | None = None
    client_app: str
    request_group_id: str | None = None
    started_at: datetime
    completed_at: datetime
    duration_ms: float = Field(ge=0)
    outcome: Literal["success", "error", "cancelled"]
    error_code: int | str | None = None


class UsageEventPage(BaseModel):
    items: list[UsageEvent]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    has_more: bool
