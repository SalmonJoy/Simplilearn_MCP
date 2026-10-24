"""Browser-session state and request-free widget callbacks."""

import streamlit as st


def initialize():
    for key, value in {
        "item_filters": {},
        "item_offset": 0,
        "item_page_size": 20,
        "selected_item_id": None,
        "uncertain_items": [],
    }.items():
        st.session_state.setdefault(key, value)


def change_page(offset):
    st.session_state.item_offset = offset
    st.session_state.item_selector = None


def change_page_size():
    st.session_state.item_page_size = st.session_state.item_limit
    change_page(0)


def select_item():
    if item_id := st.session_state.item_selector:
        st.session_state.selected_item_id = item_id
