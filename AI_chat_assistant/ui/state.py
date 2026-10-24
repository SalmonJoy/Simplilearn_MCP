"""Only successful turns enter the next request's conversation history."""

import streamlit as st
from pydantic import TypeAdapter, ValidationError
from HRMS.schemas import Identifier


def initialize():
    for key, value in {
        "chat_turns": [],
        "failed_prompt": None,
        "chat_error": None,
        "demo_user_id": None,
        "identity_error": None,
    }.items():
        st.session_state.setdefault(key, value)


def new_conversation():
    st.session_state.chat_turns = []
    st.session_state.failed_prompt = None
    st.session_state.chat_error = None
    st.session_state.chat_input = ""


def history_for_request(turns):
    return [
        {"role": turn["role"], "content": turn["content"][:20000]}
        for turn in turns[-40:]
    ]


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
        new_conversation()
        st.session_state.demo_user_id = user_id
    st.session_state.identity_error = None
