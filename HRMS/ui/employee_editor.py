"""Employee presentation and explicit save handling, separate from page routing."""

import streamlit as st
from pydantic import ValidationError
from HRMS.schemas import Employee, EmployeeCreate, EmployeePatch
from HRMS.ui.components import employee_details, employee_fields, show_validation
from HRMS.ui.services.hrms_client import ApiError


def render_employee(client, employee_id):
    revision_key = f"edit_revision_{employee_id}"
    uncertain_key = f"edit_uncertain_{employee_id}"
    st.subheader("Selected employee", icon=":material/account_circle:")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        view = st.segmented_control(
            "Employee view",
            ["Profile", "Edit details"],
            default="Profile",
            required=True,
            key=f"employee_view_{employee_id}",
        )
        if st.button(
            "Reload employee", key="reload_employee", icon=":material/refresh:"
        ):
            st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1
            st.session_state[uncertain_key] = False
    try:
        with st.spinner("Loading employee…"):
            employee = client.get_employee(employee_id)
    except (ApiError, ValidationError) as error:
        st.error(
            str(error), title="Employee could not be loaded", icon=":material/error:"
        )
        return
    employee_details(employee, show_fields=view == "Profile")
    if st.session_state.get(uncertain_key):
        st.warning(
            "The last save could not be confirmed. Reload the employee to review the current record before saving again.",
            title="Check the latest record",
            icon=":material/warning:",
        )
    if view != "Edit details":
        return
    revision = st.session_state.get(revision_key, 0)
    prefix = f"edit_{employee_id}_{revision}"
    baseline_key = prefix + "_baseline"
    if (
        baseline_key not in st.session_state
        or prefix + "_full_name" not in st.session_state
    ):
        st.session_state[baseline_key] = employee.model_dump(mode="json")
    baseline = st.session_state[baseline_key]
    with st.container(border=True):
        with st.form(prefix + "_form", border=False):
            st.caption("Update the fields you need. The employee ID stays the same.")
            _, values = employee_fields(prefix, Employee.model_validate(baseline))
            submitted = st.form_submit_button(
                "Save changes",
                icon=":material/save:",
                type="primary",
                disabled=st.session_state.get(uncertain_key, False),
            )
    if not submitted:
        return
    try:
        validated = EmployeeCreate(employee_id=employee_id, **values).model_dump(
            mode="json"
        )
        changes = {
            key: value
            for key, value in validated.items()
            if key != "employee_id" and value != baseline[key]
        }
        if not changes:
            st.info("No changes to save.", icon=":material/info:")
            return
        client.update_employee(employee_id, EmployeePatch(**changes))
    except ValidationError as error:
        show_validation(error)
    except ApiError as error:
        st.error(str(error), title="Employee could not be saved")
        if error.uncertain:
            st.session_state[uncertain_key] = True
            st.rerun()
    else:
        st.session_state[revision_key] = revision + 1
        st.session_state.directory_flash = "Employee updated successfully."
        st.rerun()
