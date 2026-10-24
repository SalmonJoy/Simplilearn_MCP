"""Demo identity comes from HTTP context, never model-supplied tool arguments."""

from pydantic import TypeAdapter, ValidationError
from HRMS.schemas import Identifier

USER_HEADER = "X-Demo-User-ID"
APP_HEADER = "X-MCP-Client"
GROUP_HEADER = "X-MCP-Request-ID"


def valid_identifier(value):
    if value is None:
        return None
    try:
        return TypeAdapter(Identifier).validate_python(value)
    except ValidationError:
        return None


def request_identity(request):
    headers = request.headers if request is not None else {}
    source = headers.get(APP_HEADER)
    return {
        "user_id": valid_identifier(headers.get(USER_HEADER)),
        "client_app": source if source in {"chat", "dashboard"} else "unknown",
        "request_group_id": valid_identifier(headers.get(GROUP_HEADER)),
    }
