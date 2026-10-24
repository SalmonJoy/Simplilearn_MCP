"""Display only server-calculated values in the validated widget order."""

from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st


def render_dashboard(result):
    st.header(result.title, icon=":material/dashboard:")
    st.caption(
        f"Generated {result.generated_at.astimezone(ZoneInfo('Asia/Kolkata')).strftime('%d %b %Y, %H:%M IST')} · "
        + " · ".join(
            f"{count} {name.replace('_', ' ')}"
            for name, count in result.dataset_counts.items()
        )
    )
    widgets = result.widgets
    index = 0
    while index < len(widgets):
        widget = widgets[index]
        if widget.type == "card":
            cards = []
            while (
                index < len(widgets)
                and widgets[index].type == "card"
                and len(cards) < 4
            ):
                cards.append(widgets[index])
                index += 1
            for column, card in zip(st.columns(len(cards)), cards):
                column.metric(card.title, card.value, border=True, height="stretch")
            continue
        with st.container(border=True):
            st.subheader(widget.title)
            if not widget.rows:
                st.info("No matching records for this widget.")
            elif widget.type == "bar":
                st.bar_chart(
                    widget.rows,
                    x=widget.group_by,
                    y="count",
                    x_label=widget.group_by.replace("_", " ").capitalize(),
                    y_label="Count",
                    height=300,
                    alt=widget.title,
                )
            else:
                st.dataframe(
                    pd.DataFrame(widget.rows, columns=widget.columns),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        field: field.replace("_", " ").capitalize()
                        for field in widget.columns
                    },
                    alt=widget.title,
                )
        index += 1
    st.caption(result.note)
    with st.expander("MCP calls and layout JSON", icon=":material/code:"):
        st.caption(
            "The backend fetches complete lists through MCP. The model chooses the layout; Python calculates every displayed count."
        )
        st.json({"calls": result.trace, "layout": result.spec.model_dump()})
