import re
from collections import Counter
from datetime import datetime, timezone
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


def serialize(document):
    if document is None:
        raise HTTPException(404, "Employee not found")
    return {
        "employee_id": document["_id"],
        **{k: v for k, v in document.items() if k != "_id"},
    }


def filters(
    name=None, department=None, status=None, joining_from=None, joining_to=None
):
    if joining_from and joining_to and joining_from > joining_to:
        raise HTTPException(422, "joining_from must be on or before joining_to")
    query = {}
    if name is not None:
        query["full_name"] = {"$regex": re.escape(name), "$options": "i"}
    if department is not None:
        query["department"] = department
    if status is not None:
        query["status"] = status
    if joining_from or joining_to:
        query["joining_date"] = {}
        if joining_from:
            query["joining_date"]["$gte"] = joining_from.isoformat()
        if joining_to:
            query["joining_date"]["$lte"] = joining_to.isoformat()
    return query


def create_employee(collection, body):
    doc = body.model_dump(mode="json")
    doc["_id"] = doc.pop("employee_id")
    doc["created_at"] = doc["updated_at"] = datetime.now(timezone.utc)
    try:
        collection.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Employee ID or email already exists") from None
    return serialize(doc)


def get_employee(collection, employee_id):
    return serialize(collection.find_one({"_id": employee_id}))


def list_employees(collection, query, limit, offset):
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


def update_employee(collection, employee_id, body):
    changes = body.model_dump(mode="json", exclude_unset=True)
    changes["updated_at"] = datetime.now(timezone.utc)
    try:
        doc = collection.find_one_and_update(
            {"_id": employee_id},
            {"$set": changes},
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        raise HTTPException(409, "Employee email already exists") from None
    return serialize(doc)


def summarize(collection, query):
    docs = list(
        collection.find(query, {"department": 1, "status": 1, "joining_date": 1})
    )
    return dict(
        total=len(docs),
        by_department=dict(Counter(d["department"] for d in docs)),
        by_status=dict(Counter(d["status"] for d in docs)),
        by_joining_month=dict(
            sorted(Counter(d["joining_date"][:7] for d in docs).items())
        ),
    )
