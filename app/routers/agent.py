import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.database import SessionLocal
from app.models.models import AgentAnalysis
from app.services.ai_agent import AIAgentError, analyze_job, analyze_profile, analyze_project
from app.services.settings import SUPPORTED_AI_AGENTS, get_ai_agent


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/agent")
async def agent_page(request: Request):
    with SessionLocal() as db:
        selected_agent = get_ai_agent(db)
        last_analysis = _load_last_analysis(db, profile_id=1, target_type="profile", target_id=None)

    return templates.TemplateResponse(
        "agent.html",
        {
            "request": request,
            "active_page": "agent",
            "agents": SUPPORTED_AI_AGENTS,
            "selected_agent": selected_agent,
            "last_analysis": last_analysis,
        },
    )


@router.post("/agent/analyze")
async def agent_analyze():
    with SessionLocal() as db:
        selected_agent = get_ai_agent(db)
        try:
            result = analyze_profile(db, profile_id=1, provider=selected_agent)
        except AIAgentError as exc:
            return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)
        _save_analysis(db, provider=selected_agent, target_type="profile", target_id=None, result=result)
        db.commit()

    return JSONResponse(
        {
            "status": "ok",
            "agent": selected_agent,
            "result": result,
        }
    )


@router.post("/agent/analyze/job/{job_id}")
async def agent_analyze_job(job_id: int):
    with SessionLocal() as db:
        selected_agent = get_ai_agent(db)
        try:
            result = analyze_job(db, job_id=job_id, provider=selected_agent)
        except AIAgentError as exc:
            return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)
        analysis = _save_analysis(db, provider=selected_agent, target_type="job", target_id=job_id, result=result)
        db.refresh(analysis)
        payload = _analysis_payload(analysis, result)
        db.commit()

    return JSONResponse({"status": "ok", "agent": selected_agent, "analysis": payload})


@router.post("/agent/analyze/project/{project_id}")
async def agent_analyze_project(project_id: int):
    with SessionLocal() as db:
        selected_agent = get_ai_agent(db)
        try:
            result = analyze_project(db, project_id=project_id, provider=selected_agent)
        except AIAgentError as exc:
            return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)
        analysis = _save_analysis(db, provider=selected_agent, target_type="project", target_id=project_id, result=result)
        db.refresh(analysis)
        payload = _analysis_payload(analysis, result)
        db.commit()

    return JSONResponse({"status": "ok", "agent": selected_agent, "analysis": payload})


def _save_analysis(db, *, provider: str, target_type: str, target_id: int | None, result: dict) -> AgentAnalysis:
    analysis = AgentAnalysis(
        profile_id=1,
        provider=provider,
        target_type=target_type,
        target_id=target_id,
        overall_score=int(result.get("overall_score") or 0),
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(analysis)
    db.flush()
    return analysis


def _load_last_analysis(db, profile_id: int, target_type: str, target_id: int | None) -> dict | None:
    statement = (
        select(AgentAnalysis)
        .where(AgentAnalysis.profile_id == profile_id, AgentAnalysis.target_type == target_type)
        .order_by(AgentAnalysis.created_at.desc(), AgentAnalysis.id.desc())
        .limit(1)
    )
    if target_id is None:
        statement = statement.where(AgentAnalysis.target_id.is_(None))
    else:
        statement = statement.where(AgentAnalysis.target_id == target_id)
    analysis = db.scalar(statement)
    if analysis is None:
        return None
    try:
        result = json.loads(analysis.result_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(result, dict):
        return None
    return _analysis_payload(analysis, result)


def _analysis_payload(analysis: AgentAnalysis, result: dict) -> dict:
    return {
        "id": analysis.id,
        "agent": analysis.provider,
        "target_type": analysis.target_type,
        "target_id": analysis.target_id,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else "",
        "result": result,
    }
