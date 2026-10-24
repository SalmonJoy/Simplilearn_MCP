import streamlit as st
from MCP_server.schemas import UsageInsights
from MCP_server.ui.components import (
    activity_chart,
    audience_charts,
    overview_metrics,
    quick_findings,
    snapshot_header,
)

st.header("Overview", icon=":material/dashboard:")
snapshot = UsageInsights.model_validate(st.session_state.usage_snapshot)
snapshot_header(snapshot)
overview_metrics(snapshot)
if not snapshot.total_calls:
    st.info(
        "No matching calls were recorded for these filters.",
        title="No recorded activity",
    )
else:
    activity_chart(snapshot)
    audience_charts(snapshot)
    quick_findings(snapshot)
