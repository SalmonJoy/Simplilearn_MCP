"""Native overview and performance presentation; no model-generated analysis."""

from zoneinfo import ZoneInfo
import streamlit as st

IST = ZoneInfo("Asia/Kolkata")


def ist_time(value):
    return value.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def snapshot_header(snapshot):
    st.caption(
        f"Loaded {ist_time(snapshot.generated_at)} · {snapshot.date_from} through {snapshot.date_to}, inclusive UTC days"
    )
    st.caption(
        "MCP execution durations exclude model generation, caller-side network time and telemetry insertion. Rates reflect all applied filters."
    )


def overview_metrics(snapshot):
    measured = snapshot.total_calls > 0
    metrics = [
        ("Recorded calls", snapshot.total_calls),
        ("Success rate", f"{snapshot.success_rate:.1f}%" if measured else "—"),
        ("Errors", snapshot.failed_calls),
        ("Cancellations", snapshot.cancelled_calls),
        (
            "Average duration",
            f"{snapshot.avg_duration_ms:,.2f} ms" if measured else "—",
        ),
        ("Longest call", f"{snapshot.max_duration_ms:,.2f} ms" if measured else "—"),
        ("Tools called", snapshot.tools_called),
        ("Identified users", snapshot.identified_users),
    ]
    for start in [0, 4]:
        for column, (label, value) in zip(st.columns(4), metrics[start : start + 4]):
            column.metric(label, value, border=True, height="stretch")


def activity_chart(snapshot):
    with st.container(border=True):
        st.subheader("Activity over time", icon=":material/timeline:")
        st.caption(
            "Buckets use UTC. Empty buckets mean no matching recorded calls, not proof that no calls occurred."
        )
        label = "UTC hour" if snapshot.granularity == "hour" else "UTC day"
        pattern = "%Y-%m-%d %H:00 UTC" if snapshot.granularity == "hour" else "%Y-%m-%d"
        # Explicit UTC strings avoid browser timezone conversion of chart axes.
        rows = [
            {
                label: row.bucket.strftime(pattern),
                "Success": row.successful_calls,
                "Error": row.failed_calls,
                "Cancelled": row.cancelled_calls,
            }
            for row in snapshot.timeline
        ]
        st.line_chart(
            rows,
            x=label,
            y=["Success", "Error", "Cancelled"],
            y_label="Recorded calls",
            height=300,
            alt="Recorded successful, failed and cancelled tool calls over UTC time buckets.",
        )


def audience_charts(snapshot):
    left, right = st.columns(2)
    with left.container(border=True, height="stretch"):
        st.subheader("Application usage", icon=":material/apps:")
        st.bar_chart(
            [
                {"Application": row.client_app, "Calls": row.total_calls}
                for row in snapshot.by_client
            ],
            x="Application",
            y="Calls",
            height=270,
            alt="Recorded calls from chat, dashboard and unknown clients.",
        )
    with right.container(border=True, height="stretch"):
        st.subheader("User activity", icon=":material/groups:")
        st.caption(
            f"Top ten identified users · Anonymous calls: {snapshot.anonymous_calls}"
        )
        if snapshot.by_user:
            st.bar_chart(
                [
                    {"User ID": row.user_id, "Calls": row.total_calls}
                    for row in snapshot.by_user
                ],
                x="User ID",
                y="Calls",
                horizontal=True,
                height=270,
                alt="Top ten identified demo users by recorded call count; anonymous calls are reported separately.",
            )
        else:
            st.info("No identified users in this selection.")


def quick_findings(snapshot):
    with st.container(border=True):
        st.subheader("Quick findings", icon=":material/lightbulb:")
        tools = snapshot.by_tool
        volume = sorted(tools, key=lambda row: (-row.total_calls, row.tool_name))[0]
        slow = sorted(tools, key=lambda row: (-row.avg_duration_ms, row.tool_name))[0]
        st.text(f"Highest volume: {volume.tool_name} · {volume.total_calls} calls")
        failures = sorted(tools, key=lambda row: (-row.failed_calls, row.tool_name))[0]
        st.text(
            f"Most errors: {failures.tool_name} · {failures.failed_calls} errors from {failures.total_calls} calls"
            if failures.failed_calls
            else "No recorded tool errors in this selection."
        )
        st.text(
            f"Highest average duration: {slow.tool_name} · {slow.avg_duration_ms:,.2f} ms from {slow.total_calls} calls"
        )


def performance_charts(snapshot):
    left, right = st.columns(2)
    volume = sorted(
        snapshot.by_tool, key=lambda row: (-row.total_calls, row.tool_name)
    )[:10]
    slow = sorted(
        snapshot.by_tool, key=lambda row: (-row.avg_duration_ms, row.tool_name)
    )[:10]
    with left.container(border=True, height="stretch"):
        st.subheader("Most-used tools")
        st.bar_chart(
            [{"Tool": row.tool_name, "Calls": row.total_calls} for row in volume],
            x="Tool",
            y="Calls",
            horizontal=True,
            height=300,
            alt="Top ten requested tool names by call volume, including unknown names.",
        )
    with right.container(border=True, height="stretch"):
        st.subheader("Highest average duration")
        st.caption(
            "Sample counts are shown with each tool; low-volume tools can have unstable averages."
        )
        st.bar_chart(
            [
                {
                    "Tool (calls)": f"{row.tool_name} (n={row.total_calls})",
                    "Average duration (ms)": row.avg_duration_ms,
                }
                for row in slow
            ],
            x="Tool (calls)",
            y="Average duration (ms)",
            horizontal=True,
            height=300,
            alt="Top ten tools by average MCP execution duration, with their sample call counts.",
        )


def performance_table(snapshot):
    rows = [
        {
            "Tool": row.tool_name,
            "Calls": row.total_calls,
            "Usage share (%)": row.usage_share,
            "Successes": row.successful_calls,
            "Errors": row.failed_calls,
            "Cancellations": row.cancelled_calls,
            "Success rate (%)": row.success_rate,
            "Error rate (%)": row.error_rate,
            "Average duration (ms)": row.avg_duration_ms,
            "Maximum duration (ms)": row.max_duration_ms,
        }
        for row in snapshot.by_tool
    ]
    with st.container(border=True):
        st.subheader("Tool comparison", icon=":material/table_chart:")
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            column_config={"Tool": st.column_config.TextColumn("Tool", pinned=True)},
            alt="Sortable comparison of recorded tool calls, outcomes, rates, usage share and execution durations.",
        )


def error_breakdown(snapshot):
    with st.container(border=True):
        st.subheader("Error codes", icon=":material/error:")
        st.caption(
            "Only failed calls are counted. Codes are recorded metadata and do not by themselves identify a root cause."
        )
        if snapshot.by_error_code:
            st.dataframe(
                [
                    {
                        "Error code": str(row.error_code)
                        if row.error_code is not None
                        else "Code unavailable",
                        "Errors": row.total_calls,
                    }
                    for row in snapshot.by_error_code
                ],
                hide_index=True,
                width="stretch",
                alt="Recorded failed-call counts by available error code, including errors without a code.",
            )
        else:
            st.info("No recorded errors in this selection.")
