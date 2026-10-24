"""Paginated metadata browsing, with separate unfiltered request-group reads."""

from datetime import datetime, timezone
import streamlit as st
from MCP_server.schemas import UsageEvent, UsageEventPage
from MCP_server.ui import state
from MCP_server.ui.components import ist_time
from MCP_server.ui.services import usage_client
from MCP_server.ui.services.usage_client import ApiError


def load_page(kind, filters):
    params = {
        **filters,
        "limit": st.session_state[f"{kind}_limit"],
        "offset": st.session_state[f"{kind}_offset"],
        "order": "oldest" if kind == "group" else "newest",
    }
    key = tuple(sorted((name, str(value)) for name, value in params.items()))
    if st.session_state[f"{kind}_attempt_key"] != key:
        st.session_state[f"{kind}_attempt_key"] = key
        try:
            with st.spinner("Loading call metadata…"):
                page = usage_client.get_client().events(**params)
        except ApiError as error:
            st.session_state[f"{kind}_error"] = str(error)
        else:
            st.session_state[f"{kind}_cache"] = {
                "params": params,
                "page": page.model_dump(mode="json"),
                "loaded_at": datetime.now(timezone.utc).isoformat(),
            }
            st.session_state[f"{kind}_error"] = None
    cache = st.session_state[f"{kind}_cache"]
    if error := st.session_state[f"{kind}_error"]:
        st.error(error, title="Call metadata could not be loaded")
        if cache:
            st.warning(
                "Previous event page: the requested page did not load. The metadata below is from the last successful read."
            )
        if st.button(
            "Retry event page", key=f"retry_{kind}", icon=":material/refresh:"
        ):
            st.session_state[f"{kind}_attempt_key"] = None
            st.rerun()
    return UsageEventPage.model_validate(cache["page"]) if cache else None


def toolbar(kind, page):
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container(width="stretch"):
            st.subheader(f"{page.total} matching calls")
            st.caption(
                f"Showing {page.offset + 1 if page.items else 0}–{page.offset + len(page.items) if page.items else 0}"
            )
        st.segmented_control(
            "Rows per page",
            [20, 50, 100],
            default=st.session_state[f"{kind}_limit"],
            required=True,
            key=f"{kind}_page_size",
            on_change=state.change_page_size,
            args=(kind,),
        )
        st.button(
            "Previous",
            key=f"{kind}_previous",
            icon=":material/chevron_left:",
            disabled=page.offset == 0,
            on_click=state.change_page,
            args=(kind, max(0, page.offset - page.limit)),
        )
        st.button(
            "Next",
            key=f"{kind}_next",
            icon=":material/chevron_right:",
            disabled=not page.has_more,
            on_click=state.change_page,
            args=(kind, page.offset + page.limit),
        )


def event_table(page, *, alt):
    rows = [
        {
            "Event ID": event.event_id,
            "Started (IST)": ist_time(event.started_at),
            "Completed (IST)": ist_time(event.completed_at),
            "Tool": event.tool_name,
            "Outcome": event.outcome,
            "Error code": str(event.error_code)
            if event.error_code is not None
            else "—",
            "Duration (ms)": event.duration_ms,
            "User ID": event.user_id
            if event.user_id is not None
            else "Anonymous (no ID)",
            "Application": event.client_app,
            "Request group": event.request_group_id,
        }
        for event in page.items
    ]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Event ID": st.column_config.TextColumn("Event ID", pinned=True)
        },
        alt=alt,
    )


def render_explorer():
    filters = {
        key: value
        for key, value in st.session_state.usage_snapshot_filters.items()
        if key != "granularity"
    }
    page = load_page("events", filters)
    if page:
        with st.container(border=True):
            toolbar("events", page)
            loaded = datetime.fromisoformat(st.session_state.events_cache["loaded_at"])
            st.caption(
                f"Event page loaded {ist_time(loaded)} · Live paginated reads may differ from the aggregate snapshot as events arrive or expire."
            )
            if page.items:
                event_table(
                    page,
                    alt="Paginated recorded call metadata matching the applied filters; timestamps are in IST.",
                )
                labels = {
                    event.event_id: f"{event.event_id} · {event.tool_name}"
                    for event in page.items
                }
                if st.session_state.get("event_selector") not in labels:
                    st.session_state.event_selector = None
                st.selectbox(
                    "Inspect an event from this page",
                    [None, *labels],
                    format_func=lambda value: labels.get(value, "Choose an event"),
                    key="event_selector",
                    on_change=state.select_event,
                )
            else:
                st.info(
                    "No recorded calls on this page. Change the filters or go back a page."
                )
    if selected := st.session_state.selected_event:
        event = UsageEvent.model_validate(selected)
        with st.container(border=True):
            st.subheader("Selected call", icon=":material/manage_search:")
            st.caption(
                "Selection uses an event ID and stays selected across event pages. Metadata reflects the page from which it was selected."
            )
            st.text(f"{event.event_id} · {event.tool_name} · {event.outcome}")
            st.caption(f"Started: {ist_time(event.started_at)}")
            st.caption(f"Completed: {ist_time(event.completed_at)}")
            st.text(
                f"Duration: {event.duration_ms:,.2f} ms · User: {event.user_id if event.user_id is not None else 'Anonymous (no ID)'} · Application: {event.client_app}"
            )
            with st.expander("Raw event metadata (UTC)"):
                st.json(event.model_dump(mode="json"))
            st.button(
                "View request group",
                icon=":material/account_tree:",
                disabled=event.request_group_id is None,
                on_click=state.open_group,
                args=(event.request_group_id,),
            )
            if event.request_group_id is None:
                st.caption("This call has no request-group ID.")
    if group_id := st.session_state.usage_group_id:
        with st.container(border=True):
            st.subheader("Request group", icon=":material/account_tree:")
            st.text(group_id)
            st.caption(
                "All retained calls in this group, oldest first. Overview filters do not apply. Summed tool durations are not end-to-end request latency."
            )
            st.button("Close request group", on_click=state.close_group)
            group = load_page("group", {"request_group_id": group_id})
            if group:
                toolbar("group", group)
                if group.items:
                    event_table(
                        group,
                        alt="All retained calls in the selected request group in chronological order, independent of overview filters.",
                    )
                else:
                    st.info("No retained calls remain in this group.")
