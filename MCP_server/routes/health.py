from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "transport": "streamable-http", "endpoint": "/mcp"}
