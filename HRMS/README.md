# HRMS tutorial: build the employee side of the system

[Project setup](../README.md#2-install-the-prerequisites) · [Next: Inventory](../Inventory_management/README.md)

[Employee UI guide](#start-the-streamlit-employee-ui) · [Tool-usage insights](../MCP_server/README.md#streamlit-tool-usage-insights) · [Git/local-file guide](../README.md#8-keep-local-files-out-of-git)

This app stores employee records and exposes five normal REST operations. It contains no LLM or MCP server. Later, MCP tools call these same operations, so you can understand and test the business API before adding AI.

The API runs on **8001** and its optional Streamlit UI on **8501**. Direct Swagger/Streamlit REST requests are not MCP tool calls and therefore do not appear in MCP usage statistics. Calls through the MCP server are recorded in its operational event collection; HRMS continues to own only employee data.

## 1. Start with the prerequisites

Complete the root [MongoDB setup and configuration](../README.md#3-configure-mongodb-and-ollama-cloud), install the root requirements, and run `seed.py` once. No Ollama key or other app is needed to use HRMS directly.

Run all commands from the repository root, even while reading this app's README:

```powershell
Set-Location C:\Salmon\Simplilearn\MCP
.venv\Scripts\python.exe -m uvicorn HRMS.main:app --host 127.0.0.1 --port 8001
```

Use your own project location if different. Open [Swagger](http://127.0.0.1:8001/docs). Leave this terminal running and use another for the exercises. Ctrl+C stops HRMS.

[config.py](config.py) reads `MONGODB_URI` and `MONGODB_DATABASE` (default `mcp_learning`) from the root configuration. HRMS creates its indexes at startup, so MongoDB must be reachable then. `/health` also pings MongoDB.

### Start the Streamlit employee UI

This optional frontend uses the same five APIs. Start HRMS as above, then run the UI in another PowerShell terminal at the repository root. Install the updated root requirements first if your environment predates the UI:

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
.venv\Scripts\python.exe -m streamlit run HRMS/ui/main.py --server.address 127.0.0.1 --server.port 8501
```

Without uv, install with `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` in a pip-created environment. Open [the HRMS UI](http://127.0.0.1:8501); stop it with Ctrl+C. Its HTTP client uses root `HRMS_URL`, default `http://127.0.0.1:8001`. It has no direct MongoDB, MCP or Ollama dependency. `run.py` does not launch this additional Streamlit process.

The sidebar contains three pages:

- **Overview:** four bordered cards show total, active, joining and inactive counts, followed by department and joining-month chart panels. Department and visible status choices use the summary endpoint; optional inclusive date bounds are under **More filters**. Counts cover the entire matching dataset. Use the header's Refresh action for current records.
- **Employee directory:** search by name, exact department/status, or optional joining-date bounds under **More filters**. Apply filters to reset the offset. The table toolbar shows matched count, page sizes 20/50/100, and Previous/Next; changing page size resets to the first page. The ID column stays pinned and joining dates are formatted for reading. Select an employee by ID from the current page or use exact-ID lookup. **Profile** shows contact/role details, a status badge and timestamps under **Record details**. Switch to **Edit details** to open the form; the ID is immutable and only changed fields are sent.
- **Add employee:** grouped **Identity and contact** and **Role and joining** fields use the existing Pydantic validation and default status to joining. Status choices are visible. Success shows the created record and an **Open in directory** action. Submitting creates a persistent dummy record; ordinary widget reruns and navigation do not create another one.

Create/edit forms preserve values on errors. Duplicate IDs/emails, invalid fields and unavailable HRMS produce readable feedback. A save with no changed fields sends no PATCH. There is no persistent API-data cache; use Refresh or Reload employee to read current data. Form baselines are held only in the current Streamlit session. Reload employee discards unsaved edit values and starts from the current backend record.

If a write outcome is uncertain, further submission is blocked until you reload/check that employee. The write may already have completed; no automatic write retry occurs. After a successful edit, the directory and details are reloaded. For a newly created record, use the directory to refresh/edit it.

The spacious light/purple workspace uses native Streamlit components and [the tracked theme configuration](../.streamlit/config.toml), including chart colors, sidebar, borders and typography. No custom CSS or HTML is injected. The entry point stays [ui/main.py](ui/main.py); direct page scripts live in [ui/app_pages](ui/app_pages/), reusable forms/profile presentation in [ui/components.py](ui/components.py), and edit handling in [ui/employee_editor.py](ui/employee_editor.py). [ui/state.py](ui/state.py) initializes session defaults and holds navigation callbacks. Every HTTP request still goes through [ui/services/hrms_client.py](ui/services/hrms_client.py). Public page URLs remain `/`, `/employees`, and `/add-employee`. Keep launching from the root so both imports and the theme resolve correctly.

Run the UI and HTTP-client tests without live services:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_hrms_ui.py
```

These AppTest exercises use the actual REST handlers backed by in-memory MongoDB and mocked HTTP transport. To troubleshoot a blank/unavailable UI, check the Streamlit terminal, port 8501, root working directory, and `HRMS_URL`; opening the UI does not start the API for you.

## 2. Follow the request through the modules

```text
HTTP request
  -> routes/employees.py: Pydantic inputs and response models
  -> services/employee_service.py: validation rules and database operations
  -> database.py: employees collection in MongoDB
  -> response with employee_id instead of _id
```

| File | Start reading here |
|---|---|
| [main.py](main.py) | FastAPI construction, lifespan, index creation and database error handler |
| [routes/employees.py](routes/employees.py) | The five endpoints; `summary` is declared before `/{employee_id}` |
| [schemas.py](schemas.py) | `EmployeeCreate`, `EmployeePatch`, `EmployeePage`, `EmployeeSummary` |
| [services/employee_service.py](services/employee_service.py) | `create_employee`, `filters`, `list_employees`, `summarize`, `update_employee`, `serialize` |
| [database.py](database.py) | `connect` and `create_indexes` |
| [config.py](config.py) | MongoDB configuration |

The route stays small. For example, `create_employee` in the routes module accepts an `EmployeeCreate` and delegates to the service. The service converts the date to JSON-friendly text, assigns timestamps, maps `employee_id` to MongoDB `_id`, and catches duplicate-key errors.

## 3. Understand the document

HRMS owns `mcp_learning.employees`:

| Field | Storage and purpose |
|---|---|
| `_id` | Immutable string ID such as `EMP001`; API name is `employee_id` |
| `full_name`, `department`, `designation` | Required nonblank strings, trimmed, maximum 150 characters |
| `email` | Required, checked for a basic email format and stored lowercase |
| `joining_date` | Validated as a date, stored as `YYYY-MM-DD` text |
| `status` | `joining`, `active`, or `inactive`; creation defaults to `joining` |
| `created_at`, `updated_at` | UTC BSON datetimes, serialized as ISO timestamps |

IDs use 1–50 letters, digits, underscores or hyphens. MongoDB provides the unique `_id` index; this app also creates a unique `email` index and a compound `(department, status, joining_date)` index. An employee reference in Inventory is an application-level relationship, not a MongoDB foreign key.

## 4. Try the five APIs

| Method and path | Input | Result | Matching MCP tool |
|---|---|---|---|
| `POST /employees` | Required employee fields; optional status | Created employee, HTTP 201 | `hrms_create_employee` |
| `GET /employees` | Filters and pagination | Employee page | `hrms_list_employees` |
| `GET /employees/summary` | Optional department/status/date filters | Total and grouped counts | `hrms_get_employee_summary` |
| `GET /employees/{employee_id}` | Exact ID | Employee or 404 | `hrms_get_employee` |
| `PATCH /employees/{employee_id}` | Nonempty subset of editable fields | Updated employee | `hrms_update_employee` |

### Read and paginate

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/employees/EMP001' | ConvertTo-Json -Depth 6
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/employees?department=Engineering&limit=2&offset=0'
$page | ConvertTo-Json -Depth 6
```

Lists sort by employee ID. `limit` defaults to 20 and accepts 1–100; `offset` starts at 0. Inspect `has_more` before treating a page as the full result. The envelope is `{items, total, limit, offset, has_more}`. For a second page, use `offset=2` with the same filters.

Supported filters are `name`, `department`, `status`, `joining_from`, and `joining_to`. Name search is a case-insensitive **literal substring**, not a regular-expression query. Other string filters are exact. Dates use inclusive `YYYY-MM-DD` bounds; a reversed range returns 422.

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/employees?name=asha&limit=100' | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/employees/summary?status=active' | ConvertTo-Json -Depth 6
```

Summary returns `total`, `by_department`, `by_status`, and `by_joining_month`. It counts all matching records without list pagination. It supports the list filters except `name`. Seeded joining dates are not refreshed on reruns, so date-based results vary with your existing records.

### Optional write exercise: create and update a fictional employee

The following commands **insert a persistent dummy record and change its department**. Choose an unused ID and email; rerunning creation with the same values returns 409. This app has no employee-delete endpoint, so the exercise record remains in the database.

```powershell
$employeeBody = @{
    employee_id = 'EMP900'
    full_name = 'Tutorial Learner'
    email = 'tutorial900@example.test'
    department = 'Engineering'
    designation = 'Trainee'
    joining_date = (Get-Date).ToString('yyyy-MM-dd')
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8001/employees' -ContentType 'application/json' -Body $employeeBody

$changes = @{ department = 'Finance' } | ConvertTo-Json
Invoke-RestMethod -Method Patch -Uri 'http://127.0.0.1:8001/employees/EMP900' -ContentType 'application/json' -Body $changes
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/employees/EMP900' | ConvertTo-Json -Depth 6
```

Expect status `joining` by default, department `Finance` after the PATCH, and server-created timestamps. For an MCP update the arguments are nested differently:

```json
{"employee_id": "EMP900", "changes": {"department": "Finance"}}
```

The REST PATCH body is only the `changes` object. Empty updates, null values, unknown fields, invalid dates/statuses, and attempts to change `employee_id` or timestamps are rejected. Inactivating an employee does not erase existing inventory ownership.

## 5. Verify and diagnose

Run the API tests from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_apis.py
```

These tests use an in-memory database. To check the real running app without changing data:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/health'
```

| Result/problem | Meaning or next step |
|---|---|
| 404 | The employee ID is absent; confirm seeding and the configured database. |
| 409 | Duplicate employee ID/email; choose unused values instead of retrying creation. |
| 422 | Check required fields, date bounds, enums, pagination, or PATCH rules. |
| 503 | The database became unavailable during a request. |
| App fails during startup | Index creation requires a reachable database and no conflicting duplicate emails. Check the URI, database user, and network access. |
| Port/import error | Use the root working directory and ensure port 8001 is not already occupied. |

Continue with [Inventory](../Inventory_management/README.md) to see another service validate an employee through this API.
