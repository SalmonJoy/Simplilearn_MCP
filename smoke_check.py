"""Explicit external checks: python smoke_check.py [--cloud] [--apps]."""

import argparse
import asyncio
import httpx
from pymongo import MongoClient
from settings import env


async def check(cloud=False, apps=False):
    failures = []
    try:
        with MongoClient(
            env("MONGODB_URI", "mongodb://localhost:27017"),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        ) as client:
            client.admin.command("ping")
        print("PASS MongoDB connection")
    except Exception as exc:
        print(
            f"FAIL MongoDB connection ({type(exc).__name__}); check credentials and network access"
        )
        failures.append("MongoDB")
    if cloud:
        from ai_runtime import ask_model

        try:
            response = await ask_model(
                [
                    {
                        "role": "user",
                        "content": "Connectivity test. Call ping with message hello.",
                    }
                ],
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "ping",
                            "description": "A fictional connectivity check",
                            "parameters": {
                                "type": "object",
                                "properties": {"message": {"type": "string"}},
                                "required": ["message"],
                            },
                        },
                    }
                ],
            )
            assert response.get("tool_calls"), "Model did not return a tool call"
            print("PASS Ollama Cloud tool calling")
        except Exception:
            print("FAIL Ollama Cloud; check key, model, network and usage limits")
            failures.append("Ollama")
    if apps:
        from ai_runtime import READ_TOOLS, mcp_connection, call_tool

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                for port in range(8001, 8006):
                    response = await client.get(f"http://127.0.0.1:{port}/health")
                    response.raise_for_status()
                print("PASS five application health checks")
                async with mcp_connection() as (session, tools):
                    assert len(tools) == 10
                    assert {
                        name
                        for name, tool in tools.items()
                        if tool.annotations.read_only_hint
                    } == READ_TOOLS
                    data, error = await call_tool(
                        session, tools, "hrms_get_employee_summary", {}
                    )
                    assert not error
                    print(
                        f"PASS MCP discovery: {len(tools)} tools; employee count: {data['total']}"
                    )
                    owners, error = await call_tool(
                        session,
                        tools,
                        "inventory_get_item_owners",
                        {"item_type": "laptop"},
                    )
                    assert not error
                    assert all(
                        set(owner) == {"employee_id", "full_name", "email"}
                        for owner in owners["items"]
                    )
                    print(
                        f"PASS composite MCP owner lookup: {owners['total']} laptop owners"
                    )
                if cloud:
                    chat = await client.post(
                        "http://127.0.0.1:8004/chat",
                        json={
                            "message": "Get employee counts by department using the summary tool."
                        },
                    )
                    chat.raise_for_status()
                    trace = chat.json()["trace"]
                    assert trace and all(not step["is_error"] for step in trace)
                    assert all(step["tool"] in READ_TOOLS for step in trace)
                    print("PASS live chat -> Ollama -> MCP -> HRMS -> MongoDB")
                    dashboard = await client.post(
                        "http://127.0.0.1:8005/dashboards/generate",
                        json={
                            "instruction": "Show total employees and employee count by department, and available devices by item type."
                        },
                    )
                    dashboard.raise_for_status()
                    result = dashboard.json()
                    assert result["widgets"]
                    employee_cards = [
                        widget
                        for widget in result["widgets"]
                        if widget["type"] == "card"
                        and widget["dataset"] == "employees"
                        and not widget["filters"]
                    ]
                    assert (
                        employee_cards and employee_cards[0]["value"] == data["total"]
                    )
                    print(
                        "PASS live dashboard -> MCP data -> Ollama layout -> Python counts"
                    )
        except Exception as exc:
            print(
                f"FAIL application integration ({type(exc).__name__}); inspect service logs"
            )
            failures.append("Applications")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Make real Ollama requests (uses Cloud quota)",
    )
    parser.add_argument(
        "--apps",
        action="store_true",
        help="Check running applications on ports 8001–8005",
    )
    options = parser.parse_args()
    raise SystemExit(bool(asyncio.run(check(options.cloud, options.apps))))
