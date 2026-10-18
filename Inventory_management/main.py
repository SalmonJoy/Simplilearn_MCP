from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from Inventory_management import database
from Inventory_management.routes.items import router


@asynccontextmanager
async def lifespan(app):
    client, app.state.collection = database.connect()
    try:
        database.create_indexes(app.state.collection)
        yield
    finally:
        client.close()


app = FastAPI(title="Learning MCP — Inventory", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(PyMongoError)
async def database_error(request, exc):
    return JSONResponse(
        status_code=503, content={"detail": "Inventory database unavailable"}
    )


@app.get("/health", tags=["Health"])
def health():
    app.state.collection.database.client.admin.command("ping")
    return {"status": "ok"}
