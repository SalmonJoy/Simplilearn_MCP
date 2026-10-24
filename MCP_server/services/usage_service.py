"""Metadata-only telemetry and aggregation, with no prompt/argument/result data."""

from datetime import datetime, time, timedelta, timezone
from pymongo import timeout


def insert_event(collection, event):
    with timeout(1):
        collection.insert_one(event)


def build_query(
    *,
    tool_name=None,
    user_id=None,
    client_app=None,
    date_from=None,
    date_to=None,
    outcome=None,
    anonymous_only=False,
    request_group_id=None,
):
    query = {
        key: value
        for key, value in {
            "tool_name": tool_name,
            "user_id": user_id,
            "client_app": client_app,
            "outcome": outcome,
            "request_group_id": request_group_id,
        }.items()
        if value is not None
    }
    if anonymous_only:
        if user_id is not None:
            raise ValueError("Choose a user ID or anonymous-only, not both")
        query["user_id"] = None
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    if date_to == datetime.max.date():
        raise ValueError("date_to must be before 9999-12-31")
    dates = {}
    if date_from:
        dates["$gte"] = datetime.combine(date_from, time.min, timezone.utc)
    if date_to:
        dates["$lt"] = datetime.combine(
            date_to + timedelta(days=1), time.min, timezone.utc
        )
    if dates:
        query["started_at"] = dates
    return query


def count_group(group_id):
    return {
        "$group": {
            "_id": group_id,
            "total_calls": {"$sum": 1},
            "successful_calls": {
                "$sum": {"$cond": [{"$eq": ["$outcome", "success"]}, 1, 0]}
            },
            "failed_calls": {"$sum": {"$cond": [{"$eq": ["$outcome", "error"]}, 1, 0]}},
            "cancelled_calls": {
                "$sum": {"$cond": [{"$eq": ["$outcome", "cancelled"]}, 1, 0]}
            },
            "total_duration_ms": {"$sum": "$duration_ms"},
            "max_duration_ms": {"$max": "$duration_ms"},
        }
    }


def summarize(groups):
    fields = ["total_calls", "successful_calls", "failed_calls", "cancelled_calls"]
    result = {field: sum(group[field] for group in groups) for field in fields}
    result["avg_duration_ms"] = (
        round(
            sum(group["total_duration_ms"] for group in groups) / result["total_calls"],
            2,
        )
        if groups
        else 0
    )
    return result


def statistics(collection, **filters):
    groups = list(
        collection.aggregate(
            [
                {"$match": build_query(**filters)},
                count_group("$tool_name"),
                {"$sort": {"_id": 1}},
            ]
        )
    )
    return {
        **summarize(groups),
        "by_tool": [
            {"tool_name": group["_id"], **summarize([group])} for group in groups
        ],
    }


def performance(groups):
    result = summarize(groups)
    total = result["total_calls"]
    return {
        **result,
        "max_duration_ms": max(
            (group["max_duration_ms"] for group in groups), default=0
        ),
        "success_rate": round(100 * result["successful_calls"] / total, 2)
        if total
        else None,
        "error_rate": round(100 * result["failed_calls"] / total, 2) if total else None,
    }


def insights(collection, *, granularity="day", **filters):
    today = datetime.now(timezone.utc).date()
    date_to = filters.get("date_to") or today
    date_from = filters.get("date_from") or date_to - timedelta(
        days=min(6, date_to.toordinal() - 1)
    )
    if (date_to - date_from).days >= 90:
        raise ValueError("Insights can display at most 90 inclusive UTC calendar days")
    filters = {**filters, "date_from": date_from, "date_to": date_to}
    query = build_query(**filters)
    date_format = (
        "%Y-%m-%dT%H:00:00Z" if granularity == "hour" else "%Y-%m-%dT00:00:00Z"
    )
    # A single facet aggregates all matching events; no browser page is sampled.
    data = next(
        collection.aggregate(
            [
                {"$match": query},
                {
                    "$facet": {
                        "tools": [count_group("$tool_name"), {"$sort": {"_id": 1}}],
                        "timeline": [
                            count_group(
                                {
                                    "$dateToString": {
                                        "format": date_format,
                                        "date": "$started_at",
                                    }
                                }
                            )
                        ],
                        "clients": [
                            {
                                "$group": {
                                    "_id": {"$ifNull": ["$client_app", "unknown"]},
                                    "total_calls": {"$sum": 1},
                                }
                            },
                            {"$sort": {"_id": 1}},
                        ],
                        "users": [
                            {"$group": {"_id": "$user_id", "total_calls": {"$sum": 1}}},
                            {"$sort": {"total_calls": -1, "_id": 1}},
                        ],
                        "errors": [
                            {"$match": {"outcome": "error"}},
                            {
                                "$group": {
                                    "_id": {"$ifNull": ["$error_code", None]},
                                    "total_calls": {"$sum": 1},
                                }
                            },
                            {"$sort": {"total_calls": -1, "_id": 1}},
                        ],
                    }
                },
            ]
        )
    )
    result = performance(data["tools"])
    total = result["total_calls"]
    timeline = {group["_id"]: group for group in data["timeline"]}
    buckets = []
    bucket = datetime.combine(date_from, time.min, timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, timezone.utc)
    while bucket < end:
        counts = (
            summarize([timeline[bucket.strftime(date_format)]])
            if bucket.strftime(date_format) in timeline
            else summarize([])
        )
        buckets.append(
            {
                "bucket": bucket,
                **{
                    key: counts[key]
                    for key in [
                        "total_calls",
                        "successful_calls",
                        "failed_calls",
                        "cancelled_calls",
                    ]
                },
            }
        )
        bucket += timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
    users = [group for group in data["users"] if group["_id"] is not None]
    return {
        **result,
        "date_from": date_from,
        "date_to": date_to,
        "granularity": granularity,
        "generated_at": datetime.now(timezone.utc),
        "tools_called": len(data["tools"]),
        "identified_users": len(users),
        "anonymous_calls": sum(
            group["total_calls"] for group in data["users"] if group["_id"] is None
        ),
        "by_tool": [
            {
                "tool_name": group["_id"],
                **performance([group]),
                "usage_share": round(100 * group["total_calls"] / total, 2)
                if total
                else 0,
            }
            for group in data["tools"]
        ],
        "timeline": buckets,
        "by_client": [
            {"client_app": group["_id"], "total_calls": group["total_calls"]}
            for group in data["clients"]
        ],
        "by_user": [
            {"user_id": group["_id"], "total_calls": group["total_calls"]}
            for group in users[:10]
        ],
        "by_error_code": [
            {"error_code": group["_id"], "total_calls": group["total_calls"]}
            for group in data["errors"]
        ],
    }


def events(collection, *, limit=20, offset=0, order="newest", **filters):
    query = build_query(**filters)
    total = collection.count_documents(query)
    direction = 1 if order == "oldest" else -1
    # Explicit projection also protects the interface if stored documents ever
    # gain unrelated fields. Tool arguments/results are never part of this API.
    fields = [
        "tool_name",
        "user_id",
        "client_app",
        "request_group_id",
        "started_at",
        "completed_at",
        "duration_ms",
        "outcome",
        "error_code",
    ]
    rows = list(
        collection.find(query, {field: 1 for field in fields})
        .sort([("started_at", direction), ("_id", direction)])
        .skip(offset)
        .limit(limit)
    )
    return {
        "items": [{"event_id": str(row.pop("_id")), **row} for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    }
