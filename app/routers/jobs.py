import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models.models import AgentAnalysis, Job, Profile, Project


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


def get_job_or_404(db, job_id: int) -> Job:
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.projects))
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def get_project_or_404(db, job_id: int, project_id: int) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.job_id == job_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_latest_analysis(db, target_type: str, target_id: int) -> dict | None:
    analysis = db.scalar(
        select(AgentAnalysis)
        .where(AgentAnalysis.target_type == target_type, AgentAnalysis.target_id == target_id)
        .order_by(AgentAnalysis.created_at.desc(), AgentAnalysis.id.desc())
        .limit(1)
    )
    if analysis is None:
        return None
    try:
        result = json.loads(analysis.result_json)
    except json.JSONDecodeError:
        return None
    return {
        "id": analysis.id,
        "agent": analysis.provider,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else "",
        "result": result,
    }


@router.get("/jobs")
async def jobs_page(request: Request):
    with SessionLocal() as db:
        jobs = db.scalars(
            select(Job)
            .options(selectinload(Job.projects))
            .order_by(Job.sort_order, Job.id.desc())
        ).all()
        return templates.TemplateResponse(
            "jobs.html",
            {
                "request": request,
                "active_page": "jobs",
                "jobs": jobs,
                "flash_success": "Место работы добавлено"
                if request.query_params.get("created") == "1"
                else None,
            },
        )


@router.post("/jobs")
async def create_job(request: Request):
    form = await request.form()
    company = (form.get("company") or "").strip()
    position = (form.get("position") or "").strip()

    if not company or not position:
        return RedirectResponse("/jobs", status_code=303)

    with SessionLocal() as db:
        profile = get_profile(db)
        max_sort = db.scalar(select(func.max(Job.sort_order))) or 0
        job = Job(
            profile_id=profile.id,
            company=company,
            position=position,
            location=(form.get("location") or "").strip() or None,
            start_date=(form.get("start_date") or "").strip() or None,
            end_date=None
            if form.get("is_current") == "on"
            else (form.get("end_date") or "").strip() or None,
            is_current=form.get("is_current") == "on",
            raw_notes=form.get("raw_notes") or None,
            sort_order=max_sort + 1,
        )
        db.add(job)
        db.commit()

    return RedirectResponse("/jobs?created=1", status_code=303)


@router.post("/jobs/reorder")
async def reorder_jobs(request: Request):
    payload = await request.json()
    with SessionLocal() as db:
        for item in payload:
            job = db.get(Job, int(item["id"]))
            if job is not None:
                job.sort_order = int(item["sort_order"])
        db.commit()
    return JSONResponse({"status": "ok"})


@router.get("/jobs/{job_id}")
async def job_detail_page(request: Request, job_id: int):
    with SessionLocal() as db:
        job = get_job_or_404(db, job_id)
        job.projects.sort(key=lambda project: (project.sort_order, project.id))
        project_analyses = {
            project.id: get_latest_analysis(db, "project", project.id)
            for project in job.projects
        }
        return templates.TemplateResponse(
            "job_detail.html",
            {
                "request": request,
                "active_page": "jobs",
                "job": job,
                "job_analysis": get_latest_analysis(db, "job", job.id),
                "project_analyses": project_analyses,
            },
        )


@router.post("/jobs/{job_id}")
async def update_job(request: Request, job_id: int):
    form = await request.form()
    is_autosave = request.headers.get("x-autosave") == "raw_notes"

    with SessionLocal() as db:
        job = get_job_or_404(db, job_id)

        if is_autosave:
            job.raw_notes = form.get("raw_notes") or None
            db.commit()
            return JSONResponse({"status": "ok"})

        job.company = (form.get("company") or "").strip()
        job.position = (form.get("position") or "").strip()
        job.location = (form.get("location") or "").strip() or None
        job.start_date = (form.get("start_date") or "").strip() or None
        job.end_date = None if form.get("is_current") == "on" else (form.get("end_date") or "").strip() or None
        job.is_current = form.get("is_current") == "on"
        job.raw_notes = form.get("raw_notes") or None
        db.commit()

    return JSONResponse({"status": "ok"})


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int):
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).options(selectinload(Job.projects)))
        if job is not None:
            project_ids = [project.id for project in job.projects]
            for analysis in db.scalars(
                select(AgentAnalysis).where(
                    (AgentAnalysis.target_type == "job") & (AgentAnalysis.target_id == job_id)
                )
            ).all():
                db.delete(analysis)
            if project_ids:
                for analysis in db.scalars(
                    select(AgentAnalysis).where(
                        (AgentAnalysis.target_type == "project") & (AgentAnalysis.target_id.in_(project_ids))
                    )
                ).all():
                    db.delete(analysis)
            db.delete(job)
            db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/jobs/{job_id}/projects")
async def create_project(request: Request, job_id: int):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    with SessionLocal() as db:
        get_job_or_404(db, job_id)
        max_sort = db.scalar(select(func.max(Project.sort_order)).where(Project.job_id == job_id)) or 0
        project = Project(
            job_id=job_id,
            name=name,
            raw_description=form.get("raw_description") or None,
            tech_stack=(form.get("tech_stack") or "").strip() or None,
            results_raw=form.get("results_raw") or None,
            my_role=(form.get("my_role") or "").strip() or None,
            team_size=(form.get("team_size") or "").strip() or None,
            sort_order=max_sort + 1,
        )
        db.add(project)
        db.commit()

    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/jobs/{job_id}/projects/reorder")
async def reorder_projects(request: Request, job_id: int):
    payload = await request.json()
    with SessionLocal() as db:
        get_job_or_404(db, job_id)
        for item in payload:
            project = db.get(Project, int(item["id"]))
            if project is not None and project.job_id == job_id:
                project.sort_order = int(item["sort_order"])
        db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/jobs/{job_id}/projects/{project_id}")
async def update_project(request: Request, job_id: int, project_id: int):
    form = await request.form()
    is_autosave = request.headers.get("x-autosave") == "raw_description"

    with SessionLocal() as db:
        project = get_project_or_404(db, job_id, project_id)

        if is_autosave:
            project.raw_description = form.get("raw_description") or None
            db.commit()
            return JSONResponse({"status": "ok"})

        project.name = (form.get("name") or "").strip()
        project.raw_description = form.get("raw_description") or None
        project.tech_stack = (form.get("tech_stack") or "").strip() or None
        project.results_raw = form.get("results_raw") or None
        project.my_role = (form.get("my_role") or "").strip() or None
        project.team_size = (form.get("team_size") or "").strip() or None
        db.commit()

    return JSONResponse({"status": "ok"})


@router.delete("/jobs/{job_id}/projects/{project_id}")
async def delete_project(job_id: int, project_id: int):
    with SessionLocal() as db:
        project = get_project_or_404(db, job_id, project_id)
        for analysis in db.scalars(
            select(AgentAnalysis).where(
                (AgentAnalysis.target_type == "project") & (AgentAnalysis.target_id == project_id)
            )
        ).all():
            db.delete(analysis)
        db.delete(project)
        db.commit()
    return JSONResponse({"status": "ok"})
