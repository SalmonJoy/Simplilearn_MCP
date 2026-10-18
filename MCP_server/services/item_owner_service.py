"""Compose Inventory and HRMS REST calls into one read-only MCP tool."""

from urllib.parse import quote
from MCP_server.config import HRMS_URL, INVENTORY_URL
from MCP_server.services.api_service import request_api, tool_result


def error(code, message):
    return tool_result({"code": code, "message": message}, is_error=True)


async def get_item_owners(client, *, item_type=None, item_id=None, limit=20, offset=0):
    if (item_type is None) == (item_id is None):
        return error(422, "Provide exactly one of item_type or item_id")
    if item_type is not None:
        item_type = item_type.strip().lower()
        if not item_type:
            return error(422, "item_type must not be blank")

    if item_id is not None:
        result = await request_api(
            client, "GET", INVENTORY_URL + "/items/" + quote(item_id, safe="")
        )
        if result.is_error:
            return result
        items = [result.structured_content]
    else:
        items, inventory_offset, expected_total = [], 0, None
        while True:
            result = await request_api(
                client,
                "GET",
                INVENTORY_URL + "/items",
                params={
                    "item_type": item_type,
                    "status": "assigned",
                    "limit": 100,
                    "offset": inventory_offset,
                },
            )
            if result.is_error:
                return result
            page = result.structured_content
            if expected_total is None:
                expected_total = page["total"]
            if page["total"] != expected_total:
                return error(
                    409, "Inventory changed while paginating; repeat the lookup"
                )
            items.extend(page["items"])
            if not page["has_more"]:
                if len(items) != expected_total or len(
                    {item["item_id"] for item in items}
                ) != len(items):
                    return error(
                        409, "Inventory changed while paginating; repeat the lookup"
                    )
                break
            if not page["items"]:
                return error(
                    503,
                    "Inventory returned an incomplete page; no owner list was produced",
                )
            inventory_offset += len(page["items"])

    owner_ids = set()
    for item in items:
        if item["status"] == "assigned":
            employee_id = (item.get("assignment") or {}).get("employee_id")
            if not employee_id:
                return error(503, "An assigned item has no employee reference")
            owner_ids.add(employee_id)

    # Deduplicate and paginate owners, rather than physical units.
    ordered_ids = sorted(owner_ids)
    employees = []
    for employee_id in ordered_ids[offset : offset + limit]:
        result = await request_api(
            client, "GET", HRMS_URL + "/employees/" + quote(employee_id, safe="")
        )
        if result.is_error:
            if result.structured_content["code"] == 404:
                return error(
                    404, f"Assigned employee {employee_id} was not found in HRMS"
                )
            return result
        employee = result.structured_content
        employees.append(
            {key: employee[key] for key in ("employee_id", "full_name", "email")}
        )

    return tool_result(
        {
            "items": employees,
            "total": len(ordered_ids),
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(employees) < len(ordered_ids),
        }
    )
