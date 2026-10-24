"""Run this Streamlit frontend alongside the FastAPI chat host."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from pydantic import ValidationError
from AI_chat_assistant.ui.components import SUGGESTIONS, render_turn
from AI_chat_assistant.ui.services import chat_client
from AI_chat_assistant.ui.services.chat_client import ApiError
from AI_chat_assistant.ui.state import (
    apply_user,
    history_for_request,
    initialize,
    new_conversation,
)

st.set_page_config(
    page_title="Chat · MCP workspace", page_icon=":material/chat:", layout="centered"
)
initialize()
st.sidebar.header("Chat workspace", icon=":material/chat:")
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
st.sidebar.button(
    "New conversation", icon=":material/add_comment:", on_click=new_conversation
)
st.sidebar.caption("Thirteen MCP tools · HRMS, Inventory and preferences")
st.sidebar.caption(
    "Requests can update demo records when you explicitly ask for a change."
)
st.title("Your workplace assistant", icon=":material/forum:")
st.caption("Ask about people and items. Open a tool trace to see MCP at work.")
prompt = None
if not st.session_state.chat_turns:
    with st.container(border=True):
        st.subheader("What would you like to explore?")
        st.caption("Try a read-only question to get started.")
        with st.container(horizontal=True):
            for index, (label, example) in enumerate(SUGGESTIONS):
                if st.button(
                    label, key=f"suggestion_{index}", icon=":material/search:"
                ):
                    prompt = example

for turn in st.session_state.chat_turns:
    render_turn(turn)
if st.session_state.chat_error:
    st.error(st.session_state.chat_error, title="Request did not finish")
    st.warning(
        "Some changes may have completed. Inspect current records before repeating a write. No request will be retried automatically."
    )
    st.text_area(
        "Last failed message (copy to edit and send again)",
        value=st.session_state.failed_prompt,
        disabled=True,
    )

typed = st.chat_input(
    "What would you like to know or change?",
    key="chat_input",
    max_chars=4000,
    submit_mode="disable",
)
prompt = typed or prompt
if prompt:
    with st.chat_message("user"):
        st.text(prompt)
    try:
        with st.spinner("Discovering tools and working on your request…"):
            result = chat_client.get_client().send(
                prompt,
                history_for_request(st.session_state.chat_turns),
                user_id=st.session_state.demo_user_id,
            )
    except (ApiError, ValidationError) as error:
        st.session_state.failed_prompt = prompt
        st.session_state.chat_error = str(error)
    else:
        st.session_state.chat_turns.extend(
            [
                {"role": "user", "content": prompt},
                {
                    "role": "assistant",
                    "content": result.answer,
                    "trace": [call.model_dump() for call in result.trace],
                },
            ]
        )
        st.session_state.failed_prompt = None
        st.session_state.chat_error = None
    st.rerun()
