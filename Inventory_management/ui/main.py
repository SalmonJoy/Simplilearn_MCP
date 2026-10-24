"""Run from the repository root with python -m streamlit run."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from Inventory_management.ui.state import initialize

st.set_page_config(
    page_title="Inventory · Workspace",
    page_icon=":material/inventory_2:",
    layout="wide",
)
initialize()
st.sidebar.header("Inventory workspace", icon=":material/inventory_2:")
st.sidebar.caption("Devices, goodies and current ownership")
st.navigation(
    [
        st.Page(
            "app_pages/overview.py",
            title="Overview",
            icon=":material/dashboard:",
            default=True,
        ),
        st.Page(
            "app_pages/directory.py",
            title="Item directory",
            icon=":material/devices:",
            url_path="items",
        ),
    ]
).run()
