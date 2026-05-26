import html
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HH_API_BASE = "https://api.hh.ru"
HH_OAUTH_BASE = "https://hh.ru/oauth"
HH_OAUTH_TOKEN_URL = f"{HH_OAUTH_BASE}/token"
DEFAULT_USER_AGENT = "career-portal/0.1 (https://github.com/hram/career-portal)"
_APP_TOKEN_CACHE: dict[str, object] = {"token": "", "expires_at": 0.0}


class HHApiError(Exception):
    pass


def search_vacancies(
    *,
    text: str,
    area: str | None = None,
    page: int = 0,
    per_page: int = 20,
    access_token: str | None = None,
) -> dict:
    params = {
        "text": text,
        "page": max(0, page),
        "per_page": max(1, min(per_page, 100)),
    }
    if area:
        params["area"] = area
    return _request_json("/vacancies", params, access_token=access_token)


def get_vacancy(vacancy_id: str, access_token: str | None = None) -> dict:
    return _request_json(f"/vacancies/{vacancy_id}", {}, access_token=access_token)


def get_current_user(access_token: str) -> dict:
    return _request_json("/me", {}, access_token=access_token)


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{HH_OAUTH_BASE}/authorize?{urlencode(params)}"


def exchange_authorization_code(*, code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    return _fetch_oauth_token(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
    )


def refresh_user_token(*, refresh_token: str, client_id: str, client_secret: str) -> dict:
    return _fetch_oauth_token(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
    )


def fetch_application_token(*, client_id: str, client_secret: str) -> dict:
    return _fetch_app_token(client_id, client_secret)


def normalize_search_item(item: dict) -> dict:
    employer = item.get("employer") if isinstance(item.get("employer"), dict) else {}
    area = item.get("area") if isinstance(item.get("area"), dict) else {}
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    salary = item.get("salary") if isinstance(item.get("salary"), dict) else None
    return {
        "hh_id": str(item.get("id") or ""),
        "title": str(item.get("name") or ""),
        "company_name": str(employer.get("name") or ""),
        "area_name": str(area.get("name") or ""),
        "salary_text": format_salary(salary),
        "vacancy_url": str(item.get("alternate_url") or ""),
        "published_at": str(item.get("published_at") or ""),
        "requirement": strip_html(snippet.get("requirement") or ""),
        "responsibility": strip_html(snippet.get("responsibility") or ""),
    }


def normalize_vacancy(payload: dict) -> dict:
    employer = payload.get("employer") if isinstance(payload.get("employer"), dict) else {}
    area = payload.get("area") if isinstance(payload.get("area"), dict) else {}
    salary = payload.get("salary") if isinstance(payload.get("salary"), dict) else None
    key_skills = payload.get("key_skills") if isinstance(payload.get("key_skills"), list) else []
    skills = [str(item.get("name") or "").strip() for item in key_skills if isinstance(item, dict)]
    description = strip_html(payload.get("description") or "")
    text_parts = [
        f"Вакансия: {payload.get('name') or ''}",
        f"Компания: {employer.get('name') or ''}",
        f"Регион: {area.get('name') or ''}",
        f"Зарплата: {format_salary(salary) or 'не указана'}",
        f"Опыт: {_nested_name(payload.get('experience'))}",
        f"Занятость: {_nested_name(payload.get('employment'))}",
        f"График: {_nested_name(payload.get('schedule'))}",
    ]
    if skills:
        text_parts.append("Ключевые навыки: " + ", ".join(skills))
    if description:
        text_parts.extend(["", description])

    return {
        "hh_id": str(payload.get("id") or ""),
        "title": str(payload.get("name") or ""),
        "company_name": str(employer.get("name") or ""),
        "area_name": str(area.get("name") or ""),
        "salary_text": format_salary(salary),
        "vacancy_url": str(payload.get("alternate_url") or ""),
        "api_url": str(payload.get("url") or ""),
        "published_at": str(payload.get("published_at") or ""),
        "description_text": "\n".join(part for part in text_parts if part is not None).strip(),
        "raw_json": json.dumps(payload, ensure_ascii=False),
    }


def format_salary(salary: dict | None) -> str:
    if not salary:
        return ""
    salary_from = salary.get("from")
    salary_to = salary.get("to")
    currency = salary.get("currency") or ""
    gross = salary.get("gross")
    if salary_from and salary_to:
        value = f"{salary_from}–{salary_to} {currency}"
    elif salary_from:
        value = f"от {salary_from} {currency}"
    elif salary_to:
        value = f"до {salary_to} {currency}"
    else:
        return ""
    if gross is not None:
        value += ", до вычета налогов" if gross else ", на руки"
    return value


def strip_html(value: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", value)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _request_json(path: str, params: dict, access_token: str | None = None) -> dict:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{HH_API_BASE}{path}{query}"
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    token = access_token if access_token is not None else _access_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            raise HHApiError(
                f"hh.ru вернул {exc.code}. Проверь авторизацию hh.ru, HH_ACCESS_TOKEN или пару HH_CLIENT_ID/HH_CLIENT_SECRET в .env."
            ) from exc
        if exc.code == 400 and "bad_user_agent" in message:
            raise HHApiError("hh.ru отклонил User-Agent. Укажи контактный HH_USER_AGENT в .env.") from exc
        raise HHApiError(f"hh.ru вернул {exc.code}: {message}") from exc
    except (URLError, TimeoutError) as exc:
        raise HHApiError(f"Не удалось подключиться к hh.ru: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HHApiError("hh.ru вернул некорректный JSON") from exc


def _user_agent() -> str:
    return os.getenv("HH_USER_AGENT") or DEFAULT_USER_AGENT


def _access_token() -> str:
    explicit_token = os.getenv("HH_ACCESS_TOKEN")
    if explicit_token:
        return explicit_token

    client_id = os.getenv("HH_CLIENT_ID")
    client_secret = os.getenv("HH_CLIENT_SECRET")
    if not client_id or not client_secret:
        return ""

    cached_token = str(_APP_TOKEN_CACHE.get("token") or "")
    expires_at = float(_APP_TOKEN_CACHE.get("expires_at") or 0)
    if cached_token and expires_at > time.time() + 60:
        return cached_token

    token_payload = _fetch_app_token(client_id, client_secret)
    token = str(token_payload.get("access_token") or "")
    if not token:
        raise HHApiError("hh.ru не вернул access_token для приложения")

    expires_in = int(token_payload.get("expires_in") or 3600)
    _APP_TOKEN_CACHE["token"] = token
    _APP_TOKEN_CACHE["expires_at"] = time.time() + expires_in
    return token


def _fetch_app_token(client_id: str, client_secret: str) -> dict:
    return _fetch_oauth_token(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        app_token=True,
    )


def _fetch_oauth_token(payload: dict[str, str], app_token: bool = False) -> dict:
    body = urlencode(payload).encode("utf-8")
    request = Request(
        HH_OAUTH_TOKEN_URL,
        data=body,
        headers={
            "User-Agent": _user_agent(),
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        if exc.code == 400 and "bad_user_agent" in message:
            raise HHApiError("hh.ru отклонил User-Agent. Укажи контактный HH_USER_AGENT в .env.") from exc
        token_label = "приложения" if app_token else "пользователя"
        if app_token and "app token refresh too early" in message:
            raise HHApiError(
                "hh.ru не даёт запросить новый токен приложения чаще одного раза в пять минут. "
                "Повтори поиск чуть позже; после успешного получения токен сохранится локально."
            ) from exc
        raise HHApiError(f"Не удалось получить токен {token_label} hh.ru: {exc.code} {message}") from exc
    except (URLError, TimeoutError) as exc:
        raise HHApiError(f"Не удалось подключиться к hh.ru для получения токена: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HHApiError("hh.ru вернул некорректный JSON при получении токена") from exc


def _nested_name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return ""
