import os

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_portal.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_database(db: Session) -> None:
    from app.models.models import Profile, ResumeTemplate

    profile = db.scalar(select(Profile).limit(1))
    if profile is not None:
        return

    profile = Profile(full_name="")
    db.add(profile)
    db.flush()

    templates = [
        ResumeTemplate(
            profile_id=profile.id,
            name="Техлид Android",
            description="Роль для технического лидерства в Android-разработке.",
            focus_areas="Android, Kotlin, команда, архитектура",
            tone="технический",
            is_default=True,
        ),
        ResumeTemplate(
            profile_id=profile.id,
            name="Руководитель отдела разработки",
            description="Роль для управленческого трека и руководства командами.",
            focus_areas="управление, процессы, найм",
            tone="управленческий",
        ),
        ResumeTemplate(
            profile_id=profile.id,
            name="Лид бэкенд разработки",
            description="Роль для лидерства в бэкенд-разработке.",
            focus_areas="бэкенд, API, масштабирование",
            tone="технический",
        ),
        ResumeTemplate(
            profile_id=profile.id,
            name="Фулстек разработчик",
            description="Роль для задач на стыке продукта, фронтенда и бэкенда.",
            focus_areas="фронтенд + бэкенд, продуктовый подход",
            tone="смешанный",
        ),
    ]
    db.add_all(templates)
    db.commit()
