import os

from sqlalchemy.orm import Session

from app.models.models import AppSetting


SUPPORTED_AI_AGENTS = {
    "claude-cli": "Claude CLI",
    "codex-cli": "Codex CLI",
}

AI_AGENT_SETTING_KEY = "ai_agent"


def normalize_ai_agent(value: object) -> str:
    agent = str(value or "").strip().lower()
    if agent in SUPPORTED_AI_AGENTS:
        return agent
    default_agent = os.getenv("RESUME_PARSE_PROVIDER", "claude-cli").strip().lower()
    return default_agent if default_agent in SUPPORTED_AI_AGENTS else "claude-cli"


def get_setting(db: Session, key: str, default: str = "") -> str:
    setting = db.get(AppSetting, key)
    if setting is None:
        return default
    return setting.value


def set_setting(db: Session, key: str, value: str) -> None:
    setting = db.get(AppSetting, key)
    if setting is None:
        db.add(AppSetting(key=key, value=value))
    else:
        setting.value = value


def delete_setting(db: Session, key: str) -> None:
    setting = db.get(AppSetting, key)
    if setting is not None:
        db.delete(setting)


def get_ai_agent(db: Session) -> str:
    return normalize_ai_agent(get_setting(db, AI_AGENT_SETTING_KEY, os.getenv("RESUME_PARSE_PROVIDER", "claude-cli")))


def set_ai_agent(db: Session, value: object) -> str:
    agent = normalize_ai_agent(value)
    set_setting(db, AI_AGENT_SETTING_KEY, agent)
    return agent
