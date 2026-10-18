# MCP server tutorial: turn business APIs into discoverable tools

[Project setup](../README.md#2-install-the-prerequisites) · [Previous: Inventory](../Inventory_management/README.md) · [Next: Chat](../AI_chat_assistant/README.md)

This app is the MCP boundary for the learning lab. It exposes **ten tools over nine REST APIs**. A client can discover their descriptions and schemas, then call them without knowing how HRMS or Inventory store their data.

The server uses the official Python MCP SDK 2.3.0, mounted inside FastAPI. It does not call Ollama, query MongoDB, or generate answers. You can use every tool directly in Inspector without an LLM.

## 1. Start the server

Install dependencies and configure/seed MongoDB through the [root setup](../README.md#3-configure-mongodb-and-ollama-cloud). Start HRMS on 8001 and Inventory on 8002 for working tool calls. The MCP process can start without them, but calls that need them will fail.

From a separate PowerShell terminal at the repository root:

```powershell
Set-Location C:\Salmon\Simplilearn\MCP
.venv\Scripts\python.exe -m uvicorn MCP_server.main:app --host 127.0.0.1 --port 8003
```

The endpoint is `http://127.0.0.1:8003/mcp`; `/health` checks only the MCP app. Ctrl+C stops this process.

[config.py](config.py) reads `HRMS_URL` and `INVENTORY_URL`, defaulting to ports 8001 and 8002. Those are trusted upstream addresses, not tool arguments. AI clients use the separate root `MCP_URL` setting. No database credentials or Ollama key are consumed by this server.

## 2. Understand the protocol boundary

```text
Client initialize -> SDK negotiates the MCP session
Client tools/list -> SDK returns tool names, descriptions, input schemas and annotations
Client tools/call -> SDK validates arguments and runs the registered function
Registered function -> service -> existing REST API(s)
SDK -> MCP tool result -> client
```

Ordinary FastAPI routes do not automatically become MCP tools. Registration with the SDK is what makes a function discoverable. `/mcp` carries protocol messages, not a separate HTTP route for every tool. Swagger does not replace `tools/list`, and a browser GET on `/mcp` is not the tool browser UI.

| File | Responsibility |
|---|---|
| [main.py](main.py) | Creates `MCPServer`, registers tools, mounts transport, manages HTTP client and MCP lifespan |
| [tools/business_tools.py](tools/business_tools.py) | `register_tools`: ten typed functions and their descriptions |
| [schemas.py](schemas.py) | `READ`/`WRITE` annotations and SDK result types |
| [services/api_service.py](services/api_service.py) | `request_api` and `tool_result`: HTTP calls and consistent MCP results |
| [services/item_owner_service.py](services/item_owner_service.py) | `get_item_owners`: composite Inventory/HRMS lookup |
| [routes/health.py](routes/health.py) | Ordinary FastAPI health endpoint |
| [config.py](config.py) | Upstream REST base URLs |

### Why mounting and lifespan matter

The source creates the server using:

```python
mcp = MCPServer("HRMS and Inventory Learning Tools")
```

It mounts `mcp.streamable_http_app(json_response=True)` at `/`. The SDK app already contains the `/mcp` route, so this produces `/mcp`, not `/mcp/mcp`. The FastAPI health route is registered before the root mount.

FastAPI's lifespan enters `mcp.session_manager.run()` while keeping a shared `httpx.AsyncClient` open. Mounted sub-app lifespans are not sufficient here: the parent must start the SDK session manager. Follow [main.py](main.py) and the [SDK mounting guide](https://py.sdk.modelcontextprotocol.io/run/asgi/) when experimenting.

## The ten-tool catalog

All list limits default to 20, accept at most 100, and use `offset=0`. Date arguments are ISO dates. Read tools have `readOnlyHint=true`; write tools have it false.

| Tool | Key arguments | REST calls | Kind |
|---|---|---|---|
| `hrms_create_employee` | `employee_id`, `full_name`, `email`, `department`, `designation`, `joining_date`; optional `status` | POST /employees | Write |
| `hrms_list_employees` | Optional `name`, `department`, `status`, `joining_from`, `joining_to`, pagination | GET /employees | Read |
| `hrms_get_employee_summary` | Optional `department`, `status`, `joining_from`, `joining_to` | GET /employees/summary | Read |
| `hrms_get_employee` | `employee_id` | GET /employees/{employee_id} | Read |
| `hrms_update_employee` | `employee_id`, nonempty `changes` object | PATCH /employees/{employee_id} | Write |
| `inventory_list_items` | Optional `category`, `item_type`, `status`, `employee_id`, pagination | GET /items | Read |
| `inventory_get_item` | `item_id` | GET /items/{item_id} | Read |
| `inventory_assign_item` | `item_id`, `employee_id` | POST /items/{item_id}/assign | Write |
| `inventory_return_item` | `item_id`, expected current `employee_id` | POST /items/{item_id}/return | Write |
| `inventory_get_item_owners` | Exactly one of `item_type` or `item_id`; pagination | Inventory lookup, then HRMS employee lookups | Read, composite |

There are six read tools and four write tools. Annotations describe intended behavior; they do not implement access control. The dashboard host also uses an explicit read-tool allowlist. Chat discovers all ten tools.

Argument typing supplies the schema, and the function docstring explains when the model should use it. Business services remain responsible for rules such as unique emails and available inventory. The update tool takes `changes` as an argument; its adapter sends that object directly as the REST PATCH body.

## 3. Exercise: inspect and call a tool

With Node.js installed, launch [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector):

```powershell
npx @modelcontextprotocol/inspector
```

Follow its printed local browser URL. Select **Streamable HTTP**, enter `http://127.0.0.1:8003/mcp`, connect, and list tools. Pick `hrms_get_employee_summary` and call it without filters. Expect structured grouped employee counts. Neither this step nor the next requires a model request.

Next, call `inventory_get_item_owners` with:

```json
{"item_type": "laptop", "limit": 20, "offset": 0}
```

An **illustrative** result is below; your current owners and total may differ:

```json
{
  "items": [
    {"employee_id": "EMP001", "full_name": "Asha Rao", "email": "employee001@example.test"}
  ],
  "total": 1,
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

### Trace the composite owner lookup

1. Trim/lowercase `item_type` and fetch every assigned matching Inventory page at 100 units per request. Alternatively, fetch one exact `item_id`.
2. Collect current owner IDs, deduplicate them, and sort them. Multiple laptops held by one employee produce one owner row.
3. Paginate the owner IDs, then fetch only those selected employees from HRMS.
4. Return `employee_id`, `full_name`, and `email`, with the standard page envelope.

Current owners are included even if now inactive. An unassigned item or unmatched type returns an empty list; a nonexistent item ID returns 404. Missing/both selectors return a tool error with code 422. Missing selected employees and dependency failures produce errors instead of partially filled owner lists. Detected changes during inventory pagination return 409; reads are not a cross-service snapshot.

In Inspector, try `{"item_id":"ITEM001"}` as the arguments object instead of `item_type`. Supplying both selectors demonstrates semantic input validation. Stick to read tools while exploring; assign/create/update/return calls change the configured dummy database.

## 4. Exercise: call from a Python MCP client

This read-only example uses the same connection helper as the AI apps. Run it from the root; `MCP_URL` must point to the running server:

```powershell
@'
import asyncio
import json
from ai_runtime import mcp_connection

async def main():
    async with mcp_connection() as (session, tools):
        print("Discovered tools:", len(tools))
        result = await session.call_tool("inventory_get_item_owners", {"item_type": "laptop"})
        print("Tool error:", result.is_error)
        print(json.dumps(result.structured_content, indent=2))

asyncio.run(main())
'@ | .venv\Scripts\python.exe -
```

Expect ten tools and a successful owners page if the upstream APIs are available. In [ai_runtime.py](../ai_runtime.py), `mcp_connection` opens `streamable_http_client`, creates `ClientSession`, calls `initialize`, and then `list_tools`. The connection belongs to the host, not the model.

### Python attributes versus protocol fields

This pinned SDK uses snake_case attributes in Python but camelCase names on the MCP wire:

| Python | Wire JSON |
|---|---|
| `tool.input_schema` | `inputSchema` |
| `result.structured_content` | `structuredContent` |
| `result.is_error` | `isError` |
| `tool.annotations.read_only_hint` | `readOnlyHint` within annotations |

`tool_result` supplies the same JSON as text content and structured content. `request_api` translates upstream REST errors into MCP results marked `isError`, with a `code` and `message`. An MCP transport HTTP 200 does not imply the underlying business operation succeeded: inspect the tool's error flag. Schema errors can also be produced by the SDK before a service executes.

## 5. Verify, extend, and diagnose

From the root, run offline transport and composite-service tests:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_mcp_and_ai.py tests/test_item_owner_service.py
```

With all five apps running, `smoke_check.py --apps` checks discovery and owner lookup against live data without calling Ollama. See [root verification](../README.md#7-verify-and-troubleshoot).

To add another tool, implement a small service or reuse `request_api`, then register a typed function inside `register_tools` with a useful docstring and `READ` or `WRITE` annotation. Update tests, catalog counts and the dashboard allowlist if applicable. No new generic HTTP or database-query tool is needed. Restart MCP and reconnect Inspector; chat discovers the current catalog on every request.

| Problem | What to check |
|---|---|
| Only nine tools | Old server process/source. Restart MCP, reconnect, and list tools again. |
| Session manager/task-group error | Confirm the parent lifespan runs the SDK manager. |
| Upstream 404/409/422 | Inspect tool arguments and the returned business error. |
| Tool dependency error | Check `HRMS_URL`, `INVENTORY_URL` and both API terminals. |
| Inspector cannot connect | Use Streamable HTTP and exactly `/mcp` at the running port. |
| Uncertain write result | Re-read the record before trying again; writes are not automatically retried. |

Continue with [chat](../AI_chat_assistant/README.md) to let a model request these same tool calls.
