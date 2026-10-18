from pymongo import MongoClient
from HRMS.config import MONGODB_URI, MONGODB_DATABASE


def connect():
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, tz_aware=True)
    return client, client[MONGODB_DATABASE].employees


def create_indexes(collection):
    collection.create_index("email", unique=True)
    collection.create_index([("department", 1), ("status", 1), ("joining_date", 1)])
