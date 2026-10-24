"""Headless UI checks use mocked HTTP and in-memory REST handlers only."""

import copy
import json
from pathlib import Path
import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest
from Inventory_management.services import inventory_service
from Inventory_management.ui.services import inventory_client
from Inventory_management.ui.services.inventory_client import (
    InventoryClient,
    ApiError as InventoryError,
)
from AI_chat_assistant.ui.services import chat_client
from AI_chat_assistant.ui.services.chat_client import ChatClient, ApiError as ChatError
from AI_chat_assistant.ui.state import history_for_request
from AI_dashboard_generation.ui.services import dashboard_client
from AI_dashboard_generation.ui.services.dashboard_client import (
    DashboardClient,
    ApiError as DashboardError,
)
from AI_dashboard_generation.services.dashboard_service import render_widgets
from AI_dashboard_generation.schemas import DashboardSpec

ROOT = Path(__file__).resolve().parents[1]


def button(app, label):
    return next(value for value in app.button if value.label == label)


def open_app(package, page=None):
    app = AppTest.from_file(ROOT / package / "ui" / "main.py", default_timeout=20).run()
    assert not app.exception
    if page:
        app.switch_page(f"app_pages/{page}.py").run(timeout=20)
        assert not app.exception
    return app


@pytest.fixture
def inventory_ui(clients, seeded, monkeypatch):
    calls = []

    def validate_employee(employee_id):
        response = clients[0].get(f"/employees/{employee_id}")
        if response.status_code == 404:
            raise HTTPException(404, "Employee not found")
        if response.json()["status"] not in ("joining", "active"):
            raise HTTPException(
                409, "Only joining or active employees can receive items"
            )

    monkeypatch.setattr(inventory_service, "validate_employee", validate_employee)

    def handle(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, dict(request.url.params), body))
        response = clients[1].request(
            request.method, request.url.path, params=dict(request.url.params), json=body
        )
        return httpx.Response(response.status_code, json=response.json())

    client = InventoryClient(
        "http://inventory.test", transport=httpx.MockTransport(handle)
    )
    monkeypatch.setattr(inventory_client, "get_client", lambda: client)
    return client, calls


def select_item(app, item_id):
    app.text_input(key="lookup_item_id").set_value(item_id)
    button(app, "Open by ID").click().run()
    assert not app.exception


def posts(calls):
    return [call for call in calls if call[0] == "POST"]


def test_inventory_client_reads_and_assignment_lifecycle(inventory_ui):
    client, calls = inventory_ui
    assert len(client.all_items()) == 60
    assert (
        client.list_items(
            category="device", status="available", item_type="laptop", limit=2
        ).total
        > 0
    )
    assert calls[-1][2]["limit"] == "2"
    assert client.get_item("ITEM021").status == "available"
    assert client.assign_item("ITEM021", "EMP001").assignment.employee_id == "EMP001"
    with pytest.raises(InventoryError, match="not available"):
        client.assign_item("ITEM021", "EMP002")
    with pytest.raises(InventoryError, match="not currently assigned"):
        client.return_item("ITEM021", "EMP002")
    assert client.return_item("ITEM021", "EMP001").assignment is None
    with pytest.raises(InventoryError, match="Employee not found"):
        client.assign_item("ITEM021", "MISSING")
    with pytest.raises(InventoryError, match="joining or active"):
        client.assign_item("ITEM021", "EMP010")
    with pytest.raises(ValidationError):
        client.get_item("../item")
    with pytest.raises(ValidationError):
        client.assign_item("ITEM021", "")


def test_inventory_complete_pagination(inventory_ui, seeded):
    client, calls = inventory_ui
    item = seeded.inventory_items.find_one({"_id": "ITEM060"})
    for index in range(61, 166):
        seeded.inventory_items.insert_one({**item, "_id": f"ITEM{index:03}"})
    assert len(client.all_items()) == 165
    assert [call[2]["offset"] for call in calls] == ["0", "100"]


@pytest.mark.parametrize(
    "failure", ["total", "duplicate", "empty", "offset", "has_more"]
)
def test_inventory_inconsistent_pagination_rejected(inventory_ui, monkeypatch, failure):
    client, _ = inventory_ui
    initial = client.list_items(limit=100).model_dump()
    if failure == "total":
        initial["total"] += 1
    elif failure == "duplicate":
        initial["items"][1] = initial["items"][0]
    elif failure == "empty":
        initial["items"] = []
        initial["has_more"] = True
    elif failure == "offset":
        initial["offset"] = 1
    else:
        initial["has_more"] = True
    from Inventory_management.schemas import ItemPage

    monkeypatch.setattr(
        client, "list_items", lambda **kwargs: ItemPage.model_validate(initial)
    )
    with pytest.raises(InventoryError):
        client.all_items()


def test_inventory_overview_filters_paging_selection_and_no_rerun_writes(inventory_ui):
    _, calls = inventory_ui
    app = open_app("Inventory_management")
    assert [value.value for value in app.metric] == ["60", "35", "20", "3", "2"]
    app.switch_page("app_pages/directory.py").run()
    assert len(app.dataframe[0].value) == 20
    app.selectbox(key="item_selector").select("ITEM001").run()
    button(app, "Next").click().run()
    assert app.session_state["selected_item_id"] == "ITEM001"
    assert app.session_state["item_offset"] == 20
    app.get_by_key("item_limit").set_value(50).run()
    assert app.session_state["item_offset"] == 0
    assert len(app.dataframe[0].value) == 50
    app.get_by_key("filter_category").set_value("device")
    app.get_by_key("filter_status").set_value("assigned")
    app.text_input(key="filter_type").set_value("laptop")
    app.text_input(key="filter_employee").set_value("EMP001")
    button(app, "Apply filters").click().run()
    assert app.session_state["item_filters"] == {
        "category": "device",
        "status": "assigned",
        "item_type": "laptop",
        "employee_id": "EMP001",
    }
    assert len(app.dataframe[0].value) == 1
    app.run()
    assert not posts(calls) and not app.exception


def test_inventory_explicit_assign_return_and_validation(inventory_ui):
    _, calls = inventory_ui
    app = open_app("Inventory_management", "directory")
    select_item(app, "ITEM021")
    button(app, "Assign item").click().run()
    assert app.error and not posts(calls)
    app.text_input(key="assignee_ITEM021").set_value("EMP010")
    button(app, "Assign item").click().run()
    assert app.error and app.text_input(key="assignee_ITEM021").value == "EMP010"
    app.text_input(key="assignee_ITEM021").set_value("EMP001")
    button(app, "Assign item").click().run()
    assert not app.exception and app.success
    app.run()
    assert (
        len(posts(calls)) == 2
    )  # rejected inactive employee and successful assignment
    button(app, "Return item").click().run()
    assert posts(calls)[-1][3] == {"employee_id": "EMP001"}
    app.run()
    assert len(posts(calls)) == 3


def test_inventory_missing_invalid_ids_and_non_actionable_items(inventory_ui):
    _, calls = inventory_ui
    app = open_app("Inventory_management", "directory")
    select_item(app, "MISSING")
    assert app.error
    app.text_input(key="lookup_item_id").set_value("../bad")
    button(app, "Open by ID").click().run()
    assert app.error
    for item_id in ["ITEM026", "ITEM034"]:
        select_item(app, item_id)
        assert not any(
            value.label in {"Assign item", "Return item"} for value in app.button
        )
    assert not posts(calls)


def test_inventory_empty_and_unavailable(inventory_ui, seeded, monkeypatch):
    client, _ = inventory_ui
    seeded.inventory_items.delete_many({})
    app = open_app("Inventory_management")
    assert [value.value for value in app.metric] == ["0"] * 5 and app.info
    app.switch_page("app_pages/directory.py").run()
    assert app.info and not app.dataframe
    monkeypatch.setattr(
        client,
        "all_items",
        lambda: (_ for _ in ()).throw(InventoryError("Inventory unavailable")),
    )
    app.switch_page("app_pages/overview.py").run()
    assert app.error and not app.metric and not app.exception


def test_inventory_uncertain_write_requires_successful_reload(
    inventory_ui, monkeypatch
):
    client, calls = inventory_ui
    attempts = []

    def uncertain(*args):
        attempts.append(args)
        raise InventoryError("Unknown outcome", uncertain=True)

    monkeypatch.setattr(client, "assign_item", uncertain)
    app = open_app("Inventory_management", "directory")
    select_item(app, "ITEM021")
    app.text_input(key="assignee_ITEM021").set_value("EMP001")
    button(app, "Assign item").click().run()
    assert button(app, "Assign item").disabled and app.warning
    original_get = client.get_item
    monkeypatch.setattr(
        client,
        "get_item",
        lambda *args: (_ for _ in ()).throw(InventoryError("Offline")),
    )
    button(app, "Reload item").click().run()
    assert "ITEM021" in app.session_state["uncertain_items"]
    monkeypatch.setattr(client, "get_item", original_get)
    app.run()
    assert button(app, "Assign item").disabled
    button(app, "Reload item").click().run()
    assert not button(app, "Assign item").disabled
    assert len(attempts) == 1 and not posts(calls)


def test_inventory_changed_owner_invalidates_old_return_form(inventory_ui, seeded):
    _, calls = inventory_ui
    app = open_app("Inventory_management", "directory")
    select_item(app, "ITEM001")
    seeded.inventory_items.update_one(
        {"_id": "ITEM001"}, {"$set": {"assignment.employee_id": "EMP002"}}
    )
    button(app, "Return item").click().run()
    assert not app.exception and not posts(calls)
    assert any("Assigned to EMP002" in text.value for text in app.text)
    button(app, "Return item").click().run()
    assert posts(calls)[0][3] == {"employee_id": "EMP002"}


def test_inventory_conflict_between_read_and_return(inventory_ui, seeded, monkeypatch):
    client, calls = inventory_ui
    original_return = client.return_item

    def competing_return(item_id, employee_id):
        seeded.inventory_items.update_one(
            {"_id": item_id}, {"$set": {"assignment.employee_id": "EMP002"}}
        )
        return original_return(item_id, employee_id)

    monkeypatch.setattr(client, "return_item", competing_return)
    app = open_app("Inventory_management", "directory")
    select_item(app, "ITEM001")
    button(app, "Return item").click().run()
    assert not app.exception and app.error
    assert (
        seeded.inventory_items.find_one({"_id": "ITEM001"})["assignment"]["employee_id"]
        == "EMP002"
    )
    app.run()
    assert len(posts(calls)) == 1


def test_inventory_directory_unavailable_does_not_hide_exact_lookup(
    inventory_ui, monkeypatch
):
    client, _ = inventory_ui
    app = open_app("Inventory_management", "directory")
    monkeypatch.setattr(
        client,
        "list_items",
        lambda **kwargs: (_ for _ in ()).throw(InventoryError("Inventory unavailable")),
    )
    app.run()
    assert app.error and not app.dataframe
    select_item(app, "ITEM001")
    assert not app.exception and app.session_state["selected_item_id"] == "ITEM001"


def test_clients_use_local_url_configuration(monkeypatch):
    monkeypatch.setenv("INVENTORY_URL", "http://inventory.test:9002/")
    monkeypatch.setenv("CHAT_URL", "http://chat.test:9004/")
    monkeypatch.setenv("DASHBOARD_URL", "http://dashboard.test:9005/")
    assert InventoryClient().base_url == "http://inventory.test:9002"
    assert ChatClient().base_url == "http://chat.test:9004"
    assert DashboardClient().base_url == "http://dashboard.test:9005"


CHAT_RESULT = {
    "answer": "One employee holds a laptop.",
    "trace": [
        {
            "tool": "inventory_get_item_owners",
            "arguments": {"item_type": "laptop"},
            "is_error": False,
            "result": {
                "items": [
                    {
                        "employee_id": "EMP001",
                        "full_name": "Asha Rao",
                        "email": "asha@example.test",
                    }
                ]
            },
        }
    ],
}


@pytest.fixture
def chat_ui(monkeypatch):
    calls, responses = [], [CHAT_RESULT]

    def handle(request):
        calls.append(json.loads(request.content))
        result = responses.pop(0) if len(responses) > 1 else responses[0]
        return (
            result
            if isinstance(result, httpx.Response)
            else httpx.Response(200, json=result)
        )

    client = ChatClient("http://chat.test", transport=httpx.MockTransport(handle))
    monkeypatch.setattr(chat_client, "get_client", lambda: client)
    return client, calls, responses


def test_chat_suggestions_history_trace_new_conversation(chat_ui):
    _, calls, _ = chat_ui
    app = open_app("AI_chat_assistant")
    assert not calls
    button(app, "Laptop owners").click().run()
    assert len(calls) == 1 and calls[0]["history"] == []
    assert len(app.chat_message) == 2 and app.expander
    assert "inventory_get_item_owners" in app.subheader[-1].value
    app.run()
    assert len(calls) == 1
    app.chat_input[0].set_value("What is their email?").run()
    assert len(calls) == 2 and len(calls[1]["history"]) == 2
    assert calls[1]["history"][1]["content"] == CHAT_RESULT["answer"]
    button(app, "New conversation").click().run()
    assert not app.chat_message and app.session_state["chat_turns"] == []
    assert len(calls) == 2


def test_chat_history_limits_and_local_validation(chat_ui):
    client, calls, _ = chat_ui
    history = history_for_request([{"role": "assistant", "content": "x" * 21000}] * 44)
    assert len(history) == 40 and all(len(turn["content"]) == 20000 for turn in history)
    with pytest.raises(ValidationError):
        client.send(" ", [])
    with pytest.raises(ValidationError):
        client.send("x" * 4001, [])
    assert not calls


def test_chat_tool_errors_are_visible_in_returned_trace(chat_ui):
    _, calls, responses = chat_ui
    failed_tool = copy.deepcopy(CHAT_RESULT)
    failed_tool["answer"] = "The item was not found."
    failed_tool["trace"][0]["is_error"] = True
    failed_tool["trace"][0]["result"] = {"code": 404, "message": "Item not found"}
    responses[:] = [failed_tool]
    app = open_app("AI_chat_assistant")
    app.chat_input[0].set_value("Find this item's owner").run()
    assert not app.exception and len(calls) == 1
    assert any("Tool error" in badge.value for badge in app.markdown)


def test_chat_demo_user_switch_clears_local_history_but_new_conversation_keeps_id(
    chat_ui,
):
    _, calls, _ = chat_ui
    app = open_app("AI_chat_assistant")
    app.text_input(key="demo_user_input").set_value("alice")
    button(app, "Use profile").click().run()
    button(app, "Laptop owners").click().run()
    assert calls[-1]["user_id"] == "alice"
    button(app, "New conversation").click().run()
    assert (
        not app.session_state["chat_turns"]
        and app.session_state["demo_user_id"] == "alice"
    )
    button(app, "Available laptops").click().run()
    app.text_input(key="demo_user_input").set_value("bob")
    button(app, "Use profile").click().run()
    assert not app.session_state["chat_turns"] and not app.chat_message
    app.text_input(key="demo_user_input").set_value("../invalid")
    button(app, "Use profile").click().run()
    assert app.session_state["demo_user_id"] == "bob" and app.error
    app.text_input(key="demo_user_input").set_value("")
    button(app, "Use profile").click().run()
    button(app, "Laptop owners").click().run()
    assert "user_id" not in calls[-1] and calls[-1]["history"] == []


def test_chat_failure_preserves_prompt_and_never_resubmits(chat_ui):
    _, calls, responses = chat_ui
    responses[:] = [httpx.Response(503, json={"detail": "MCP unavailable"})]
    app = open_app("AI_chat_assistant")
    app.chat_input[0].set_value("Assign ITEM021 to EMP001").run()
    assert not app.exception and app.error and app.warning
    assert app.text_area[0].value == "Assign ITEM021 to EMP001"
    assert not app.session_state["chat_turns"]
    app.run()
    assert len(calls) == 1
    responses[:] = [CHAT_RESULT]
    button(app, "Available laptops").click().run()
    assert len(calls) == 2 and not app.error


def dashboard_payload():
    spec = DashboardSpec.model_validate(
        {
            "title": "Demo snapshot",
            "widgets": [
                {"type": "card", "title": "Employees", "dataset": "employees"},
                {
                    "type": "card",
                    "title": "Missing items",
                    "dataset": "items",
                    "filters": {"item_type": "unknown"},
                },
                {
                    "type": "bar",
                    "title": "People by department",
                    "dataset": "employees",
                    "group_by": "department",
                },
                {
                    "type": "table",
                    "title": "Employees",
                    "dataset": "employees",
                    "columns": ["employee_id", "full_name"],
                },
                {
                    "type": "table",
                    "title": "Items by type",
                    "dataset": "items",
                    "group_by": "item_type",
                },
            ],
        }
    )
    datasets = {
        "employees": [
            {
                "employee_id": "EMP001",
                "full_name": "Asha Rao",
                "department": "Engineering",
            }
        ],
        "items": [{"item_id": "ITEM021", "item_type": "laptop"}],
        "assigned_items": [],
    }
    return {
        "title": spec.title,
        "spec": spec.model_dump(),
        "widgets": render_widgets(spec, datasets),
        "trace": [
            {
                "tool": "hrms_list_employees",
                "arguments": {"limit": 100, "offset": 0},
                "is_error": False,
            }
        ],
        "generated_at": "2026-10-24T10:00:00Z",
        "dataset_counts": {"employees": 1, "items": 1, "assigned_items": 0},
        "note": "Counts use complete fetched lists.",
    }


@pytest.fixture
def dashboard_ui(monkeypatch):
    calls, responses = [], [dashboard_payload()]

    def handle(request):
        calls.append(json.loads(request.content))
        result = responses.pop(0) if len(responses) > 1 else responses[0]
        return (
            result
            if isinstance(result, httpx.Response)
            else httpx.Response(200, json=result)
        )

    client = DashboardClient(
        "http://dashboard.test", transport=httpx.MockTransport(handle)
    )
    monkeypatch.setattr(dashboard_client, "get_client", lambda: client)
    return client, calls, responses


def test_dashboard_example_render_and_regenerate(dashboard_ui):
    _, calls, _ = dashboard_ui
    app = open_app("AI_dashboard_generation")
    assert button(app, "Regenerate").disabled and not calls
    button(app, "People overview").click().run()
    assert (
        app.text_area[0].value == "Show employee count by department and status."
        and not calls
    )
    button(app, "Generate dashboard").click().run()
    assert not app.exception and [metric.value for metric in app.metric] == ["1", "0"]
    assert len(app.dataframe) == 2 and app.expander
    assert list(app.dataframe[1].value.columns) == ["item_type", "count"]
    app.run()
    assert len(calls) == 1
    app.text_area(key="dashboard_instruction").set_value("Unused draft").run()
    button(app, "Regenerate").click().run()
    assert len(calls) == 2 and calls[0] == calls[1]


def test_dashboard_failure_keeps_previous_snapshot_and_instruction(dashboard_ui):
    _, calls, responses = dashboard_ui
    app = open_app("AI_dashboard_generation")
    app.text_area[0].set_value("Show people")
    button(app, "Generate dashboard").click().run()
    responses[:] = [
        httpx.Response(
            422, json={"detail": "Incomplete data: twenty-call limit reached"}
        )
    ]
    app.text_area[0].set_value("Show devices")
    button(app, "Generate dashboard").click().run()
    assert not app.exception and app.error and app.warning
    assert app.metric[0].value == "1"
    assert app.text_area[0].value == "Show devices"
    assert app.session_state["last_instruction"] == "Show people"
    app.run()
    assert len(calls) == 2


def test_dashboard_demo_user_switch_discards_previous_snapshot(dashboard_ui):
    _, calls, _ = dashboard_ui
    app = open_app("AI_dashboard_generation")
    app.text_input(key="demo_user_input").set_value("alice")
    button(app, "Use profile").click().run()
    app.text_area(key="dashboard_instruction").set_value("Show employees")
    button(app, "Generate dashboard").click().run()
    assert calls[-1]["user_id"] == "alice" and app.metric
    app.text_input(key="demo_user_input").set_value("bob")
    button(app, "Use profile").click().run()
    assert not app.exception and not app.metric
    assert app.session_state["dashboard_result"] is None
    assert app.text_area(key="dashboard_instruction").value == ""
    assert button(app, "Regenerate").disabled
    assert len(calls) == 1


def test_dashboard_empty_data_and_invalid_input(dashboard_ui):
    _, calls, responses = dashboard_ui
    app = open_app("AI_dashboard_generation")
    button(app, "Generate dashboard").click().run()
    assert app.error and not calls
    payload = dashboard_payload()
    for widget in payload["widgets"]:
        if widget["type"] == "card":
            widget["value"] = 0
        else:
            widget["rows"] = []
    responses[:] = [payload]
    app.text_area[0].set_value("Show empty company")
    button(app, "Generate dashboard").click().run()
    assert not app.exception and [metric.value for metric in app.metric] == ["0", "0"]
    assert len(app.info) == 3


@pytest.mark.parametrize(
    "kind", ["missing_value", "negative_count", "invalid_layout", "missing_rows"]
)
def test_dashboard_invalid_calculated_results_rejected(dashboard_ui, kind):
    client, _, responses = dashboard_ui
    payload = copy.deepcopy(dashboard_payload())
    if kind == "missing_value":
        del payload["widgets"][0]["value"]
    elif kind == "negative_count":
        payload["widgets"][2]["rows"][0]["count"] = -1
    elif kind == "invalid_layout":
        payload["spec"]["widgets"][0]["type"] = "html"
    else:
        del payload["widgets"][3]["rows"]
    responses[:] = [payload]
    with pytest.raises(DashboardError, match="invalid layout"):
        client.generate("Show people")


@pytest.mark.parametrize(
    "client_type,error_type,action",
    [
        (
            InventoryClient,
            InventoryError,
            lambda client: client.assign_item("ITEM021", "EMP001"),
        ),
        (ChatClient, ChatError, lambda client: client.send("Show people", [])),
        (
            DashboardClient,
            DashboardError,
            lambda client: client.generate("Show people"),
        ),
    ],
)
@pytest.mark.parametrize("failure", ["timeout", "html", "malformed", "503"])
def test_clients_handle_failure_once_without_retry(
    client_type, error_type, action, failure
):
    calls = []

    def fail(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("Demo timeout")
        if failure == "html":
            return httpx.Response(200, text="<html>error</html>")
        if failure == "malformed":
            return httpx.Response(200, json={})
        return httpx.Response(503, json={"detail": "Dependency unavailable"})

    client = client_type("http://demo.test", transport=httpx.MockTransport(fail))
    with pytest.raises(error_type) as error:
        action(client)
    assert len(calls) == 1
    expected_read_timeout = {
        InventoryClient: 30,
        ChatClient: 3000,
        DashboardClient: 600,
    }
    assert calls[0].extensions["timeout"]["read"] == expected_read_timeout[client_type]
    if client_type is InventoryClient:
        assert error.value.uncertain
