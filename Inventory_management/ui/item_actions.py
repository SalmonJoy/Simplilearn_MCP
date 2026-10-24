"""Explicit form submissions are the only path to assignment changes."""

import streamlit as st
from pydantic import ValidationError
from Inventory_management.ui.components import item_card, validation_error
from Inventory_management.ui.services.inventory_client import ApiError


def render_item(client, item_id):
    st.subheader("Selected item", icon=":material/devices:")
    reload_clicked = st.button("Reload item", icon=":material/refresh:")
    try:
        item = client.get_item(item_id)
    except (ApiError, ValidationError) as error:
        st.error(str(error), title="Item could not be loaded")
        return
    # A failed reload never unlocks a write with an unknown outcome.
    if reload_clicked and item_id in st.session_state.uncertain_items:
        st.session_state.uncertain_items = [
            value for value in st.session_state.uncertain_items if value != item_id
        ]
    item_card(item)
    blocked = item_id in st.session_state.uncertain_items
    if blocked:
        st.warning(
            "The last change could not be confirmed. Use Reload item and inspect its current ownership before submitting again.",
            title="Check the current item",
        )
    if item.status == "available":
        with st.form(f"assign_{item_id}"):
            st.subheader("Assign to an employee")
            st.caption(
                "Only joining or active employees can receive this unit. The Inventory API checks HRMS before assigning."
            )
            employee_id = st.text_input("Employee ID", key=f"assignee_{item_id}")
            submitted = st.form_submit_button(
                "Assign item",
                type="primary",
                icon=":material/person_add:",
                disabled=blocked,
            )
        action = client.assign_item
    elif item.status == "assigned" and item.assignment:
        employee_id = item.assignment.employee_id
        # A changed owner creates a new form, invalidating an old return click.
        with st.form(f"return_{item_id}_{employee_id}"):
            st.subheader("Return this item")
            st.text(f"Return {item_id} from {employee_id}")
            st.caption(
                "Returning clears this current assignment and makes the unit available. The API checks the expected employee ID."
            )
            submitted = st.form_submit_button(
                "Return item",
                type="primary",
                icon=":material/assignment_return:",
                disabled=blocked,
            )
        action = client.return_item
    else:
        st.info("This item cannot be assigned or returned in its current state.")
        return
    if not submitted:
        return
    try:
        action(item_id, employee_id.strip())
    except ValidationError as error:
        validation_error(error)
    except ApiError as error:
        if error.uncertain:
            st.session_state.uncertain_items = list(
                set(st.session_state.uncertain_items) | {item_id}
            )
            st.rerun()
        st.error(str(error), title="Assignment could not be changed")
    else:
        st.session_state.item_flash = f"{item_id}: assignment updated successfully."
        st.rerun()
