from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.database import SessionLocal
from app.models.models import Profile


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def get_or_create_profile(db) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.id == 1))
    if profile is not None:
        return profile

    profile = Profile(id=1, full_name="")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/profile")
async def profile_page(request: Request):
    with SessionLocal() as db:
        profile = get_or_create_profile(db)
        title = profile.full_name.strip() if profile.full_name else "Мой профиль"
        show_contact_warning = request.query_params.get("contact_warning") == "1"

        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "active_page": "profile",
                "profile": profile,
                "page_title": title,
                "flash_success": "✓ Профиль обновлён"
                if request.query_params.get("saved") == "1"
                else None,
                "contact_warning": show_contact_warning,
            },
        )


@router.post("/profile")
async def save_profile(request: Request):
    form = await request.form()
    is_autosave = request.headers.get("x-autosave") == "summary"

    with SessionLocal() as db:
        profile = get_or_create_profile(db)

        if is_autosave:
            profile.summary_raw = form.get("summary_raw") or None
            db.commit()
            return JSONResponse({"status": "ok"})

        profile.full_name = (form.get("full_name") or "").strip()
        profile.email = (form.get("email") or "").strip() or None
        profile.phone = (form.get("phone") or "").strip() or None
        profile.location = (form.get("location") or "").strip() or None
        profile.linkedin_url = (form.get("linkedin_url") or "").strip() or None
        profile.github_url = (form.get("github_url") or "").strip() or None
        profile.telegram = (form.get("telegram") or "").strip() or None
        profile.summary_raw = form.get("summary_raw") or None

        has_contact_warning = not profile.email or not profile.phone
        db.commit()

    redirect_url = "/profile?saved=1"
    if has_contact_warning:
        redirect_url += "&contact_warning=1"
    return RedirectResponse(redirect_url, status_code=303)
