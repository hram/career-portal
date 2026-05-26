import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select

from app.database import SessionLocal
from app.models.models import Profile, SavedVacancy
from app.services.hh import (
    HHApiError,
    build_authorization_url,
    exchange_authorization_code,
    fetch_application_token,
    get_current_user,
    get_vacancy,
    normalize_search_item,
    normalize_vacancy,
    refresh_user_token,
    search_vacancies,
)
from app.services.settings import delete_setting, get_setting, set_setting


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")

HH_ACCESS_TOKEN_KEY = "hh_access_token"
HH_REFRESH_TOKEN_KEY = "hh_refresh_token"
HH_EXPIRES_AT_KEY = "hh_expires_at"
HH_ACCOUNT_KEY = "hh_account"
HH_OAUTH_STATE_KEY = "hh_oauth_state"
HH_APP_ACCESS_TOKEN_KEY = "hh_app_access_token"
HH_APP_EXPIRES_AT_KEY = "hh_app_expires_at"


def get_profile(db) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.id == 1))
    if profile is not None:
        return profile

    profile = Profile(id=1, full_name="")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/hh")
async def hh_page(request: Request):
    query = str(request.query_params.get("text") or "").strip()
    area = str(request.query_params.get("area") or "").strip()
    page = _int_or_zero(request.query_params.get("page"))
    results = None
    error = None
    auth_error = request.query_params.get("auth_error")
    auth_success = request.query_params.get("auth") == "connected"

    with SessionLocal() as db:
        profile = get_profile(db)
        try:
            app_access_token = get_hh_app_access_token(db)
        except HHApiError as exc:
            error = str(exc)

        if query and error is None:
            try:
                payload = search_vacancies(text=query, area=area or None, page=page, per_page=20, access_token=app_access_token)
                results = {
                    "items": [normalize_search_item(item) for item in payload.get("items", [])],
                    "found": int(payload.get("found") or 0),
                    "page": int(payload.get("page") or 0),
                    "pages": int(payload.get("pages") or 0),
                }
            except HHApiError as exc:
                error = str(exc)

        saved_vacancies = db.scalars(
            select(SavedVacancy)
            .where(SavedVacancy.profile_id == profile.id)
            .order_by(desc(SavedVacancy.created_at), desc(SavedVacancy.id))
            .limit(10)
        ).all()
        auth_status = get_hh_auth_status(db)

    if auth_error:
        error = auth_error

    return templates.TemplateResponse(
        "hh.html",
        {
            "request": request,
            "active_page": "hh",
            "query": query,
            "area": area,
            "results": results,
            "saved_vacancies": saved_vacancies,
            "hh_auth": auth_status,
            "flash_error": error,
            "flash_success": _success_message(request, auth_success),
        },
    )


@router.get("/hh/auth/start")
async def start_hh_auth(request: Request):
    client_id, _ = get_hh_client_config()
    redirect_uri = get_hh_redirect_uri(request)
    state = secrets.token_urlsafe(24)

    with SessionLocal() as db:
        set_setting(db, HH_OAUTH_STATE_KEY, state)
        db.commit()

    return RedirectResponse(build_authorization_url(client_id=client_id, redirect_uri=redirect_uri, state=state))


@router.get("/hh/oauth/callback")
async def hh_oauth_callback(request: Request):
    error = request.query_params.get("error")
    if error:
        return redirect_hh_error(f"hh.ru отклонил авторизацию: {error}")

    code = str(request.query_params.get("code") or "")
    state = str(request.query_params.get("state") or "")
    if not code or not state:
        return redirect_hh_error("hh.ru не вернул code/state")

    client_id, client_secret = get_hh_client_config()
    redirect_uri = get_hh_redirect_uri(request)

    with SessionLocal() as db:
        expected_state = get_setting(db, HH_OAUTH_STATE_KEY)
        if not expected_state or not secrets.compare_digest(expected_state, state):
            return redirect_hh_error("Некорректный state авторизации hh.ru")

        try:
            token_payload = exchange_authorization_code(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
            save_hh_token_payload(db, token_payload)
            access_token = str(token_payload.get("access_token") or "")
            if access_token:
                save_hh_account(db, access_token)
            delete_setting(db, HH_OAUTH_STATE_KEY)
            db.commit()
        except HHApiError as exc:
            return redirect_hh_error(str(exc))

    return RedirectResponse("/hh?auth=connected", status_code=303)


@router.post("/hh/auth/disconnect")
async def disconnect_hh_auth():
    with SessionLocal() as db:
        for key in [
            HH_ACCESS_TOKEN_KEY,
            HH_REFRESH_TOKEN_KEY,
            HH_EXPIRES_AT_KEY,
            HH_ACCOUNT_KEY,
            HH_OAUTH_STATE_KEY,
        ]:
            delete_setting(db, key)
        db.commit()
    return RedirectResponse("/hh", status_code=303)


@router.post("/hh/vacancies/{hh_id}/save")
async def save_hh_vacancy(hh_id: str):
    with SessionLocal() as db:
        profile = get_profile(db)
        try:
            access_token = get_hh_app_access_token(db)
            normalized = normalize_vacancy(get_vacancy(hh_id, access_token=access_token))
        except HHApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        saved = db.scalar(
            select(SavedVacancy).where(
                SavedVacancy.profile_id == profile.id,
                SavedVacancy.hh_id == normalized["hh_id"],
            )
        )
        if saved is None:
            saved = SavedVacancy(profile_id=profile.id, hh_id=normalized["hh_id"], title=normalized["title"])
            db.add(saved)

        saved.title = normalized["title"] or saved.title
        saved.company_name = normalized["company_name"] or None
        saved.area_name = normalized["area_name"] or None
        saved.salary_text = normalized["salary_text"] or None
        saved.vacancy_url = normalized["vacancy_url"] or None
        saved.api_url = normalized["api_url"] or None
        saved.published_at = normalized["published_at"] or None
        saved.description_text = normalized["description_text"] or None
        saved.raw_json = normalized["raw_json"] or None
        db.commit()
        db.refresh(saved)

    return RedirectResponse(f"/generate?vacancy_id={saved.id}", status_code=303)


@router.delete("/hh/vacancies/{vacancy_id}")
async def delete_saved_vacancy(vacancy_id: int):
    with SessionLocal() as db:
        vacancy = db.get(SavedVacancy, vacancy_id)
        if vacancy is not None:
            db.delete(vacancy)
            db.commit()
    return {"status": "ok"}


def _int_or_zero(value: object) -> int:
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0


def get_hh_client_config() -> tuple[str, str]:
    client_id = os.getenv("HH_CLIENT_ID", "").strip()
    client_secret = os.getenv("HH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Заполни HH_CLIENT_ID и HH_CLIENT_SECRET в .env")
    return client_id, client_secret


def get_hh_redirect_uri(request: Request) -> str:
    configured = os.getenv("HH_REDIRECT_URI", "").strip()
    if configured:
        return configured
    return str(request.url_for("hh_oauth_callback"))


def get_hh_access_token(db) -> str | None:
    access_token = get_setting(db, HH_ACCESS_TOKEN_KEY)
    refresh_token = get_setting(db, HH_REFRESH_TOKEN_KEY)
    expires_at = _float_or_zero(get_setting(db, HH_EXPIRES_AT_KEY))

    if access_token and expires_at > time.time() + 60:
        return access_token
    if not refresh_token:
        return access_token or None

    client_id, client_secret = get_hh_client_config()
    token_payload = refresh_user_token(refresh_token=refresh_token, client_id=client_id, client_secret=client_secret)
    save_hh_token_payload(db, token_payload)
    db.commit()
    return str(token_payload.get("access_token") or "") or None


def get_hh_app_access_token(db) -> str:
    access_token = get_setting(db, HH_APP_ACCESS_TOKEN_KEY)
    expires_at = _float_or_zero(get_setting(db, HH_APP_EXPIRES_AT_KEY))
    if access_token and expires_at > time.time() + 60:
        return access_token

    client_id, client_secret = get_hh_client_config()
    token_payload = fetch_application_token(client_id=client_id, client_secret=client_secret)
    token = str(token_payload.get("access_token") or "")
    if not token:
        raise HHApiError("hh.ru не вернул access_token приложения")

    expires_in = int(token_payload.get("expires_in") or 3600)
    set_setting(db, HH_APP_ACCESS_TOKEN_KEY, token)
    set_setting(db, HH_APP_EXPIRES_AT_KEY, str(time.time() + expires_in))
    db.commit()
    return token


def save_hh_token_payload(db, payload: dict) -> None:
    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or "")
    expires_in = int(payload.get("expires_in") or 0)
    if access_token:
        set_setting(db, HH_ACCESS_TOKEN_KEY, access_token)
    if refresh_token:
        set_setting(db, HH_REFRESH_TOKEN_KEY, refresh_token)
    if expires_in > 0:
        set_setting(db, HH_EXPIRES_AT_KEY, str(time.time() + expires_in))


def save_hh_account(db, access_token: str) -> None:
    try:
        user = get_current_user(access_token)
    except HHApiError:
        return
    label = str(user.get("email") or user.get("first_name") or user.get("last_name") or user.get("id") or "").strip()
    if label:
        set_setting(db, HH_ACCOUNT_KEY, label)


def get_hh_auth_status(db) -> dict:
    access_token = get_setting(db, HH_ACCESS_TOKEN_KEY)
    expires_at = _float_or_zero(get_setting(db, HH_EXPIRES_AT_KEY))
    return {
        "connected": bool(access_token),
        "account": get_setting(db, HH_ACCOUNT_KEY),
        "expires_at": expires_at,
        "expires_at_text": time.strftime("%Y-%m-%d %H:%M", time.localtime(expires_at)) if expires_at else "",
        "configured": bool(os.getenv("HH_CLIENT_ID", "").strip() and os.getenv("HH_CLIENT_SECRET", "").strip()),
    }


def _success_message(request: Request, auth_success: bool) -> str | None:
    if auth_success:
        return "hh.ru подключен"
    if request.query_params.get("saved") == "1":
        return "Вакансия сохранена"
    return None


def redirect_hh_error(message: str) -> RedirectResponse:
    return RedirectResponse(f"/hh?{urlencode({'auth_error': message})}", status_code=303)


def _float_or_zero(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0
