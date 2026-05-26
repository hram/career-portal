from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.database import SessionLocal
from app.models.models import Profile, ResumeTemplate


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def get_profile(db) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.id == 1))
    if profile is not None:
        return profile

    profile = Profile(id=1, full_name="")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def get_role_or_404(db, role_id: int) -> ResumeTemplate:
    role = db.get(ResumeTemplate, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.get("/roles")
async def roles_page(request: Request):
    with SessionLocal() as db:
        profile = get_profile(db)
        roles = db.scalars(
            select(ResumeTemplate)
            .where(ResumeTemplate.profile_id == profile.id)
            .order_by(ResumeTemplate.is_default.desc(), ResumeTemplate.id)
        ).all()

        return templates.TemplateResponse(
            "resume_templates.html",
            {
                "request": request,
                "active_page": "roles",
                "roles": roles,
                "flash_success": "Роль создана" if request.query_params.get("created") == "1" else None,
            },
        )


@router.post("/roles")
async def create_role(request: Request):
    form = await request.form()
    name = str(form.get("name") or "").strip()
    focus_areas = str(form.get("focus_areas") or "").strip()
    if not name or not focus_areas:
        return RedirectResponse("/roles", status_code=303)

    with SessionLocal() as db:
        profile = get_profile(db)
        role = ResumeTemplate(
            profile_id=profile.id,
            name=name,
            description=str(form.get("description") or "").strip() or None,
            focus_areas=focus_areas,
            tone=str(form.get("tone") or "").strip() or None,
            hh_search_query=str(form.get("hh_search_query") or "").strip() or None,
            is_default=False,
        )
        db.add(role)
        db.commit()

    return RedirectResponse("/roles?created=1", status_code=303)


@router.get("/roles/{role_id}/edit")
async def role_edit_page(request: Request, role_id: int):
    with SessionLocal() as db:
        role = get_role_or_404(db, role_id)
        return templates.TemplateResponse(
            "role_edit.html",
            {
                "request": request,
                "active_page": "roles",
                "role": role,
            },
        )


@router.post("/roles/{role_id}")
async def update_role(request: Request, role_id: int):
    form = await request.form()
    name = str(form.get("name") or "").strip()
    focus_areas = str(form.get("focus_areas") or "").strip()
    if not name or not focus_areas:
        return RedirectResponse(f"/roles/{role_id}/edit", status_code=303)

    with SessionLocal() as db:
        role = get_role_or_404(db, role_id)
        role.name = name
        role.description = str(form.get("description") or "").strip() or None
        role.focus_areas = focus_areas
        role.tone = str(form.get("tone") or "").strip() or None
        role.hh_search_query = str(form.get("hh_search_query") or "").strip() or None
        db.commit()

    return RedirectResponse("/roles", status_code=303)


@router.delete("/roles/{role_id}")
async def delete_role(role_id: int):
    with SessionLocal() as db:
        role = db.get(ResumeTemplate, role_id)
        if role is not None:
            db.delete(role)
            db.commit()
    return JSONResponse({"status": "ok"})


@router.get("/roles/{role_id}/hh")
async def search_role_on_hh(role_id: int):
    with SessionLocal() as db:
        role = get_role_or_404(db, role_id)
        query = role.hh_search_query or role.name
    return RedirectResponse(f"/hh?{urlencode({'text': query})}", status_code=303)
