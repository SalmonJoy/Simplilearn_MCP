"""The MCP SDK generates wire schemas from the typed tool functions."""

from mcp.types import CallToolResult, TextContent, ToolAnnotations

__all__ = ["CallToolResult", "TextContent", "READ", "WRITE"]

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)
