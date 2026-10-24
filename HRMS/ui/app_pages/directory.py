import streamlit as st
from pydantic import TypeAdapter, ValidationError
from HRMS.schemas import Identifier
from HRMS.ui import state
from HRMS.ui.components import (
    directory_table,
    filter_form,
    page_header,
    show_validation,
)
from HRMS.ui.employee_editor import render_employee
from HRMS.ui.services import hrms_client
from HRMS.ui.services.hrms_client import ApiError

page_header(
    "Employee directory",
    "Find the right person and keep their details up to date.",
    icon=":material/groups:",
    refresh_label="Refresh directory",
)
if flash := st.session_state.pop("directory_flash", None):
    st.success(flash, icon=":material/check_circle:")
applied = filter_form("directory", include_name=True)
if applied is not None:
    st.session_state.directory_applied = applied
    state.change_page(0)

client = hrms_client.get_client()
limit = st.session_state.directory_page_size
offset = st.session_state.directory_offset
page = None
try:
    with st.spinner("Finding employees…"):
        page = client.list_employees(
            **st.session_state.directory_applied, limit=limit, offset=offset
        )
except ApiError as error:
    st.error(str(error), title="Directory is unavailable", icon=":material/error:")

if page is not None:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            with st.container(width="stretch"):
                st.subheader(f"{page.total} matched employees")
                st.caption(
                    f"Showing {offset + 1 if page.items else 0}–{offset + len(page.items) if page.items else 0}"
                )
            st.segmented_control(
                "Rows per page",
                [20, 50, 100],
                default=limit,
                required=True,
                key="directory_limit",
                on_change=state.change_page_size,
            )
            st.button(
                "Previous",
                icon=":material/chevron_left:",
                disabled=offset == 0,
                on_click=state.change_page,
                args=(max(0, offset - limit),),
            )
            st.button(
                "Next",
                icon=":material/chevron_right:",
                disabled=not page.has_more,
                on_click=state.change_page,
                args=(offset + limit,),
            )
        if page.items:
            directory_table(page)
        else:
            st.info(
                "No employees on this page. Change the filters, go back a page, or add an employee.",
                icon=":material/search:",
            )

with st.container(border=True):
    st.subheader("Open an employee", icon=":material/person_search:")
    # Both selection methods store an ID, never a dataframe row number.
    with st.form("employee_lookup", border=False):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            lookup = st.text_input(
                "Find by exact employee ID",
                key="lookup_employee_id",
                placeholder="e.g. EMP001",
            )
            opened = st.form_submit_button("Open by ID", icon=":material/search:")
    if opened:
        try:
            st.session_state.selected_employee_id = TypeAdapter(
                Identifier
            ).validate_python(lookup.strip())
            st.session_state.directory_employee_selector = None
        except ValidationError as error:
            show_validation(error)
    if page and page.items:
        labels = {
            employee.employee_id: f"{employee.employee_id} · {employee.full_name}"
            for employee in page.items
        }
        if st.session_state.get("directory_employee_selector") not in labels:
            st.session_state.directory_employee_selector = None
        st.selectbox(
            "Or choose from this page",
            [None, *labels],
            format_func=lambda value: labels.get(value, "Choose an employee"),
            key="directory_employee_selector",
            on_change=state.select_employee,
        )

if employee_id := st.session_state.selected_employee_id:
    render_employee(client, employee_id)
