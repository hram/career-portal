import json
import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.models import AgentAnalysis, Education, ExtraNote, GeneratedResume, Job, Profile, Project, Skill
from app.services.parser import ResumeParseError, extract_text, parse_resume_pipeline
from app.services.settings import SUPPORTED_AI_AGENTS, get_ai_agent, normalize_ai_agent


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = PROJECT_ROOT / "uploads"
PREVIEW_DIR = UPLOAD_DIR / "previews"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".docx"}

def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def _preview_path(preview_id: str) -> Path:
    return PREVIEW_DIR / f"{preview_id}.json"


def _load_preview(preview_id: str) -> dict:
    path = _preview_path(preview_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_preview(payload: dict) -> str:
    _ensure_dirs()
    preview_id = uuid.uuid4().hex
    _preview_path(preview_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return preview_id


@router.get("/upload")
async def upload_page(request: Request):
    error = request.query_params.get("error")
    with SessionLocal() as db:
        selected_agent = get_ai_agent(db)
    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "active_page": "upload",
            "mode": "upload",
            "flash_error": error,
            "agents": SUPPORTED_AI_AGENTS,
            "selected_agent": selected_agent,
        },
    )


@router.post("/upload")
async def upload_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    _ensure_dirs()
    with SessionLocal() as db:
        selected_agent = get_ai_agent(db)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return RedirectResponse(
            "/upload?error=Поддерживаются только PDF и DOCX",
            status_code=303,
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        return RedirectResponse(
            "/upload?error=Максимальный размер файла — 10 МБ",
            status_code=303,
        )

    file_id = uuid.uuid4().hex
    safe_name = f"{file_id}{suffix}"
    file_path = UPLOAD_DIR / safe_name
    file_path.write_bytes(content)

    raw_text = ""
    parse_error = None
    try:
        raw_text = await asyncio.to_thread(extract_text, str(file_path))
    except ResumeParseError as exc:
        parse_error = str(exc)

    preview_id = _save_preview(
        {
            "filename": file.filename,
            "file_path": str(file_path),
            "raw_text": raw_text,
            "agent": selected_agent,
            "parsed": None,
            "parse_error": parse_error,
            "parse_status": "error" if parse_error else "processing",
            "pipeline": {
                "stage": "queued",
                "total_jobs": 0,
                "completed_jobs": 0,
                "current_job": "",
            },
            "progress_version": 0,
        }
    )
    if not parse_error:
        background_tasks.add_task(_parse_preview_in_background, preview_id)
    return RedirectResponse(f"/upload/preview/{preview_id}", status_code=303)


@router.get("/upload/preview/{preview_id}")
async def upload_preview(request: Request, preview_id: str):
    preview = _load_preview(preview_id)
    with SessionLocal() as db:
        profile = db.scalar(select(Profile).where(Profile.id == 1))
        requires_replace_confirmation = _profile_has_knowledge(db, profile) if profile is not None else False
    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "active_page": "upload",
            "mode": "preview",
            "preview_id": preview_id,
            "preview": preview,
            "parsed": preview.get("parsed"),
            "raw_text": preview.get("raw_text") or "",
            "agents": SUPPORTED_AI_AGENTS,
            "selected_agent": normalize_ai_agent(preview.get("agent")),
            "parse_error": preview.get("parse_error"),
            "confirm_error": preview.get("confirm_error"),
            "parse_status": preview.get("parse_status") or ("done" if preview.get("parsed") else "error"),
            "pipeline": preview.get("pipeline") or {},
            "requires_replace_confirmation": requires_replace_confirmation,
        },
    )


@router.get("/upload/preview/{preview_id}/status")
async def upload_preview_status(preview_id: str):
    preview = _load_preview(preview_id)
    parsed = preview.get("parsed")
    return JSONResponse(
        {
            "status": preview.get("parse_status") or ("done" if parsed else "error"),
            "error": preview.get("parse_error"),
            "has_parsed": isinstance(parsed, dict),
            "agent": normalize_ai_agent(preview.get("agent")),
            "pipeline": preview.get("pipeline") or {},
            "progress_version": int(preview.get("progress_version") or 0),
        }
    )


@router.post("/upload/confirm")
async def upload_confirm(request: Request):
    form = await request.form()
    preview_id = str(form.get("preview_id") or "")
    preview = _load_preview(preview_id)
    parsed = preview.get("parsed")
    if not isinstance(parsed, dict):
        return RedirectResponse(f"/upload/preview/{preview_id}", status_code=303)

    with SessionLocal() as db:
        profile = db.scalar(select(Profile).where(Profile.id == 1))
        if profile is None:
            profile = Profile(id=1, full_name="")
            db.add(profile)
            db.flush()
        has_existing_knowledge = _profile_has_knowledge(db, profile)
        if has_existing_knowledge and form.get("replace_confirmed") != "on":
            preview["confirm_error"] = "Подтверди удаление текущей базы знаний перед импортом."
            _write_preview(_preview_path(preview_id), preview)
            return RedirectResponse(f"/upload/preview/{preview_id}", status_code=303)

        if has_existing_knowledge:
            _clear_profile_knowledge(db, profile.id)
            db.flush()

        _replace_profile(profile, parsed.get("profile") or {})

        for job_index, job_data in enumerate(parsed.get("jobs") or [], start=1):
            if not job_data.get("company") and not job_data.get("position"):
                continue
            job = Job(
                profile_id=profile.id,
                company=job_data.get("company") or "Без названия",
                position=job_data.get("position") or None,
                location=job_data.get("location") or None,
                start_date=job_data.get("start_date") or None,
                end_date=job_data.get("end_date") or None,
                is_current=bool(job_data.get("is_current")),
                raw_notes=job_data.get("raw_notes") or None,
                sort_order=job_index,
            )
            db.add(job)
            db.flush()

            for project_index, project_data in enumerate(job_data.get("projects") or [], start=1):
                if not project_data.get("name") and not project_data.get("raw_description"):
                    continue
                db.add(
                    Project(
                        job_id=job.id,
                        name=project_data.get("name") or "Проект без названия",
                        raw_description=project_data.get("raw_description") or None,
                        tech_stack=project_data.get("tech_stack") or None,
                        results_raw=project_data.get("results_raw") or None,
                        my_role=project_data.get("my_role") or None,
                        team_size=project_data.get("team_size") or None,
                        sort_order=project_index,
                    )
                )

        skills_raw = parsed.get("skills_raw")
        if skills_raw:
            db.add(Skill(profile_id=profile.id, raw_dump=skills_raw, category="import"))

        for education_data in parsed.get("education") or []:
            if not education_data.get("institution") and not education_data.get("raw_notes"):
                continue
            db.add(
                Education(
                    profile_id=profile.id,
                    institution=education_data.get("institution") or None,
                    degree=education_data.get("degree") or None,
                    field=education_data.get("field") or None,
                    start_year=education_data.get("start_year") or None,
                    end_year=education_data.get("end_year") or None,
                    raw_notes=education_data.get("raw_notes") or None,
                )
            )

        db.commit()

    _preview_path(preview_id).unlink(missing_ok=True)
    return RedirectResponse("/jobs", status_code=303)


@router.post("/upload/retry")
async def upload_retry(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    preview_id = str(form.get("preview_id") or "")
    preview = _load_preview(preview_id)
    if not (preview.get("raw_text") or "").strip():
        return RedirectResponse(f"/upload/preview/{preview_id}", status_code=303)

    if form.get("agent"):
        preview["agent"] = normalize_ai_agent(form.get("agent"))
    else:
        with SessionLocal() as db:
            preview["agent"] = get_ai_agent(db)
    preview["parsed"] = None
    preview["parse_error"] = None
    preview["parse_status"] = "processing"
    preview["pipeline"] = {
        "stage": "queued",
        "total_jobs": 0,
        "completed_jobs": 0,
        "current_job": "",
    }
    preview["progress_version"] = int(preview.get("progress_version") or 0) + 1
    _preview_path(preview_id).write_text(
        json.dumps(preview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    background_tasks.add_task(_parse_preview_in_background, preview_id)
    return RedirectResponse(f"/upload/preview/{preview_id}", status_code=303)


def _replace_profile(profile: Profile, incoming: dict) -> None:
    profile.full_name = (incoming.get("full_name") or "").strip()
    for field in (
        "email",
        "phone",
        "location",
        "linkedin_url",
        "github_url",
        "telegram",
        "summary_raw",
    ):
        value = (incoming.get(field) or "").strip()
        setattr(profile, field, value or None)


def _profile_has_knowledge(db, profile: Profile | None) -> bool:
    if profile is None:
        return False
    checks = [
        select(func.count(Job.id)).where(Job.profile_id == profile.id),
        select(func.count(Skill.id)).where(Skill.profile_id == profile.id),
        select(func.count(Education.id)).where(Education.profile_id == profile.id),
        select(func.count(ExtraNote.id)).where(ExtraNote.profile_id == profile.id),
        select(func.count(GeneratedResume.id)).where(GeneratedResume.profile_id == profile.id),
        select(func.count(AgentAnalysis.id)).where(AgentAnalysis.profile_id == profile.id),
    ]
    return any((db.scalar(statement) or 0) > 0 for statement in checks)


def _clear_profile_knowledge(db, profile_id: int) -> None:
    for model in (Job, Skill, Education, ExtraNote, GeneratedResume, AgentAnalysis):
        for item in db.scalars(select(model).where(model.profile_id == profile_id)).all():
            db.delete(item)


def _merge_profile(profile: Profile, incoming: dict) -> None:
    for field in (
        "full_name",
        "email",
        "phone",
        "location",
        "linkedin_url",
        "github_url",
        "telegram",
        "summary_raw",
    ):
        value = (incoming.get(field) or "").strip()
        if value:
            setattr(profile, field, value)


def _parse_preview_in_background(preview_id: str) -> None:
    path = _preview_path(preview_id)
    if not path.exists():
        return

    preview = json.loads(path.read_text(encoding="utf-8"))
    try:
        preview["parse_status"] = "processing"
        preview["pipeline"] = {
            "stage": "outline_processing",
            "total_jobs": 0,
            "completed_jobs": 0,
            "current_job": "",
        }
        preview["progress_version"] = int(preview.get("progress_version") or 0) + 1
        _write_preview(path, preview)

        def on_progress(update: dict) -> None:
            preview["parsed"] = update.get("parsed")
            preview["parse_error"] = None
            preview["parse_status"] = "processing"
            preview["pipeline"] = {
                "stage": update.get("stage") or "processing",
                "total_jobs": int(update.get("total_jobs") or 0),
                "completed_jobs": int(update.get("completed_jobs") or 0),
                "current_job": str(update.get("current_job") or ""),
            }
            preview["progress_version"] = int(preview.get("progress_version") or 0) + 1
            _write_preview(path, preview)

        parsed = parse_resume_pipeline(
            preview.get("raw_text") or "",
            provider=normalize_ai_agent(preview.get("agent")),
            on_progress=on_progress,
        )
        preview["parsed"] = parsed
        preview["parse_error"] = None
        preview["parse_status"] = "done"
        preview["pipeline"] = {
            "stage": "done",
            "total_jobs": len(parsed.get("jobs") or []),
            "completed_jobs": len(parsed.get("jobs") or []),
            "current_job": "",
        }
        preview["progress_version"] = int(preview.get("progress_version") or 0) + 1
    except ResumeParseError as exc:
        preview["parsed"] = None
        preview["parse_error"] = str(exc)
        preview["parse_status"] = "error"
        preview["progress_version"] = int(preview.get("progress_version") or 0) + 1

    _write_preview(path, preview)


def _write_preview(path: Path, preview: dict) -> None:
    path.write_text(
        json.dumps(preview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
