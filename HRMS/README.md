# HRMS tutorial: build the employee side of the system

[Project setup](../README.md#2-install-the-prerequisites) · [Next: Inventory](../Inventory_management/README.md)

This app stores employee records and exposes five normal REST operations. It contains no LLM or MCP server. Later, MCP tools call these same operations, so you can understand and test the business API before adding AI.

## 1. Start with the prerequisites

Complete the root [MongoDB setup and configuration](../README.md#3-configure-mongodb-and-ollama-cloud), install the root requirements, and run `seed.py` once. No Ollama key or other app is needed to use HRMS directly.

Run all commands from the repository root, even while reading this app's README:

```powershell
Set-Location C:\Salmon\Simplilearn\MCP
.venv\Scripts\python.exe -m uvicorn HRMS.main:app --host 127.0.0.1 --port 8001
```

Use your own project location if different. Open [Swagger](http://127.0.0.1:8001/docs). Leave this terminal running and use another for the exercises. Ctrl+C stops HRMS.

[config.py](config.py) reads `MONGODB_URI` and `MONGODB_DATABASE` (default `mcp_learning`) from the root configuration. HRMS creates its indexes at startup, so MongoDB must be reachable then. `/health` also pings MongoDB.

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
