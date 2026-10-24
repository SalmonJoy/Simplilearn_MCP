from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, StrictInt, model_validator
from AI_dashboard_generation.schemas import DashboardSpec, Widget


class CalculatedWidget(Widget):
    value: StrictInt | None = Field(default=None, ge=0)
    rows: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def check_calculated_data(self):
        if self.type == "card":
            if self.value is None:
                raise ValueError("Count card is missing its value")
        else:
            if self.rows is None or not self.columns:
                raise ValueError("Chart or table is missing its data or columns")
            if any(not set(self.columns).issubset(row) for row in self.rows):
                raise ValueError("Widget rows do not match its columns")
            if self.group_by and any(
                type(row.get("count")) is not int or row["count"] < 0
                for row in self.rows
            ):
                raise ValueError("Grouped data must contain nonnegative integer counts")
        return self

    @model_validator(mode="before")
    @classmethod
    def check_grouped_columns(cls, data):
        # render_widgets adds a calculated count column; Widget validates domain fields.
        if (
            isinstance(data, dict)
            and data.get("group_by")
            and data.get("type") != "card"
        ):
            expected = [data["group_by"], "count"]
            if data.get("columns") != expected:
                raise ValueError("Grouped columns do not match the calculated output")
            data = {**data, "columns": [data["group_by"]]}
        return data


class DashboardResult(BaseModel):
    title: str
    spec: DashboardSpec
    widgets: list[CalculatedWidget] = Field(min_length=1, max_length=12)
    trace: list[dict[str, Any]]
    generated_at: datetime
    dataset_counts: dict[str, int]
    note: str

    @model_validator(mode="after")
    def restore_calculated_columns(self):
        for widget in self.widgets:
            if widget.group_by:
                widget.columns = [widget.group_by, "count"]
        if len(self.widgets) != len(self.spec.widgets):
            raise ValueError("Widget count does not match the layout")
        return self
