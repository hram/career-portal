import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.database import Base, SessionLocal, engine, seed_database
from app.models.models import GeneratedResume, Job, Project
from app.routers.agent import router as agent_router
from app.routers.hh import router as hh_router
from app.routers.jobs import router as jobs_router
from app.routers.profile import router as profile_router
from app.routers.resumes import router as resumes_router
from app.routers.roles import router as roles_router
from app.routers.settings import router as settings_router
from app.routers.skills import router as skills_router
from app.routers.upload import router as upload_router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Career Portal")
app.state.asset_version = os.getenv("SOURCE_COMMIT", "dev")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.include_router(agent_router)
app.include_router(hh_router)
app.include_router(jobs_router)
app.include_router(profile_router)
app.include_router(resumes_router)
app.include_router(roles_router)
app.include_router(settings_router)
app.include_router(skills_router)
app.include_router(upload_router)


@app.on_event("startup")
async def startup_message() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    print("🚀 Career Portal запущен: http://localhost:8000")


@app.get("/")
async def index(request: Request):
    with SessionLocal() as db:
        stats = {
            "jobs": db.scalar(select(func.count(Job.id))) or 0,
            "projects": db.scalar(select(func.count(Project.id)).join(Job)) or 0,
            "resumes": db.scalar(select(func.count(GeneratedResume.id))) or 0,
        }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "active_page": "dashboard",
            "stats": stats,
        },
    )
