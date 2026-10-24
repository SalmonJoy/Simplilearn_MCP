import streamlit as st

SUGGESTIONS = [
    ("People by department", "Show employee counts by department."),
    ("Available laptops", "List available laptops."),
    ("Laptop owners", "List the IDs, names and emails of employees assigned laptops."),
]


def render_turn(turn):
    with st.chat_message(turn["role"]):
        st.text(turn["content"])
        if trace := turn.get("trace"):
            with st.expander(
                f"MCP trace · {len(trace)} tool calls", icon=":material/build:"
            ):
                for index, call in enumerate(trace, 1):
                    st.subheader(f"{index}. {call['tool']}")
                    st.badge(
                        "Tool error" if call["is_error"] else "Completed",
                        color="red" if call["is_error"] else "green",
                    )
                    st.caption("Arguments")
                    st.json(call["arguments"])
                    st.caption("Result")
                    st.json(call["result"])
