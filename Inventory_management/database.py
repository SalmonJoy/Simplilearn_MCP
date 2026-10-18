from pymongo import MongoClient
from Inventory_management.config import MONGODB_URI, MONGODB_DATABASE


def connect():
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, tz_aware=True)
    return client, client[MONGODB_DATABASE].inventory_items


def create_indexes(collection):
    collection.create_index([("category", 1), ("status", 1)])
    collection.create_index("assignment.employee_id")
