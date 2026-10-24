import streamlit as st
from HRMS.ui.components import filter_form, page_header
from HRMS.ui.services import hrms_client
from HRMS.ui.services.hrms_client import ApiError

page_header(
    "People overview",
    "Your workforce at a glance.",
    icon=":material/dashboard:",
    refresh_label="Refresh overview",
)
applied = filter_form("overview")
if applied is not None:
    st.session_state.overview_applied = applied

try:
    with st.spinner("Loading your workforce overview…"):
        summary = hrms_client.get_client().summary(**st.session_state.overview_applied)
except ApiError as error:
    st.error(str(error), title="Overview is unavailable", icon=":material/error:")
    st.stop()

st.caption(
    "All employees matching your applied filters · Refresh for the latest records"
)
metrics = [
    ("Total employees", summary.total, "groups"),
    ("Active", summary.by_status.get("active", 0), "verified_user"),
    ("Joining", summary.by_status.get("joining", 0), "person_add"),
    ("Inactive", summary.by_status.get("inactive", 0), "person_off"),
]
for column, (label, value, icon) in zip(st.columns(4), metrics):
    column.metric(
        label, value, icon=f":material/{icon}:", border=True, height="stretch"
    )
if not summary.total:
    st.info(
        "No employees match these filters. Change the filters or add an employee.",
        title="No matching employees",
        icon=":material/search:",
    )
    st.stop()

left, right = st.columns(2)
with left.container(border=True, height="stretch"):
    st.subheader("Employees by department", icon=":material/business:")
    st.caption("Matching employees in each department")
    st.bar_chart(
        [
            {"Department": key, "Employees": count}
            for key, count in sorted(summary.by_department.items())
        ],
        x="Department",
        y="Employees",
        horizontal=True,
        height=280,
        alt="Employee counts by department for the applied filters.",
    )
with right.container(border=True, height="stretch"):
    st.subheader("Joining by month", icon=":material/calendar_month:")
    st.caption("Joining dates across the matching workforce")
    st.bar_chart(
        [
            {"Month": key, "Employees": count}
            for key, count in sorted(summary.by_joining_month.items())
        ],
        x="Month",
        y="Employees",
        height=280,
        alt="Employee joining counts by month for the applied filters.",
    )
