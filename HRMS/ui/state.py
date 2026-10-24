"""Session defaults and callbacks contain no requests or writes."""

import streamlit as st


def initialize():
    defaults = {
        "overview_applied": {},
        "directory_applied": {},
        "directory_offset": 0,
        "directory_page_size": 20,
        "selected_employee_id": None,
        "created_employee": None,
        "create_uncertain_id": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def change_page(offset):
    st.session_state.directory_offset = offset
    st.session_state.directory_employee_selector = None


def change_page_size():
    st.session_state.directory_page_size = st.session_state.directory_limit
    change_page(0)


def select_employee():
    if chosen := st.session_state.directory_employee_selector:
        st.session_state.selected_employee_id = chosen


def open_created_employee(employee_id):
    st.session_state.selected_employee_id = employee_id
    st.session_state[f"employee_view_{employee_id}"] = "Profile"
    st.switch_page("app_pages/directory.py")
