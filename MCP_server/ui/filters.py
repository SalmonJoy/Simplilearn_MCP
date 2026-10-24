from datetime import date
import streamlit as st


def filter_form():
    defaults = st.session_state.usage_filters
    with st.sidebar.form("usage_filter_form"):
        st.subheader("Filters", icon=":material/tune:")
        start = st.date_input(
            "From (UTC)", value=defaults["date_from"], key="usage_from"
        )
        end = st.date_input("Through (UTC)", value=defaults["date_to"], key="usage_to")
        st.caption("Inclusive UTC days · Up to 90 days per view")
        tool = st.text_input(
            "Exact tool name", key="usage_tool", placeholder="All requested tool names"
        )
        source = st.segmented_control(
            "Client application",
            ["All", "chat", "dashboard", "unknown"],
            default="All",
            required=True,
            format_func=str.capitalize,
            key="usage_client",
            wrap=True,
        )
        user = st.text_input(
            "Exact user ID",
            key="usage_user",
            placeholder="All users, including anonymous",
        )
        anonymous = st.checkbox("Anonymous only", key="usage_anonymous")
        outcome = st.segmented_control(
            "Outcome",
            ["All", "success", "error", "cancelled"],
            default="All",
            required=True,
            format_func=str.capitalize,
            key="usage_outcome",
            wrap=True,
        )
        granularity = st.segmented_control(
            "Time buckets",
            ["day", "hour"],
            default="day",
            required=True,
            format_func=lambda value: "Daily" if value == "day" else "Hourly",
            key="usage_granularity",
        )
        submitted = st.form_submit_button(
            "Apply filters", type="primary", icon=":material/filter_list:"
        )
    if not submitted:
        return None
    if (
        not start
        or not end
        or start > end
        or end == date.max
        or (end - start).days >= 90
    ):
        st.sidebar.error(
            "Choose an ordered UTC date range covering at most 90 inclusive days. The last applied filters remain in use."
        )
        return None
    if anonymous and user.strip():
        st.sidebar.error(
            "Choose a user ID or Anonymous only, not both. The last applied filters remain in use."
        )
        return None
    return {
        key: value
        for key, value in {
            "date_from": start,
            "date_to": end,
            "tool_name": tool.strip() or None,
            "client_app": None if source == "All" else source,
            "user_id": user.strip() or None,
            "anonymous_only": anonymous,
            "outcome": None if outcome == "All" else outcome,
            "granularity": granularity,
        }.items()
        if value is not None
    }
