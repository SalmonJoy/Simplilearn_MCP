import asyncio
from collections.abc import Mapping
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from pymongo.errors import PyMongoError
from mcp.server.mcpserver import Context
from MCP_server.identity import request_identity
from MCP_server.schemas import READ, WRITE, CallToolResult
from MCP_server.services.api_service import tool_result
from MCP_server.services import preference_service

Scope = Literal["chat", "dashboard"]
PreferenceKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
PreferenceValue = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class ReadPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeletePreference(ReadPreferences):
    scope: Scope
    key: PreferenceKey


class SavePreference(DeletePreference):
    value: PreferenceValue


async def validate_memory_arguments(ctx, call_next):
    models = {
        "memory_get_preferences": ReadPreferences,
        "memory_set_preference": SavePreference,
        "memory_delete_preference": DeletePreference,
    }
    params = ctx.params if isinstance(ctx.params, Mapping) else {}
    name = params.get("name")
    model = (
        models.get(name)
        if ctx.method == "tools/call" and isinstance(name, str)
        else None
    )
    if model:
        try:
            model.model_validate(params.get("arguments") or {})
        except ValidationError:
            return tool_result(
                {
                    "code": 422,
                    "message": "Invalid preference arguments. Use a valid scope, key and nonempty value; user identity is supplied by the client.",
                },
                is_error=True,
            )
    return await call_next(ctx)


def register_memory_tools(mcp, collection_provider):
    # Keep the SDK's typed schemas while giving invalid memory input the same
    # structured error envelope as business adapters. Usage middleware goes first.
    mcp.middleware.append(validate_memory_arguments)

    async def execute(ctx, operation, *args):
        user_id = request_identity(ctx.request_context.request)["user_id"]
        if not user_id:
            return tool_result(
                {
                    "code": 422,
                    "message": "Preference memory requires a valid X-Demo-User-ID header.",
                },
                is_error=True,
            )
        try:
            data = await asyncio.to_thread(
                operation, collection_provider(), user_id, *args
            )
        except PyMongoError:
            return tool_result(
                {
                    "code": 503,
                    "message": "Preference storage is unavailable. A save or delete may have completed; read preferences before retrying.",
                },
                is_error=True,
            )
        return tool_result(data)

    @mcp.tool(annotations=READ)
    async def memory_get_preferences(ctx: Context) -> CallToolResult:
        """Read the current demo user's saved chat and dashboard preferences. Missing profiles return empty maps. Identity comes from the client, not tool arguments."""
        return await execute(ctx, preference_service.get_preferences)

    @mcp.tool(annotations=WRITE)
    async def memory_set_preference(
        scope: Scope, key: PreferenceKey, value: PreferenceValue, ctx: Context
    ) -> CallToolResult:
        """Remember one presentation preference only when the latest user message explicitly asks to remember or change it. scope is chat or dashboard; key is a short identifier, value is plain text. Never save inferred preferences or use memory to authorize business writes."""
        return await execute(ctx, preference_service.set_preference, scope, key, value)

    @mcp.tool(annotations=WRITE)
    async def memory_delete_preference(
        scope: Scope, key: PreferenceKey, ctx: Context
    ) -> CallToolResult:
        """Forget one saved preference only when explicitly requested. Returns whether the preference existed. Does not delete conversations or employee records."""
        return await execute(ctx, preference_service.delete_preference, scope, key)
