import json
import socket
import threading
import time
from contextlib import asynccontextmanager
import httpx
import pytest
import uvicorn
from fastapi import FastAPI, HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer
from mcp.types import Tool
from HRMS.main import app as hrms
from Inventory_management.main import app as inventory
from Inventory_management.services import inventory_service
from MCP_server.tools.business_tools import register_tools
from ai_runtime import READ_TOOLS, call_tool
from AI_chat_assistant.schemas import ChatRequest
from AI_chat_assistant.services import chat_service
from AI_dashboard_generation.services import dashboard_service
from AI_dashboard_generation.schemas import DashboardSpec


class BusinessTransport(httpx.AsyncBaseTransport):
    """Real REST handlers with in-memory MongoDB; no cloud calls in the test suite."""

    async def handle_async_request(self, request):
        app = hrms if request.url.port == 8001 else inventory
        return await httpx.ASGITransport(app=app).handle_async_request(request)


@pytest.fixture
def mcp_url(clients, seeded, monkeypatch):
    monkeypatch.setattr(inventory_service, "validate_employee", lambda employee: None)
    server = MCPServer("Test tools")

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(transport=BusinessTransport()) as client:
            app.state.client = client
            async with server.session_manager.run():
                yield

    app = FastAPI(lifespan=lifespan)
    register_tools(server, lambda: app.state.client)
    app.mount("/", server.streamable_http_app(json_response=True))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}/mcp"
    runner = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(
        target=runner.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    for _ in range(500):
        if runner.started:
            break
        time.sleep(0.01)
    assert runner.started, "Test MCP server did not start"
    try:
        yield url
    finally:
        runner.should_exit = True
        thread.join(timeout=10)
        sock.close()


@asynccontextmanager
async def connect(url):
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            yield session, tools


async def test_real_mcp_discovery_and_calls(mcp_url):
    async with connect(mcp_url) as (session, tools):
        assert len(tools) == 10
        assert {
            name for name, tool in tools.items() if tool.annotations.read_only_hint
        } == READ_TOOLS
        data, error = await call_tool(
            session, tools, "hrms_get_employee", {"employee_id": "EMP001"}
        )
        assert not error and data["employee_id"] == "EMP001"
        page, error = await call_tool(
            session, tools, "inventory_list_items", {"limit": 5}
        )
        assert not error and len(page["items"]) == 5 and page["total"] == 60
        data, error = await call_tool(
            session, tools, "hrms_get_employee", {"employee_id": "missing"}
        )
        assert error and data["code"] == 404
        _, error = await call_tool(
            session, tools, "inventory_list_items", {"limit": 101}
        )
        assert error
        _, error = await call_tool(session, tools, "invented_tool", {})
        assert error
        # Exercise SDK argument validation too, bypassing the host-side validator.
        invalid = await session.call_tool("inventory_list_items", {"limit": 101})
        assert invalid.is_error


async def test_chat_write_then_cross_system_read(mcp_url, monkeypatch, seeded):
    monkeypatch.setattr(chat_service, "mcp_connection", lambda: connect(mcp_url))
    sequence = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {
                        "name": "hrms_update_employee",
                        "arguments": {
                            "employee_id": "EMP001",
                            "changes": {"department": "Finance"},
                        },
                    }
                }
            ],
        },
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {
                        "name": "hrms_get_employee",
                        "arguments": {"employee_id": "EMP001"},
                    }
                },
                {
                    "function": {
                        "name": "inventory_list_items",
                        "arguments": {"employee_id": "EMP001"},
                    }
                },
            ],
        },
        {
            "role": "assistant",
            "content": "EMP001 now belongs to Finance and has company items.",
        },
    ]

    async def model(messages, definitions=None):
        assert len(definitions) == 10
        return sequence.pop(0)

    monkeypatch.setattr(chat_service, "ask_model", model)
    result = await chat_service.chat(
        ChatRequest(message="Move EMP001 to Finance and show their assigned items.")
    )
    assert len(result["trace"]) == 3
    assert not any(row["is_error"] for row in result["trace"])
    assert seeded.employees.find_one({"_id": "EMP001"})["department"] == "Finance"
    assert any("Finance" in json.dumps(row["result"]) for row in result["trace"])


async def test_item_owner_lookup_over_mcp(mcp_url, seeded):
    duplicate = seeded.inventory_items.find_one({"_id": "ITEM001"})
    duplicate["_id"] = "ITEM061"
    seeded.inventory_items.insert_one(duplicate)
    seeded.employees.update_one({"_id": "EMP001"}, {"$set": {"status": "inactive"}})
    async with connect(mcp_url) as (session, tools):
        data, error = await call_tool(
            session, tools, "inventory_get_item_owners", {"item_type": " Laptop "}
        )
        assert not error and data["total"] == 5
        assert [owner["employee_id"] for owner in data["items"]] == [
            "EMP001",
            "EMP004",
            "EMP005",
            "EMP008",
            "EMP009",
        ]
        assert all(
            set(owner) == {"employee_id", "full_name", "email"}
            for owner in data["items"]
        )
        assert data["items"][0]["email"] == "employee001@example.test"
        assert (
            data["items"][0]["full_name"]
            == seeded.employees.find_one({"_id": "EMP001"})["full_name"]
        )
        page, error = await call_tool(
            session,
            tools,
            "inventory_get_item_owners",
            {"item_type": "laptop", "limit": 2, "offset": 2},
        )
        assert not error and page["total"] == 5 and page["has_more"]
        assert [owner["employee_id"] for owner in page["items"]] == ["EMP005", "EMP008"]
        for args in (
            {"item_id": "ITEM021"},
            {"item_type": "unknown"},
            {"item_type": "laptop", "offset": 99},
        ):
            empty, error = await call_tool(
                session, tools, "inventory_get_item_owners", args
            )
            assert not error and empty["items"] == [] and not empty["has_more"]
        one, error = await call_tool(
            session, tools, "inventory_get_item_owners", {"item_id": "ITEM001"}
        )
        assert not error and one["items"] == [data["items"][0]]
        missing, error = await call_tool(
            session, tools, "inventory_get_item_owners", {"item_id": "UNKNOWN"}
        )
        assert error and missing["code"] == 404
        for args in (
            {},
            {"item_type": " "},
            {"item_type": "laptop", "item_id": "ITEM001"},
        ):
            invalid = await session.call_tool("inventory_get_item_owners", args)
            assert invalid.is_error and invalid.structured_content["code"] == 422
        for args in (
            {"item_id": "../invalid"},
            {"item_id": ""},
            {"item_type": "laptop", "limit": 101},
            {"item_type": "laptop", "offset": -1},
        ):
            invalid = await session.call_tool("inventory_get_item_owners", args)
            assert invalid.is_error


async def test_chat_discovers_and_uses_owner_lookup(mcp_url, monkeypatch):
    monkeypatch.setattr(chat_service, "mcp_connection", lambda: connect(mcp_url))

    async def model(messages, definitions):
        assert "inventory_get_item_owners" in {
            tool["function"]["name"] for tool in definitions
        }
        if messages[-1]["role"] != "tool":
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "inventory_get_item_owners",
                            "arguments": {"item_type": "laptop"},
                        }
                    }
                ],
            }
        assert (
            json.loads(messages[-1]["content"])["items"][0]["email"]
            == "employee001@example.test"
        )
        return {
            "role": "assistant",
            "content": "There are five laptop owners, with IDs, names and emails in the tool result.",
        }

    monkeypatch.setattr(chat_service, "ask_model", model)
    result = await chat_service.chat(
        ChatRequest(message="List laptop owners with their IDs, names and emails.")
    )
    assert len(result["trace"]) == 1 and not result["trace"][0]["is_error"]
    assert result["trace"][0]["tool"] == "inventory_get_item_owners"


async def test_dashboard_through_real_mcp(mcp_url, monkeypatch):
    monkeypatch.setattr(dashboard_service, "mcp_connection", lambda: connect(mcp_url))

    async def model(messages):
        return {
            "content": json.dumps(
                {
                    "title": "Overview",
                    "widgets": [
                        {"type": "card", "title": "Employees", "dataset": "employees"},
                        {
                            "type": "bar",
                            "title": "Departments",
                            "dataset": "employees",
                            "group_by": "department",
                        },
                        {
                            "type": "table",
                            "title": "Assigned laptops",
                            "dataset": "assigned_items",
                            "filters": {"item_type": "laptop"},
                            "columns": ["item_id", "employee_name"],
                        },
                    ],
                }
            )
        }

    monkeypatch.setattr(dashboard_service, "ask_model", model)
    result = await dashboard_service.generate(
        "Show employees by department and assigned laptops."
    )
    assert result["widgets"][0]["value"] == 30
    assert sum(row["count"] for row in result["widgets"][1]["rows"]) == 30
    assert len(result["widgets"][2]["rows"]) == 5
    assert all(row["employee_name"] for row in result["widgets"][2]["rows"])
    assert all(row["tool"] in READ_TOOLS for row in result["trace"])


async def test_dashboard_pagination_and_budget(monkeypatch):
    calls = []

    async def fake_call(session, tools, name, args):
        calls.append((name, args))
        if name == "hrms_list_employees":
            rows = [{"employee_id": f"EMP{i}"} for i in range(105)]
        else:
            rows = []
        start = args["offset"]
        page = rows[start : start + args["limit"]]
        return {
            "items": page,
            "total": len(rows),
            "has_more": start + len(page) < len(rows),
        }, False

    monkeypatch.setattr(dashboard_service, "call_tool", fake_call)
    datasets, trace = await dashboard_service.collect_datasets(None, {})
    assert len(datasets["employees"]) == 105 and len(trace) == 3
    assert calls[1][1]["offset"] == 100
    with pytest.raises(HTTPException, match="Incomplete data"):
        await dashboard_service.collect_datasets(None, {}, max_calls=1)


@pytest.mark.parametrize("changing_total", [False, True])
async def test_dashboard_rejects_changed_or_duplicate_pages(
    monkeypatch, changing_total
):
    async def fake_call(session, tools, name, args):
        if args["offset"] == 0:
            return {
                "items": [{"employee_id": "EMP001"}],
                "total": 2,
                "has_more": True,
            }, False
        return {
            "items": [{"employee_id": "EMP001"}],
            "total": 3 if changing_total else 2,
            "has_more": False,
        }, False

    monkeypatch.setattr(dashboard_service, "call_tool", fake_call)
    with pytest.raises(HTTPException, match="Data changed"):
        await dashboard_service.collect_datasets(None, {})


async def test_dashboard_repair_and_failure(monkeypatch):
    @asynccontextmanager
    async def connection():
        yield None, {}

    monkeypatch.setattr(dashboard_service, "mcp_connection", connection)

    async def data(*args):
        return {"employees": [], "items": [], "assigned_items": []}, []

    monkeypatch.setattr(dashboard_service, "collect_datasets", data)
    sequence = [
        "not JSON",
        '{"title":"Empty","widgets":[{"type":"card","title":"Employees","dataset":"employees"}]}',
    ]

    async def model(messages):
        return {"content": sequence.pop(0)}

    monkeypatch.setattr(dashboard_service, "ask_model", model)
    result = await dashboard_service.generate("Employee count")
    assert result["widgets"][0]["value"] == 0 and not sequence

    async def invalid(messages):
        return {"content": "invalid"}

    monkeypatch.setattr(dashboard_service, "ask_model", invalid)
    with pytest.raises(HTTPException, match="one repair attempt"):
        await dashboard_service.generate("Employee count")


@pytest.mark.parametrize(
    "widget",
    [
        {"type": "script", "title": "Bad", "dataset": "employees"},
        {"type": "card", "title": "Bad", "dataset": "employees", "value": 999},
        {"type": "bar", "title": "Bad", "dataset": "employees", "group_by": "salary"},
        {"type": "bar", "title": "Bad", "dataset": "employees"},
        {"type": "card", "title": "Bad", "dataset": "employees", "metric": "sum"},
        {
            "type": "table",
            "title": "Bad",
            "dataset": "items",
            "filters": {"$where": "code"},
        },
    ],
)
def test_dashboard_rejects_unknown_fields_and_code(widget):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DashboardSpec.model_validate({"title": "Invalid", "widgets": [widget]})


async def test_dashboard_does_not_allow_writes():
    write = Tool(name="inventory_assign_item", inputSchema={"type": "object"})
    allowed = {
        name: tool for name, tool in {write.name: write}.items() if name in READ_TOOLS
    }
    _, error = await call_tool(None, allowed, write.name, {})
    assert error


async def test_ai_errors_are_clear(monkeypatch):
    import ai_runtime

    monkeypatch.setenv("OLLAMA_API_KEY", "")
    with pytest.raises(HTTPException, match="OLLAMA_API_KEY"):
        await ai_runtime.ask_model([])
    monkeypatch.setenv("OLLAMA_API_KEY", "fictional-test-key")

    async def fail(*args, **kwargs):
        raise httpx.ConnectError("Simulated failure")

    monkeypatch.setattr(ai_runtime.httpx.AsyncClient, "post", fail)
    with pytest.raises(HTTPException, match="Ollama Cloud request failed"):
        await ai_runtime.ask_model([])


async def test_chat_limits(monkeypatch):
    @asynccontextmanager
    async def connection():
        yield None, {}

    async def model(*args):
        return {
            "role": "assistant",
            "tool_calls": [{"function": {"name": "missing", "arguments": {}}}],
        }

    monkeypatch.setattr(chat_service, "mcp_connection", connection)
    monkeypatch.setattr(chat_service, "ask_model", model)
    monkeypatch.setattr(chat_service, "MAX_ROUNDS", 2)
    result = await chat_service.chat(ChatRequest(message="Test"))
    assert "Model-round limit" in result["answer"] and len(result["trace"]) == 2
    monkeypatch.setattr(chat_service, "MAX_CALLS", 1)
    result = await chat_service.chat(ChatRequest(message="Test"))
    assert "Tool-call limit" in result["answer"] and len(result["trace"]) == 1


async def test_chat_preserves_trace_when_model_fails_after_write(
    mcp_url, monkeypatch, seeded
):
    monkeypatch.setattr(chat_service, "mcp_connection", lambda: connect(mcp_url))
    calls = 0

    async def model(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "hrms_update_employee",
                            "arguments": {
                                "employee_id": "EMP001",
                                "changes": {"department": "Finance"},
                            },
                        }
                    }
                ],
            }
        raise HTTPException(503, "Simulated model outage")

    monkeypatch.setattr(chat_service, "ask_model", model)
    result = await chat_service.chat(ChatRequest(message="Move EMP001 to Finance"))
    assert "Some requested changes may have completed" in result["answer"]
    assert len(result["trace"]) == 1 and not result["trace"][0]["is_error"]
    assert seeded.employees.find_one({"_id": "EMP001"})["department"] == "Finance"


async def test_mcp_upstream_failures_are_errors():
    from MCP_server.services.api_service import request_api

    def html_response(request):
        return httpx.Response(200, text="<html>Unexpected proxy page</html>")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(html_response)
    ) as client:
        result = await request_api(client, "GET", "http://fictional.test/employees")
        assert result.is_error and result.structured_content["code"] == 503

    def unavailable(request):
        raise httpx.ConnectError("Simulated network outage")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        result = await request_api(
            client, "POST", "http://fictional.test/employees", body={}
        )
        assert result.is_error and "unknown" in result.structured_content["message"]


def test_browser_pages_and_assets():
    from fastapi.testclient import TestClient
    from AI_chat_assistant.main import app as chat_app
    from AI_dashboard_generation.main import app as dashboard_app

    for app, filename in [(chat_app, "chat.js"), (dashboard_app, "dashboard.js")]:
        with TestClient(app) as client:
            page = client.get("/")
            assert (
                page.status_code == 200 and "text/html" in page.headers["content-type"]
            )
            assert client.get("/static/" + filename).status_code == 200
            assert client.get("/static/style.css").status_code == 200
            assert client.get("/health").json()["status"] == "ok"
