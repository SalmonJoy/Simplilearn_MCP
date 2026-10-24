# Dashboard tutorial: MCP data, AI layouts, Python values

[Project setup](../README.md#2-install-the-prerequisites) · [Previous: Chat](../AI_chat_assistant/README.md) · [Back to project](../README.md)

[Streamlit dashboard guide](#streamlit-dashboard-studio) · [Saved preferences](#saved-dashboard-preferences) · [Tool-usage insights](../MCP_server/README.md#streamlit-tool-usage-insights) · [Git/local-file guide](../README.md#8-keep-local-files-out-of-git)

This app turns a natural-language instruction into a dashboard of cards, bar charts and tables. It is a FastAPI host that retrieves data through MCP. **Python controls retrieval and calculations; the model chooses a validated JSON layout.** It does not generate or execute new application source code.

## 1. Start the dependencies and app

Complete the root [MongoDB and Ollama Cloud setup](../README.md#3-configure-mongodb-and-ollama-cloud), seed data, and start HRMS, Inventory and MCP. They are needed for generation; the dashboard process can serve its empty page before they are available.

In a separate PowerShell terminal at the repository root:

```powershell
Set-Location C:\Salmon\Simplilearn\MCP
.venv\Scripts\python.exe -m uvicorn AI_dashboard_generation.main:app --host 127.0.0.1 --port 8005
```

Open [the dashboard](http://127.0.0.1:8005), or [API docs](http://127.0.0.1:8005/docs). Ctrl+C stops it. `/health` confirms only that this app is serving.

The shared runtime consumes root `MCP_URL` (default `http://127.0.0.1:8003/mcp`), `OLLAMA_HOST` (`https://ollama.com`), `OLLAMA_MODEL` (`gpt-oss:120b`) and your `OLLAMA_API_KEY`. Root `.env` values override inherited variables. Restart the process after configuration edits. There is no direct MongoDB connection here.

## 2. Follow generation through the code

```text
Instruction -> POST /dashboards/generate
  -> discover tools and keep the read-only allowlist
  -> fetch every employee page using hrms_list_employees
  -> fetch every inventory page using inventory_list_items
  -> join assignments to employee details in Python
  -> ask Ollama for layout JSON using schema and dataset context
  -> validate; allow one repair attempt
  -> filter, group and count in Python
  -> return layout, calculated widgets, trace and metadata
  -> fixed browser renderer displays the result
```

The retrieval step is deterministic: it always requests both complete lists, even when an instruction only needs employees. Seven read tools are allowed; current generation invokes the two list tools and, for an identified user, the preference-read tool first. The model is not selecting data tools in this app. This is a useful comparison with the [chat model/tool loop](../AI_chat_assistant/README.md).

| File | What to read |
|---|---|
| [main.py](main.py) | FastAPI, static files and health |
| [routes/dashboard.py](routes/dashboard.py) | `GET /` and `POST /dashboards/generate` |
| [schemas.py](schemas.py) | `GenerateRequest`, `Widget`, `DashboardSpec`, `DATASET_FIELDS` |
| [services/dashboard_service.py](services/dashboard_service.py) | `collect_datasets`, `generate`, and `render_widgets` |
| [config.py](config.py) | App directory and twenty-call budget |
| [templates/index.html](templates/index.html) | Instruction form and display containers |
| [static/dashboard.js](static/dashboard.js) | Fetch, chart/table/card rendering, trace and layout display |
| [shared ai_runtime.py](../ai_runtime.py) | MCP discovery/calls, `READ_TOOLS`, native Ollama requests |

### Retrieval must finish before counting

`collect_datasets` reads pages of 100 rows under a shared **twenty-MCP-call budget**. It checks `has_more`, expected totals and duplicate IDs. An incomplete intermediate page, exhausted budget, or detected pagination change prevents a successful dashboard result. Employee and item reads are still separate requests, not a transactional snapshot.

Seven tools are permitted by `READ_TOOLS`; all business and memory write tools are excluded by name. That host policy is separate from advisory MCP read-only annotations. The composite owner tool is in the allowlist but does not change the fixed list retrieval flow. Identified requests spend one of the twenty calls loading preferences, leaving nineteen for complete data retrieval.

## 3. Understand the datasets and layout

| Dataset | One row represents | Available fields |
|---|---|---|
| `employees` | One employee | `employee_id`, `full_name`, `email`, `department`, `designation`, `joining_date`, `status` |
| `items` | One physical unit | `item_id`, `name`, `category`, `item_type`, `status`, `employee_id` |
| `assigned_items` | One currently assigned unit, enriched with its owner | Item fields plus `employee_name`, `employee_department`, `employee_status`, `employee_joining_date` |

Python derives `items.employee_id` from the current assignment and joins employee details by ID. Missing joined details remain null. `assigned_items` counts are **item counts**, not distinct employee counts: one person holding two laptops contributes two rows. Use `employees` for employee counts.

Here is a complete **illustrative layout**, not a generated response with calculated values:

```json
{
  "title": "Company overview",
  "widgets": [
    {
      "type": "card",
      "title": "Employees",
      "dataset": "employees",
      "metric": "count"
    },
    {
      "type": "bar",
      "title": "Available devices by type",
      "dataset": "items",
      "filters": {"category": "device", "status": "available"},
      "group_by": "item_type",
      "metric": "count"
    },
    {
      "type": "table",
      "title": "Assigned laptop units and owners",
      "dataset": "assigned_items",
      "filters": {"item_type": "laptop"},
      "columns": ["item_id", "employee_name", "employee_department"]
    }
  ]
}
```

`DashboardSpec` allows 1–12 widgets. Each has a nonempty title, supported type/dataset, optional exact-match string `filters`, optional `group_by`, `metric=count`, and optional table `columns`. Bar charts require `group_by`; cards do not allow grouping. Raw tables choose columns; grouped tables use `group_by` and a count column. Unknown fields and extra JSON properties are rejected. Filters are literal equality checks, not query expressions or ranges.

The model receives schema, dataset counts and selected categorical values, not the full fetched employee records. It returns layout JSON. The code does not request Cloud schema-enforced output; Pydantic validates locally. On invalid JSON or schema errors it asks once for a repaired layout, then returns 422 if still invalid. This also avoids executing generated HTML or Python.

After validation, `render_widgets` computes card counts, grouped counts and table rows from the actual datasets. It never trusts a model-supplied numeric value. The fixed JavaScript renderer displays the result; Chart.js is loaded from a CDN and charts fall back to tables if it is unavailable. Fonts also use a CDN, with local fallbacks. No frontend build command is needed.

## 4. Exercise: generate and inspect a dashboard

In the browser, try:

> Show total employees, employee count by department, and available devices by item type.

Or:

> Show available goodies by type and a table of assigned laptops with their owners.

Expect a relevant supported layout; exact widget choices and titles can vary. Open **MCP calls & layout JSON** and check that retrieval uses the list tools and the layout contains field references rather than invented values. Compare a card's count with the underlying API data.

You can submit the same read-only request through PowerShell:

```powershell
$dashboardBody = @{
    instruction = 'Show total employees and employee count by department.'
} | ConvertTo-Json
$dashboard = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8005/dashboards/generate' -ContentType 'application/json' -Body $dashboardBody -TimeoutSec 180
$dashboard.dataset_counts | ConvertTo-Json
$dashboard.spec | ConvertTo-Json -Depth 10
$dashboard.widgets | ConvertTo-Json -Depth 10
```

The request model is:

```json
{"instruction": "Show total employees and employee count by department."}
```

Instructions accept 1–4000 characters. A successful response contains `title`, `spec`, calculated `widgets`, `trace`, `generated_at`, `dataset_counts`, and a snapshot `note`. Cards have a calculated `value`; bars and tables have calculated `rows` and `columns`. Values depend on your database, not the sample layout above.

The page holds the result in browser memory. Reloading clears it. Submitting another instruction retrieves fresh records; there is no saved-dashboard store or automatic refresh. If a later request fails, the page labels any still-visible result as the previous successful dashboard.

## Streamlit dashboard studio

Keep the existing dashboard API on 8005 running, together with MCP, HRMS, Inventory, MongoDB and configured Ollama Cloud. Complete the [shared installation](../README.md#2-install-the-prerequisites), then run in a separate PowerShell terminal from the repository root:

```powershell
.venv\Scripts\python.exe -m streamlit run AI_dashboard_generation/ui/main.py --server.address 127.0.0.1 --server.port 8504
```

Open [the dashboard studio](http://127.0.0.1:8504). Stop it with Ctrl+C. `DASHBOARD_URL` defaults to `http://127.0.0.1:8005`, using the root `.env` loader. The original HTML page on 8005 stays available. Streamlit replaces Chart.js with native components in this new interface; both pages use the same generation API and calculated data.

1. Click **People overview** to populate the instruction form; choosing an example does not call the backend.
2. Submit **Generate dashboard**. The UI validates the instruction and posts it to `/dashboards/generate`. The existing backend retrieves complete employee/item datasets through MCP, joins them, asks AI for layout JSON, validates/repairs it and calculates the counts in Python.
3. Inspect native count cards, bar charts and tables. Widget order follows the returned layout; consecutive cards share rows of up to four, and charts/tables have full-width bordered panels. Zero counts and empty results are valid.
4. Expand **MCP calls and layout JSON** to inspect retrieval and layout choices. The generated time, dataset counts and snapshot note describe the successful result.
5. Use **Regenerate** to fetch fresh data using the last successful instruction. An edited draft is used only when you submit Generate dashboard.

The UI validates returned widget data and displays server-calculated values; it does not recalculate counts, query MCP or call Ollama. The backend's seven-tool read-only restriction includes preference reads. Deterministic list retrieval, the twenty-call limit and one repair attempt remain in place. Generation has a 600-second read timeout and no automatic retries. If a request fails, its instruction stays in the form and any previous result remains visible with an explicit warning. Session state preserves the last successful dashboard across ordinary reruns, without a saved-dashboard store or automatic regeneration.

| Module | Responsibility |
|---|---|
| [ui/main.py](ui/main.py) / [state.py](ui/state.py) | Form, examples, regeneration and session snapshot |
| [ui/components.py](ui/components.py) | Native rendering in widget order |
| [ui/schemas.py](ui/schemas.py) | Validate layout plus calculated counts/rows |
| [ui/services/dashboard_client.py](ui/services/dashboard_client.py) | HTTP request to the existing generation API |

Run `.venv\Scripts\python.exe -m pytest -q tests/test_streamlit_workspaces.py` for offline rendering, validation and failure checks. If the service is unavailable, verify 8005 and its dependencies. For incomplete-data or invalid-layout errors, inspect the displayed message and use a simpler supported instruction. A warning above an existing dashboard means it is the previous snapshot. Native charts in Streamlit do not depend on the Chart.js CDN. If 8504 is occupied, stop the previous Streamlit process; `run.py` launches only the five FastAPI services.

## Saved dashboard preferences

Use the same **Demo user ID** as chat. In Streamlit, enter it in the sidebar and click **Use profile**; the original HTML page has an optional demo-user input. Changing profiles clears the displayed dashboard, draft instruction, errors and regeneration state. A demo ID is not a login; anyone who supplies it can use that profile. Blank means anonymous, preserving the original generation behavior.

Save dashboard preferences through an explicit chat request, for example “Remember for dashboards that I prefer bar charts.” This **writes preference data** through a memory tool; dashboard generation itself cannot invoke memory write tools.

The generation request accepts an optional identity:

```json
{"user_id": "alice", "instruction": "Show employee counts by department."}
```

For identified users, the backend reads preferences through MCP first, includes that call in the trace and budget, and passes only the dashboard scope into the layout prompt. Chat preferences are omitted from dashboard prompts and returned traces. Saved preferences are lower-priority presentation defaults: the current instruction wins, and count-only analytics, validation and read-only rules still apply. They cannot add unsupported metrics or run code. A failed preference read stops generation with `503` before requesting a model layout.

Profiles survive application restarts in MongoDB; generated dashboards remain temporary session snapshots. [MCP owns the preference collection](../MCP_server/README.md#mongodb-usage-events-and-preference-memory), so neither this host nor its UI queries MongoDB directly.

## 5. Verify and troubleshoot

From the root, run offline schema, calculation and MCP tests:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_mcp_and_ai.py
.venv\Scripts\python.exe -m pytest -q tests/test_mcp_memory_and_usage.py
```

For explicit live database/Cloud checks, use the [root verification commands](../README.md#7-verify-and-troubleshoot). Model requests consume your Cloud allowance. No write tools are called by dashboard generation.

| Problem | What to check |
|---|---|
| Data retrieval error / 503 | Check MCP, HRMS, Inventory, MongoDB and configured URLs. |
| Incomplete-data / twenty-call error | The app will not calculate partial totals; the fixed full-list flow may exceed its budget on larger datasets. |
| Data changed / 409 | Records changed or duplicated across pages; try again when the data is stable. |
| Layout invalid after repair / 422 | Try a clear request for cards, bars or tables using known fields and counts. |
| Salary totals, averages, date ranges, or distinct-owner metrics unavailable | Only count, exact-match filters and known fields are implemented. Unsupported analytics are outside this tutorial. |
| Ollama error | Check root key, Cloud model access, host and usage; restart after `.env` edits. |
| Charts are tables | Chart.js CDN access failed; the table fallback still shows the calculated rows. |
| Owner count differs from an assigned-items chart | The composite owner tool deduplicates employees; assigned-items charts count units. |

Try changing the instruction and inspecting the JSON again. The key lesson is the separation between obtaining trusted data through MCP, letting AI choose a presentation, and calculating the displayed values in ordinary code.
