"""One explicit request to the chat host; no MCP or model calls in the UI."""

import httpx
from pydantic import ValidationError
from AI_chat_assistant.schemas import ChatRequest
from AI_chat_assistant.ui.schemas import ChatResult
from settings import env


class ApiError(Exception):
    pass


class ChatClient:
    def __init__(self, base_url=None, transport=None):
        self.base_url = (base_url or env("CHAT_URL", "http://127.0.0.1:8004")).rstrip(
            "/"
        )
        self.transport = transport

    def send(self, message, history, user_id=None):
        body = ChatRequest(message=message, history=history, user_id=user_id)
        try:
            with httpx.Client(
                timeout=httpx.Timeout(30, read=3000), transport=self.transport
            ) as client:
                response = client.post(
                    self.base_url + "/chat", json=body.model_dump(exclude_none=True)
                )
        except httpx.RequestError:
            raise ApiError(
                "The chat request could not be confirmed. Check that the chat API is running. Changes may have completed; read the affected records before repeating a write."
            ) from None
        try:
            data = response.json()
        except ValueError:
            raise ApiError(
                "Chat returned an unreadable response. Review affected records before repeating a write."
            ) from None
        if response.is_error:
            detail = (
                data.get("detail", "Chat request failed")
                if isinstance(data, dict)
                else "Chat request failed"
            )
            raise ApiError(str(detail))
        try:
            return ChatResult.model_validate(data)
        except ValidationError:
            raise ApiError(
                "Chat returned an unexpected response. Review affected records before repeating a write."
            ) from None


def get_client():
    return ChatClient()
