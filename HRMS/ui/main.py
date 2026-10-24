"""Run from the repository root: python -m streamlit run HRMS/ui/main.py."""

from pathlib import Path
import sys

# Streamlit also puts the script directory on sys.path; keep root package imports reliable.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from HRMS.ui.state import initialize

st.set_page_config(
    page_title="HRMS · People", page_icon=":material/groups:", layout="wide"
)
initialize()
st.sidebar.header("People workspace", icon=":material/groups:")
st.sidebar.caption("HRMS · Employee management")
page = st.navigation(
    [
        st.Page(
            "app_pages/overview.py",
            title="Overview",
            icon=":material/dashboard:",
            default=True,
            url_path="overview",
        ),
        st.Page(
            "app_pages/directory.py",
            title="Employee directory",
            icon=":material/groups:",
            url_path="employees",
        ),
        st.Page(
            "app_pages/create_employee.py",
            title="Add employee",
            icon=":material/person_add:",
            url_path="add-employee",
        ),
    ]
)
page.run()
