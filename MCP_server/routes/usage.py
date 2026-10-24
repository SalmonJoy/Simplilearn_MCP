from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from MCP_server.services.usage_service import statistics, insights, events
from MCP_server.schemas import UsageSummary, UsageInsights, UsageEventPage

router = APIRouter(prefix="/usage", tags=["Usage statistics"])


@router.get("/stats", response_model=UsageSummary)
def usage_stats(
    request: Request,
    tool_name: str | None = None,
    user_id: str | None = None,
    client_app: Literal["chat", "dashboard", "unknown"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    if date_to == date.max:
        raise HTTPException(422, "date_to must be before 9999-12-31")
    return statistics(
        request.app.state.database.tool_usage_events,
        tool_name=tool_name,
        user_id=user_id,
        client_app=client_app,
        date_from=date_from,
        date_to=date_to,
    )


def shared_filters(
    tool_name: str | None = None,
    user_id: str | None = None,
    client_app: Literal["chat", "dashboard", "unknown"] | None = None,
    outcome: Literal["success", "error", "cancelled"] | None = None,
    anonymous_only: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
):
    return dict(
        tool_name=tool_name,
        user_id=user_id,
        client_app=client_app,
        outcome=outcome,
        anonymous_only=anonymous_only,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/insights", response_model=UsageInsights)
def usage_insights(
    request: Request,
    filters: dict = Depends(shared_filters),
    granularity: Literal["day", "hour"] = "day",
):
    try:
        return insights(
            request.app.state.database.tool_usage_events,
            granularity=granularity,
            **filters,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.get("/events", response_model=UsageEventPage)
def usage_events(
    request: Request,
    filters: dict = Depends(shared_filters),
    request_group_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    order: Literal["newest", "oldest"] = "newest",
):
    try:
        return events(
            request.app.state.database.tool_usage_events,
            request_group_id=request_group_id,
            limit=limit,
            offset=offset,
            order=order,
            **filters,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
