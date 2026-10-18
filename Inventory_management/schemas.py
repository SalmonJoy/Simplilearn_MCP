from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, StringConstraints

Category = Literal["device", "goody"]
ItemStatus = Literal["available", "assigned", "maintenance", "retired"]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,50}$")]


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: Identifier


class Assignment(BaseModel):
    employee_id: str
    assigned_at: datetime


class Item(BaseModel):
    item_id: str
    name: str
    category: Category
    item_type: str
    status: ItemStatus
    assignment: Assignment | None
    created_at: datetime
    updated_at: datetime


class ItemPage(BaseModel):
    items: list[Item]
    total: int
    limit: int
    offset: int
    has_more: bool
