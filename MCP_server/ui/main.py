"""Run from the root: python -m streamlit run MCP_server/ui/main.py."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from MCP_server.ui import state
from MCP_server.ui.filters import filter_form
from MCP_server.ui.services import usage_client
from MCP_server.ui.services.usage_client import ApiError

st.set_page_config(
    page_title="Tool usage · MCP workspace",
    page_icon=":material/monitoring:",
    layout="wide",
)
state.initialize()
st.sidebar.header("MCP insights", icon=":material/monitoring:")
st.sidebar.caption("Read-only operational statistics · No model requests")
applied = filter_form()
with st.container(horizontal=True, vertical_alignment="center"):
    with st.container(width="stretch"):
        st.title("Tool usage insights", icon=":material/monitoring:")
        st.caption(
            "Understand which tools are used, where errors occur and how long calls take."
        )
    refresh = st.button("Refresh", icon=":material/refresh:")
page = st.navigation(
    [
        st.Page(
            "app_pages/overview.py",
            title="Overview",
            icon=":material/dashboard:",
            default=True,
        ),
        st.Page(
            "app_pages/performance.py",
            title="Tool performance",
            icon=":material/speed:",
            url_path="performance",
        ),
        st.Page(
            "app_pages/explorer.py",
            title="Call explorer",
            icon=":material/manage_search:",
            url_path="calls",
        ),
    ]
)
if applied is not None or refresh or not st.session_state.usage_loaded_once:
    requested = applied if applied is not None else st.session_state.usage_filters
    st.session_state.usage_loaded_once = True
    try:
        with st.spinner("Loading complete usage aggregates…"):
            snapshot = usage_client.get_client().insights(**requested)
    except ApiError as error:
        st.session_state.usage_error = str(error)
    else:
        st.session_state.usage_snapshot = snapshot.model_dump(mode="json")
        st.session_state.usage_filters = requested
        st.session_state.usage_snapshot_filters = requested.copy()
        st.session_state.usage_error = None
        state.reset_events()
if st.session_state.usage_error:
    st.error(st.session_state.usage_error, title="Statistics could not be refreshed")
    if st.session_state.usage_snapshot:
        st.warning(
            "Previous snapshot: the last successful aggregates and their applied filters remain displayed. Refresh explicitly to try again."
        )
if not st.session_state.usage_snapshot:
    st.info(
        "No statistics snapshot has loaded yet. Start the MCP API and check its MongoDB connection, then use Refresh."
    )
    st.stop()
with st.expander("Applied filters", icon=":material/filter_list:"):
    st.json(st.session_state.usage_snapshot_filters)
st.caption(
    "90-day retention · Best-effort logging may have gaps · Zero recorded calls does not prove inactivity · No arguments, results or conversations are stored"
)
page.run()
