"""MCP owns operational data only; business collections remain with their APIs."""

from pymongo import MongoClient
from MCP_server.config import MONGODB_URI, MONGODB_DATABASE

USAGE_RETENTION_SECONDS = 90 * 24 * 60 * 60


def connect():
    client = MongoClient(
        MONGODB_URI, serverSelectionTimeoutMS=5000, timeoutMS=5000, tz_aware=True
    )
    return client, client[MONGODB_DATABASE]


def initialize(db):
    db.client.admin.command("ping")
    db.tool_usage_events.create_index(
        "completed_at", expireAfterSeconds=USAGE_RETENTION_SECONDS
    )
    db.tool_usage_events.create_index([("tool_name", 1), ("started_at", 1)])
    db.tool_usage_events.create_index([("user_id", 1), ("started_at", 1)])
    db.tool_usage_events.create_index([("started_at", -1), ("_id", -1)])
    db.tool_usage_events.create_index(
        [("request_group_id", 1), ("started_at", 1), ("_id", 1)]
    )
    # Preference documents use the built-in unique _id index, with no expiration.
