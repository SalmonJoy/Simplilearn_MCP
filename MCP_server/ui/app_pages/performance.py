import streamlit as st
from MCP_server.schemas import UsageInsights
from MCP_server.ui.components import (
    error_breakdown,
    performance_charts,
    performance_table,
    snapshot_header,
)

st.header("Tool performance", icon=":material/speed:")
snapshot = UsageInsights.model_validate(st.session_state.usage_snapshot)
snapshot_header(snapshot)
if not snapshot.total_calls:
    st.info("No matching calls were recorded for these filters.")
else:
    performance_charts(snapshot)
    performance_table(snapshot)
    error_breakdown(snapshot)
