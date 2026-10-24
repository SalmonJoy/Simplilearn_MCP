"""REST requests and complete pagination; no database access or retries."""

from urllib.parse import quote
import httpx
from pydantic import TypeAdapter, ValidationError
from Inventory_management.schemas import AssignmentRequest, Identifier, Item, ItemPage
from settings import env


class ApiError(Exception):
    def __init__(self, message, status_code=None, uncertain=False):
        super().__init__(message)
        self.status_code = status_code
        self.uncertain = uncertain


class InventoryClient:
    def __init__(self, base_url=None, transport=None):
        self.base_url = (
            base_url or env("INVENTORY_URL", "http://127.0.0.1:8002")
        ).rstrip("/")
        self.transport = transport

    def _request(self, method, path, model, *, params=None, body=None):
        writing = method == "POST"
        try:
            with httpx.Client(timeout=30, transport=self.transport) as client:
                response = client.request(
                    method, self.base_url + path, params=params, json=body
                )
        except httpx.RequestError:
            raise ApiError(
                "The change could not be confirmed. Reload this item before submitting again; it may have completed."
                if writing
                else "Inventory is unavailable. Check the API and refresh.",
                uncertain=writing,
            ) from None
        try:
            data = response.json()
        except ValueError:
            raise ApiError(
                "Inventory returned an unreadable response. Reload the item before trying again.",
                uncertain=writing,
            ) from None
        if response.is_error:
            detail = (
                data.get("detail", "Inventory request failed")
                if isinstance(data, dict)
                else "Inventory request failed"
            )
            if isinstance(detail, list):
                detail = "; ".join(
                    error.get("msg", "Invalid input") for error in detail
                )
            raise ApiError(
                str(detail),
                response.status_code,
                uncertain=writing and response.status_code >= 500,
            )
        try:
            return model.model_validate(data)
        except ValidationError:
            raise ApiError(
                "Inventory returned an unexpected response. Reload before trying again.",
                uncertain=writing,
            ) from None

    def list_items(self, *, limit=20, offset=0, **filters):
        return self._request(
            "GET",
            "/items",
            ItemPage,
            params={
                "limit": limit,
                "offset": offset,
                **{key: value for key, value in filters.items() if value is not None},
            },
        )

    def get_item(self, item_id):
        identifier = TypeAdapter(Identifier).validate_python(item_id)
        return self._request("GET", "/items/" + quote(identifier, safe=""), Item)

    def _change_assignment(self, action, item_id, employee_id):
        identifier = TypeAdapter(Identifier).validate_python(item_id)
        body = AssignmentRequest(employee_id=employee_id)
        return self._request(
            "POST",
            f"/items/{quote(identifier, safe='')}/{action}",
            Item,
            body=body.model_dump(),
        )

    def assign_item(self, item_id, employee_id):
        return self._change_assignment("assign", item_id, employee_id)

    def return_item(self, item_id, employee_id):
        return self._change_assignment("return", item_id, employee_id)

    def all_items(self):
        rows, seen, offset, total = [], set(), 0, None
        while True:
            page = self.list_items(limit=100, offset=offset)
            if total is None:
                total = page.total
            ids = [item.item_id for item in page.items]
            if (
                page.total != total
                or page.limit != 100
                or page.offset != offset
                or len(ids) != len(set(ids))
                or seen.intersection(ids)
                or len(rows) + len(ids) > total
                or page.has_more != (offset + len(ids) < total)
            ):
                raise ApiError(
                    "Inventory changed while paging or returned inconsistent pages. Refresh; totals were not calculated."
                )
            rows.extend(page.items)
            seen.update(ids)
            if not page.has_more:
                if len(rows) != total:
                    raise ApiError(
                        "Inventory data is incomplete. Refresh; totals were not calculated."
                    )
                return rows
            if not page.items:
                raise ApiError(
                    "Inventory returned an empty intermediate page. Totals were not calculated."
                )
            offset += len(page.items)


def get_client():
    return InventoryClient()
