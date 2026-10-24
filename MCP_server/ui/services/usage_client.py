"""All UI HTTP calls live here; no database, MCP protocol or model access."""

from datetime import date
import httpx
from pydantic import ValidationError
from MCP_server.schemas import UsageInsights, UsageEventPage
from settings import env


class ApiError(Exception):
    pass


class UsageClient:
    def __init__(self, base_url=None, transport=None):
        self.base_url = (
            base_url or env("MCP_API_URL", "http://127.0.0.1:8003")
        ).rstrip("/")
        self.transport = transport

    def _get(self, path, model, params):
        query = {
            key: value.isoformat()
            if isinstance(value, date)
            else str(value).lower()
            if isinstance(value, bool)
            else value
            for key, value in params.items()
            if value is not None
        }
        try:
            with httpx.Client(timeout=30, transport=self.transport) as client:
                response = client.get(self.base_url + path, params=query)
        except httpx.RequestError:
            raise ApiError(
                "MCP statistics are unavailable or timed out. Check the MCP API and MongoDB, then refresh explicitly."
            ) from None
        try:
            data = response.json()
        except ValueError:
            raise ApiError("MCP returned an unreadable statistics response.") from None
        if response.is_error:
            detail = (
                data.get("detail", "Statistics request failed")
                if isinstance(data, dict)
                else "Statistics request failed"
            )
            if isinstance(detail, list):
                detail = "; ".join(
                    error.get("msg", "Invalid filter") for error in detail
                )
            raise ApiError(str(detail))
        try:
            return model.model_validate(data)
        except ValidationError:
            raise ApiError("MCP returned an unexpected statistics response.") from None

    def insights(self, **filters):
        return self._get("/usage/insights", UsageInsights, filters)

    def events(self, *, limit=20, offset=0, order="newest", **filters):
        return self._get(
            "/usage/events",
            UsageEventPage,
            {**filters, "limit": limit, "offset": offset, "order": order},
        )


def get_client():
    return UsageClient()
