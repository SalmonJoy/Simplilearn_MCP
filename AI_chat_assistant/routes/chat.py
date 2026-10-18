from fastapi import APIRouter
from fastapi.responses import FileResponse
from AI_chat_assistant.config import APP_DIR
from AI_chat_assistant.schemas import ChatRequest, ChatResponse
from AI_chat_assistant.services.chat_service import chat

router = APIRouter()


@router.get("/", include_in_schema=False)
def index():
    return FileResponse(APP_DIR / "templates" / "index.html")


@router.post("/chat", response_model=ChatResponse)
async def send_message(body: ChatRequest):
    return await chat(body)
