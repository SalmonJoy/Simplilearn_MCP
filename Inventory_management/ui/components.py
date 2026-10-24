"""Native layout helpers; business requests stay in the client."""

import streamlit as st

STATUSES = ["available", "assigned", "maintenance", "retired"]
STATUS_COLORS = {
    "available": "green",
    "assigned": "violet",
    "maintenance": "orange",
    "retired": "gray",
}


def header(title, subtitle, icon):
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container(width="stretch"):
            st.title(title, icon=icon)
            st.caption(subtitle)
        st.button("Refresh", icon=":material/refresh:")


def validation_error(error):
    st.error(
        "\n".join(
            f"- {'.'.join(map(str, item['loc'])) or 'ID'}: {item['msg']}"
            for item in error.errors()
        ),
        title="Check your input",
    )


def filters():
    with st.form("item_filters_form"):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            category = st.segmented_control(
                "Category",
                ["All", "device", "goody"],
                default="All",
                format_func=str.capitalize,
                required=True,
                key="filter_category",
                wrap=True,
            )
            status = st.segmented_control(
                "Status",
                ["All", *STATUSES],
                default="All",
                format_func=str.capitalize,
                required=True,
                key="filter_status",
                wrap=True,
            )
        with st.container(horizontal=True):
            item_type = st.text_input(
                "Exact item type", key="filter_type", placeholder="e.g. laptop"
            )
            employee_id = st.text_input(
                "Assigned employee ID", key="filter_employee", placeholder="e.g. EMP001"
            )
        submitted = st.form_submit_button(
            "Apply filters", type="primary", icon=":material/filter_list:"
        )
    if submitted:
        return {
            key: value
            for key, value in {
                "category": None if category == "All" else category,
                "status": None if status == "All" else status,
                "item_type": item_type.strip() or None,
                "employee_id": employee_id.strip() or None,
            }.items()
            if value is not None
        }
    return None


def item_table(page):
    rows = [
        {
            "item_id": item.item_id,
            "name": item.name,
            "category": item.category,
            "item_type": item.item_type,
            "status": item.status,
            "employee_id": item.assignment.employee_id if item.assignment else None,
        }
        for item in page.items
    ]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        height=min(460, 42 * (len(rows) + 1) + 6),
        row_height=42,
        column_config={
            "item_id": st.column_config.TextColumn("Item ID", pinned=True),
            "name": "Name",
            "category": "Category",
            "item_type": "Item type",
            "status": "Status",
            "employee_id": "Employee ID",
        },
        alt="Inventory units matching the applied filters, with their current assigned employee IDs.",
    )


def item_card(item):
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            with st.container(width="stretch"):
                st.subheader(item.name)
                st.caption(
                    f"{item.item_id} · {item.category.capitalize()} · {item.item_type}"
                )
            st.badge(item.status.capitalize(), color=STATUS_COLORS[item.status])
        if item.assignment:
            st.text(f"Assigned to {item.assignment.employee_id}")
            st.caption(f"Assigned at: {item.assignment.assigned_at.isoformat()}")
        else:
            st.caption("No current employee assignment")
        with st.expander("Record details", icon=":material/history:"):
            st.caption(f"Created: {item.created_at.isoformat()}")
            st.caption(f"Updated: {item.updated_at.isoformat()}")
