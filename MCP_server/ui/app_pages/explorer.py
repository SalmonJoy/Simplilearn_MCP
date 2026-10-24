import streamlit as st
from MCP_server.schemas import UsageInsights
from MCP_server.ui.components import snapshot_header
from MCP_server.ui.event_explorer import render_explorer

st.header("Call explorer", icon=":material/manage_search:")
snapshot_header(UsageInsights.model_validate(st.session_state.usage_snapshot))
render_explorer()
