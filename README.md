# MCP Learning Lab: a hands-on tutorial

Learn Model Context Protocol (MCP) by connecting two small business systems to a chat assistant and a dashboard. The project has **five FastAPI apps, nine business REST APIs, and thirteen MCP tools**, plus five Streamlit interfaces for HRMS, Inventory, chat, AI dashboards, and tool-usage insights. Seven tools read data; six change state, including two preference-memory tools.

The example company gives laptops, mice, T-shirts, and bottles to employees. HRMS knows who the employees are. Inventory knows who holds each item. MCP makes these capabilities discoverable to other applications.

## Your learning path

1. [Understand the architecture](#1-understand-the-architecture).
2. [Install the prerequisites](#2-install-the-prerequisites).
3. [Configure MongoDB and Ollama Cloud](#3-configure-mongodb-and-ollama-cloud).
4. [Seed and start the apps](#4-seed-and-start-the-apps).
5. [Follow the first exercises](#5-follow-the-first-exercises).
6. [Explore the code and extend it](#6-explore-the-code-and-extend-it).
7. [Verify and troubleshoot](#7-verify-and-troubleshoot).
8. [Keep local files out of Git](#8-keep-local-files-out-of-git).

For a closer look at each app, follow these tutorials in order:

| Tutorial | What you will learn | Port |
|---|---|---:|
| [HRMS](HRMS/README.md) | Employee APIs, validation, and MongoDB documents | 8001 |
| [HRMS browser UI](HRMS/README.md#start-the-streamlit-employee-ui) | Overview, employee directory, create and edit forms | 8501 |
| [Inventory](Inventory_management/README.md) | Assigning physical items and checking employee eligibility | 8002 |
| [Inventory workspace](Inventory_management/README.md#streamlit-inventory-workspace) | Complete inventory counts, directory, assign and return forms | 8502 |
| [MCP server](MCP_server/README.md) | Discovering and calling tools, including a composite lookup | 8003 |
| [AI chat assistant](AI_chat_assistant/README.md) | Connecting model tool requests to an MCP client | 8004 |
| [Streamlit chat](AI_chat_assistant/README.md#streamlit-chat-workspace) | Conversation history and inspectable tool traces | 8503 |
| [AI dashboard](AI_dashboard_generation/README.md) | MCP data, AI-selected layouts, and Python-calculated values | 8005 |
| [Streamlit dashboard studio](AI_dashboard_generation/README.md#streamlit-dashboard-studio) | Native rendering of AI-selected cards, charts and tables | 8504 |
| [Tool-usage insights](MCP_server/README.md#streamlit-tool-usage-insights) | Usage trends, tool performance and call-level metadata | 8505 |

## 1. Understand the architecture

```mermaid
flowchart LR
    Browser[Browser] --> Chat[Chat host :8004]
    Browser --> Dashboard[Dashboard host :8005]
    Browser --> HRUI[Streamlit HRMS UI :8501]
    HRUI -->|REST| HRMS
    Browser --> INVUI[Streamlit Inventory :8502]
    INVUI -->|REST| Inventory
    Browser --> ChatUI[Streamlit chat :8503]
    ChatUI -->|REST| Chat
    Browser --> DashUI[Streamlit dashboard :8504]
    DashUI -->|REST| Dashboard
    Browser --> UsageUI[Streamlit usage insights :8505]
    UsageUI -->|operational REST APIs| MCP
    Chat <-->|messages and tool requests| Model[Ollama Cloud GPT-OSS]
    Dashboard <-->|layout prompt and JSON| Model
    Chat -->|MCP client| MCP[MCP server :8003]
    Dashboard -->|MCP client| MCP
    MCP -->|REST| HRMS[HRMS :8001]
    MCP -->|REST| Inventory[Inventory :8002]
    Inventory -->|validate employee| HRMS
    HRMS --> Mongo[(One MongoDB cluster)]
    Inventory --> Mongo
    MCP -->|usage events and preference memory| Mongo
```

| Term | Meaning in this project |
|---|---|
| REST API | A normal HTTP interface, such as `GET /employees/EMP001`. HRMS and Inventory implement business rules behind these endpoints. |
| MCP server | Publishes tool names, descriptions, argument schemas, and results through a standard protocol. It calls the REST APIs. |
| MCP client | Connects, initializes a session, discovers tools, and invokes them. Both AI apps use the client in [ai_runtime.py](ai_runtime.py). |
| Host | The application coordinating the model, tools, and UI. Chat and the dashboard are hosts. |
| LLM | Ollama Cloud's `gpt-oss:120b` model. It generates chat responses and dashboard layouts. |
| Tool | A capability such as `inventory_get_item_owners`. A tool may wrap one REST request or compose several. |

When you ask chat for laptop owners, the host sends discovered tool descriptions to the model. The model requests a tool call. The host executes it through MCP and sends the result back to the model to produce an answer. Ollama does not connect to MCP itself.

The dashboard uses a fixed retrieval flow: it fetches both complete datasets through MCP, joins them in Python, and then asks the model to choose a layout. The model supplies no calculated values or executable application code.

HRMS and Inventory own their business collections. MCP owns tool-usage events and preference memory in the same database; it still accesses business records through REST and has no LLM integration. The AI hosts access memory through MCP, with no direct database access.

## 2. Install the prerequisites

Use **Windows PowerShell**. All project commands in these tutorials run from the repository root, not from an app folder:

```powershell
Set-Location C:\Salmon\Simplilearn\MCP
```

If you copied the project elsewhere, substitute that location.

You need Python 3.11+, a MongoDB deployment, and an Ollama Cloud API key for the AI exercises. Dependencies are pinned in [requirements.txt](requirements.txt); [requirements-dev.txt](requirements-dev.txt) adds the offline test tools. Node.js is optional for MCP Inspector. The browser pages need no Node.js build step.

### Option A: use uv

If needed, install uv using the [official Windows instructions](https://docs.astral.sh/uv/getting-started/installation/):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Reopen PowerShell if required for PATH changes. From the repository root:

```powershell
uv --version
uv python install 3.11
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
.venv\Scripts\python.exe --version
```

### Option B: use Python and pip

Install Python 3.11+ from the [official Windows downloads](https://www.python.org/downloads/windows/). With the `py` launcher:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe --version
```

If you have `python` instead of `py`, verify `python --version` is at least 3.11 and use `python -m venv .venv` for the first command. Choose one installation option; do not recreate an environment that already works.

The remaining commands call the environment's Python directly. Activation and changes to PowerShell's activation policy are unnecessary.

## 3. Configure MongoDB and Ollama Cloud

### Create the local configuration file

Copy the template only when `.env` does not already exist:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
notepad .env
```

Fill in your own credentials in the editor. The examples below contain placeholders. The existing [.gitignore](.gitignore) excludes `.env` from source control.

[settings.py](settings.py) loads the root `.env` with `override=True`, so that file takes precedence over inherited environment variables. Restart affected processes after changing it.

| Variable | Default/template value | Used by |
|---|---|---|
| `MONGODB_URI` | `mongodb://localhost:27017` | HRMS, Inventory, MCP, seed and connectivity scripts |
| `MONGODB_DATABASE` | `mcp_learning` | Four collections in the same database |
| `OLLAMA_API_KEY` | Empty; fill in your key | Shared AI runtime |
| `OLLAMA_HOST` | `https://ollama.com` | Base URL for native `/api/chat` requests |
| `OLLAMA_MODEL` | `gpt-oss:120b` | Model requested by both AI apps |
| `HRMS_URL` | `http://127.0.0.1:8001` | Streamlit HRMS UI, Inventory validation and MCP upstream requests |
| `INVENTORY_URL` | `http://127.0.0.1:8002` | Streamlit Inventory UI and MCP upstream inventory requests |
| `MCP_URL` | `http://127.0.0.1:8003/mcp` | Both AI apps' MCP clients |
| `MCP_API_URL` | `http://127.0.0.1:8003` | Tool-usage Streamlit UI's operational REST API; no `/mcp` suffix |
| `CHAT_URL` | `http://127.0.0.1:8004` | Streamlit chat frontend's FastAPI backend |
| `DASHBOARD_URL` | `http://127.0.0.1:8005` | Streamlit dashboard frontend's FastAPI backend |

### Choose a MongoDB deployment

**MongoDB Atlas:** create or reuse a cluster in an Atlas project. Create a database user with read/write access to `mcp_learning`, add your current machine's public IP to the network access list, and copy the driver connection string from the cluster's connection workflow. See the [Atlas connection guide](https://www.mongodb.com/docs/atlas/connect-to-database-deployment/).

Replace the username/password placeholders in that URI and set it in `.env`:

```dotenv
MONGODB_URI=mongodb+srv://DB_USER:ENCODED_PASSWORD@cluster0.example.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=mcp_learning
```

Use your actual cluster hostname. Percent-encode special characters in credentials as described in [MongoDB connection strings](https://www.mongodb.com/docs/manual/reference/connection-string/). The database user's password is distinct from your Atlas account password. This code does not read separate `MONGODB_USERNAME` or `MONGODB_PASSWORD` variables.

**Local MongoDB:** install and start [MongoDB Community Server on Windows](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-windows/). For a local server without authentication, retain `MONGODB_URI=mongodb://localhost:27017`. Otherwise use its authenticated URI. MongoDB Compass is optional for inspecting data; Compass alone does not run a database server.

Both options use the same structure:

```text
One MongoDB cluster / deployment
└── mcp_learning
    ├── employees          # owned by HRMS
    ├── inventory_items    # owned by Inventory
    ├── tool_usage_events  # owned by MCP; 90-day retention
    └── user_preferences   # owned by MCP; no expiration
```

### Configure Ollama Cloud

Sign in to Ollama and create a key in [API key settings](https://ollama.com/settings/keys). Set `OLLAMA_API_KEY` in `.env`. Keep `OLLAMA_HOST=https://ollama.com` and `OLLAMA_MODEL=gpt-oss:120b` for this project. The runtime sends the key in a server-side Bearer header. Direct Cloud requests need no local Ollama installation or model download; see the [Ollama Cloud guide](https://docs.ollama.com/cloud).

The REST and MCP Inspector exercises work without an Ollama key. Chat and dashboard generation require the key and model access. Cloud checks and model requests consume your account's usage allowance.

## 4. Seed and start the apps

### Insert the demo records

This creates indexes and inserts missing fictional records into your configured database:

```powershell
.venv\Scripts\python.exe seed.py
```

On a new database, expect 30 employees and 60 individual inventory units. Departments are Engineering, Finance, People, and Sales. Inventory includes assigned, available, maintenance, and retired items.

Seeding uses stable IDs with `$setOnInsert`. Rerunning preserves changed records, assignments, and existing joining dates. Dates are based on the first insertion, so a later question about "this month" may return fewer employees. Seeding is not a reset command.

### Start all five together

```powershell
.venv\Scripts\python.exe run.py
```

Wait for the application-startup messages. If any process exits, the runner stops its remaining children. **Ctrl+C** stops the group.

### Or start each app in its own terminal

Open five PowerShell terminals at the repository root. Start HRMS and Inventory first, then MCP, then the two AI apps. Choose this method or `run.py`; starting both competes for the same ports.

HRMS:

```powershell
.venv\Scripts\python.exe -m uvicorn HRMS.main:app --host 127.0.0.1 --port 8001
```

Inventory:

```powershell
.venv\Scripts\python.exe -m uvicorn Inventory_management.main:app --host 127.0.0.1 --port 8002
```

MCP server:

```powershell
.venv\Scripts\python.exe -m uvicorn MCP_server.main:app --host 127.0.0.1 --port 8003
```

AI chat assistant:

```powershell
.venv\Scripts\python.exe -m uvicorn AI_chat_assistant.main:app --host 127.0.0.1 --port 8004
```

AI dashboard:

```powershell
.venv\Scripts\python.exe -m uvicorn AI_dashboard_generation.main:app --host 127.0.0.1 --port 8005
```

Stop an individual service with Ctrl+C in its terminal. URL variables do not change Uvicorn listening ports; the command's `--port` and corresponding configuration URLs must agree. `run.py` uses the fixed ports above.

### Start the Streamlit HRMS UI separately

The root requirements include Streamlit 1.66.0. If upgrading an existing environment, reinstall the requirements before launching the UI:

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
.venv\Scripts\python.exe -m streamlit run HRMS/ui/main.py --server.address 127.0.0.1 --server.port 8501
```

For a pip-created environment, use `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` instead of the `uv` install command. Run the launch command from the repository root in another terminal and stop it with Ctrl+C. Only HRMS on 8001 and its MongoDB connection are needed; MCP, Inventory, Ollama and an API key are not required. `run.py` still launches only the original five FastAPI processes.

Open [the HRMS UI](http://127.0.0.1:8501). The spacious purple workspace uses native Streamlit controls: **Overview** has summary cards and chart panels; **Employee directory** has compact filters, a table/pagination toolbar, exact-ID lookup, and **Profile / Edit details** views; **Add employee** groups identity/contact and role/joining fields. Optional dates are under **More filters**, and status/page-size choices use segmented controls. Writes happen only on form submission and update the configured dummy database. See [the HRMS UI guide](HRMS/README.md#start-the-streamlit-employee-ui) for details.

### Start the other Streamlit workspaces

All five interfaces use the root [.streamlit/config.toml](.streamlit/config.toml) purple theme. Run each command in its own PowerShell terminal from the repository root. The dependencies are already included in the requirements above. Keep the required FastAPI backend processes running; `run.py` launches those five backends and does not launch Streamlit. The original chat/dashboard pages on 8004/8005 remain available.

Inventory overview, directory and current assignments; requires Inventory and MongoDB, plus HRMS for new assignments:

```powershell
.venv\Scripts\python.exe -m streamlit run Inventory_management/ui/main.py --server.address 127.0.0.1 --server.port 8502
```

Chat with session history and expandable MCP tool traces; requires chat on 8004, MCP, both business APIs, MongoDB and Ollama Cloud:

```powershell
.venv\Scripts\python.exe -m streamlit run AI_chat_assistant/ui/main.py --server.address 127.0.0.1 --server.port 8503
```

Dashboard instructions, regeneration and native count cards/charts/tables; requires dashboard on 8005 and the same MCP/data/Cloud dependencies:

```powershell
.venv\Scripts\python.exe -m streamlit run AI_dashboard_generation/ui/main.py --server.address 127.0.0.1 --server.port 8504
```

Tool-usage insights, including trends, performance and call metadata; requires only the MCP API on 8003 and its MongoDB connection:

```powershell
.venv\Scripts\python.exe -m streamlit run MCP_server/ui/main.py --server.address 127.0.0.1 --server.port 8505
```

Open the corresponding addresses below. Stop each interface with Ctrl+C in its terminal. For a port conflict, stop the previous instance before starting another; changing a Streamlit port does not change the backend URL. Root `.env` remains the configuration source; existing files need no edits when using default URLs. No UI connects directly to MongoDB, the MCP protocol, or Ollama. Chat and AI dashboard state is held in the Streamlit browser session, with no saved conversations or dashboards. Requests are never automatically retried, and ordinary reruns do not repeat chat or generation calls.

The usage workspace has **Overview**, **Tool performance**, and **Call explorer** pages with shared filters and manual Refresh. It reads `/usage/insights` and `/usage/events` through `MCP_API_URL`; these ordinary REST requests do not generate tool-usage events. No model request or business API is needed to inspect existing logs. Follow the [usage dashboard tutorial](MCP_server/README.md#streamlit-tool-usage-insights) for metric definitions and request-group drill-down.

| Address | What to expect |
|---|---|
| [HRMS docs](http://127.0.0.1:8001/docs) | Five employee operations, plus health |
| [Inventory docs](http://127.0.0.1:8002/docs) | Four item operations, plus health |
| `http://127.0.0.1:8003/mcp` | MCP protocol endpoint; connect with a client or Inspector |
| [Chat](http://127.0.0.1:8004) | Conversation page and expandable tool traces |
| [Dashboard](http://127.0.0.1:8005) | Instruction form and generated cards, charts, and tables |
| [HRMS UI](http://127.0.0.1:8501) | Streamlit employee overview, directory, details and create/edit forms |
| [Inventory UI](http://127.0.0.1:8502) | Streamlit complete counts, paginated units, explicit assign/return forms |
| [Streamlit chat](http://127.0.0.1:8503) | Chat messages, read-only suggestions and returned tool traces |
| [Dashboard studio](http://127.0.0.1:8504) | Instruction form, calculated widgets, regeneration and layout JSON |
| [Tool-usage insights](http://127.0.0.1:8505) | Complete usage aggregates, tool performance and paginated call metadata |

Every FastAPI app exposes `/health`. HRMS, Inventory and MCP ping MongoDB; the AI health routes only confirm that their app is serving and do not verify Ollama or MCP connectivity. Streamlit has its own `/_stcore/health` endpoint, which does not test its backend.

## 5. Follow the first exercises

### Exercise 1: read REST data

These commands do not change records:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/employees/EMP001' | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/employees/summary' | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri 'http://127.0.0.1:8002/items?employee_id=EMP001&limit=100' | ConvertTo-Json -Depth 6
```

Expect employee details, employee counts, and current assignments. List responses include `items`, `total`, `limit`, `offset`, and `has_more`. An empty result is valid. Numbers depend on the current database state.

For optional write exercises, follow the [HRMS](HRMS/README.md) and [Inventory](Inventory_management/README.md) tutorials. They explain the effects before creating employees or assigning items.

### Exercise 2: discover tools without an LLM

Install a supported [Node.js](https://nodejs.org/en/download) release if you want MCP Inspector. Launch it from a separate terminal:

```powershell
npx @modelcontextprotocol/inspector
```

Open the local Inspector address it prints. Select **Streamable HTTP**, connect to `http://127.0.0.1:8003/mcp`, and list tools. Expect thirteen tools with seven read-only annotations; see the [full catalog](MCP_server/README.md#the-thirteen-tool-catalog).

Call `hrms_get_employee_summary` with no arguments. Then call `inventory_get_item_owners` with:

```json
{"item_type": "laptop"}
```

Or look up one physical unit:

```json
{"item_id": "ITEM001"}
```

Supply exactly one selector. The result contains distinct current owners' `employee_id`, `full_name`, and `email`. This tool composes Inventory and HRMS calls without adding a tenth REST API. No model is involved in this exercise.

### Exercise 3: ask chat to use tools

Open [chat](http://127.0.0.1:8004) and try:

- "Show employee counts by department."
- "List laptop owners with their employee IDs, names and emails."
- "What items are currently assigned to EMP001?"

Open the **MCP trace** under the reply. Inspect the tool name, arguments, result, and error flag. The exact tool sequence depends on the model. Chat also exposes write tools: explicit change requests can update dummy records. Its intent rules are model instructions in this learning implementation, not production authorization.

### Exercise 4: generate a dashboard

Open [the dashboard](http://127.0.0.1:8005) and enter:

> Show total employees, employee count by department, and available devices by item type.

Expect supported cards, bar charts, or tables. Open **MCP calls & layout JSON** to compare retrieval calls with the layout. Python calculates values from complete lists; AI selects the presentation. Only `count` metrics are supported. The [dashboard tutorial](AI_dashboard_generation/README.md) explains dataset meanings and includes layout JSON.

### Permanent preferences and tool statistics

In either Streamlit AI app, enter a **Demo user ID** such as `alice` and click **Use profile**. The original HTML pages also have a demo-user input. Use the same ID in chat and dashboard. Blank means anonymous use with memory disabled. IDs are case-sensitive demo profiles, not authentication; anyone who supplies an ID can use that profile.

The following chat requests **write or delete preference data** in MongoDB, without modifying employees or inventory:

- “Remember that I prefer concise answers.”
- “Remember for dashboards that I prefer bar charts.”
- “What preferences have you saved for me?”
- “Forget my concise-answer preference.”

Preferences load through MCP at the beginning of each identified request and appear in its trace. They survive New conversation and service restarts. Switching users clears local chat/dashboard state. Current instructions and business rules take precedence over saved preferences. A failed memory read stops an identified request; it is not silently treated as an empty profile. Anonymous API requests remain supported.

For direct API use, add `user_id` to the existing request body:

```json
{"user_id": "alice", "message": "Explain the MCP learning lab.", "history": []}
```

```json
{"user_id": "alice", "instruction": "Show employee counts by department."}
```

Inspect statistics without a model request:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8003/usage/stats' | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri 'http://127.0.0.1:8003/usage/stats?user_id=alice&client_app=chat&date_from=2026-10-01&date_to=2026-10-31' | ConvertTo-Json -Depth 8
```

Dates are illustrative inclusive UTC calendar days. Statistics include overall/per-tool calls, successes, errors, cancellations and average duration. MCP records metadata only, with no arguments, results or conversation transcripts. Events expire after 90 days through MongoDB's asynchronous TTL cleanup; preferences have no expiration. Logging is best effort after startup, so statistics may have gaps during storage failures. The statistics endpoint itself is not an MCP tool and is not counted. See the [MCP storage tutorial](MCP_server/README.md#mongodb-usage-events-and-preference-memory) for schemas, headers and direct tool examples.

## 6. Explore the code and extend it

| Location | Responsibility |
|---|---|
| Each app's `main.py` | FastAPI construction, route registration, and resource lifecycle |
| `routes/` | HTTP inputs and outputs |
| `services/` | Business behavior or orchestration |
| `schemas.py` | Pydantic models or MCP result/annotation exports |
| `config.py` | App configuration and constants |
| HRMS/Inventory `database.py` | Business collection connections and indexes |
| [MCP database setup](MCP_server/database.py) | Operational collections, retention and browsing indexes |
| [Business tools](MCP_server/tools/business_tools.py) / [memory tools](MCP_server/tools/memory_tools.py) | Thirteen typed functions exposed to MCP clients |
| [Usage analytics](MCP_server/services/usage_service.py) | Complete event aggregates and paginated metadata for the operational REST APIs |
| [settings.py](settings.py) | Root `.env` loading |
| [ai_runtime.py](ai_runtime.py) | MCP connection, schema mapping, and native Ollama HTTP requests |
| [HRMS UI](HRMS/ui/main.py) | Streamlit navigation and page modules; [HTTP client](HRMS/ui/services/hrms_client.py) calls HRMS REST APIs |
| [Inventory UI](Inventory_management/ui/main.py) | Inventory overview, directory and explicit assign/return forms |
| [Chat UI](AI_chat_assistant/ui/main.py) | Conversation state, demo profile selection and returned tool traces |
| [AI dashboard UI](AI_dashboard_generation/ui/main.py) | Instruction form and native rendering of server-calculated widgets |
| [Usage UI](MCP_server/ui/main.py) | Manual-refresh insights, tool performance and call explorer; read-only REST access |
| [seed.py](seed.py) | Insert-only demo data |
| [tests](tests/) | API, MCP transport, chat, dashboard, and composite-tool checks |

To add a capability, first check whether an existing REST endpoint provides the data. Add service logic where needed, register a typed MCP function with a clear description and read/write annotation, then try it in Inspector. Update the dashboard's allowlist if the new read-only capability should be permitted. Chat discovers tools per request. Restart processes after source changes unless you explicitly use Uvicorn reload support.

The pinned MCP SDK is 2.3.0 and uses `MCPServer`. Older SDK tutorials can have different class names and Python attributes; follow this codebase's interfaces. The [MCP tutorial](MCP_server/README.md) shows the connection and mounting pattern.

## 7. Verify and troubleshoot

### Offline checks

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests use in-memory MongoDB and mocked model replies, including real MCP transport on temporary localhost ports. They do not need your database or Cloud key. Install [requirements-dev.txt](requirements-dev.txt) if pytest is missing.

The [Streamlit workspace tests](tests/test_streamlit_workspaces.py) use mocked HTTP clients and AppTest to exercise navigation, complete Inventory pagination, explicit writes, uncertain outcomes, conversation history, returned traces, dashboard rendering and failed regeneration. Run them independently with `.venv\Scripts\python.exe -m pytest -q tests/test_streamlit_workspaces.py`. They make no live database writes or Cloud calls.

The [usage analytics tests](tests/test_usage_insights.py) and [usage UI tests](tests/test_usage_ui.py) cover MongoDB aggregation, UTC windows, timeline gaps, filters, read-only metadata pagination, stable selection, request groups and stale snapshots. Run `.venv\Scripts\python.exe -m pytest -q tests/test_usage_insights.py tests/test_usage_ui.py`; these also use in-memory MongoDB and mocked HTTP, without Cloud calls.

### Explicit live checks

Run the level you want to check:

| Command | What it checks |
|---|---|
| `.venv\Scripts\python.exe smoke_check.py` | MongoDB connection |
| `.venv\Scripts\python.exe smoke_check.py --apps` | MongoDB, five app health routes, discovery, summary and owner lookup; no model requests |
| `.venv\Scripts\python.exe smoke_check.py --cloud` | MongoDB and a real Ollama tool-calling request |
| `.venv\Scripts\python.exe smoke_check.py --cloud --apps` | All of the above, plus real chat and dashboard requests |

Expect `PASS` messages; failures produce `FAIL` and a nonzero exit code. Cloud variants consume model usage. Live smoke calls do not modify business records or preferences; MCP calls append usage events. Code: [smoke_check.py](smoke_check.py).

### Common problems

| Symptom | What to check |
|---|---|
| `uv`, `py`, or `python` not found | Complete an installation option and reopen PowerShell after PATH changes. |
| `No module named HRMS` or another project import | Run from the repository root with module targets such as `HRMS.main:app`. |
| MongoDB startup/seed failure | Check the running server/cluster, database-user credentials, encoded URI characters, and Atlas access for your current IP. |
| Ollama authentication/model error | Check the key in root `.env`, Cloud host, model access and usage; restart AI apps after edits. |
| Connection refused or dependency error | Check HRMS, Inventory and MCP at their configured URLs and inspect their terminal logs. |
| Address already in use / Windows error 10048 | Stop the previous copy in its owning terminal; avoid running `run.py` alongside individual services. |
| Inspector shows fewer than thirteen tools | Restart MCP with current source, reconnect, and list tools again. |
| Saved preferences cannot be loaded | Check MCP and MongoDB; identified requests require a successful memory read. |
| `/mcp` shows no web page | Connect using MCP Inspector or an MCP client. It is a protocol endpoint. |
| Invalid dashboard layout after repair | Try a simpler count-based instruction; arbitrary fields, metrics and executable code are unsupported. |
| Incomplete/changed dashboard data | Retry when data is stable; it refuses totals for incomplete pagination and large datasets can exceed twenty calls. |
| Charts appear as tables | Chart.js loads from a CDN; the UI falls back to tables when unavailable. |
| A write timed out or the model failed after it | Read the record and inspect the trace before retrying; the change may have completed. |

To identify an occupied port without stopping anything:

```powershell
Get-NetTCPConnection -LocalPort 8003 -State Listen | Select-Object LocalAddress, LocalPort, OwningProcess
```

These are localhost learning apps with fictional data. Production authentication, audit history, deployment, saved dashboards, payroll, and quantity-based stock are outside the project. See [MCP_system_plan.md](MCP_system_plan.md) for the architecture; the app tutorials and source describe current behavior.

## 8. Keep local files out of Git

[.gitignore](.gitignore) excludes local `.env` files, Streamlit secrets, virtual environments, Python/test caches, coverage reports, logs, PID files, downloaded Node tooling, editor settings and machine-specific Claude settings. Root `dump/`, `mongodump/` and `exports/` directories are reserved for local database backups and exported data.

Keep [.env.example](.env.example), [.streamlit/config.toml](.streamlit/config.toml), source files, tests and tutorials in version control. The two installed `developing-with-streamlit` entries under `.agents/skills/` and `.claude/skills/` are local symbolic links into `.venv/Lib/site-packages/streamlit/`; they are ignored without deleting them. Other self-contained shared skill sources remain eligible for version control. Configuration stays in the existing root `.env`; copying the example is only needed for a new checkout.

Before committing, inspect filenames and changes from the repository root:

```powershell
git status --short
git diff --stat
git diff --cached --name-only
git ls-files -ci --exclude-standard
```

The last command should print nothing: it lists files already tracked by Git that now match ignore rules. Ignore rules do not untrack an existing file. To check the intended local exclusions without opening credentials:

```powershell
git check-ignore .env .streamlit/secrets.toml .venv/pyvenv.cfg .logs/app.log .claude/settings.local.json dump/example.bson exports/example.json
```

The configuration example, shared theme and application source should remain visible in `git status` until committed. The parent skill directories are not blanket-ignored; only the two installed Streamlit links are excluded.
