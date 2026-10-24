import streamlit as st
from pydantic import TypeAdapter, ValidationError
from HRMS.schemas import Identifier

EXAMPLES = {
    "People overview": "Show employee count by department and status.",
    "Device overview": "Show available devices by item type and a table of assigned laptops and their owners.",
    "Company snapshot": "Show total employees, total items, and available goodies by type.",
}


def initialize():
    for key, value in {
        "dashboard_result": None,
        "dashboard_instruction": "",
        "last_instruction": None,
        "dashboard_error": None,
        "demo_user_id": None,
        "identity_error": None,
    }.items():
        st.session_state.setdefault(key, value)


def use_example(instruction):
    st.session_state.dashboard_instruction = instruction


def apply_user():
    value = st.session_state.demo_user_input.strip()
    try:
        user_id = TypeAdapter(Identifier).validate_python(value) if value else None
    except ValidationError:
        st.session_state.identity_error = (
            "Use 1–50 letters, digits, underscores or hyphens."
        )
        return
    if user_id != st.session_state.demo_user_id:
        st.session_state.demo_user_id = user_id
        st.session_state.dashboard_result = None
        st.session_state.last_instruction = None
        st.session_state.dashboard_instruction = ""
        st.session_state.dashboard_error = None
    st.session_state.identity_error = None
