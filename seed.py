"""Seed only missing demo records; existing records are never overwritten."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from HRMS.database import create_indexes as employee_indexes
from Inventory_management.database import create_indexes as inventory_indexes
from settings import env


def seed_database(db):
    employee_indexes(db.employees)
    inventory_indexes(db.inventory_items)
    now = datetime.now(timezone.utc)
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    departments = ["Engineering", "Finance", "People", "Sales"]
    first_names = [
        "Asha",
        "Ravi",
        "Meera",
        "Arun",
        "Nisha",
        "Dev",
        "Sara",
        "Kabir",
        "Leela",
        "Ishan",
    ]
    last_names = ["Rao", "Shah", "Sen"]
    employees_created = items_created = 0
    for i in range(1, 31):
        status = "inactive" if i % 10 == 0 else "joining" if i % 5 == 0 else "active"
        joining = (
            today + timedelta(days=i % 14)
            if status == "joining"
            else today - timedelta(days=i * 8)
        )
        employee = {
            "_id": f"EMP{i:03}",
            "full_name": f"{first_names[(i - 1) % 10]} {last_names[(i - 1) // 10]}",
            "email": f"employee{i:03}@example.test",
            "department": departments[(i - 1) % 4],
            "designation": ["Engineer", "Analyst", "Specialist", "Executive"][
                (i - 1) % 4
            ],
            "joining_date": joining.isoformat(),
            "status": status,
            "created_at": now,
            "updated_at": now,
        }
        employees_created += (
            db.employees.update_one(
                {"_id": employee["_id"]}, {"$setOnInsert": employee}, upsert=True
            ).upserted_id
            is not None
        )
    types = [
        ("device", "laptop", "Dell Latitude Laptop"),
        ("device", "mouse", "Wireless Mouse"),
        ("goody", "tshirt", "Company T-shirt"),
        ("goody", "bottle", "Welcome Bottle"),
    ]
    for i in range(1, 61):
        category, item_type, name = types[(i - 1) % 4]
        status = (
            "assigned"
            if i <= 20
            else "maintenance"
            if i % 13 == 0
            else "retired"
            if i % 17 == 0
            else "available"
        )
        assignment = (
            {"employee_id": f"EMP{((i - 1) % 9) + 1:03}", "assigned_at": now}
            if status == "assigned"
            else None
        )
        item = {
            "_id": f"ITEM{i:03}",
            "name": name,
            "category": category,
            "item_type": item_type,
            "status": status,
            "assignment": assignment,
            "created_at": now,
            "updated_at": now,
        }
        items_created += (
            db.inventory_items.update_one(
                {"_id": item["_id"]}, {"$setOnInsert": item}, upsert=True
            ).upserted_id
            is not None
        )
    return {
        "employees_created": employees_created,
        "items_created": items_created,
        "employees_total": db.employees.count_documents({}),
        "items_total": db.inventory_items.count_documents({}),
    }


if __name__ == "__main__":
    try:
        with MongoClient(
            env("MONGODB_URI", "mongodb://localhost:27017"),
            serverSelectionTimeoutMS=5000,
            tz_aware=True,
        ) as client:
            print(seed_database(client[env("MONGODB_DATABASE", "mcp_learning")]))
    except PyMongoError:
        raise SystemExit(
            "Seeding failed. Check MONGODB_URI, credentials, and MongoDB network access. No credentials were logged."
        ) from None
