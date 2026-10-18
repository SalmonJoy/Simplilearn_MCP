from datetime import date
from typing import Annotated
from urllib.parse import quote
from pydantic import Field
from HRMS.schemas import EmployeePatch, EmployeeStatus, Identifier, Text
from Inventory_management.schemas import Category, ItemStatus
from MCP_server.config import HRMS_URL, INVENTORY_URL
from MCP_server.schemas import READ, WRITE, CallToolResult
from MCP_server.services.api_service import request_api
from MCP_server.services.item_owner_service import get_item_owners

Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0)]


def register_tools(mcp, client_provider):
    """Nine REST adapters plus one composite tool using Inventory and HRMS."""

    async def request(method, base, path, params=None, body=None):
        return await request_api(
            client_provider(), method, base + path, params=params, body=body
        )

    @mcp.tool(annotations=WRITE)
    async def hrms_create_employee(
        employee_id: Identifier,
        full_name: Text,
        email: Text,
        department: Text,
        designation: Text,
        joining_date: date,
        status: EmployeeStatus = "joining",
    ) -> CallToolResult:
        """Create an employee only when the user explicitly requests it. Requires a unique employee ID and email."""
        body = dict(
            employee_id=employee_id,
            full_name=full_name,
            email=email,
            department=department,
            designation=designation,
            joining_date=joining_date.isoformat(),
            status=status,
        )
        return await request("POST", HRMS_URL, "/employees", body=body)

    @mcp.tool(annotations=READ)
    async def hrms_list_employees(
        name: str | None = None,
        department: str | None = None,
        status: EmployeeStatus | None = None,
        joining_from: date | None = None,
        joining_to: date | None = None,
        limit: Limit = 20,
        offset: Offset = 0,
    ) -> CallToolResult:
        """Find employees by literal name substring, department, status or inclusive joining dates. Paginated; inspect has_more."""
        return await request(
            "GET",
            HRMS_URL,
            "/employees",
            params=dict(
                name=name,
                department=department,
                status=status,
                joining_from=joining_from,
                joining_to=joining_to,
                limit=limit,
                offset=offset,
            ),
        )

    @mcp.tool(annotations=READ)
    async def hrms_get_employee_summary(
        department: str | None = None,
        status: EmployeeStatus | None = None,
        joining_from: date | None = None,
        joining_to: date | None = None,
    ) -> CallToolResult:
        """Get full employee counts by department, status and joining month; optional filters apply to all counts."""
        return await request(
            "GET",
            HRMS_URL,
            "/employees/summary",
            params=dict(
                department=department,
                status=status,
                joining_from=joining_from,
                joining_to=joining_to,
            ),
        )

    @mcp.tool(annotations=READ)
    async def hrms_get_employee(employee_id: Identifier) -> CallToolResult:
        """Get one employee by exact employee ID. Resolve ambiguous names using hrms_list_employees first."""
        return await request(
            "GET", HRMS_URL, "/employees/" + quote(employee_id, safe="")
        )

    @mcp.tool(annotations=WRITE)
    async def hrms_update_employee(
        employee_id: Identifier, changes: EmployeePatch
    ) -> CallToolResult:
        """Update explicitly requested employee fields. changes contains a nonempty subset of editable fields; ID is immutable."""
        return await request(
            "PATCH",
            HRMS_URL,
            "/employees/" + quote(employee_id, safe=""),
            body=changes.model_dump(mode="json", exclude_unset=True),
        )

    @mcp.tool(annotations=READ)
    async def inventory_list_items(
        category: Category | None = None,
        item_type: str | None = None,
        status: ItemStatus | None = None,
        employee_id: Identifier | None = None,
        limit: Limit = 20,
        offset: Offset = 0,
    ) -> CallToolResult:
        """List individual devices or goodies. Filter by current employee ownership, category, type or status. Paginated."""
        return await request(
            "GET",
            INVENTORY_URL,
            "/items",
            params=dict(
                category=category,
                item_type=item_type,
                status=status,
                employee_id=employee_id,
                limit=limit,
                offset=offset,
            ),
        )

    @mcp.tool(annotations=READ)
    async def inventory_get_item(item_id: Identifier) -> CallToolResult:
        """Get one inventory unit and its current assignment by exact item ID."""
        return await request("GET", INVENTORY_URL, "/items/" + quote(item_id, safe=""))

    @mcp.tool(annotations=READ)
    async def inventory_get_item_owners(
        item_type: str | None = None,
        item_id: Identifier | None = None,
        limit: Limit = 20,
        offset: Offset = 0,
    ) -> CallToolResult:
        """Find current owners' employee IDs, full names and emails. Provide exactly one of item_type (e.g. laptop) or item_id (e.g. ITEM001). Types are trimmed and lowercased. Employees appear once, regardless of status; paginate owners using has_more."""
        return await get_item_owners(
            client_provider(),
            item_type=item_type,
            item_id=item_id,
            limit=limit,
            offset=offset,
        )

    @mcp.tool(annotations=WRITE)
    async def inventory_assign_item(
        item_id: Identifier, employee_id: Identifier
    ) -> CallToolResult:
        """Assign an available unit to a joining or active employee, only when explicitly requested. Conflicts do not overwrite ownership."""
        return await request(
            "POST",
            INVENTORY_URL,
            "/items/" + quote(item_id, safe="") + "/assign",
            body={"employee_id": employee_id},
        )

    @mcp.tool(annotations=WRITE)
    async def inventory_return_item(
        item_id: Identifier, employee_id: Identifier
    ) -> CallToolResult:
        """Return a unit only when explicitly requested. employee_id must match its current owner; clears current ownership."""
        return await request(
            "POST",
            INVENTORY_URL,
            "/items/" + quote(item_id, safe="") + "/return",
            body={"employee_id": employee_id},
        )
