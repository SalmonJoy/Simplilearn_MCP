# MCP server tutorial: turn business APIs into discoverable tools

[Project setup](../README.md#2-install-the-prerequisites) · [Previous: Inventory](../Inventory_management/README.md) · [Next: Chat](../AI_chat_assistant/README.md)

[Tool catalog](#the-thirteen-tool-catalog) · [Usage and memory storage](#mongodb-usage-events-and-preference-memory) · [Streamlit insights guide](#streamlit-tool-usage-insights) · [Git/local-file guide](../README.md#8-keep-local-files-out-of-git)

This app is the MCP boundary for the learning lab. It exposes **thirteen tools: ten business tools over nine REST APIs, plus three preference-memory tools**. A client discovers their descriptions and schemas, then calls them through MCP.

The server uses the official Python MCP SDK 2.3.0, mounted inside FastAPI. It calls MongoDB for operational events and preferences, and REST for business records. It does not call Ollama or generate answers. You can use every tool directly in Inspector without an LLM.

## 1. Start the server

Install dependencies and configure/seed MongoDB through the [root setup](../README.md#3-configure-mongodb-and-ollama-cloud). Start HRMS on 8001 and Inventory on 8002 for working tool calls. The MCP process can start without them, but calls that need them will fail.

From a separate PowerShell terminal at the repository root:

```powershell
Set-Location C:\Salmon\Simplilearn\MCP
.venv\Scripts\python.exe -m uvicorn MCP_server.main:app --host 127.0.0.1 --port 8003
```

The endpoint is `http://127.0.0.1:8003/mcp`; `/health` also pings MongoDB. MongoDB must be available at startup. Ctrl+C stops this process.

[config.py](config.py) reads `HRMS_URL`, `INVENTORY_URL`, `MONGODB_URI` and `MONGODB_DATABASE`. These come from the existing root `.env`; preserve its credentials. AI clients use the separate root `MCP_URL` setting. No Ollama key is consumed by this server.

## 2. Understand the protocol boundary

```text
Client initialize -> SDK negotiates the MCP session
Client tools/list -> SDK returns tool names, descriptions, input schemas and annotations
Client tools/call -> SDK validates arguments and runs the registered function
Registered function -> service -> existing REST API(s)
Memory function -> preference service -> MCP-owned MongoDB collection
Usage middleware -> one metadata event around each tools/call
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
| [database.py](database.py) | MongoDB connection and usage indexes |
| [usage_middleware.py](usage_middleware.py) | Bounded metadata-only logging around SDK calls |
| [tools/memory_tools.py](tools/memory_tools.py) | Typed memory tools, context identity and structured validation errors |
| [services/preference_service.py](services/preference_service.py) | Atomic preference updates |
| [services/usage_service.py](services/usage_service.py) / [routes/usage.py](routes/usage.py) | Statistics aggregation and read-only REST endpoint |

### Why mounting and lifespan matter

The source creates the server using:

```python
mcp = MCPServer("HRMS and Inventory Learning Tools")
```

It mounts `mcp.streamable_http_app(json_response=True)` at `/`. The SDK app already contains the `/mcp` route, so this produces `/mcp`, not `/mcp/mcp`. The FastAPI health route is registered before the root mount.

`create_app` builds a fresh SDK instance because its session manager runs only once. FastAPI's lifespan connects to MongoDB, checks it and creates indexes, enters `mcp.session_manager.run()`, and keeps a shared `httpx.AsyncClient` open. It closes the MongoDB client on shutdown. Synchronous database operations run in worker threads. Mounted sub-app lifespans are not sufficient: the parent starts the SDK manager. Follow [main.py](main.py) and the [SDK mounting guide](https://py.sdk.modelcontextprotocol.io/run/asgi/) when experimenting.

## The thirteen-tool catalog

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
| `memory_get_preferences` | None; identity comes from HTTP context | MongoDB preferences | Read |
| `memory_set_preference` | `scope`, `key`, `value` | MongoDB atomic update | Write |
| `memory_delete_preference` | `scope`, `key` | MongoDB atomic removal | Write |

There are seven read tools and six write tools. Annotations describe intended behavior; they do not implement access control. The dashboard host also uses an explicit read-tool allowlist. Chat discovers all thirteen tools.

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

Expect thirteen tools and a successful owners page if the upstream APIs are available. In [ai_runtime.py](../ai_runtime.py), `mcp_connection` opens the SDK HTTP client and `streamable_http_client`, creates `ClientSession`, calls `initialize`, and then `list_tools`. The connection belongs to the host, not the model.

### Python attributes versus protocol fields

This pinned SDK uses snake_case attributes in Python but camelCase names on the MCP wire:

| Python | Wire JSON |
|---|---|
| `tool.input_schema` | `inputSchema` |
| `result.structured_content` | `structuredContent` |
| `result.is_error` | `isError` |
| `tool.annotations.read_only_hint` | `readOnlyHint` within annotations |

`tool_result` supplies the same JSON as text content and structured content. `request_api` translates upstream REST errors into MCP results marked `isError`, with a `code` and `message`. An MCP transport HTTP 200 does not imply the underlying business operation succeeded: inspect the tool's error flag. Schema errors can also be produced by the SDK before a service executes.

## MongoDB usage events and preference memory

The existing database now has four collections. MCP owns `tool_usage_events` and `user_preferences`; it does not query `employees` or `inventory_items` directly. No seed data is required for either new collection.

### Usage events

Each `tools/call` produces one event with `_id`, `tool_name`, `user_id`, `client_app`, `request_group_id`, UTC `started_at`/`completed_at`, `duration_ms`, `outcome` and optional `error_code`. The middleware observes calls before SDK validation, including invalid arguments, unknown tools and cancellations. The composite owner lookup is one call, despite its multiple REST requests. Initialization, discovery, health and statistics requests are excluded; host-side validation rejections never reach MCP.

No arguments, results, prompts, employee records or model reasoning are stored. A TTL index expires events 90 days after completion; MongoDB deletes asynchronously, so expired records may remain briefly. Compound indexes support tool/time and user/time lookups. Preference documents have no TTL.

After startup, telemetry uses one bounded insert and logs a generic warning if it fails. The original tool outcome is preserved, and a business write is never repeated because logging failed. This is best-effort learning telemetry, not a complete audit or billing record.

Open [Swagger](http://127.0.0.1:8003/docs) or use:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8003/usage/stats' | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri 'http://127.0.0.1:8003/usage/stats?tool_name=memory_get_preferences&user_id=alice&client_app=chat&date_from=2026-10-01&date_to=2026-10-31' | ConvertTo-Json -Depth 8
```

Dates are illustrative inclusive UTC calendar days; omit them for all retained events. The response contains `total_calls`, `successful_calls`, `failed_calls`, `cancelled_calls`, `avg_duration_ms`, and `by_tool` summaries. Empty results have zero counts and an empty `by_tool`. `/usage/stats` is an operational REST endpoint, not a fourteenth tool.

### Preference profiles

Each profile has `_id` equal to its demo user ID, `preferences.chat` and `preferences.dashboard` key/value maps, plus UTC `created_at`/`updated_at`. Missing profiles return empty maps. Saves use atomic `$set` and deletions use `$unset`, preserving other keys. Deletion reports whether the key existed. A known duplicate-key race during the first profile insertion is handled with an update to the newly created profile; uncertain writes are not retried.

In Inspector, configure the HTTP header `X-Demo-User-ID: tutorial-user` and reconnect. The optional `X-MCP-Client` values are `chat` or `dashboard`; other clients are recorded as `unknown`. Hosts generate an `X-MCP-Request-ID` UUID for each logical chat/generation request. These are ordinary demo headers, not authentication. Anyone who can supply an ID can use that profile. SDK-injected `Context` is absent from tool schemas; identity is never a model-supplied tool argument.

Call `memory_get_preferences` with `{}`. The next call **writes a permanent preference** for `tutorial-user`:

```json
{"scope": "chat", "key": "response_style", "value": "concise"}
```

Use it with `memory_set_preference`, then call `memory_get_preferences` again. To remove that preference explicitly, call `memory_delete_preference` with:

```json
{"scope": "chat", "key": "response_style"}
```

`scope` is `chat` or `dashboard`; keys allow 1–64 letters/digits/underscores/hyphens. Values are trimmed, nonempty strings of at most 1,000 characters. Invalid input or missing identity returns structured code `422`; storage failures return `503`. Read current preferences before retrying an uncertain save or deletion. Preferences are presentation defaults; they cannot authorize business changes or override current instructions or validation.

## Streamlit tool-usage insights

This separate read-only workspace helps answer which tools are popular, which fail or run slowly, who invokes them, and what happened within one request. It uses the same purple theme as the other interfaces. It makes no model calls and does not add tools to the thirteen-tool catalog.

### Setup and launch

Complete the [root installation](../README.md#2-install-the-prerequisites) using `uv` or Python/pip. Keep the MCP FastAPI service running on 8003 with its MongoDB connection. HRMS, Inventory, chat, dashboard generation and Ollama are not required to inspect existing logs. The installed Streamlit dependency is sufficient; there are no new packages or database collections.

From another PowerShell terminal at the repository root:

```powershell
.venv\Scripts\python.exe -m streamlit run MCP_server/ui/main.py --server.address 127.0.0.1 --server.port 8505
```

Open [tool-usage insights](http://127.0.0.1:8505). Stop it with Ctrl+C in its terminal. `run.py` still launches only the five FastAPI apps. If 8505 is occupied, stop the previous Streamlit instance before starting another.

The UI reads `MCP_API_URL`, default `http://127.0.0.1:8003`, through the existing root `.env` loader. This is the REST base URL, **without `/mcp`**. Keep `MCP_URL=http://127.0.0.1:8003/mcp` for protocol clients. No credentials move into Streamlit configuration; the UI never queries MongoDB directly.

### Apply filters and refresh

The sidebar form controls inclusive UTC start/end dates, exact tool name, client (`chat`, `dashboard`, `unknown`), exact user ID, anonymous-only and outcome. Blank text fields mean all values. User ID and Anonymous only cannot be combined. The default is the last seven UTC calendar days; each view supports up to 90 inclusive days, matching the intended retention window. Choose daily or hourly UTC time buckets, then submit **Apply filters**.

All metrics use every matching retained event, not just a visible event page. Rates use all matching calls as their denominator, including cancellations; choosing an outcome filter also changes that denominator. Unknown requested tool names count as tools called. Distinct identified users exclude anonymous calls, which are reported separately.

**Refresh** reads the currently applied filters again. Ordinary widget reruns and navigation reuse the aggregate snapshot. The successful load time is shown in IST, while chart buckets and date boundaries are explicitly UTC. **Applied filters** shows the filters belonging to the displayed snapshot, even when a failed request leaves different draft values in the form.

If refreshing fails, the last successful snapshot remains visible with a warning. An initial failure shows no invented metrics and waits for an explicit refresh. HTTP requests have a 30-second timeout and no automatic retries. There is no automatic refresh or cross-session data cache.

### Overview: activity and audience

Eight cards show recorded calls, success rate, errors, cancellations, average duration, longest call, tools called and identified users. Empty selections show zero counts and “—” for rates/durations with no observations.

- **Activity over time:** successful, failed and cancelled calls per UTC day/hour. Empty buckets show zero recorded calls.
- **Application usage:** call counts from chat, dashboard and unknown sources.
- **User activity:** top ten identified users by volume; anonymous-call count appears separately.
- **Quick findings:** deterministic text names the highest-volume tool, the tool with most errors and the tool with highest mean duration, including supporting call counts. Equal rankings use tool-name order. No AI or invented thresholds are involved.

### Tool performance: compare tools and errors

Two charts show the top ten requested tool names by call volume and mean duration. The duration chart labels each sample count; a slow tool with one call is different evidence from one with hundreds.

The sortable comparison table includes calls, usage share, successes, errors, cancellations, success/error rates, mean duration and maximum duration. Overall means are weighted by individual calls, not averages of tool averages. Error-code counts include **Code unavailable** for failures without a recorded code. A code alone is not proof of a particular root cause.

Durations measure MCP execution, including validation and tool execution. They exclude model generation, caller-side network time and telemetry insertion. This UI does not estimate percentiles, costs, token usage or end-user conversation latency.

### Call explorer: investigate a request

The event table shows IDs, start/completion times in IST, tool, outcome, error code, duration, user, client and request-group ID. Use 20/50/100 rows with Previous/Next. Selecting a call stores its stable event ID, so moving to another page does not accidentally select a different row. Its details indicate when the metadata was read; raw JSON is available with UTC timestamps.

**View request group** retrieves all retained calls sharing the selected group ID, oldest first, independently of overview filters. This is useful when an error-only selection would otherwise hide the successful calls before it. Group results also paginate. Calls with no group ID cannot open this view. Adding tool durations is not a measure of end-to-end request latency.

Event pagination reads fresh data on explicit page changes. Its load time is separate from the aggregate snapshot: new calls or TTL expiration can change results between requests. Failed page reads preserve the previous page with a warning and an explicit retry action. Applying filters or refreshing successfully clears prior selections and resets pagination.

### Read-only APIs and modules

| Endpoint | Behavior |
|---|---|
| `GET /usage/stats` | Existing overall/per-tool response, unchanged |
| `GET /usage/insights` | Complete performance aggregates, UTC timeline, client/user/error breakdowns |
| `GET /usage/events` | Metadata-only pagination, with optional group and chronological ordering |

The new endpoints share `tool_name`, `user_id`, `client_app`, `outcome`, `anonymous_only`, `date_from` and `date_to`. Insights adds `granularity=day|hour` and defaults to seven UTC days. Events adds `request_group_id`, `limit` (20, maximum 100), `offset` (0) and `order=newest|oldest`. Omitting event date filters reads all retained events, as used by group drill-down. Invalid filters return `422`; unavailable MongoDB returns `503`.

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8003/usage/insights?granularity=day' | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri 'http://127.0.0.1:8003/usage/events?outcome=error&limit=20&offset=0' | ConvertTo-Json -Depth 8
```

These are ordinary FastAPI REST endpoints and are visible in [Swagger](http://127.0.0.1:8003/docs). Reading them does not create usage events. Native MCP tool calls remain the source of events; if the dashboard is empty, call `memory_get_preferences` from Inspector with a demo-user header, then refresh. That reads memory without changing saved preferences or business records, while the server records the tool invocation.

| Source | Responsibility |
|---|---|
| [ui/main.py](ui/main.py), [filters.py](ui/filters.py), [state.py](ui/state.py) | Navigation, shared filter form and explicit snapshot lifecycle |
| [ui/app_pages/overview.py](ui/app_pages/overview.py), [performance.py](ui/app_pages/performance.py), [explorer.py](ui/app_pages/explorer.py) | Direct page scripts |
| [ui/components.py](ui/components.py), [event_explorer.py](ui/event_explorer.py) | Native charts, metrics, metadata browsing and stable selection |
| [ui/services/usage_client.py](ui/services/usage_client.py) | Validated read-only HTTP requests and readable errors |
| [services/usage_service.py](services/usage_service.py), [routes/usage.py](routes/usage.py) | Shared queries, complete MongoDB aggregates and paginated projections |

The event schema, logging and 90-day TTL are unchanged. New indexes support recent-call browsing and request-group chronology. Retention cleanup is asynchronous and logging is best effort: zero recorded calls is not proof of inactivity. This local learning dashboard has no authentication and should be treated like the other localhost apps.

## 5. Verify, extend, and diagnose

From the root, run offline transport and composite-service tests:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_mcp_and_ai.py tests/test_item_owner_service.py
.venv\Scripts\python.exe -m pytest -q tests/test_mcp_memory_and_usage.py
.venv\Scripts\python.exe -m pytest -q tests/test_usage_insights.py tests/test_usage_ui.py
```

With all five apps running, `smoke_check.py --apps` checks discovery and owner lookup against live data without calling Ollama. It does not alter business records or preferences, but tool calls append usage events. See [root verification](../README.md#7-verify-and-troubleshoot).

To add another tool, implement a small service or reuse `request_api`, then register a typed function inside `register_tools` with a useful docstring and `READ` or `WRITE` annotation. Update tests, catalog counts and the dashboard allowlist if applicable. No new generic HTTP or database-query tool is needed. Restart MCP and reconnect Inspector; chat discovers the current catalog on every request.

| Problem | What to check |
|---|---|
| Fewer than thirteen tools | Old server process/source. Restart MCP, reconnect, and list tools again. |
| MongoDB startup or health error | MCP now requires the root MongoDB connection and access to its two operational collections. |
| Session manager/task-group error | Confirm the parent lifespan runs the SDK manager. |
| Upstream 404/409/422 | Inspect tool arguments and the returned business error. |
| Tool dependency error | Check `HRMS_URL`, `INVENTORY_URL` and both API terminals. |
| Inspector cannot connect | Use Streamable HTTP and exactly `/mcp` at the running port. |
| Uncertain write result | Re-read the record before trying again; writes are not automatically retried. |

Continue with [chat](../AI_chat_assistant/README.md) to let a model request these same tool calls.
