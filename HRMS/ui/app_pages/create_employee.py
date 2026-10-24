import streamlit as st
from pydantic import ValidationError
from HRMS.schemas import Employee, EmployeeCreate
from HRMS.ui.components import (
    employee_details,
    employee_fields,
    page_header,
    show_validation,
)
from HRMS.ui.services import hrms_client
from HRMS.ui.services.hrms_client import ApiError
from HRMS.ui.state import open_created_employee

page_header(
    "Add employee", "Welcome someone new to your team.", icon=":material/person_add:"
)
client = hrms_client.get_client()
uncertain_id = st.session_state.create_uncertain_id
if uncertain_id:
    st.warning(
        f"The last creation result is unknown. Check {uncertain_id} before submitting again.",
        title="Check the latest record",
        icon=":material/warning:",
    )
    if st.button("Check employee before retrying", icon=":material/search:"):
        try:
            employee = client.get_employee(uncertain_id)
        except ApiError as error:
            st.error(str(error))
            if error.status_code == 404:
                st.session_state.create_uncertain_id = None
                st.info(
                    "The employee was not found. Review your values before submitting again."
                )
        else:
            st.session_state.created_employee = employee.model_dump(mode="json")
            st.session_state.create_uncertain_id = None
            st.success(
                "The employee exists. Review the record below before creating another employee."
            )

with st.container(border=True):
    with st.form("create_employee_form", border=False):
        st.caption(
            "All fields are required. Choose a unique employee ID and email address."
        )
        employee_id, values = employee_fields("create")
        submitted = st.form_submit_button(
            "Create employee",
            type="primary",
            icon=":material/person_add:",
            disabled=bool(st.session_state.create_uncertain_id),
        )
if submitted:
    try:
        body = EmployeeCreate(employee_id=employee_id.strip(), **values)
        employee = client.create_employee(body)
    except ValidationError as error:
        show_validation(error)
    except ApiError as error:
        st.error(str(error), title="Employee could not be created")
        if error.uncertain:
            st.session_state.create_uncertain_id = employee_id.strip()
            st.rerun()
    else:
        st.session_state.created_employee = employee.model_dump(mode="json")
        st.success(
            "Employee created successfully.",
            title="Ready to join the team",
            icon=":material/check_circle:",
        )

if record := st.session_state.created_employee:
    st.subheader("Most recent employee")
    employee_details(Employee.model_validate(record))
    if st.button(
        "Open in directory",
        icon=":material/arrow_forward:",
    ):
        open_created_employee(record["employee_id"])
