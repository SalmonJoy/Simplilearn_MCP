# Dashboard tutorial: MCP data, AI layouts, Python values

[Project setup](../README.md#2-install-the-prerequisites) · [Previous: Chat](../AI_chat_assistant/README.md) · [Back to project](../README.md)

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

The retrieval step is deterministic: it always requests both complete lists, even when an instruction only needs employees. Although six tools are allowed, current generation invokes the two list tools. The model is not selecting data tools in this app. This is a useful comparison with the [chat model/tool loop](../AI_chat_assistant/README.md).

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

Six tools are permitted by `READ_TOOLS`; write tools are excluded by name. That host policy is separate from advisory MCP read-only annotations. The composite owner tool is in the allowlist but does not change the fixed retrieval flow.

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

## 5. Verify and troubleshoot

From the root, run offline schema, calculation and MCP tests:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_mcp_and_ai.py
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
