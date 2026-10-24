from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request):
    request.app.state.database.client.admin.command("ping")
    return {
        "status": "ok",
        "database": "ok",
        "transport": "streamable-http",
        "endpoint": "/mcp",
    }
