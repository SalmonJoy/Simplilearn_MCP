from contextlib import asynccontextmanager
import asyncio
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from mcp.server import MCPServer
from MCP_server.routes.health import router
from MCP_server.tools.business_tools import register_tools
from MCP_server.tools.memory_tools import register_memory_tools
from MCP_server.usage_middleware import usage_middleware
from MCP_server.routes.usage import router as usage_router
from MCP_server import database


def create_app():
    # Each application instance needs a fresh SDK session manager; it runs once.
    mcp = MCPServer("HRMS and Inventory Learning Tools")

    @asynccontextmanager
    async def lifespan(app):
        mongo, app.state.database = await asyncio.to_thread(database.connect)
        try:
            await asyncio.to_thread(database.initialize, app.state.database)
            async with httpx.AsyncClient(timeout=15) as client:
                app.state.http = client
                async with mcp.session_manager.run():
                    yield
        finally:
            await asyncio.to_thread(mongo.close)

    app = FastAPI(title="Learning MCP — Tool Server", lifespan=lifespan)
    register_tools(mcp, lambda: app.state.http)
    mcp.middleware.append(
        usage_middleware(lambda: app.state.database.tool_usage_events)
    )
    register_memory_tools(mcp, lambda: app.state.database.user_preferences)
    app.include_router(router)
    app.include_router(usage_router)

    @app.exception_handler(PyMongoError)
    async def database_error(request, exc):
        return JSONResponse(
            status_code=503, content={"detail": "MCP database unavailable"}
        )

    # The SDK already registers /mcp. Put operational REST routes before the mount.
    app.mount("/", mcp.streamable_http_app(json_response=True))
    return app


app = create_app()
