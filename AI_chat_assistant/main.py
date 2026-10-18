from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from AI_chat_assistant.config import APP_DIR
from AI_chat_assistant.routes.chat import router

app = FastAPI(title="Learning MCP — AI Chat")
app.include_router(router)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}
