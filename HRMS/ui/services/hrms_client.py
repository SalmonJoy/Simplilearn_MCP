"""All frontend HTTP requests live here; no MongoDB or MCP dependencies."""

from urllib.parse import quote
import httpx
from pydantic import TypeAdapter, ValidationError
from HRMS.schemas import (
    Employee,
    EmployeeCreate,
    EmployeePage,
    EmployeePatch,
    EmployeeSummary,
    Identifier,
)
from settings import env


class ApiError(Exception):
    def __init__(self, message, status_code=None, uncertain=False):
        super().__init__(message)
        self.status_code = status_code
        self.uncertain = uncertain


class HRMSClient:
    def __init__(self, base_url=None, transport=None):
        self.base_url = (base_url or env("HRMS_URL", "http://127.0.0.1:8001")).rstrip(
            "/"
        )
        self.transport = transport

    def _request(self, method, path, model, *, params=None, body=None):
        writing = method in {"POST", "PATCH"}
        params = {
            key: str(value)
            for key, value in (params or {}).items()
            if value is not None
        }
        try:
            with httpx.Client(timeout=10, transport=self.transport) as client:
                response = client.request(
                    method, self.base_url + path, params=params, json=body
                )
        except httpx.RequestError:
            message = (
                "HRMS is unavailable. Check that the API is running and try refreshing."
            )
            if writing:
                message = "The write result could not be confirmed. Reload the employee before submitting again; the change may have completed."
            raise ApiError(message, uncertain=writing) from None
        try:
            data = response.json()
        except ValueError:
            raise ApiError(
                "HRMS returned an unreadable response. Refresh before trying again.",
                uncertain=writing,
            ) from None
        if response.is_error:
            detail = (
                data.get("detail", "HRMS request failed")
                if isinstance(data, dict)
                else "HRMS request failed"
            )
            if isinstance(detail, list):
                detail = "; ".join(
                    f"{'.'.join(str(part) for part in error.get('loc', []) if part != 'body')}: {error.get('msg', 'Invalid value')}"
                    for error in detail
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
                "HRMS returned an unexpected response. Refresh before trying again.",
                uncertain=writing,
            ) from None

    def summary(self, **filters) -> EmployeeSummary:
        return self._request(
            "GET", "/employees/summary", EmployeeSummary, params=filters
        )

    def list_employees(self, *, limit=20, offset=0, **filters) -> EmployeePage:
        return self._request(
            "GET",
            "/employees",
            EmployeePage,
            params={**filters, "limit": limit, "offset": offset},
        )

    def get_employee(self, employee_id) -> Employee:
        employee_id = TypeAdapter(Identifier).validate_python(employee_id)
        return self._request(
            "GET", "/employees/" + quote(employee_id, safe=""), Employee
        )

    def create_employee(self, body: EmployeeCreate) -> Employee:
        return self._request(
            "POST", "/employees", Employee, body=body.model_dump(mode="json")
        )

    def update_employee(self, employee_id, changes: EmployeePatch) -> Employee:
        employee_id = TypeAdapter(Identifier).validate_python(employee_id)
        return self._request(
            "PATCH",
            "/employees/" + quote(employee_id, safe=""),
            Employee,
            body=changes.model_dump(mode="json", exclude_unset=True),
        )


def get_client():
    return HRMSClient()
