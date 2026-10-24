"""Explicit refreshes and stable IDs keep widget reruns free of repeated reads."""

from datetime import datetime, timedelta, timezone
import streamlit as st


def initialize():
    today = datetime.now(timezone.utc).date()
    defaults = {
        "usage_filters": {
            "date_from": today - timedelta(days=6),
            "date_to": today,
            "granularity": "day",
        },
        "usage_snapshot": None,
        "usage_snapshot_filters": None,
        "usage_loaded_once": False,
        "usage_error": None,
        "selected_event": None,
        "usage_group_id": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    for kind in ["events", "group"]:
        for suffix, default in {
            "offset": 0,
            "limit": 20,
            "cache": None,
            "attempt_key": None,
            "error": None,
        }.items():
            st.session_state.setdefault(f"{kind}_{suffix}", default)


def reset_events():
    for kind in ["events", "group"]:
        st.session_state[f"{kind}_offset"] = 0
        st.session_state[f"{kind}_cache"] = None
        st.session_state[f"{kind}_attempt_key"] = None
        st.session_state[f"{kind}_error"] = None
    st.session_state.selected_event = None
    st.session_state.event_selector = None
    st.session_state.usage_group_id = None


def change_page(kind, offset):
    st.session_state[f"{kind}_offset"] = offset
    st.session_state[f"{kind}_attempt_key"] = None
    if kind == "events":
        st.session_state.event_selector = None


def change_page_size(kind):
    st.session_state[f"{kind}_limit"] = st.session_state[f"{kind}_page_size"]
    change_page(kind, 0)


def select_event():
    event_id = st.session_state.event_selector
    cache = st.session_state.events_cache
    if event_id and cache:
        for event in cache["page"]["items"]:
            if event["event_id"] == event_id:
                st.session_state.selected_event = event
                break


def open_group(group_id):
    st.session_state.usage_group_id = group_id
    st.session_state.group_offset = 0
    st.session_state.group_cache = None
    st.session_state.group_attempt_key = None
    st.session_state.group_error = None


def close_group():
    st.session_state.usage_group_id = None
