"""Streamlit dashboard studio; no direct database, MCP or Ollama calls."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from pydantic import ValidationError
from AI_dashboard_generation.ui.components import render_dashboard
from AI_dashboard_generation.ui.schemas import DashboardResult
from AI_dashboard_generation.ui.services import dashboard_client
from AI_dashboard_generation.ui.services.dashboard_client import ApiError
from AI_dashboard_generation.ui.state import (
    EXAMPLES,
    apply_user,
    initialize,
    use_example,
)

st.set_page_config(
    page_title="Dashboard · MCP workspace",
    page_icon=":material/dashboard:",
    layout="wide",
)
initialize()
st.sidebar.header("Dashboard studio", icon=":material/auto_awesome:")
with st.sidebar.form("demo_user_form"):
    st.text_input(
        "Demo user ID", key="demo_user_input", placeholder="e.g. alice", max_chars=50
    )
    st.form_submit_button("Use profile", on_click=apply_user)
st.sidebar.caption(
    f"Current profile: {st.session_state.demo_user_id or 'Anonymous (memory off)'}"
)
st.sidebar.caption(
    "Demo IDs separate preferences; they are not a login. Leave blank for anonymous use."
)
if st.session_state.identity_error:
    st.sidebar.error(st.session_state.identity_error)
st.sidebar.caption("Read-only data · AI-selected layouts · Python-calculated counts")
st.title("A dashboard, in your words", icon=":material/auto_awesome:")
st.caption(
    "Describe what matters. MCP retrieves the records and AI chooses how to present them."
)
with st.container(horizontal=True):
    for label, instruction in EXAMPLES.items():
        st.button(
            label,
            icon=":material/lightbulb:",
            on_click=use_example,
            args=(instruction,),
        )
with st.form("dashboard_form"):
    st.text_area(
        "Describe your dashboard",
        key="dashboard_instruction",
        max_chars=4000,
        height=110,
        placeholder="Show employee counts by department and available devices by type…",
    )
    submitted = st.form_submit_button(
        "Generate dashboard", type="primary", icon=":material/auto_awesome:"
    )
regenerate = st.button(
    "Regenerate",
    icon=":material/refresh:",
    disabled=st.session_state.last_instruction is None,
    help="Fetch fresh data using the last successful instruction.",
)
if submitted or regenerate:
    instruction = (
        st.session_state.last_instruction
        if regenerate
        else st.session_state.dashboard_instruction
    )
    try:
        with st.spinner("Retrieving complete data and generating your layout…"):
            result = dashboard_client.get_client().generate(
                instruction, user_id=st.session_state.demo_user_id
            )
    except (ApiError, ValidationError) as error:
        st.session_state.dashboard_error = str(error)
    else:
        st.session_state.dashboard_result = result.model_dump(mode="json")
        st.session_state.last_instruction = instruction
        st.session_state.dashboard_error = None
if st.session_state.dashboard_error:
    st.error(st.session_state.dashboard_error, title="Dashboard could not be generated")
    if st.session_state.dashboard_result:
        st.warning(
            "Previous result: this dashboard is from the last successful request and has not been refreshed."
        )
if st.session_state.dashboard_result:
    render_dashboard(DashboardResult.model_validate(st.session_state.dashboard_result))
elif not st.session_state.dashboard_error:
    st.info(
        "Choose an example or describe a dashboard to begin. Supported widgets: count cards, bar charts and tables.",
        title="Your next insight starts here",
    )
