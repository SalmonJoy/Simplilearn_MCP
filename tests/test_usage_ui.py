"""AppTest and mocked HTTP checks for the standalone usage workspace."""

from pathlib import Path
from datetime import timedelta
import httpx
import pytest
from streamlit.testing.v1 import AppTest
from test_usage_insights import usage_api as usage_api, usage_records as usage_records
from MCP_server.ui.services import usage_client
from MCP_server.ui.services.usage_client import ApiError, UsageClient

ENTRY = Path(__file__).resolve().parents[1] / "MCP_server" / "ui" / "main.py"


@pytest.fixture
def ui_api(usage_api, monkeypatch):
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path, dict(request.url.params)))
        response = usage_api.request(
            request.method, request.url.path, params=dict(request.url.params)
        )
        return httpx.Response(response.status_code, json=response.json())

    client = UsageClient("http://mcp.test", transport=httpx.MockTransport(handle))
    monkeypatch.setattr(usage_client, "get_client", lambda: client)
    return client, calls


def button(app, label):
    return next(value for value in app.button if value.label == label)


def open_app(page=None):
    # The first native chart imports pandas/Arrow/Altair on a cold Windows run.
    # Keep subsequent widget runs bounded independently of this startup cost.
    app = AppTest.from_file(ENTRY, default_timeout=20).run(timeout=60)
    assert not app.exception
    if page:
        app.switch_page(f"app_pages/{page}.py").run()
        assert not app.exception
    return app


def test_client_filters_models_read_only_and_configuration(
    ui_api, usage_records, monkeypatch
):
    client, calls = ui_api
    _, day = usage_records
    data = client.insights(
        date_from=day, date_to=day, anonymous_only=True, granularity="hour"
    )
    assert data.total_calls == 2 and len(data.timeline) == 24
    assert calls[-1][2]["anonymous_only"] == "true"
    assert calls[-1][2]["date_from"] == day.isoformat()
    page = client.events(request_group_id="g2", limit=1, offset=1, order="oldest")
    assert page.total == 2 and page.items[0].event_id == "EVT005"
    assert all(method == "GET" for method, _, _ in calls)
    monkeypatch.setenv("MCP_API_URL", "http://custom.test:9003/")
    assert UsageClient().base_url == "http://custom.test:9003"


@pytest.mark.parametrize(
    "failure", ["timeout", "503", "validation", "html", "malformed"]
)
def test_client_errors_are_readable_and_never_retried(failure):
    calls = []

    def handle(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("Simulated timeout")
        if failure == "html":
            return httpx.Response(200, text="<html>Error</html>")
        if failure == "malformed":
            return httpx.Response(200, json={})
        if failure == "validation":
            return httpx.Response(422, json={"detail": [{"msg": "Invalid date range"}]})
        return httpx.Response(503, json={"detail": "MCP database unavailable"})

    client = UsageClient("http://mcp.test", transport=httpx.MockTransport(handle))
    with pytest.raises(ApiError):
        client.insights()
    assert len(calls) == 1 and calls[0].method == "GET"
    assert calls[0].extensions["timeout"]["read"] == 30


def test_overview_values_findings_navigation_and_no_repeated_aggregate_reads(ui_api):
    _, calls = ui_api
    app = open_app()
    assert [metric.value for metric in app.metric] == [
        "7",
        "57.1%",
        "2",
        "1",
        "60.00 ms",
        "200.00 ms",
        "4",
        "2",
    ]
    assert any("Highest volume: a · 4 calls" in text.value for text in app.text)
    assert any("Highest average duration: b" in text.value for text in app.text)
    app.run()
    app.switch_page("app_pages/performance.py").run()
    assert not app.exception and len(app.dataframe) == 2
    assert "Code unavailable" in app.dataframe[1].value["Error code"].tolist()
    app.switch_page("app_pages/overview.py").run()
    assert len(calls) == 1
    button(app, "Refresh").click().run()
    assert len(calls) == 2


def test_shared_filter_form_hourly_resolution_and_invalid_ranges(ui_api, usage_records):
    _, calls = ui_api
    _, day = usage_records
    app = open_app()
    app.date_input(key="usage_from").set_value(day)
    app.date_input(key="usage_to").set_value(day)
    app.get_by_key("usage_client").set_value("dashboard")
    app.get_by_key("usage_outcome").set_value("error")
    app.get_by_key("usage_granularity").set_value("hour")
    app.text_input(key="usage_tool").set_value("a")
    app.text_input(key="usage_user").set_value("bob")
    button(app, "Apply filters").click().run()
    assert not app.exception and app.metric[0].value == "1"
    assert calls[-1][2]["granularity"] == "hour"
    assert len(app.session_state["usage_snapshot"]["timeline"]) == 24
    previous_calls = len(calls)
    app.checkbox(key="usage_anonymous").check()
    button(app, "Apply filters").click().run()
    assert app.error and len(calls) == previous_calls
    app.checkbox(key="usage_anonymous").uncheck()
    app.date_input(key="usage_from").set_value(day + timedelta(days=1))
    button(app, "Apply filters").click().run()
    assert app.error and len(calls) == previous_calls
    assert app.metric[0].value == "1"


def test_anonymous_and_empty_views(ui_api):
    _, calls = ui_api
    app = open_app()
    app.checkbox(key="usage_anonymous").check()
    button(app, "Apply filters").click().run()
    assert app.metric[0].value == "2" and app.metric[-1].value == "0"
    assert calls[-1][2]["anonymous_only"] == "true"
    app.checkbox(key="usage_anonymous").uncheck()
    app.text_input(key="usage_tool").set_value("missing")
    button(app, "Apply filters").click().run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == [
        "0",
        "—",
        "0",
        "0",
        "—",
        "—",
        "0",
        "0",
    ]
    app.switch_page("app_pages/performance.py").run()
    assert app.info and not app.dataframe
    app.switch_page("app_pages/explorer.py").run()
    assert app.info and not app.dataframe


def test_failed_refresh_retains_previous_snapshot_and_applied_filters(
    ui_api, monkeypatch
):
    client, calls = ui_api
    app = open_app()
    old_filters = dict(app.session_state["usage_snapshot_filters"])

    def unavailable(**kwargs):
        calls.append(("GET", "/usage/insights", kwargs))
        raise ApiError("MCP unavailable")

    monkeypatch.setattr(client, "insights", unavailable)
    app.text_input(key="usage_tool").set_value("new_filter")
    button(app, "Apply filters").click().run()
    assert app.error and app.warning and app.metric[0].value == "7"
    assert app.session_state["usage_snapshot_filters"] == old_filters
    assert app.text_input(key="usage_tool").value == "new_filter"
    app.run()
    assert len(calls) == 2  # initial success and explicit failure only


def test_initial_failure_waits_for_explicit_refresh(ui_api, monkeypatch):
    client, calls = ui_api
    original = client.insights

    def unavailable(**kwargs):
        calls.append(("GET", "/usage/insights", kwargs))
        raise ApiError("MCP unavailable")

    monkeypatch.setattr(client, "insights", unavailable)
    app = open_app()
    assert app.error and not app.metric
    app.run()
    assert len(calls) == 1
    monkeypatch.setattr(client, "insights", original)
    button(app, "Refresh").click().run()
    assert not app.exception and app.metric[0].value == "7"


def test_explorer_paging_stable_selection_and_unfiltered_group(ui_api, usage_records):
    _, calls = ui_api
    db, _ = usage_records
    sample = db.tool_usage_events.find_one({"_id": "EVT000"})
    for index in range(30):
        db.tool_usage_events.insert_one({**sample, "_id": f"EXTRA{index:03}"})
    app = open_app("explorer")
    assert len(app.dataframe[0].value) == 20
    event_id = app.dataframe[0].value.iloc[0]["Event ID"]
    app.selectbox(key="event_selector").select(event_id).run()
    count = len(calls)
    app.run()
    assert len(calls) == count
    app.button(key="events_next").click().run()
    assert app.session_state["selected_event"]["event_id"] == event_id
    assert app.session_state["events_offset"] == 20
    app.get_by_key("events_page_size").set_value(50).run()
    assert app.session_state["events_offset"] == 0
    assert len(app.dataframe[0].value) == 37
    # Apply a filter that selects only one call in g2, then inspect the whole group.
    app.text_input(key="usage_tool").set_value("a")
    app.get_by_key("usage_outcome").set_value("error")
    button(app, "Apply filters").click().run()
    assert (
        app.session_state["events_offset"] == 0
        and app.session_state["selected_event"] is None
    )
    app.selectbox(key="event_selector").select("EVT002").run()
    button(app, "View request group").click().run()
    assert not app.exception and len(app.dataframe[-1].value) == 2
    assert app.dataframe[-1].value["Event ID"].tolist() == ["EVT002", "EVT005"]
    group_query = calls[-1][2]
    assert group_query["request_group_id"] == "g2" and group_query["order"] == "oldest"
    assert (
        "tool_name" not in group_query
        and "outcome" not in group_query
        and "date_from" not in group_query
    )
    count = len(calls)
    app.run()
    assert len(calls) == count
    button(app, "Close request group").click().run()
    assert app.session_state["usage_group_id"] is None


def test_event_page_failure_preserves_previous_page_until_explicit_retry(
    ui_api, monkeypatch
):
    client, calls = ui_api
    app = open_app("explorer")
    old_page = app.dataframe[0].value.copy()
    original = client.events

    def unavailable(**kwargs):
        calls.append(("GET", "/usage/events", kwargs))
        raise ApiError("Metadata unavailable")

    monkeypatch.setattr(client, "events", unavailable)
    app.get_by_key("events_page_size").set_value(50).run()
    assert app.error and app.warning
    assert app.dataframe[0].value.equals(old_page)
    count = len(calls)
    app.run()
    assert len(calls) == count
    monkeypatch.setattr(client, "events", original)
    button(app, "Retry event page").click().run()
    assert not app.exception and not app.error


def test_selected_call_without_group_cannot_open_group(ui_api):
    app = open_app("explorer")
    app.selectbox(key="event_selector").select("EVT003").run()
    assert button(app, "View request group").disabled
    assert any(
        "IST" in caption.value and "Started:" in caption.value
        for caption in app.caption
    )
