from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import SessionLocal
from app.services.settings import SUPPORTED_AI_AGENTS, get_ai_agent, set_ai_agent


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/settings")
async def settings_page(request: Request):
    with SessionLocal() as db:
        selected_agent = get_ai_agent(db)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active_page": "settings",
            "agents": SUPPORTED_AI_AGENTS,
            "selected_agent": selected_agent,
        },
    )


@router.post("/settings")
async def settings_save(request: Request):
    form = await request.form()
    with SessionLocal() as db:
        set_ai_agent(db, form.get("ai_agent"))
        db.commit()
    return RedirectResponse("/settings?saved=1", status_code=303)
