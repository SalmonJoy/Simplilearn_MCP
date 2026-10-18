from datetime import date, datetime
import re
from typing import Annotated, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,50}$")]
EmployeeStatus = Literal["joining", "active", "inactive"]


class EmployeeFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: Text
    email: Text
    department: Text
    designation: Text
    joining_date: date
    status: EmployeeStatus = "joining"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Provide a valid email address")
        return value


class EmployeeCreate(EmployeeFields):
    employee_id: Identifier


class Employee(EmployeeCreate):
    created_at: datetime
    updated_at: datetime


class EmployeePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: Text | None = None
    email: Text | None = None
    department: Text | None = None
    designation: Text | None = None
    joining_date: date | None = None
    status: EmployeeStatus | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        changes = self.model_dump(exclude_unset=True)
        if not changes or any(value is None for value in changes.values()):
            raise ValueError(
                "Provide at least one editable field; null values are not allowed"
            )
        if "email" in changes:
            self.email = EmployeeFields.normalize_email(self.email)
        return self


class EmployeePage(BaseModel):
    items: list[Employee]
    total: int
    limit: int
    offset: int
    has_more: bool


class EmployeeSummary(BaseModel):
    total: int
    by_department: dict[str, int]
    by_status: dict[str, int]
    by_joining_month: dict[str, int]
