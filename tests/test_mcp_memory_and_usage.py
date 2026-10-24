"""MCP transport, storage and host tests; no external database or Cloud calls."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import ConnectionFailure
from starlette.datastructures import Headers
from test_mcp_and_ai import connect, mcp_url as mcp_url
from ai_runtime import READ_TOOLS, call_tool, mcp_connection
from AI_chat_assistant.schemas import ChatRequest
from AI_chat_assistant.services import chat_service
from AI_dashboard_generation.services import dashboard_service
from MCP_server import database as mcp_database
from MCP_server import usage_middleware as telemetry
from MCP_server.main import create_app
from MCP_server.services import preference_service, usage_service
from MCP_server.tools import business_tools


async def test_memory_transport_identity_validation_and_dedicated_storage(
    mcp_url, seeded
):
    async with connect(mcp_url, user_id="alice", client_app="chat") as (session, tools):
        assert len(tools) == 13 and len(READ_TOOLS) == 7
        assert tools["memory_get_preferences"].input_schema.get("properties", {}) == {}
        assert (
            "user_id" not in tools["memory_set_preference"].input_schema["properties"]
        )
        empty, error = await call_tool(session, tools, "memory_get_preferences", {})
        assert not error and empty["preferences"] == {"chat": {}, "dashboard": {}}
        saved, error = await call_tool(
            session,
            tools,
            "memory_set_preference",
            {"scope": "chat", "key": "response_style", "value": "  concise  "},
        )
        assert not error and saved["saved"] and saved["value"] == "concise"
        for arguments in [
            {"scope": "chat", "key": "$bad", "value": "x"},
            {"scope": "chat", "key": "bad.key", "value": "x"},
            {"scope": "system", "key": "style", "value": "x"},
            {"scope": "chat", "key": "style", "value": " "},
            {"scope": "chat", "key": "style", "value": "x" * 1001},
            {"scope": "chat", "key": "style", "value": "x", "user_id": "bob"},
        ]:
            result = await session.call_tool("memory_set_preference", arguments)
            assert result.is_error and result.structured_content["code"] == 422
    async with connect(mcp_url, user_id="bob") as (session, tools):
        data, error = await call_tool(session, tools, "memory_get_preferences", {})
        assert not error and data["preferences"]["chat"] == {}
    async with connect(mcp_url) as (session, tools):
        data, error = await call_tool(session, tools, "memory_get_preferences", {})
        assert error and data["code"] == 422
    assert seeded.user_preferences.count_documents({}) == 1
    assert (
        seeded.user_preferences.find_one({"_id": "alice"})["preferences"]["chat"][
            "response_style"
        ]
        == "concise"
    )
    assert seeded.employees.count_documents({}) == 30


async def test_tool_events_cover_failures_and_composite_once(mcp_url, seeded):
    async with connect(mcp_url, user_id="alice", client_app="chat") as (session, tools):
        assert seeded.tool_usage_events.count_documents({}) == 0  # init/list excluded
        await session.call_tool("hrms_get_employee", {"employee_id": "EMP001"})
        await session.call_tool("hrms_get_employee", {"employee_id": "MISSING"})
        await session.call_tool("inventory_list_items", {"limit": 101})
        await session.call_tool("unknown_tool", {})
        await session.call_tool("inventory_get_item_owners", {"item_type": "laptop"})
    events = list(seeded.tool_usage_events.find())
    assert len(events) == 5
    assert [event["outcome"] for event in events] == [
        "success",
        "error",
        "error",
        "error",
        "success",
    ]
    assert events[1]["error_code"] == 404
    assert len({event["request_group_id"] for event in events}) == 1
    assert all(
        event["client_app"] == "chat"
        and event["user_id"] == "alice"
        and event["duration_ms"] >= 0
        for event in events
    )
    expected = {
        "_id",
        "tool_name",
        "user_id",
        "client_app",
        "request_group_id",
        "started_at",
        "completed_at",
        "duration_ms",
        "outcome",
        "error_code",
    }
    assert all(set(event) == expected for event in events)
    assert "EMP001" not in json.dumps(events, default=str)


async def test_actual_runtime_forwards_identity_headers(mcp_url, monkeypatch, seeded):
    monkeypatch.setenv("MCP_URL", mcp_url)
    async with mcp_connection(user_id="runtime_user", client_app="dashboard") as (
        session,
        tools,
    ):
        data, error = await call_tool(session, tools, "memory_get_preferences", {})
        assert not error and data["user_id"] == "runtime_user"
    event = seeded.tool_usage_events.find_one({})
    assert event["user_id"] == "runtime_user" and event["client_app"] == "dashboard"
    assert event["request_group_id"]


async def test_memory_save_and_delete_storage_failures_are_tool_errors(
    mcp_url, monkeypatch, seeded
):
    def unavailable(*args, **kwargs):
        raise ConnectionFailure("Simulated storage failure")

    monkeypatch.setattr(seeded.user_preferences, "update_one", unavailable)
    monkeypatch.setattr(seeded.user_preferences, "find_one_and_update", unavailable)
    async with connect(mcp_url, user_id="alice") as (session, tools):
        for name, args in [
            (
                "memory_set_preference",
                {"scope": "chat", "key": "style", "value": "concise"},
            ),
            ("memory_delete_preference", {"scope": "chat", "key": "style"}),
        ]:
            data, error = await call_tool(session, tools, name, args)
            assert error and data["code"] == 503
            assert "read preferences before retrying" in data["message"]
    assert seeded.user_preferences.count_documents({}) == 0
    assert all(row["error_code"] == 503 for row in seeded.tool_usage_events.find())


async def test_protocol_exceptions_preserve_code_and_original_error(database):
    observer = telemetry.usage_middleware(lambda: database.tool_usage_events)
    failure = RuntimeError("Simulated protocol failure")
    failure.error = SimpleNamespace(code=-32602)

    async def next_call(ctx):
        raise failure

    ctx = SimpleNamespace(method="tools/call", params={"name": "demo"}, request=None)
    with pytest.raises(RuntimeError) as caught:
        await observer(ctx, next_call)
    assert caught.value is failure
    event = database.tool_usage_events.find_one({})
    assert event["outcome"] == "error" and event["error_code"] == -32602


async def test_usage_failure_never_changes_or_repeats_business_write(
    mcp_url, monkeypatch, seeded
):
    calls = []
    original = business_tools.request_api

    async def request(*args, **kwargs):
        calls.append(args[1])
        return await original(*args, **kwargs)

    def unavailable(*args):
        raise ConnectionFailure("Simulated unavailable telemetry")

    monkeypatch.setattr(business_tools, "request_api", request)
    monkeypatch.setattr(telemetry, "insert_event", unavailable)
    async with connect(mcp_url) as (session, tools):
        result, error = await call_tool(
            session,
            tools,
            "hrms_update_employee",
            {"employee_id": "EMP001", "changes": {"department": "Finance"}},
        )
        assert not error and result["department"] == "Finance"
    assert calls == ["PATCH"]
    assert seeded.employees.find_one({"_id": "EMP001"})["department"] == "Finance"


async def test_cancelled_calls_are_logged_and_cancellation_preserved(database):
    observer = telemetry.usage_middleware(lambda: database.tool_usage_events)
    started = asyncio.Event()

    async def next_call(ctx):
        started.set()
        await asyncio.Event().wait()

    ctx = SimpleNamespace(
        method="tools/call",
        params={"name": "slow_tool"},
        request=SimpleNamespace(headers=Headers()),
    )
    task = asyncio.create_task(observer(ctx, next_call))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    event = database.tool_usage_events.find_one({})
    assert event["outcome"] == "cancelled"


async def test_slow_logging_is_bounded_and_does_not_change_result(
    database, monkeypatch
):
    def slow_insert(*args):
        time.sleep(0.2)

    monkeypatch.setattr(telemetry, "insert_event", slow_insert)
    monkeypatch.setattr(telemetry, "LOG_TIMEOUT_SECONDS", 0.01)
    observer = telemetry.usage_middleware(lambda: database.tool_usage_events)
    ctx = SimpleNamespace(method="tools/call", params={"name": "demo"}, request=None)

    async def next_call(ctx):
        return {"content": [], "isError": False}

    result = await asyncio.wait_for(observer(ctx, next_call), timeout=0.15)
    assert not result["isError"]
    await asyncio.sleep(0.2)  # finish the bounded test worker before teardown


def test_atomic_preference_updates_and_idempotent_delete(database):
    collection = database.user_preferences
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda index: preference_service.set_preference(
                    collection, "alice", "chat", f"key_{index}", str(index)
                ),
                range(20),
            )
        )
    assert (
        len(
            preference_service.get_preferences(collection, "alice")["preferences"][
                "chat"
            ]
        )
        == 20
    )
    assert preference_service.delete_preference(collection, "alice", "chat", "key_1")[
        "removed"
    ]
    assert not preference_service.delete_preference(
        collection, "alice", "chat", "key_1"
    )["removed"]
    assert (
        len(
            preference_service.get_preferences(collection, "alice")["preferences"][
                "chat"
            ]
        )
        == 19
    )


def test_mcp_lifespan_persistence_indexes_stats_and_health(database, monkeypatch):
    monkeypatch.setattr(mcp_database, "connect", lambda: (database.client, database))
    now = datetime.now(timezone.utc)
    with TestClient(create_app()) as client:
        preference_service.set_preference(
            database.user_preferences, "alice", "chat", "style", "concise"
        )
        assert client.get("/health").json()["database"] == "ok"
        assert client.get("/usage/stats").json()["total_calls"] == 0
        for tool, outcome, duration, user, day in [
            ("a", "success", 10, "alice", now),
            ("a", "error", 30, "alice", now),
            ("b", "cancelled", 20, "bob", now),
            ("a", "success", 40, "alice", now - timedelta(days=2)),
        ]:
            database.tool_usage_events.insert_one(
                {
                    "tool_name": tool,
                    "outcome": outcome,
                    "duration_ms": duration,
                    "user_id": user,
                    "client_app": "chat",
                    "started_at": day,
                    "completed_at": now,
                }
            )
        stats = client.get("/usage/stats").json()
        assert stats["total_calls"] == 4 and stats["avg_duration_ms"] == 25
        assert (
            stats["successful_calls"] == 2
            and stats["failed_calls"] == stats["cancelled_calls"] == 1
        )
        assert [row["tool_name"] for row in stats["by_tool"]] == ["a", "b"]
        filtered = client.get(
            "/usage/stats",
            params={
                "tool_name": "a",
                "user_id": "alice",
                "client_app": "chat",
                "date_from": now.date().isoformat(),
                "date_to": now.date().isoformat(),
            },
        ).json()
        assert filtered["total_calls"] == 2 and filtered["avg_duration_ms"] == 20
        assert client.get("/usage/stats?user_id=nobody").json()["by_tool"] == []
        assert (
            client.get(
                "/usage/stats?date_from=2026-10-25&date_to=2026-10-24"
            ).status_code
            == 422
        )
        assert client.get("/usage/stats?client_app=invalid").status_code == 422
        assert (
            database.tool_usage_events.count_documents({}) == 4
        )  # stats/health excluded
    with TestClient(create_app()):
        assert (
            preference_service.get_preferences(database.user_preferences, "alice")[
                "preferences"
            ]["chat"]["style"]
            == "concise"
        )
    indexes = database.tool_usage_events.index_information()
    assert indexes["completed_at_1"]["expireAfterSeconds"] == 90 * 24 * 60 * 60
    assert "tool_name_1_started_at_1" in indexes and "user_id_1_started_at_1" in indexes
    assert not any(
        "expireAfterSeconds" in index
        for index in database.user_preferences.index_information().values()
    )


def test_mcp_storage_failures_are_explicit(database, monkeypatch):
    monkeypatch.setattr(mcp_database, "connect", lambda: (database.client, database))
    with TestClient(create_app()) as client:

        def unavailable(*args, **kwargs):
            raise ConnectionFailure("Simulated unavailable database")

        monkeypatch.setattr(database.client.admin, "command", unavailable)
        assert client.get("/health").status_code == 503
        monkeypatch.setattr(usage_service, "statistics", unavailable)
        # The route imports the function directly.
        monkeypatch.setattr("MCP_server.routes.usage.statistics", unavailable)
        assert client.get("/usage/stats").status_code == 503
    with pytest.raises(ConnectionFailure):
        with TestClient(create_app()):
            pass  # startup requires the database; it must not start degraded


def tool_request(name, arguments):
    return {
        "role": "assistant",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


async def test_explicit_chat_memory_save_use_and_forget(mcp_url, monkeypatch, seeded):
    monkeypatch.setenv("MCP_URL", mcp_url)
    sequence = [
        tool_request(
            "memory_set_preference",
            {"scope": "chat", "key": "response_style", "value": "concise"},
        ),
        {"role": "assistant", "content": "Saved your preference."},
    ]

    async def model(messages, definitions=None):
        assert len(definitions) == 13
        assert "Only save or delete preferences" in messages[0]["content"]
        return sequence.pop(0)

    monkeypatch.setattr(chat_service, "ask_model", model)
    saved = await chat_service.chat(
        ChatRequest(user_id="alice", message="Remember that I prefer concise answers.")
    )
    assert [step["tool"] for step in saved["trace"]] == [
        "memory_get_preferences",
        "memory_set_preference",
    ]

    async def concise(messages, definitions=None):
        assert '"response_style": "concise"' in messages[0]["content"]
        return {"role": "assistant", "content": "A concise answer."}

    monkeypatch.setattr(chat_service, "ask_model", concise)
    result = await chat_service.chat(
        ChatRequest(user_id="alice", message="Explain this lab.")
    )
    assert len(result["trace"]) == 1
    sequence[:] = [
        tool_request(
            "memory_delete_preference", {"scope": "chat", "key": "response_style"}
        ),
        {"role": "assistant", "content": "Forgotten."},
    ]
    monkeypatch.setattr(chat_service, "ask_model", model)
    await chat_service.chat(
        ChatRequest(user_id="alice", message="Forget my response style preference.")
    )
    assert (
        preference_service.get_preferences(seeded.user_preferences, "alice")[
            "preferences"
        ]["chat"]
        == {}
    )


async def test_dashboard_preferences_are_read_only_scoped_and_budgeted(
    mcp_url, monkeypatch, seeded
):
    monkeypatch.setenv("MCP_URL", mcp_url)
    preference_service.set_preference(
        seeded.user_preferences,
        "alice",
        "chat",
        "private_chat_style",
        "chat-only-value",
    )
    preference_service.set_preference(
        seeded.user_preferences,
        "alice",
        "dashboard",
        "preferred_widgets",
        "count cards",
    )

    async def model(messages, definitions=None):
        prompt = messages[0]["content"]
        assert "count cards" in prompt and "chat-only-value" not in prompt
        assert "current instruction takes precedence" in prompt
        assert definitions is None
        return {
            "content": json.dumps(
                {
                    "title": "Snapshot",
                    "widgets": [
                        {"type": "card", "title": "Employees", "dataset": "employees"}
                    ],
                }
            )
        }

    monkeypatch.setattr(dashboard_service, "ask_model", model)
    result = await dashboard_service.generate("Show employees", user_id="alice")
    assert len(result["trace"]) == 3 and result["widgets"][0]["value"] == 30
    assert "chat-only-value" not in json.dumps(result)
    assert all(step["tool"] in READ_TOOLS for step in result["trace"])
    assert (
        "memory_set_preference" not in READ_TOOLS
        and "memory_delete_preference" not in READ_TOOLS
    )
    monkeypatch.setattr(dashboard_service, "MAX_CALLS", 2)
    with pytest.raises(HTTPException, match="Incomplete data"):
        await dashboard_service.generate("Show employees", user_id="alice")


async def test_unavailable_memory_stops_identified_hosts_before_model(
    mcp_url, monkeypatch, seeded
):
    monkeypatch.setenv("MCP_URL", mcp_url)

    def unavailable(*args, **kwargs):
        raise ConnectionFailure("Simulated unavailable memory")

    async def no_model(*args, **kwargs):
        pytest.fail("Model must not run after a failed preference read")

    monkeypatch.setattr(seeded.user_preferences, "find_one", unavailable)
    monkeypatch.setattr(chat_service, "ask_model", no_model)
    monkeypatch.setattr(dashboard_service, "ask_model", no_model)
    for run in [
        chat_service.chat(ChatRequest(user_id="alice", message="Hello")),
        dashboard_service.generate("Show employees", user_id="alice"),
    ]:
        with pytest.raises(
            HTTPException, match="Saved preferences could not be loaded"
        ) as failure:
            await run
        assert failure.value.status_code == 503
