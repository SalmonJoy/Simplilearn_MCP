from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

DATASET_FIELDS = {
    "employees": {
        "employee_id",
        "full_name",
        "email",
        "department",
        "designation",
        "joining_date",
        "status",
    },
    "items": {"item_id", "name", "category", "item_type", "status", "employee_id"},
    "assigned_items": {
        "item_id",
        "name",
        "category",
        "item_type",
        "status",
        "employee_id",
        "employee_name",
        "employee_department",
        "employee_status",
        "employee_joining_date",
    },
}


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    instruction: str = Field(min_length=1, max_length=4000)


class Widget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["card", "bar", "table"]
    title: str = Field(min_length=1, max_length=150)
    dataset: Literal["employees", "items", "assigned_items"]
    filters: dict[str, str] = Field(default_factory=dict)
    group_by: str | None = None
    metric: Literal["count"] = "count"
    columns: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def check_fields(self):
        allowed = DATASET_FIELDS[self.dataset]
        used = set(self.filters) | set(self.columns)
        if self.group_by:
            used.add(self.group_by)
        if not used.issubset(allowed):
            raise ValueError("Widget references unknown dataset fields")
        if self.type == "bar" and not self.group_by:
            raise ValueError("Bar charts require group_by")
        if self.type == "card" and self.group_by:
            raise ValueError("Cards display one count; use filters, not group_by")
        return self


class DashboardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=150)
    widgets: list[Widget] = Field(min_length=1, max_length=12)
