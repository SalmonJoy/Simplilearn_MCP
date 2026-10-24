"""Small shared MCP/Ollama plumbing. No application business logic lives here."""

import json
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4
import jsonschema
import httpx
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from settings import env

READ_TOOLS = {
    "hrms_list_employees",
    "hrms_get_employee",
    "hrms_get_employee_summary",
    "inventory_list_items",
    "inventory_get_item",
    "inventory_get_item_owners",
    "memory_get_preferences",
}


def today():
    return datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()


@asynccontextmanager
async def mcp_connection(*, user_id=None, client_app="unknown"):
    try:
        headers = {"X-MCP-Client": client_app, "X-MCP-Request-ID": str(uuid4())}
        if user_id:
            headers["X-Demo-User-ID"] = user_id
        async with create_mcp_http_client(headers=headers) as client:
            async with streamable_http_client(
                env("MCP_URL", "http://127.0.0.1:8003/mcp"), http_client=client
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    discovered = await session.list_tools()
                    yield session, {tool.name: tool for tool in discovered.tools}
    except HTTPException:
        raise
    except ExceptionGroup as exc:
        # Task-group cleanup can wrap errors raised by request handling.
        def find_http(group):
            for child in group.exceptions:
                if isinstance(child, HTTPException):
                    return child
                if isinstance(child, BaseExceptionGroup):
                    found = find_http(child)
                    if found:
                        return found

        found = find_http(exc)
        if found:
            raise found from None
        raise HTTPException(
            503, "MCP connection failed. Check that the tool server is running."
        ) from None
    except Exception:
        raise HTTPException(
            503, "MCP connection failed. Check that the tool server is running."
        ) from None


def ollama_tools(tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }
        for tool in tools.values()
    ]


async def load_preferences(session, tools, user_id, trace, *, scope=None):
    """An identified request must distinguish unavailable memory from empty memory."""
    if user_id is None:
        return {}
    data, error = await call_tool(session, tools, "memory_get_preferences", {})
    if not error and (
        not isinstance(data, dict) or not isinstance(data.get("preferences"), dict)
    ):
        error = True
    if error:
        raise HTTPException(
            503,
            "Saved preferences could not be loaded. Check MCP and MongoDB before trying again.",
        )
    preferences = data["preferences"]
    if scope:
        preferences = {scope: preferences.get(scope, {})}
        data = {"user_id": user_id, "preferences": preferences}
    trace.append(
        {
            "tool": "memory_get_preferences",
            "arguments": {},
            "is_error": False,
            "result": data,
        }
    )
    return preferences


async def call_tool(session, tools, name, arguments):
    if name not in tools:
        return {"code": 422, "message": "Unknown or disallowed tool"}, True
    try:
        jsonschema.validate(
            arguments,
            tools[name].input_schema,
            format_checker=jsonschema.FormatChecker(),
        )
    except (jsonschema.ValidationError, jsonschema.SchemaError):
        return {
            "code": 422,
            "message": "Arguments do not match the discovered tool schema",
        }, True
    try:
        result = await session.call_tool(name, arguments, read_timeout_seconds=20)
        data = result.structured_content
        if data is None:
            data = json.loads(
                "\n".join(c.text for c in result.content if c.type == "text")
            )
        return data, result.is_error
    except Exception:
        return {
            "code": 503,
            "message": "MCP call failed. For writes, read the affected record before retrying; outcome may be unknown.",
        }, True


async def ask_model(messages, tools=None):
    key = env("OLLAMA_API_KEY")
    if not key:
        raise HTTPException(503, "Set OLLAMA_API_KEY in the root .env file")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            body = {
                "model": env("OLLAMA_MODEL", "gpt-oss:120b"),
                "messages": messages,
                "stream": False,
            }
            if tools is not None:
                body["tools"] = tools
            response = await client.post(
                env("OLLAMA_HOST", "https://ollama.com").rstrip("/") + "/api/chat",
                headers={"Authorization": f"Bearer {key}"},
                json=body,
            )
            response.raise_for_status()
            message = response.json()["message"]
            # Thinking may be needed in the next model turn, but is never shown in the UI.
            return message
    except Exception:
        raise HTTPException(
            503,
            "Ollama Cloud request failed. Check the API key, model, network, and usage limits.",
        ) from None
