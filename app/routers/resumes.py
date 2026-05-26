import html
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models.models import GeneratedResume, Profile, ResumeTemplate, SavedVacancy
from app.services.ai_agent import AIAgentError, build_resume_prompt_preview, generate_resume
from app.services.settings import get_ai_agent


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


def _load_roles(db, profile_id: int) -> list[ResumeTemplate]:
    return list(
        db.scalars(
            select(ResumeTemplate)
            .where(ResumeTemplate.profile_id == profile_id)
            .order_by(ResumeTemplate.is_default.desc(), ResumeTemplate.id)
        ).all()
    )


@router.get("/generate")
async def generate_page(request: Request):
    selected_template_id = _int_or_none(request.query_params.get("template_id"))
    selected_vacancy_id = _int_or_none(request.query_params.get("vacancy_id"))
    with SessionLocal() as db:
        profile = get_profile(db)
        roles = _load_roles(db, profile.id)
        if selected_template_id is None and roles:
            selected_template_id = roles[0].id
        selected_agent = get_ai_agent(db)
        values = {}
        if selected_vacancy_id is not None:
            vacancy = db.scalar(
                select(SavedVacancy).where(
                    SavedVacancy.id == selected_vacancy_id,
                    SavedVacancy.profile_id == profile.id,
                )
            )
            if vacancy is not None:
                values = {
                    "company_name": vacancy.company_name or "",
                    "vacancy_url": vacancy.vacancy_url or "",
                    "vacancy_text": vacancy.description_text or "",
                }

        return templates.TemplateResponse(
            "generate.html",
            {
                "request": request,
                "active_page": "generate",
                "roles": roles,
                "selected_template_id": selected_template_id,
                "selected_agent": selected_agent,
                "values": values,
                "flash_error": "Сначала создай хотя бы одну роль" if not roles else None,
                "flash_success": "Вакансия hh.ru подставлена в форму" if values else None,
            },
        )


@router.post("/generate")
async def create_generated_resume(request: Request):
    form = await request.form()
    template_id = _int_or_none(form.get("template_id"))
    vacancy_text = str(form.get("vacancy_text") or "").strip()
    company_name = str(form.get("company_name") or "").strip()
    vacancy_url = str(form.get("vacancy_url") or "").strip()

    with SessionLocal() as db:
        profile = get_profile(db)
        roles = _load_roles(db, profile.id)
        selected_agent = get_ai_agent(db)

        if template_id is None:
            return templates.TemplateResponse(
                "generate.html",
                {
                    "request": request,
                    "active_page": "generate",
                    "roles": roles,
                    "selected_template_id": template_id,
                    "selected_agent": selected_agent,
                    "values": {
                        "company_name": company_name,
                        "vacancy_url": vacancy_url,
                        "vacancy_text": vacancy_text,
                    },
                    "flash_error": "Выбери роль",
                },
                status_code=400,
            )

        role = db.scalar(
            select(ResumeTemplate).where(
                ResumeTemplate.id == template_id,
                ResumeTemplate.profile_id == profile.id,
            )
        )
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")

        try:
            result_markdown = generate_resume(
                db,
                profile_id=profile.id,
                template_id=role.id,
                vacancy_text=vacancy_text,
                company_name=company_name,
                vacancy_url=vacancy_url,
                provider=selected_agent,
            )
        except AIAgentError as exc:
            return templates.TemplateResponse(
                "generate.html",
                {
                    "request": request,
                    "active_page": "generate",
                    "roles": roles,
                    "selected_template_id": role.id,
                    "selected_agent": selected_agent,
                    "values": {
                        "company_name": company_name,
                        "vacancy_url": vacancy_url,
                        "vacancy_text": vacancy_text,
                    },
                    "flash_error": str(exc),
                },
                status_code=502,
            )

        title = _resume_title(role, company_name)
        generated = GeneratedResume(
            profile_id=profile.id,
            template_id=role.id,
            title=title,
            vacancy_text=vacancy_text,
            vacancy_url=vacancy_url or None,
            company_name=company_name or None,
            result_markdown=result_markdown,
            ai_feedback=f"agent={selected_agent}",
        )
        db.add(generated)
        db.commit()
        db.refresh(generated)

    return RedirectResponse(f"/resumes/{generated.id}?created=1", status_code=303)


@router.post("/generate/preview-prompt")
async def preview_generate_prompt(request: Request):
    form = await request.form()
    template_id = _int_or_none(form.get("template_id"))
    if template_id is None:
        return JSONResponse({"status": "error", "error": "Выбери роль"}, status_code=400)

    vacancy_text = str(form.get("vacancy_text") or "").strip()
    company_name = str(form.get("company_name") or "").strip()
    vacancy_url = str(form.get("vacancy_url") or "").strip()

    with SessionLocal() as db:
        profile = get_profile(db)
        selected_agent = get_ai_agent(db)
        try:
            prompt = build_resume_prompt_preview(
                db,
                profile_id=profile.id,
                template_id=template_id,
                vacancy_text=vacancy_text,
                company_name=company_name,
                vacancy_url=vacancy_url,
                provider=selected_agent,
            )
        except AIAgentError as exc:
            return JSONResponse({"status": "error", "error": str(exc)}, status_code=404)

    return JSONResponse(
        {
            "status": "ok",
            "agent": selected_agent,
            "prompt": prompt,
        }
    )


@router.get("/resumes")
async def resumes_page(request: Request):
    with SessionLocal() as db:
        profile = get_profile(db)
        resumes = db.scalars(
            select(GeneratedResume)
            .where(GeneratedResume.profile_id == profile.id)
            .options(selectinload(GeneratedResume.template))
            .order_by(desc(GeneratedResume.created_at), desc(GeneratedResume.id))
        ).all()

        return templates.TemplateResponse(
            "resumes.html",
            {
                "request": request,
                "active_page": "resumes",
                "resumes": resumes,
            },
        )


@router.get("/resumes/{resume_id}")
async def resume_view(request: Request, resume_id: int):
    with SessionLocal() as db:
        resume = db.scalar(
            select(GeneratedResume)
            .where(GeneratedResume.id == resume_id)
            .options(selectinload(GeneratedResume.template))
        )
        if resume is None:
            raise HTTPException(status_code=404, detail="Resume not found")

        return templates.TemplateResponse(
            "resume_view.html",
            {
                "request": request,
                "active_page": "resumes",
                "resume": resume,
                "resume_html": Markup(render_markdown(resume.result_markdown or "")),
                "flash_success": "Резюме создано" if request.query_params.get("created") == "1" else None,
            },
        )


@router.get("/resumes/{resume_id}/download")
async def download_resume(resume_id: int):
    with SessionLocal() as db:
        resume = db.get(GeneratedResume, resume_id)
        if resume is None:
            raise HTTPException(status_code=404, detail="Resume not found")

        filename = f"resume-{resume.id}.md"
        return PlainTextResponse(
            resume.result_markdown or "",
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


@router.delete("/resumes/{resume_id}")
async def delete_resume(resume_id: int):
    with SessionLocal() as db:
        resume = db.get(GeneratedResume, resume_id)
        if resume is not None:
            db.delete(resume)
            db.commit()
    return JSONResponse({"status": "ok"})


def render_markdown(markdown: str) -> str:
    blocks: list[str] = []
    list_items: list[str] = []

    def flush_list() -> None:
        if list_items:
            blocks.append("<ul>" + "".join(list_items) + "</ul>")
            list_items.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush_list()
            continue

        if line.startswith("#"):
            flush_list()
            level = min(len(line) - len(line.lstrip("#")), 4)
            text = line[level:].strip()
            blocks.append(f"<h{level}>{_inline_markdown(text)}</h{level}>")
            continue

        if line.startswith(("- ", "* ")):
            list_items.append(f"<li>{_inline_markdown(line[2:].strip())}</li>")
            continue

        flush_list()
        blocks.append(f"<p>{_inline_markdown(line)}</p>")

    flush_list()
    return "\n".join(blocks)


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _resume_title(role: ResumeTemplate, company_name: str) -> str:
    if company_name:
        return f"{role.name} · {company_name}"
    return role.name
