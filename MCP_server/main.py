from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from mcp.server import MCPServer
from MCP_server.routes.health import router
from MCP_server.tools.business_tools import register_tools

mcp = MCPServer("HRMS and Inventory Learning Tools")


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=15) as client:
        app.state.http = client
        async with mcp.session_manager.run():
            yield


app = FastAPI(title="Learning MCP — Tool Server", lifespan=lifespan)
register_tools(mcp, lambda: app.state.http)
app.include_router(router)
# Mount at root because the SDK already registers /mcp. Put REST routes first.
app.mount("/", mcp.streamable_http_app(json_response=True))
