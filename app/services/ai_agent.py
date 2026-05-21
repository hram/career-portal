import json
import os
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.models import Education, ExtraNote, Job, Profile, Project, ResumeTemplate, Skill
from app.services.parser import ResumeParseError, _parse_json_response, _run_claude_json, _run_claude_text, _run_codex_text
from app.services.settings import normalize_ai_agent


AI_AGENT_TIMEOUT_SECONDS = int(os.getenv("AI_AGENT_TIMEOUT_SECONDS", "180"))


class AIAgentError(Exception):
    pass


def analyze_profile(db: Session, profile_id: int = 1, provider: str | None = None) -> dict:
    selected_provider = normalize_ai_agent(provider)
    context = build_profile_context(db, profile_id)
    raw = _run_analysis_prompt(
        selected_provider,
        prompt=_build_analysis_prompt(context, selected_provider),
        file_prompt_builder=_build_analysis_file_prompt,
        context=context,
    )
    return _normalize_analysis(raw)


def analyze_profile_only(db: Session, profile_id: int = 1, provider: str | None = None) -> dict:
    selected_provider = normalize_ai_agent(provider)
    context = build_profile_only_context(db, profile_id)
    raw = _run_analysis_prompt(
        selected_provider,
        prompt=_build_profile_only_analysis_prompt(context, selected_provider),
        file_prompt_builder=_build_profile_only_analysis_file_prompt,
        context=context,
    )
    return _normalize_analysis(raw)


def analyze_job(db: Session, job_id: int, provider: str | None = None) -> dict:
    selected_provider = normalize_ai_agent(provider)
    context = build_job_context(db, job_id)
    raw = _run_analysis_prompt(
        selected_provider,
        prompt=_build_job_analysis_prompt(context, selected_provider),
        file_prompt_builder=_build_job_analysis_file_prompt,
        context=context,
    )
    return _normalize_job_analysis(raw)


def analyze_project(db: Session, project_id: int, provider: str | None = None) -> dict:
    selected_provider = normalize_ai_agent(provider)
    context = build_project_context(db, project_id)
    raw = _run_analysis_prompt(
        selected_provider,
        prompt=_build_project_analysis_prompt(context, selected_provider),
        file_prompt_builder=_build_project_analysis_file_prompt,
        context=context,
    )
    return _normalize_project_analysis(raw)


def build_analysis_prompt_preview(
    db: Session,
    *,
    target_type: str,
    target_id: int | None = None,
    profile_id: int = 1,
    provider: str | None = None,
) -> str:
    selected_provider = normalize_ai_agent(provider)
    if target_type == "profile":
        return _build_analysis_prompt(build_profile_context(db, profile_id), selected_provider)
    if target_type == "profile_only":
        return _build_profile_only_analysis_prompt(build_profile_only_context(db, profile_id), selected_provider)
    if target_type == "job":
        if target_id is None:
            raise AIAgentError("Не указан ID места работы")
        return _build_job_analysis_prompt(build_job_context(db, target_id), selected_provider)
    if target_type == "project":
        if target_id is None:
            raise AIAgentError("Не указан ID проекта")
        return _build_project_analysis_prompt(build_project_context(db, target_id), selected_provider)
    raise AIAgentError("Неизвестный тип проверки")


def generate_resume(
    db: Session,
    profile_id: int,
    template_id: int,
    vacancy_text: str,
    company_name: str | None = None,
    vacancy_url: str | None = None,
    provider: str | None = None,
) -> str:
    selected_provider = normalize_ai_agent(provider)
    template = db.scalar(
        select(ResumeTemplate).where(
            ResumeTemplate.id == template_id,
            ResumeTemplate.profile_id == profile_id,
        )
    )
    if template is None:
        raise AIAgentError("Роль не найдена")

    context = build_profile_context(db, profile_id)
    prompt = _build_resume_generation_prompt(
        context=context,
        template=template,
        vacancy_text=vacancy_text,
        company_name=company_name,
        vacancy_url=vacancy_url,
        provider=selected_provider,
    )
    file_prompt_builder = lambda context_path: _build_resume_generation_file_prompt(
        context_path=context_path,
        template=template,
        vacancy_text=vacancy_text,
        company_name=company_name,
        vacancy_url=vacancy_url,
        provider=selected_provider,
    )
    try:
        if selected_provider == "claude-cli":
            with tempfile.TemporaryDirectory(prefix="career-resume-generate-") as tmpdir:
                context_path = Path(tmpdir) / "knowledge_base.md"
                context_path.write_text(context, encoding="utf-8")
                raw_response = _run_claude_text(
                    file_prompt_builder(context_path),
                    allowed_dir=context_path.parent,
                    timeout=AI_AGENT_TIMEOUT_SECONDS,
                )
        else:
            raw_response = _run_codex_text(prompt, timeout=AI_AGENT_TIMEOUT_SECONDS)
    except ResumeParseError as exc:
        raise AIAgentError(str(exc)) from exc

    markdown = _strip_markdown_fence(raw_response)
    if not markdown:
        raise AIAgentError("ИИ-агент вернул пустое резюме")
    return markdown


def build_resume_prompt_preview(
    db: Session,
    profile_id: int,
    template_id: int,
    vacancy_text: str,
    company_name: str | None = None,
    vacancy_url: str | None = None,
    provider: str | None = None,
) -> str:
    selected_provider = normalize_ai_agent(provider)
    template = db.scalar(
        select(ResumeTemplate).where(
            ResumeTemplate.id == template_id,
            ResumeTemplate.profile_id == profile_id,
        )
    )
    if template is None:
        raise AIAgentError("Роль не найдена")

    return _build_resume_generation_prompt(
        context=build_profile_context(db, profile_id),
        template=template,
        vacancy_text=vacancy_text,
        company_name=company_name,
        vacancy_url=vacancy_url,
        provider=selected_provider,
    )


def _run_analysis_prompt(selected_provider: str, *, prompt: str, file_prompt_builder, context: str) -> dict:
    try:
        if selected_provider == "claude-cli":
            with tempfile.TemporaryDirectory(prefix="career-agent-analysis-") as tmpdir:
                context_path = Path(tmpdir) / "knowledge_base.md"
                context_path.write_text(context, encoding="utf-8")
                return _run_claude_json(
                    file_prompt_builder(context_path),
                    allowed_dir=context_path.parent,
                    timeout=AI_AGENT_TIMEOUT_SECONDS,
                )
        raw_response = _run_codex_text(prompt, timeout=AI_AGENT_TIMEOUT_SECONDS)
        return _parse_json_response(raw_response)
    except (ResumeParseError, json.JSONDecodeError) as exc:
        raise AIAgentError(str(exc)) from exc


def build_profile_context(db: Session, profile_id: int = 1) -> str:
    profile = db.scalar(select(Profile).where(Profile.id == profile_id))
    if profile is None:
        return "# База знаний кандидата\n\nПрофиль пока пуст."

    jobs = db.scalars(
        select(Job)
        .where(Job.profile_id == profile.id)
        .options(selectinload(Job.projects))
        .order_by(Job.sort_order, Job.id)
    ).all()
    skills = db.scalars(select(Skill).where(Skill.profile_id == profile.id).order_by(Skill.id)).all()
    education = db.scalars(select(Education).where(Education.profile_id == profile.id).order_by(Education.id)).all()
    notes = db.scalars(select(ExtraNote).where(ExtraNote.profile_id == profile.id).order_by(ExtraNote.id)).all()

    parts: list[str] = ["# База знаний кандидата"]
    parts.append(
        "\n".join(
            [
                "## Профиль",
                f"Имя: {profile.full_name or ''}",
                f"Email: {profile.email or ''}",
                f"Телефон: {profile.phone or ''}",
                f"Локация: {profile.location or ''}",
                f"LinkedIn: {profile.linkedin_url or ''}",
                f"GitHub: {profile.github_url or ''}",
                f"Telegram: {profile.telegram or ''}",
                f"О себе: {profile.summary_raw or ''}",
            ]
        )
    )

    parts.append("## Опыт и проекты")
    if not jobs:
        parts.append("Опыт не заполнен.")
    for job in jobs:
        parts.append(
            "\n".join(
                [
                    f"### Job ID {job.id}: {job.company}",
                    f"Страница: /jobs/{job.id}",
                    f"Должность: {job.position or ''}",
                    f"Период: {job.start_date or ''} — {'по настоящее время' if job.is_current else job.end_date or ''}",
                    f"Локация: {job.location or ''}",
                    f"Заметки: {job.raw_notes or ''}",
                ]
            )
        )
        if job.projects:
            for project in sorted(job.projects, key=lambda item: (item.sort_order, item.id)):
                parts.append(
                    "\n".join(
                        [
                            f"#### Project ID {project.id}: {project.name}",
                            f"Страница: /jobs/{job.id}",
                            f"Описание: {project.raw_description or ''}",
                            f"Стек: {project.tech_stack or ''}",
                            f"Результаты: {project.results_raw or ''}",
                            f"Роль: {project.my_role or ''}",
                            f"Команда: {project.team_size or ''}",
                        ]
                    )
                )

    parts.append("## Навыки")
    if skills:
        for skill in skills:
            parts.append(f"- [{skill.category or 'без категории'}] {skill.raw_dump}")
    else:
        parts.append("Навыки не заполнены.")

    parts.append("## Образование")
    if education:
        for item in education:
            parts.append(
                f"- {item.institution or ''}; {item.degree or ''}; {item.field or ''}; "
                f"{item.start_year or ''}-{item.end_year or ''}; {item.raw_notes or ''}"
            )
    else:
        parts.append("Образование не заполнено.")

    parts.append("## Прочие заметки")
    if notes:
        for note in notes:
            parts.append(f"- [{note.category or 'другое'}] {note.title}: {note.raw_content or ''}")
    else:
        parts.append("Заметки не заполнены.")

    return "\n\n".join(parts)


def build_profile_only_context(db: Session, profile_id: int = 1) -> str:
    profile = db.scalar(select(Profile).where(Profile.id == profile_id))
    if profile is None:
        return "# Проверяем профиль кандидата\n\nПрофиль пока пуст."

    return "\n".join(
        [
            "# Проверяем профиль кандидата",
            "## Личные данные",
            f"Имя: {profile.full_name or ''}",
            f"Email: {profile.email or ''}",
            f"Телефон: {profile.phone or ''}",
            f"Локация: {profile.location or ''}",
            f"LinkedIn: {profile.linkedin_url or ''}",
            f"GitHub: {profile.github_url or ''}",
            f"Telegram: {profile.telegram or ''}",
            f"О себе: {profile.summary_raw or ''}",
        ]
    )


def build_job_context(db: Session, job_id: int) -> str:
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.projects), selectinload(Job.profile))
    )
    if job is None:
        raise AIAgentError("Место работы не найдено")

    profile = job.profile
    parts = [
        "# Проверяем одно место работы",
        "## Кандидат",
        f"Имя: {profile.full_name or ''}",
        f"О себе: {profile.summary_raw or ''}",
        "## Место работы",
        f"Job ID {job.id}: {job.company}",
        f"Страница: /jobs/{job.id}",
        f"Должность: {job.position or ''}",
        f"Период: {job.start_date or ''} — {'по настоящее время' if job.is_current else job.end_date or ''}",
        f"Локация: {job.location or ''}",
        f"Заметки: {job.raw_notes or ''}",
        "## Проекты этого места работы",
    ]
    if not job.projects:
        parts.append("Проекты не заполнены.")
    for project in sorted(job.projects, key=lambda item: (item.sort_order, item.id)):
        parts.append(_project_context_block(project, job))
    return "\n\n".join(parts)


def build_project_context(db: Session, project_id: int) -> str:
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.job).selectinload(Job.profile))
    )
    if project is None:
        raise AIAgentError("Проект не найден")

    job = project.job
    profile = job.profile
    return "\n\n".join(
        [
            "# Проверяем один проект",
            "## Кандидат",
            f"Имя: {profile.full_name or ''}",
            f"О себе: {profile.summary_raw or ''}",
            "## Место работы",
            f"Job ID {job.id}: {job.company}",
            f"Страница: /jobs/{job.id}",
            f"Должность: {job.position or ''}",
            f"Период: {job.start_date or ''} — {'по настоящее время' if job.is_current else job.end_date or ''}",
            f"Заметки места работы: {job.raw_notes or ''}",
            "## Проект",
            _project_context_block(project, job),
        ]
    )


def _project_context_block(project: Project, job: Job) -> str:
    return "\n".join(
        [
            f"Project ID {project.id}: {project.name}",
            f"Страница: /jobs/{job.id}",
            f"Описание: {project.raw_description or ''}",
            f"Стек: {project.tech_stack or ''}",
            f"Результаты: {project.results_raw or ''}",
            f"Роль: {project.my_role or ''}",
            f"Команда: {project.team_size or ''}",
        ]
    )


def _build_analysis_prompt(context: str, provider: str) -> str:
    return f"""{_analysis_instructions(provider)}

База знаний:
{context}
"""


def _build_analysis_file_prompt(context_path: Path) -> str:
    return f"""{_analysis_instructions("claude-cli")}

Прочитай базу знаний из файла:
{context_path}
"""


def _build_profile_only_analysis_prompt(context: str, provider: str) -> str:
    return f"""{_profile_only_analysis_instructions(provider)}

Контекст:
{context}
"""


def _build_profile_only_analysis_file_prompt(context_path: Path) -> str:
    return f"""{_profile_only_analysis_instructions("claude-cli")}

Прочитай контекст из файла:
{context_path}
"""


def _build_job_analysis_prompt(context: str, provider: str) -> str:
    return f"""{_job_analysis_instructions(provider)}

Контекст:
{context}
"""


def _build_job_analysis_file_prompt(context_path: Path) -> str:
    return f"""{_job_analysis_instructions("claude-cli")}

Прочитай контекст из файла:
{context_path}
"""


def _build_project_analysis_prompt(context: str, provider: str) -> str:
    return f"""{_project_analysis_instructions(provider)}

Контекст:
{context}
"""


def _build_project_analysis_file_prompt(context_path: Path) -> str:
    return f"""{_project_analysis_instructions("claude-cli")}

Прочитай контекст из файла:
{context_path}
"""


def _build_resume_generation_prompt(
    *,
    context: str,
    template: ResumeTemplate,
    vacancy_text: str,
    company_name: str | None,
    vacancy_url: str | None,
    provider: str,
) -> str:
    return f"""{_resume_generation_instructions(template, provider)}

База знаний кандидата:
{context}

Вакансия:
Компания: {company_name or "не указана"}
Ссылка: {vacancy_url or "не указана"}
Текст вакансии:
{vacancy_text or "Вакансия не указана. Сгенерируй универсальное резюме под выбранную роль."}
"""


def _build_resume_generation_file_prompt(
    *,
    context_path: Path,
    template: ResumeTemplate,
    vacancy_text: str,
    company_name: str | None,
    vacancy_url: str | None,
    provider: str,
) -> str:
    return f"""{_resume_generation_instructions(template, provider)}

Прочитай базу знаний кандидата из файла:
{context_path}

Вакансия:
Компания: {company_name or "не указана"}
Ссылка: {vacancy_url or "не указана"}
Текст вакансии:
{vacancy_text or "Вакансия не указана. Сгенерируй универсальное резюме под выбранную роль."}
"""


def _resume_generation_instructions(template: ResumeTemplate, provider: str) -> str:
    return f"""Ты — опытный HR-консультант и копирайтер резюме.
Твоя задача: написать сильное резюме на русском языке под конкретную вакансию.
Используемый инструмент: {provider}.

Роль: {template.name}
Описание роли: {template.description or ""}
Фокус роли: {template.focus_areas or ""}
Тон: {template.tone or "смешанный"}

Правила:
1. Используй ТОЛЬКО данные из базы знаний кандидата. Не выдумывай компании, даты, стек, метрики и достижения.
2. Адаптируй акценты под роль и конкретную вакансию.
3. Встрой ключевые слова из вакансии органично, без механического перечисления.
4. Метрики, масштаб ответственности и результаты выноси вперёд.
5. Длина: 1-1.5 страницы A4, без воды.
6. Формат ответа: только Markdown готового резюме, без комментариев вокруг.

Структура:
# Имя Фамилия
Контакты в одну строку

## О себе
2-3 предложения, адаптированные под вакансию.

## Опыт работы
### Компания, период
**Должность**
- Проект или зона ответственности: краткое описание, стек, результат.

## Навыки
Структурированный список релевантных навыков.

## Образование

Не добавляй секции, если данных для них нет.
Если важной информации для вакансии не хватает, добавь в конце короткую секцию:
## Что стоит уточнить
и перечисли только критичные вопросы.
"""


def _analysis_instructions(provider: str) -> str:
    return f"""Ты — персональный HR-агент и карьерный консультант.
Твоя задача: проанализировать базу знаний кандидата и помочь её улучшить.

Ты не пишешь резюме прямо сейчас. Ты проверяешь данные.
Используемый инструмент: {provider}.

Верни ТОЛЬКО валидный JSON без markdown и текста вокруг:
{{
  "overall_score": 75,
  "missing_critical": [],
  "questions": [
    {{
      "text": "",
      "target_url": "/jobs",
      "target_label": "Перейти",
      "project_id": 22
    }}
  ],
  "weak_points": [],
  "strengths": [],
  "recommendations": [],
  "ats_keywords_missing": [],
  "ats_keywords_present": [],
  "empty_projects": []
}}

Правила:
- {_overall_score_scale("база знаний")}
- missing_critical: короткие конкретные пункты, чего критически не хватает.
- {_questions_rule()}
- Если вопрос относится к Job ID или Project ID, target_url поставь соответствующий путь из контекста.
- project_id: необязательно, указывай если вопрос относится к конкретному проекту.
- weak_points: что выглядит слабо или расплывчато.
- strengths: что выглядит сильно.
- {_recommendations_rule("этой базы знаний")}
- {_ats_keywords_rule()}
- {_empty_projects_rule()}
- Будь конкретным. Не давай общих советов.
- Не выдумывай факты, которых нет в базе.
"""


def _profile_only_analysis_instructions(provider: str) -> str:
    return f"""Ты — карьерный консультант и редактор профиля кандидата.
Проверь только личный профиль кандидата: имя, контакты, локацию, ссылки и раздел "О себе".
Не анализируй опыт работы, проекты, навыки, образование и заметки.
Используемый инструмент: {provider}.

Верни ТОЛЬКО валидный JSON без markdown и текста вокруг:
{{
  "overall_score": 75,
  "missing_critical": [],
  "questions": [
    {{
      "text": "",
      "target_url": "/profile",
      "target_label": "Перейти к профилю"
    }}
  ],
  "weak_points": [],
  "strengths": [],
  "recommendations": [],
  "ats_keywords_missing": [],
  "ats_keywords_present": []
}}

Правила:
- {_overall_score_scale("профиль")}
- Проверь, есть ли имя, email, телефон, локация и релевантные публичные ссылки.
- Проверь, достаточно ли "О себе" объясняет позиционирование, целевую роль, seniority, формат работы и карьерные ограничения.
- {_questions_rule()}
- Вопросы должны относиться только к полям профиля.
- target_url всегда ставь "/profile".
- {_ats_keywords_rule()}
- {_recommendations_rule("этого профиля")}
- Не требуй данных, которые относятся к отдельным местам работы, проектам, навыкам или образованию.
- Не выдумывай факты, которых нет в профиле.
"""


def _job_analysis_instructions(provider: str) -> str:
    return f"""Ты — карьерный консультант и редактор базы знаний.
Проверь только одно место работы как совокупность проектов.
Используемый инструмент: {provider}.

Верни ТОЛЬКО валидный JSON без markdown и текста вокруг:
{{
  "overall_score": 75,
  "missing_critical": [],
  "questions": [
    {{
      "text": "",
      "target_url": "/jobs/1",
      "target_label": "Перейти",
      "project_id": 22
    }}
  ],
  "weak_points": [],
  "strengths": [],
  "recommendations": [],
  "ats_keywords_missing": [],
  "ats_keywords_present": [],
  "empty_projects": [],
  "suggested_job_summary": ""
}}

Правила:
- {_overall_score_scale("место работы")}
- Оцени, насколько это место работы готово для генерации резюме.
- Проверь цельность периода: понятна ли роль, рост, ответственность, вклад.
- Проверь нарратив: виден ли рост ответственности за период? Есть ли переход от исполнителя к лидеру? Если роль не менялась — это нормально, но должно быть видно масштабирование влияния.
- Проверь проекты: не дублируются ли, какие проекты пустые, где нет метрик/стека/роли.
- {_questions_rule()}
- Вопросы должны быть конкретными и относиться только к этому месту работы.
- project_id: необязательно, указывай если вопрос относится к конкретному проекту.
- target_url ставь на страницу места работы из контекста.
- {_ats_keywords_rule()}
- {_recommendations_rule("этого места работы")}
- {_empty_projects_rule()}
- suggested_job_summary: предложи 2-3 предложения для шапки блока компании в резюме. Активные глаголы, масштаб, роль.
- Не анализируй всю карьеру, только это место работы.
"""


def _project_analysis_instructions(provider: str) -> str:
    return f"""Ты — карьерный консультант и редактор базы знаний.
Проверь только один проект.
Используемый инструмент: {provider}.

Верни ТОЛЬКО валидный JSON без markdown и текста вокруг:
{{
  "overall_score": 75,
  "missing_critical": [],
  "questions": [
    {{
      "text": "",
      "target_url": "/jobs/1",
      "target_label": "Перейти к проекту",
      "project_id": 22
    }}
  ],
  "weak_points": [],
  "strengths": [],
  "recommendations": [],
  "ats_keywords_missing": [],
  "ats_keywords_present": [],
  "suggested_edits": {{
    "raw_description": "",
    "tech_stack": "",
    "results_raw": "",
    "my_role": "",
    "team_size": ""
  }}
}}

Правила:
- {_overall_score_scale("проект")}
- Оцени, насколько конкретный проект готов для использования в резюме.
- Проверь поля: описание, стек, результаты/метрики, роль, команда.
- {_questions_rule()}
- Вопросы должны помогать дозаполнить именно этот проект.
- project_id: необязательно, указывай если вопрос относится к конкретному проекту.
- suggested_edits заполняй только если можно улучшить формулировку без выдумывания фактов. Если фактов не хватает — оставь пустую строку и задай вопрос.
- suggested_edits: переформулируй для резюме — активные глаголы, конкретика, без воды. Стиль: "Спроектировал X, что привело к Y".
- target_url ставь на страницу места работы из контекста.
- {_ats_keywords_rule()}
- {_recommendations_rule("этого проекта")}
- Не анализируй всю карьеру, только этот проект.
"""


def _overall_score_scale(subject: str) -> str:
    return f"""overall_score: число 0-100, насколько {subject} готов(а) для использования в резюме. Используй шкалу:
  0-40: нельзя использовать в резюме, критически мало данных.
  41-65: можно, но слабо — нет метрик или роли.
  66-85: хорошо, есть всё основное.
  86-100: отлично, конкретные метрики + роль + стек + результат.
Не ориентируйся на значение 75 из JSON-примера, это только пример формата."""


def _questions_rule() -> str:
    return (
        "questions: максимум 3 вопроса, только самые важные для резюме. "
        "Сортируй по важности: метрики > роль > контекст. "
        "Каждый вопрос должен быть конкретным и проверяемым."
    )


def _ats_keywords_rule() -> str:
    return (
        "ats_keywords_missing: важные ATS-ключевые слова для этой роли/контекста, которых нет или которые слабо выражены. "
        "ats_keywords_present: сильные ATS-ключевые слова, которые уже есть в данных. "
        "Указывай только слова и короткие фразы, полезные для HR-фильтров и поиска."
    )


def _recommendations_rule(subject_phrase: str) -> str:
    return (
        f"recommendations: максимум 3 конкретных действия, которые повысят overall_score именно {subject_phrase}. "
        "Только то, что можно сделать прямо сейчас."
    )


def _empty_projects_rule() -> str:
    return (
        "empty_projects: список project_id, где данных критически мало: нет описания, нет стека "
        "или нет результатов/метрик. Указывай только ID проектов из контекста."
    )


def _normalize_analysis(payload: dict) -> dict:
    questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
    return {
        "overall_score": _clamp_score(payload.get("overall_score")),
        "missing_critical": _string_list(payload.get("missing_critical")),
        "questions": [_normalize_question(item) for item in questions[:3]],
        "weak_points": _string_list(payload.get("weak_points")),
        "strengths": _string_list(payload.get("strengths")),
        "recommendations": _string_list(payload.get("recommendations"))[:3],
        "ats_keywords_missing": _string_list(payload.get("ats_keywords_missing")),
        "ats_keywords_present": _string_list(payload.get("ats_keywords_present")),
        "empty_projects": _int_list(payload.get("empty_projects")),
    }


def _normalize_project_analysis(payload: dict) -> dict:
    result = _normalize_analysis(payload)
    suggested = payload.get("suggested_edits") if isinstance(payload.get("suggested_edits"), dict) else {}
    result["suggested_edits"] = {
        "raw_description": str(suggested.get("raw_description") or ""),
        "tech_stack": str(suggested.get("tech_stack") or ""),
        "results_raw": str(suggested.get("results_raw") or ""),
        "my_role": str(suggested.get("my_role") or ""),
        "team_size": str(suggested.get("team_size") or ""),
    }
    return result


def _normalize_job_analysis(payload: dict) -> dict:
    result = _normalize_analysis(payload)
    result["suggested_job_summary"] = str(payload.get("suggested_job_summary") or "")
    return result


def _normalize_question(item: object) -> dict:
    if isinstance(item, str):
        return {"text": item, "target_url": "/jobs", "target_label": "Перейти к проектам"}
    if not isinstance(item, dict):
        return {"text": str(item), "target_url": "/jobs", "target_label": "Перейти к проектам"}

    text = str(item.get("text") or item.get("question") or "").strip()
    target_url = str(item.get("target_url") or item.get("url") or "/jobs").strip()
    if not target_url.startswith("/"):
        target_url = "/jobs"
    target_label = str(item.get("target_label") or "Перейти").strip()
    question = {
        "text": text,
        "target_url": target_url,
        "target_label": target_label,
    }
    project_id = _int_or_none(item.get("project_id"))
    if project_id is not None:
        question["project_id"] = project_id
    return question


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        number = _int_or_none(item)
        if number is not None:
            result.append(number)
    return result


def _clamp_score(value: object) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(score, 100))


def _strip_markdown_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
