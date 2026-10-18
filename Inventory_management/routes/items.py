from fastapi import APIRouter, Query, Request
from Inventory_management.schemas import (
    AssignmentRequest,
    Category,
    Item,
    ItemPage,
    ItemStatus,
)
from Inventory_management.services import inventory_service as service

router = APIRouter(prefix="/items", tags=["Inventory"])


@router.get("", response_model=ItemPage)
def list_items(
    request: Request,
    category: Category | None = None,
    item_type: str | None = None,
    status: ItemStatus | None = None,
    employee_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return service.list_items(
        request.app.state.collection,
        category,
        item_type,
        status,
        employee_id,
        limit,
        offset,
    )


@router.get("/{item_id}", response_model=Item)
def get_item(item_id: str, request: Request):
    return service.get_item(request.app.state.collection, item_id)


@router.post("/{item_id}/assign", response_model=Item)
def assign_item(item_id: str, body: AssignmentRequest, request: Request):
    return service.assign_item(request.app.state.collection, item_id, body.employee_id)


@router.post("/{item_id}/return", response_model=Item)
def return_item(item_id: str, body: AssignmentRequest, request: Request):
    return service.return_item(request.app.state.collection, item_id, body.employee_id)
