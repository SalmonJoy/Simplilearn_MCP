import httpx
import pytest
from MCP_server.services.item_owner_service import get_item_owners


async def test_inventory_paging_then_distinct_owner_paging():
    items = [
        {
            "item_id": f"ITEM{i:03}",
            "status": "assigned",
            "assignment": {"employee_id": f"EMP{102 - i:03}"},
        }
        for i in range(1, 102)
    ]
    items.append(
        {
            "item_id": "ITEM102",
            "status": "assigned",
            "assignment": {"employee_id": "EMP001"},
        }
    )
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/items":
            assert request.url.params["status"] == "assigned"
            assert request.url.params["item_type"] == "laptop"
            assert request.url.params["limit"] == "100"
            start = int(request.url.params["offset"])
            return httpx.Response(
                200,
                json={
                    "items": items[start : start + 100],
                    "total": len(items),
                    "has_more": start + 100 < len(items),
                },
            )
        employee_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "employee_id": employee_id,
                "full_name": "Demo " + employee_id,
                "email": employee_id.lower() + "@example.test",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await get_item_owners(client, item_type=" LAPTOP ", limit=3, offset=98)
    assert not result.is_error
    page = result.structured_content
    assert page["total"] == 101 and not page["has_more"]
    assert [owner["employee_id"] for owner in page["items"]] == [
        "EMP099",
        "EMP100",
        "EMP101",
    ]
    assert len(calls) == 5  # Two Inventory pages, only three selected HRMS employees.


@pytest.mark.parametrize(
    "failure", ["inventory", "hrms", "missing_employee", "network", "malformed_json"]
)
async def test_failures_never_return_partial_owners(failure):
    def handler(request):
        if failure == "network":
            raise httpx.ConnectError("Simulated outage")
        if failure == "malformed_json":
            return httpx.Response(200, text="not JSON")
        if request.url.path == "/items":
            if failure == "inventory":
                return httpx.Response(503, json={"detail": "Inventory unavailable"})
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "item_id": "ITEM001",
                            "status": "assigned",
                            "assignment": {"employee_id": "EMP001"},
                        },
                        {
                            "item_id": "ITEM002",
                            "status": "assigned",
                            "assignment": {"employee_id": "EMP002"},
                        },
                    ],
                    "total": 2,
                    "has_more": False,
                },
            )
        if request.url.path.endswith("EMP001"):
            return httpx.Response(
                200,
                json={
                    "employee_id": "EMP001",
                    "full_name": "Demo One",
                    "email": "one@example.test",
                },
            )
        return httpx.Response(
            404 if failure == "missing_employee" else 503,
            json={
                "detail": "Employee not found"
                if failure == "missing_employee"
                else "HRMS unavailable"
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await get_item_owners(client, item_type="laptop")
    assert result.is_error and "items" not in result.structured_content
    assert result.structured_content["code"] == (
        404 if failure == "missing_employee" else 503
    )
    if failure == "missing_employee":
        assert "EMP002" in result.structured_content["message"]


async def test_incomplete_inventory_page_fails():
    def handler(request):
        return httpx.Response(200, json={"items": [], "total": 1, "has_more": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await get_item_owners(client, item_type="laptop")
    assert result.is_error and result.structured_content["code"] == 503
