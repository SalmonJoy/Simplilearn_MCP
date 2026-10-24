"""Read-only analytics API tests use a local in-memory collection."""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from MCP_server import database as mcp_database
from MCP_server.main import create_app


@pytest.fixture
def usage_records(database):
    day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = [
        ("a", "success", 10, "alice", "chat", "g1", day, None),
        ("a", "success", 30, "alice", "chat", "g1", day + timedelta(hours=1), None),
        ("a", "error", 50, "bob", "dashboard", "g2", day + timedelta(hours=2), 503),
        (
            "b",
            "success",
            110,
            None,
            "unknown",
            None,
            day + timedelta(hours=23, minutes=59, seconds=59),
            None,
        ),
        (
            "unknown_tool",
            "error",
            0,
            None,
            "unknown",
            "g3",
            day + timedelta(hours=3),
            None,
        ),
        (
            "memory_get_preferences",
            "cancelled",
            20,
            "alice",
            "dashboard",
            "g2",
            day + timedelta(hours=4),
            None,
        ),
        ("a", "success", 200, "alice", "chat", "g4", day - timedelta(seconds=1), None),
        ("b", "error", 70, "charlie", "chat", "g5", day + timedelta(days=1), 422),
    ]
    for index, (
        tool,
        outcome,
        duration,
        user,
        source,
        group,
        started,
        code,
    ) in enumerate(rows):
        database.tool_usage_events.insert_one(
            {
                "_id": f"EVT{index:03}",
                "tool_name": tool,
                "outcome": outcome,
                "duration_ms": duration,
                "user_id": user,
                "client_app": source,
                "request_group_id": group,
                "started_at": started,
                "completed_at": datetime.now(timezone.utc),
                "error_code": code,
            }
        )
    return database, day.date()


@pytest.fixture
def usage_api(usage_records, monkeypatch):
    database, _ = usage_records
    monkeypatch.setattr(mcp_database, "connect", lambda: (database.client, database))
    with TestClient(create_app()) as client:
        yield client


def today_filters(usage_records):
    _, day = usage_records
    return {"date_from": day.isoformat(), "date_to": day.isoformat()}


def test_insights_complete_aggregates_weighted_means_and_breakdowns(
    usage_api, usage_records
):
    result = usage_api.get("/usage/insights", params=today_filters(usage_records))
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["total_calls"] == 6 and data["successful_calls"] == 3
    assert data["failed_calls"] == 2 and data["cancelled_calls"] == 1
    assert data["avg_duration_ms"] == 36.67 and data["max_duration_ms"] == 110
    assert data["success_rate"] == 50 and data["error_rate"] == 33.33
    assert data["tools_called"] == 4 and data["identified_users"] == 2
    assert data["anonymous_calls"] == 2
    a = next(row for row in data["by_tool"] if row["tool_name"] == "a")
    assert (
        a["total_calls"] == 3 and a["avg_duration_ms"] == 30 and a["usage_share"] == 50
    )
    assert data["by_user"] == [
        {"user_id": "alice", "total_calls": 3},
        {"user_id": "bob", "total_calls": 1},
    ]
    assert {row["client_app"]: row["total_calls"] for row in data["by_client"]} == {
        "chat": 2,
        "dashboard": 2,
        "unknown": 2,
    }
    assert {
        str(row["error_code"]): row["total_calls"] for row in data["by_error_code"]
    } == {"503": 1, "None": 1}


def test_timeline_zero_fill_hour_and_day_boundaries(usage_api, usage_records):
    hourly = usage_api.get(
        "/usage/insights",
        params={**today_filters(usage_records), "granularity": "hour"},
    ).json()
    assert len(hourly["timeline"]) == 24
    assert hourly["timeline"][0]["successful_calls"] == 1
    assert hourly["timeline"][5]["total_calls"] == 0
    assert hourly["timeline"][23]["total_calls"] == 1
    assert sum(row["total_calls"] for row in hourly["timeline"]) == 6
    _, day = usage_records
    daily = usage_api.get(
        "/usage/insights",
        params={
            "date_from": (day - timedelta(days=2)).isoformat(),
            "date_to": day.isoformat(),
        },
    ).json()
    assert len(daily["timeline"]) == 3
    assert [row["total_calls"] for row in daily["timeline"]] == [0, 1, 6]
    assert daily["avg_duration_ms"] == 60  # weighted by calls, not tool averages


@pytest.mark.parametrize(
    "filters,total",
    [
        ({"tool_name": "a"}, 3),
        ({"user_id": "alice"}, 3),
        ({"client_app": "dashboard"}, 2),
        ({"outcome": "error"}, 2),
        ({"anonymous_only": True}, 2),
        ({"tool_name": ".*"}, 0),
    ],
)
def test_insight_filters_are_exact_and_shared(usage_api, usage_records, filters, total):
    params = {**today_filters(usage_records), **filters}
    data = usage_api.get("/usage/insights", params=params).json()
    page = usage_api.get("/usage/events", params=params).json()
    assert data["total_calls"] == page["total"] == total


def test_event_projection_pagination_stable_order_and_group_lookup(
    usage_api, usage_records
):
    db, _ = usage_records
    db.tool_usage_events.update_one(
        {"_id": "EVT000"},
        {"$set": {"arguments": {"secret": "not public"}, "result": "not public"}},
    )
    params = {**today_filters(usage_records), "limit": 2}
    first = usage_api.get("/usage/events", params=params).json()
    second = usage_api.get("/usage/events", params={**params, "offset": 2}).json()
    assert first["total"] == 6 and first["has_more"] and len(first["items"]) == 2
    assert not (
        {row["event_id"] for row in first["items"]}
        & {row["event_id"] for row in second["items"]}
    )
    group = usage_api.get(
        "/usage/events", params={"request_group_id": "g2", "order": "oldest"}
    ).json()
    assert [row["event_id"] for row in group["items"]] == ["EVT002", "EVT005"]
    assert "secret" not in usage_api.get("/usage/events").text
    assert all("arguments" not in row and "result" not in row for row in group["items"])
    empty = usage_api.get("/usage/events", params={"offset": 100}).json()
    assert empty["items"] == [] and not empty["has_more"]


def test_empty_insights_have_no_fabricated_rates(usage_api, usage_records):
    data = usage_api.get(
        "/usage/insights", params={**today_filters(usage_records), "user_id": "nobody"}
    ).json()
    assert data["total_calls"] == 0 and data["avg_duration_ms"] == 0
    assert data["success_rate"] is None and data["error_rate"] is None
    assert data["by_tool"] == data["by_user"] == data["by_error_code"] == []
    assert data["timeline"][0]["total_calls"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "date_from=2026-10-25&date_to=2026-10-24",
        "anonymous_only=true&user_id=alice",
        "client_app=invalid",
        "outcome=invalid",
        "date_to=9999-12-31",
    ],
)
def test_invalid_shared_filters(usage_api, query):
    assert usage_api.get("/usage/insights?" + query).status_code == 422
    assert usage_api.get("/usage/events?" + query).status_code == 422


def test_bounds_compatibility_indexes_and_no_self_recording(usage_api, usage_records):
    db, _ = usage_records
    before = db.tool_usage_events.count_documents({})
    assert usage_api.get("/usage/insights?granularity=minute").status_code == 422
    assert (
        usage_api.get(
            "/usage/insights?date_from=2020-01-01&date_to=2021-01-01"
        ).status_code
        == 422
    )
    assert usage_api.get("/usage/events?limit=101").status_code == 422
    assert usage_api.get("/usage/events?offset=-1").status_code == 422
    assert usage_api.get("/usage/events?order=invalid").status_code == 422
    old = usage_api.get("/usage/stats").json()
    assert set(old) == {
        "total_calls",
        "successful_calls",
        "failed_calls",
        "cancelled_calls",
        "avg_duration_ms",
        "by_tool",
    }
    assert old["total_calls"] == 8 and old["avg_duration_ms"] == 61.25
    assert db.tool_usage_events.count_documents({}) == before
    indexes = db.tool_usage_events.index_information()
    assert "started_at_-1__id_-1" in indexes
    assert "request_group_id_1_started_at_1__id_1" in indexes


def test_top_users_does_not_truncate_distinct_user_count(usage_api, usage_records):
    db, _ = usage_records
    sample = db.tool_usage_events.find_one({"_id": "EVT000"})
    for index in range(15):
        db.tool_usage_events.insert_one(
            {**sample, "_id": f"USER{index:03}", "user_id": f"user{index:03}"}
        )
    data = usage_api.get("/usage/insights", params=today_filters(usage_records)).json()
    assert len(data["by_user"]) == 10 and data["identified_users"] == 17
    assert data["anonymous_calls"] == 2
    assert data["by_user"][0] == {"user_id": "alice", "total_calls": 3}


def test_earliest_date_does_not_underflow_default_window(usage_api):
    response = usage_api.get("/usage/insights?date_to=0001-01-01")
    assert response.status_code == 200
    assert response.json()["date_from"] == "0001-01-01"
    assert len(response.json()["timeline"]) == 1
