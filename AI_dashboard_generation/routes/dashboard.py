from fastapi import APIRouter
from fastapi.responses import FileResponse
from AI_dashboard_generation.config import APP_DIR
from AI_dashboard_generation.schemas import GenerateRequest
from AI_dashboard_generation.services.dashboard_service import generate

router = APIRouter()


@router.get("/", include_in_schema=False)
def index():
    return FileResponse(APP_DIR / "templates" / "index.html")


@router.post("/dashboards/generate")
async def generate_dashboard(body: GenerateRequest):
    return await generate(body.instruction)
