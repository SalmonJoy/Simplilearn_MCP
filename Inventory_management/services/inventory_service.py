from datetime import datetime, timezone
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from pymongo import ReturnDocument
from Inventory_management.config import HRMS_URL


def serialize(document):
    if document is None:
        raise HTTPException(404, "Item not found")
    return {
        "item_id": document["_id"],
        **{k: v for k, v in document.items() if k != "_id"},
    }


def get_item(collection, item_id):
    return serialize(collection.find_one({"_id": item_id}))


def list_items(collection, category, item_type, status, employee_id, limit, offset):
    query = {
        key: value
        for key, value in {
            "category": category,
            "item_type": item_type,
            "status": status,
            "assignment.employee_id": employee_id,
        }.items()
        if value is not None
    }
    total = collection.count_documents(query)
    items = [
        serialize(doc)
        for doc in collection.find(query).sort("_id", 1).skip(offset).limit(limit)
    ]
    return dict(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


def validate_employee(employee_id):
    try:
        response = httpx.get(
            f"{HRMS_URL}/employees/{quote(employee_id, safe='')}", timeout=10
        )
    except httpx.RequestError:
        raise HTTPException(
            503, "HRMS unavailable; assignment was not attempted"
        ) from None
    if response.status_code == 404:
        raise HTTPException(404, "Employee not found")
    if response.status_code != 200:
        raise HTTPException(503, "HRMS unavailable; assignment was not attempted")
    if response.json()["status"] not in ("joining", "active"):
        raise HTTPException(409, "Only joining or active employees can receive items")


def assign_item(collection, item_id, employee_id):
    validate_employee(employee_id)
    now = datetime.now(timezone.utc)
    # The predicate and update are one atomic MongoDB operation.
    doc = collection.find_one_and_update(
        {"_id": item_id, "status": "available", "assignment": None},
        {
            "$set": {
                "status": "assigned",
                "assignment": {"employee_id": employee_id, "assigned_at": now},
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        get_item(collection, item_id)  # Distinguish a missing item from a conflict.
        raise HTTPException(409, "Item is not available")
    return serialize(doc)


def return_item(collection, item_id, employee_id):
    doc = collection.find_one_and_update(
        {"_id": item_id, "status": "assigned", "assignment.employee_id": employee_id},
        {
            "$set": {
                "status": "available",
                "assignment": None,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        get_item(collection, item_id)
        raise HTTPException(409, "Item is not currently assigned to that employee")
    return serialize(doc)
