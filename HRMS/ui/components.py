"""Native presentation helpers shared by the three HRMS screens."""

from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
from pydantic import ValidationError

STATUSES = ["joining", "active", "inactive"]
STATUS_COLORS = {"active": "green", "joining": "orange", "inactive": "gray"}


def today():
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def page_header(title, subtitle, *, icon, refresh_label=None):
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container(width="stretch"):
            st.title(title, icon=icon)
            st.caption(subtitle)
        if refresh_label:
            st.button(refresh_label, icon=":material/refresh:")


def show_validation(error: ValidationError):
    messages = []
    for item in error.errors():
        field = ".".join(str(part) for part in item["loc"]) or "Form"
        messages.append(f"- {field.replace('_', ' ')}: {item['msg']}")
    st.error(
        "\n".join(messages), title="Check the employee details", icon=":material/error:"
    )


def filter_form(prefix, *, include_name=False):
    with st.container(border=True):
        with st.form(f"{prefix}_filters_form", border=False):
            with st.container(horizontal=True, vertical_alignment="bottom"):
                name = (
                    st.text_input(
                        "Name contains",
                        placeholder="Search employees",
                        key=f"{prefix}_name",
                    )
                    if include_name
                    else None
                )
                department = st.text_input(
                    "Department",
                    placeholder="All departments",
                    key=f"{prefix}_department",
                    help="An exact department match.",
                )
                status = st.segmented_control(
                    "Status",
                    ["All", *STATUSES],
                    default="All",
                    required=True,
                    format_func=lambda value: value.capitalize(),
                    key=f"{prefix}_status",
                    wrap=True,
                )
            with st.expander("More filters", icon=":material/tune:"):
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    joining_from = st.date_input(
                        "Joined from (optional)", value=None, key=f"{prefix}_from"
                    )
                    joining_to = st.date_input(
                        "Joined through (optional)", value=None, key=f"{prefix}_to"
                    )
                st.caption(
                    "Joining dates include both boundaries. Leave them empty for all dates."
                )
            submitted = st.form_submit_button(
                "Apply filters", icon=":material/filter_list:", type="primary"
            )
    if not submitted:
        return None
    if joining_from and joining_to and joining_from > joining_to:
        st.error(
            "Joined from must be on or before joined through. The last applied filters remain in use.",
            title="Check the date range",
        )
        return None
    filters = {
        "department": department.strip() or None,
        "status": status if status != "All" else None,
        "joining_from": joining_from,
        "joining_to": joining_to,
    }
    if include_name:
        filters["name"] = name.strip() or None
    return {key: value for key, value in filters.items() if value is not None}


def employee_fields(prefix, employee=None):
    st.subheader("Identity and contact", icon=":material/person:")
    first, second = st.columns([1, 2], vertical_alignment="bottom")
    id_key = f"{prefix}_id" if employee else "create_employee_id"
    employee_id = first.text_input(
        "Employee ID (cannot be changed)" if employee else "Employee ID",
        value=employee.employee_id if employee else "",
        disabled=employee is not None,
        key=id_key,
        help="Use 1–50 letters, digits, underscores or hyphens.",
    )
    full_name = second.text_input(
        "Full name",
        value=employee.full_name if employee else "",
        key=f"{prefix}_full_name",
        placeholder="e.g. Asha Rao",
    )
    email = st.text_input(
        "Email",
        value=employee.email if employee else "",
        key=f"{prefix}_email",
        placeholder="name@company.com",
    )
    st.subheader("Role and joining", icon=":material/work:")
    left, right = st.columns(2)
    department = left.text_input(
        "Department",
        value=employee.department if employee else "",
        key=f"{prefix}_department",
    )
    designation = right.text_input(
        "Designation",
        value=employee.designation if employee else "",
        key=f"{prefix}_designation",
    )
    with st.container(horizontal=True, vertical_alignment="bottom"):
        joining_date = st.date_input(
            "Joining date",
            value=employee.joining_date if employee else today(),
            key=f"{prefix}_joining_date",
        )
        status = st.segmented_control(
            "Employee status",
            STATUSES,
            default=employee.status if employee else "joining",
            format_func=str.capitalize,
            required=True,
            key=f"{prefix}_status",
            wrap=True,
        )
    return employee_id, dict(
        full_name=full_name,
        email=email,
        department=department,
        designation=designation,
        joining_date=joining_date,
        status=status,
    )


def employee_details(employee, *, show_fields=True):
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            with st.container(width="stretch"):
                st.subheader(employee.full_name)
                st.caption(employee.employee_id)
            st.badge(
                employee.status.capitalize(),
                color=STATUS_COLORS[employee.status],
                icon=":material/person:",
            )
        if show_fields:
            left, right = st.columns(2)
            for column, fields in [
                (
                    left,
                    [("Email", employee.email), ("Department", employee.department)],
                ),
                (
                    right,
                    [
                        ("Designation", employee.designation),
                        ("Joining date", employee.joining_date.strftime("%d %b %Y")),
                    ],
                ),
            ]:
                for label, value in fields:
                    column.caption(label)
                    column.text(value)
            with st.expander("Record details", icon=":material/history:"):
                st.caption(f"Created: {employee.created_at.isoformat()}")
                st.caption(f"Updated: {employee.updated_at.isoformat()}")


def directory_table(page):
    fields = [
        "employee_id",
        "full_name",
        "email",
        "department",
        "designation",
        "joining_date",
        "status",
    ]
    rows = [
        {field: employee.model_dump()[field] for field in fields}
        for employee in page.items
    ]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        height=min(460, (len(rows) + 1) * 42 + 6),
        row_height=42,
        alt="Employees matching the applied search filters, with IDs, contact details and employment status.",
        column_config={
            "employee_id": st.column_config.TextColumn("Employee ID", pinned=True),
            "full_name": "Name",
            "email": "Email",
            "department": "Department",
            "designation": "Designation",
            "joining_date": st.column_config.DateColumn(
                "Joining date", format="DD MMM YYYY"
            ),
            "status": "Status",
        },
    )
