from collections import Counter
import streamlit as st
from Inventory_management.ui.components import STATUSES, header
from Inventory_management.ui.services import inventory_client
from Inventory_management.ui.services.inventory_client import ApiError

header(
    "Inventory overview",
    "Every unit, from laptops to welcome kits.",
    ":material/dashboard:",
)
try:
    with st.spinner("Loading all inventory pages…"):
        items = inventory_client.get_client().all_items()
except ApiError as error:
    st.error(str(error), title="Overview is unavailable")
    st.stop()

counts = Counter(item.status for item in items)
st.caption("Counts include all fetched units · Refresh for the latest records")
with st.container(horizontal=True):
    st.metric("Total items", len(items), border=True)
    for status in STATUSES:
        st.metric(status.capitalize(), counts[status], border=True)
if not items:
    st.info(
        "No inventory units yet. Run the seed script to insert demo inventory.",
        title="Inventory is empty",
    )
    st.stop()
for column, (field, title) in zip(
    st.columns(2), [("item_type", "Items by type"), ("category", "Items by category")]
):
    with column.container(border=True, height="stretch"):
        st.subheader(title)
        counts = Counter(getattr(item, field) for item in items)
        st.bar_chart(
            [
                {"Category": key, "Items": value}
                for key, value in sorted(counts.items())
            ],
            x="Category",
            y="Items",
            height=280,
            horizontal=True,
            alt=f"Complete inventory unit counts by {field.replace('_', ' ')}.",
        )
