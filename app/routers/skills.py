from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.database import SessionLocal
from app.models.models import Education, ExtraNote, Profile, Skill


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


def _skills_text(skills: list[Skill]) -> str:
    manual = next((item for item in skills if item.category == "manual"), None)
    if manual is not None:
        return manual.raw_dump
    return "\n\n".join(item.raw_dump for item in skills if item.raw_dump)


@router.get("/skills")
async def skills_page(request: Request):
    with SessionLocal() as db:
        profile = get_profile(db)
        skills = db.scalars(
            select(Skill)
            .where(Skill.profile_id == profile.id)
            .order_by(Skill.category.desc(), Skill.id)
        ).all()
        education = db.scalars(
            select(Education)
            .where(Education.profile_id == profile.id)
            .order_by(Education.id.desc())
        ).all()
        notes = db.scalars(
            select(ExtraNote)
            .where(ExtraNote.profile_id == profile.id)
            .order_by(ExtraNote.id.desc())
        ).all()

        return templates.TemplateResponse(
            "skills.html",
            {
                "request": request,
                "active_page": "skills",
                "skills_text": _skills_text(skills),
                "education": education,
                "notes": notes,
                "note_categories": ["сертификат", "достижение", "публикация", "хобби", "другое"],
            },
        )


@router.post("/skills")
async def save_skills(request: Request):
    form = await request.form()
    raw_dump = str(form.get("raw_dump") or "").strip()

    with SessionLocal() as db:
        profile = get_profile(db)
        skill = db.scalar(
            select(Skill).where(Skill.profile_id == profile.id, Skill.category == "manual")
        )
        if skill is None:
            skill = Skill(profile_id=profile.id, raw_dump=raw_dump, category="manual")
            db.add(skill)
        else:
            skill.raw_dump = raw_dump
        db.commit()

    return JSONResponse({"status": "ok"})


@router.post("/education")
async def create_education(request: Request):
    form = await request.form()
    institution = str(form.get("institution") or "").strip()
    if not institution:
        raise HTTPException(status_code=400, detail="Institution is required")

    with SessionLocal() as db:
        profile = get_profile(db)
        item = Education(
            profile_id=profile.id,
            institution=institution,
            degree=str(form.get("degree") or "").strip() or None,
            field=str(form.get("field") or "").strip() or None,
            start_year=str(form.get("start_year") or "").strip() or None,
            end_year=str(form.get("end_year") or "").strip() or None,
            raw_notes=str(form.get("raw_notes") or "").strip() or None,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        return JSONResponse(
            {
                "id": item.id,
                "institution": item.institution or "",
                "degree": item.degree or "",
                "field": item.field or "",
                "start_year": item.start_year or "",
                "end_year": item.end_year or "",
                "raw_notes": item.raw_notes or "",
            }
        )


@router.delete("/education/{education_id}")
async def delete_education(education_id: int):
    with SessionLocal() as db:
        item = db.get(Education, education_id)
        if item is not None:
            db.delete(item)
            db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/notes")
async def create_note(request: Request):
    form = await request.form()
    title = str(form.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    with SessionLocal() as db:
        profile = get_profile(db)
        item = ExtraNote(
            profile_id=profile.id,
            category=str(form.get("category") or "").strip() or "другое",
            title=title,
            raw_content=str(form.get("raw_content") or "").strip() or None,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        return JSONResponse(
            {
                "id": item.id,
                "category": item.category or "",
                "title": item.title,
                "raw_content": item.raw_content or "",
            }
        )


@router.delete("/notes/{note_id}")
async def delete_note(note_id: int):
    with SessionLocal() as db:
        item = db.get(ExtraNote, note_id)
        if item is not None:
            db.delete(item)
            db.commit()
    return JSONResponse({"status": "ok"})
