"""One generation request; data retrieval and calculations stay on the server."""

import httpx
from pydantic import ValidationError
from AI_dashboard_generation.schemas import GenerateRequest
from AI_dashboard_generation.ui.schemas import DashboardResult
from settings import env


class ApiError(Exception):
    pass


class DashboardClient:
    def __init__(self, base_url=None, transport=None):
        self.base_url = (
            base_url or env("DASHBOARD_URL", "http://127.0.0.1:8005")
        ).rstrip("/")
        self.transport = transport

    def generate(self, instruction, user_id=None):
        body = GenerateRequest(instruction=instruction, user_id=user_id)
        try:
            with httpx.Client(
                timeout=httpx.Timeout(30, read=600), transport=self.transport
            ) as client:
                response = client.post(
                    self.base_url + "/dashboards/generate",
                    json=body.model_dump(exclude_none=True),
                )
        except httpx.RequestError:
            raise ApiError(
                "Dashboard service is unavailable or the request timed out. Check the services; generate again explicitly when ready."
            ) from None
        try:
            data = response.json()
        except ValueError:
            raise ApiError(
                "Dashboard service returned an unreadable response."
            ) from None
        if response.is_error:
            detail = (
                data.get("detail", "Dashboard generation failed")
                if isinstance(data, dict)
                else "Dashboard generation failed"
            )
            raise ApiError(str(detail))
        try:
            return DashboardResult.model_validate(data)
        except ValidationError:
            raise ApiError(
                "Dashboard service returned an invalid layout or calculated result. Try a simpler instruction."
            ) from None


def get_client():
    return DashboardClient()
