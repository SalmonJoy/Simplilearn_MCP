"""Streamlit interactions use the real REST handlers with in-memory MongoDB."""

import json
from datetime import date
from pathlib import Path
import httpx
import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest
from HRMS.schemas import EmployeeCreate, EmployeePatch
from HRMS.ui.services import hrms_client
from HRMS.ui.services.hrms_client import ApiError, HRMSClient

ENTRY = Path(__file__).resolve().parents[1] / "HRMS" / "ui" / "main.py"
NEW_EMPLOYEE = {
    "employee_id": "EMP900",
    "full_name": "Tutorial Person",
    "email": "TUTORIAL900@EXAMPLE.TEST",
    "department": "Engineering",
    "designation": "Engineer",
    "joining_date": "2026-10-24",
}


@pytest.fixture
def ui_client(clients, seeded, monkeypatch):
    calls = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, dict(request.url.params), body))
        response = clients[0].request(
            request.method, request.url.path, params=dict(request.url.params), json=body
        )
        return httpx.Response(response.status_code, json=response.json())

    client = HRMSClient("http://hrms.test", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(hrms_client, "get_client", lambda: client)
    return client, calls


def button(app, label):
    return next(element for element in app.button if element.label == label)


def open_app(page=None):
    app = AppTest.from_file(ENTRY, default_timeout=20).run()
    assert not app.exception
    if page:
        app.switch_page(f"app_pages/{page}.py").run(timeout=20)
        assert not app.exception
    return app


def open_editor(app, employee_id):
    app.get_by_key(f"employee_view_{employee_id}").set_value("Edit details").run()
    assert not app.exception


def fill_new_employee(app):
    for field in ("employee_id", "full_name", "email", "department", "designation"):
        app.text_input(key=f"create_{field}").set_value(NEW_EMPLOYEE[field])
    app.date_input(key="create_joining_date").set_value(date(2026, 10, 24))


def test_client_reads_filters_and_writes(ui_client):
    client, calls = ui_client
    assert client.summary().total == 30
    page = client.list_employees(name="asha", joining_from=date(2000, 1, 1), limit=2)
    assert page.total == 3 and len(page.items) == 2 and page.has_more
    assert calls[-1][2]["joining_from"] == "2000-01-01"
    assert client.get_employee("EMP001").employee_id == "EMP001"
    created = client.create_employee(EmployeeCreate(**NEW_EMPLOYEE))
    assert created.email == "tutorial900@example.test"
    changed = client.update_employee("EMP900", EmployeePatch(department="Finance"))
    assert changed.department == "Finance"
    assert calls[-1][3] == {"department": "Finance"}
    with pytest.raises(ApiError, match="already exists") as duplicate:
        client.create_employee(EmployeeCreate(**NEW_EMPLOYEE))
    assert duplicate.value.status_code == 409
    with pytest.raises(ApiError) as missing:
        client.get_employee("MISSING")
    assert missing.value.status_code == 404
    with pytest.raises(ApiError, match="limit") as invalid:
        client.list_employees(limit=101)
    assert invalid.value.status_code == 422
    with pytest.raises(ValidationError):
        client.get_employee("../bad")


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH"])
def test_client_network_failures_never_retry(method):
    attempts = []

    def fail(request):
        attempts.append(request)
        raise httpx.ReadTimeout("Simulated timeout")

    client = HRMSClient("http://hrms.test", transport=httpx.MockTransport(fail))
    with pytest.raises(ApiError) as failure:
        if method == "GET":
            client.get_employee("EMP001")
        elif method == "POST":
            client.create_employee(EmployeeCreate(**NEW_EMPLOYEE))
        else:
            client.update_employee("EMP001", EmployeePatch(department="Finance"))
    assert len(attempts) == 1
    assert failure.value.uncertain == (method != "GET")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="html"),
        httpx.Response(200, json={}),
        httpx.Response(503, json={"detail": "Employee database unavailable"}),
    ],
)
def test_client_handles_bad_or_unavailable_backend(response):
    client = HRMSClient(
        "http://hrms.test", transport=httpx.MockTransport(lambda request: response)
    )
    with pytest.raises(ApiError):
        client.summary()


def test_overview_navigation_and_filters(ui_client, seeded):
    app = open_app()
    assert [metric.value for metric in app.metric] == ["30", "24", "3", "3"]
    app.text_input(key="overview_department").set_value("Finance")
    button(app, "Apply filters").click().run()
    assert not app.exception
    assert int(app.metric[0].value) == seeded.employees.count_documents(
        {"department": "Finance"}
    )
    app.switch_page("app_pages/directory.py").run()
    assert app.title[0].value == "Employee directory"
    app.switch_page("app_pages/create_employee.py").run()
    assert app.title[0].value == "Add employee"


def test_directory_pagination_filter_and_exact_lookup(ui_client):
    _, calls = ui_client
    app = open_app("directory")
    assert len(app.dataframe[0].value) == 20
    button(app, "Next").click().run()
    assert len(app.dataframe[0].value) == 10
    assert app.session_state["directory_offset"] == 20
    app.text_input(key="directory_name").set_value("asha")
    button(app, "Apply filters").click().run()
    assert app.session_state["directory_offset"] == 0
    assert len(app.dataframe[0].value) == 3
    app.text_input(key="lookup_employee_id").set_value("EMP002")
    button(app, "Open by ID").click().run()
    assert not app.exception and app.session_state["selected_employee_id"] == "EMP002"
    open_editor(app, "EMP002")
    assert app.text_input(key="edit_EMP002_0_id").disabled
    assert any(call[1] == "/employees/EMP002" for call in calls)


def test_directory_edit_only_changed_fields_and_no_repeated_writes(ui_client):
    _, calls = ui_client
    app = open_app("directory")
    app.selectbox(key="directory_employee_selector").select("EMP001").run()
    open_editor(app, "EMP001")
    assert not app.exception and app.session_state["selected_employee_id"] == "EMP001"
    button(app, "Save changes").click().run()
    assert any("No changes" in info.value for info in app.info)
    assert not any(call[0] == "PATCH" for call in calls)
    app.text_input(key="edit_EMP001_0_department").set_value("Finance")
    button(app, "Save changes").click().run()
    assert not app.exception
    writes = [call for call in calls if call[0] == "PATCH"]
    assert len(writes) == 1 and writes[0][3] == {"department": "Finance"}
    assert app.text_input(key="edit_EMP001_1_department").value == "Finance"
    button(app, "Refresh directory").click().run()
    assert len([call for call in calls if call[0] == "PATCH"]) == 1


def test_create_validation_success_and_conflict(ui_client):
    _, calls = ui_client
    app = open_app("create_employee")
    button(app, "Create employee").click().run()
    assert app.error and not any(call[0] == "POST" for call in calls)
    fill_new_employee(app)
    button(app, "Create employee").click().run()
    assert not app.exception and app.success
    assert app.session_state["created_employee"]["email"] == "tutorial900@example.test"
    app.run()
    assert len([call for call in calls if call[0] == "POST"]) == 1
    button(app, "Create employee").click().run()
    assert any("already exists" in error.value for error in app.error)
    assert app.text_input(key="create_full_name").value == NEW_EMPLOYEE["full_name"]


def test_empty_unavailable_and_invalid_dates(ui_client, seeded, monkeypatch):
    client, calls = ui_client
    app = open_app()
    app.date_input(key="overview_from").set_value(date(2026, 11, 1))
    app.date_input(key="overview_to").set_value(date(2026, 10, 1))
    count = len(calls)
    button(app, "Apply filters").click().run()
    assert app.error and app.session_state.get("overview_applied", {}) == {}
    assert all("joining_from" not in call[2] for call in calls[count:])
    seeded.employees.delete_many({})
    app.run()
    assert app.metric[0].value == "0" and app.info
    app.switch_page("app_pages/directory.py").run()
    assert not app.exception and app.info and not app.dataframe
    app.text_input(key="lookup_employee_id").set_value("MISSING")
    button(app, "Open by ID").click().run()
    assert any("not found" in error.value for error in app.error)

    def unavailable(**filters):
        raise ApiError("HRMS unavailable")

    monkeypatch.setattr(client, "summary", unavailable)
    app.switch_page("app_pages/overview.py").run()
    assert not app.exception and app.error and not app.metric


def test_create_uncertain_outcome_requires_check_without_reposting(
    ui_client, monkeypatch
):
    client, calls = ui_client
    original = client.create_employee

    def uncertain(body):
        original(body)  # The server commits, but the reply is lost.
        raise ApiError("Result unknown", uncertain=True)

    monkeypatch.setattr(client, "create_employee", uncertain)
    app = open_app("create_employee")
    fill_new_employee(app)
    button(app, "Create employee").click().run()
    assert not app.exception and app.warning
    assert button(app, "Create employee").disabled
    assert len([call for call in calls if call[0] == "POST"]) == 1
    assert app.text_input(key="create_full_name").value == NEW_EMPLOYEE["full_name"]
    button(app, "Check employee before retrying").click().run()
    assert not app.exception and app.success
    assert app.session_state["created_employee"]["employee_id"] == "EMP900"
    assert len([call for call in calls if call[0] == "POST"]) == 1


def test_edit_uncertain_outcome_requires_reload(ui_client, monkeypatch):
    client, calls = ui_client
    original = client.update_employee

    def uncertain(employee_id, changes):
        original(employee_id, changes)
        raise ApiError("Result unknown", uncertain=True)

    monkeypatch.setattr(client, "update_employee", uncertain)
    app = open_app("directory")
    app.selectbox(key="directory_employee_selector").select("EMP001").run()
    open_editor(app, "EMP001")
    app.text_input(key="edit_EMP001_0_department").set_value("Finance")
    button(app, "Save changes").click().run()
    assert not app.exception and app.warning and button(app, "Save changes").disabled
    assert len([call for call in calls if call[0] == "PATCH"]) == 1
    button(app, "Reload employee").click().run()
    assert app.text_input(key="edit_EMP001_1_department").value == "Finance"
    assert not button(app, "Save changes").disabled
    button(app, "Save changes").click().run()
    assert any("No changes" in info.value for info in app.info)
    assert len([call for call in calls if call[0] == "PATCH"]) == 1


def test_edit_validation_and_duplicate_email_preserve_input(ui_client):
    _, calls = ui_client
    app = open_app("directory")
    app.selectbox(key="directory_employee_selector").select("EMP001").run()
    open_editor(app, "EMP001")
    app.text_input(key="edit_EMP001_0_email").set_value("employee002@example.test")
    button(app, "Save changes").click().run()
    assert not app.exception and any(
        "already exists" in error.value for error in app.error
    )
    assert app.text_input(key="edit_EMP001_0_email").value == "employee002@example.test"
    writes = len([call for call in calls if call[0] == "PATCH"])
    app.text_input(key="edit_EMP001_0_email").set_value("invalid")
    button(app, "Save changes").click().run()
    assert app.error and len([call for call in calls if call[0] == "PATCH"]) == writes


def test_selected_employee_stays_by_id_when_page_changes(ui_client):
    app = open_app("directory")
    app.selectbox(key="directory_employee_selector").select("EMP001").run()
    open_editor(app, "EMP001")
    button(app, "Next").click().run()
    assert not app.exception
    assert app.session_state["selected_employee_id"] == "EMP001"
    assert app.text_input(key="edit_EMP001_0_id").value == "EMP001"
    assert app.dataframe[0].value.iloc[0]["employee_id"] == "EMP021"


def test_returning_to_directory_starts_from_current_record(ui_client):
    client, calls = ui_client
    app = open_app("directory")
    app.selectbox(key="directory_employee_selector").select("EMP001").run()
    open_editor(app, "EMP001")
    app.switch_page("app_pages/create_employee.py").run()
    client.update_employee("EMP001", EmployeePatch(department="Finance"))
    app.switch_page("app_pages/directory.py").run()
    open_editor(app, "EMP001")
    assert app.text_input(key="edit_EMP001_0_department").value == "Finance"
    writes = len([call for call in calls if call[0] == "PATCH"])
    button(app, "Save changes").click().run()
    assert any("No changes" in info.value for info in app.info)
    assert len([call for call in calls if call[0] == "PATCH"]) == writes


def test_segmented_filters_and_page_size_use_server_pagination(ui_client):
    _, calls = ui_client
    app = open_app()
    app.get_by_key("overview_status").set_value("active")
    button(app, "Apply filters").click().run()
    assert not app.exception and app.metric[0].value == "24"
    app.switch_page("app_pages/directory.py").run()
    button(app, "Next").click().run()
    app.get_by_key("directory_limit").set_value(50).run()
    assert not app.exception and app.session_state["directory_offset"] == 0
    assert len(app.dataframe[0].value) == 30
    app.get_by_key("directory_status").set_value("inactive")
    button(app, "Apply filters").click().run()
    assert not app.exception and len(app.dataframe[0].value) == 3
    assert set(app.dataframe[0].value["status"]) == {"inactive"}
    assert not any(call[0] in {"POST", "PATCH"} for call in calls)


def test_profile_edit_switch_does_not_write(ui_client):
    _, calls = ui_client
    app = open_app("directory")
    app.selectbox(key="directory_employee_selector").select("EMP001").run()
    assert app.get_by_key("employee_view_EMP001").value == "Profile"
    assert not any(element.label == "Save changes" for element in app.button)
    open_editor(app, "EMP001")
    assert app.text_input(key="edit_EMP001_0_id").disabled
    app.get_by_key("employee_view_EMP001").set_value("Profile").run()
    assert not app.exception and not any(
        element.label == "Save changes" for element in app.button
    )
    assert any(element.label == "Record details" for element in app.expander)
    assert not any(call[0] in {"POST", "PATCH"} for call in calls)


def test_created_employee_can_be_opened_in_directory(ui_client):
    _, calls = ui_client
    app = open_app("create_employee")
    app.get_by_key("create_status").set_value("active")
    fill_new_employee(app)
    button(app, "Create employee").click().run()
    assert (
        not app.exception
        and app.session_state["created_employee"]["status"] == "active"
    )
    button(app, "Open in directory").click().run()
    assert not app.exception and app.title[0].value == "Employee directory"
    assert app.session_state["selected_employee_id"] == "EMP900"
    assert app.get_by_key("employee_view_EMP900").value == "Profile"
    assert len([call for call in calls if call[0] == "POST"]) == 1
