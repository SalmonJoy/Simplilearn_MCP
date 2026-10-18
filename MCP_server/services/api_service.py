import json
import httpx
from MCP_server.schemas import CallToolResult, TextContent


def tool_result(data, *, is_error=False):
    """Expose the same JSON in MCP text and structured content."""
    return CallToolResult(
        content=[TextContent(text=json.dumps(data))],
        structuredContent=data,
        isError=is_error,
    )


async def request_api(
    client: httpx.AsyncClient, method, url, *, params=None, body=None
):
    """One upstream request. In particular, never automatically retry writes."""
    try:
        response = await client.request(
            method,
            url,
            params={k: v for k, v in (params or {}).items() if v is not None},
            json=body,
        )
        try:
            data = response.json()
        except ValueError:
            data = {
                "code": 503,
                "message": "Upstream returned an invalid JSON response",
            }
            return tool_result(data, is_error=True)
        if response.is_error:
            data = {
                "code": response.status_code,
                "message": data.get("detail", "Upstream request failed"),
            }
        return tool_result(data, is_error=response.is_error)
    except httpx.RequestError:
        data = {
            "code": 503,
            "message": "Upstream unavailable. For a write, re-read the record before retrying; the outcome may be unknown.",
        }
        return tool_result(data, is_error=True)
