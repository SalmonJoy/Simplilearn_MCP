"""Atomic, scoped key/value preferences. No conversation or tool result storage."""

from datetime import datetime, timezone
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


def get_preferences(collection, user_id):
    doc = collection.find_one({"_id": user_id}) or {}
    preferences = doc.get("preferences", {})
    return {
        "user_id": user_id,
        "preferences": {
            "chat": preferences.get("chat", {}),
            "dashboard": preferences.get("dashboard", {}),
        },
    }


def set_preference(collection, user_id, scope, key, value):
    now = datetime.now(timezone.utc)
    update = {
        "$set": {f"preferences.{scope}.{key}": value, "updated_at": now},
        "$setOnInsert": {"created_at": now},
    }
    try:
        collection.update_one({"_id": user_id}, update, upsert=True)
    except DuplicateKeyError:
        # A simultaneous first insert created this profile. This known failure
        # did not apply our update; apply it once to the now-existing document.
        collection.update_one({"_id": user_id}, update, upsert=False)
    return {
        "user_id": user_id,
        "scope": scope,
        "key": key,
        "value": value,
        "saved": True,
    }


def delete_preference(collection, user_id, scope, key):
    # Returning the previous document reports actual removal atomically, even
    # when another request updates a different preference at the same time.
    previous = collection.find_one_and_update(
        {"_id": user_id, f"preferences.{scope}.{key}": {"$exists": True}},
        {
            "$unset": {f"preferences.{scope}.{key}": ""},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
        return_document=ReturnDocument.BEFORE,
    )
    return {
        "user_id": user_id,
        "scope": scope,
        "key": key,
        "removed": previous is not None,
    }
