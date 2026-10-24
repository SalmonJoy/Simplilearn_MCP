import streamlit as st
from pydantic import TypeAdapter, ValidationError
from Inventory_management.schemas import Identifier
from Inventory_management.ui import state
from Inventory_management.ui.components import (
    filters,
    header,
    item_table,
    validation_error,
)
from Inventory_management.ui.item_actions import render_item
from Inventory_management.ui.services import inventory_client
from Inventory_management.ui.services.inventory_client import ApiError

header(
    "Item directory",
    "Find a unit and manage its current ownership.",
    ":material/inventory_2:",
)
if flash := st.session_state.pop("item_flash", None):
    st.success(flash, icon=":material/check_circle:")
if (applied := filters()) is not None:
    st.session_state.item_filters = applied
    state.change_page(0)
client = inventory_client.get_client()
limit, offset = st.session_state.item_page_size, st.session_state.item_offset
page = None
try:
    with st.spinner("Finding inventory units…"):
        page = client.list_items(
            limit=limit, offset=offset, **st.session_state.item_filters
        )
except ApiError as error:
    st.error(str(error), title="Directory is unavailable")
if page is not None:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            with st.container(width="stretch"):
                st.subheader(f"{page.total} matched items")
                st.caption(
                    f"Showing {offset + 1 if page.items else 0}–{offset + len(page.items) if page.items else 0}"
                )
            st.segmented_control(
                "Rows per page",
                [20, 50, 100],
                default=limit,
                required=True,
                key="item_limit",
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
            item_table(page)
        else:
            st.info("No items on this page. Change the filters or go back a page.")
with st.container(border=True):
    st.subheader("Open an item", icon=":material/search:")
    with st.form("item_lookup", border=False):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            lookup = st.text_input(
                "Exact item ID", key="lookup_item_id", placeholder="e.g. ITEM001"
            )
            opened = st.form_submit_button("Open by ID", icon=":material/search:")
    if opened:
        try:
            st.session_state.selected_item_id = TypeAdapter(Identifier).validate_python(
                lookup.strip()
            )
            st.session_state.item_selector = None
        except ValidationError as error:
            validation_error(error)
    if page and page.items:
        labels = {item.item_id: f"{item.item_id} · {item.name}" for item in page.items}
        if st.session_state.get("item_selector") not in labels:
            st.session_state.item_selector = None
        st.selectbox(
            "Or choose from this page",
            [None, *labels],
            format_func=lambda value: labels.get(value, "Choose an item"),
            key="item_selector",
            on_change=state.select_item,
        )
if item_id := st.session_state.selected_item_id:
    render_item(client, item_id)
