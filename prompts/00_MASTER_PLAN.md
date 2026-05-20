# Career Portal — Master Plan
**Архитектор:** Claude (chat)  
**Исполнитель:** Claude Code  
**Владелец:** ты  

---

## Стек
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, SQLite (→ PostgreSQL позже)
- **Frontend:** Jinja2 templates, vanilla JS/CSS (без SPA)
- **ИИ:** Anthropic Claude API (`claude-sonnet-4-20250514`)
- **Парсинг резюме:** pdfplumber, python-docx
- **Деплой:** Railway или локально через uvicorn

---

## Структура данных (ядро)

```
Profile
  ├── personal info (name, email, phone, location, links)
  ├── summary_raw (свободный текст о себе)
  ├── Jobs[]
  │     ├── company, position, dates, is_current
  │     ├── raw_notes (заметки про работу целиком)
  │     └── Projects[]
  │           ├── name, raw_description
  │           ├── tech_stack, results_raw
  │           ├── my_role, team_size
  │           └── sort_order
  ├── Skills[]  (raw_dump — сваливать всё, AI организует)
  ├── Education[]
  └── ExtraNotes[]  (сертификаты, хобби, "заметки на полях")

ResumeTemplate  (роль: "Техлид Android", "Фулстек" и т.д.)
  ├── name, description
  ├── focus_areas  (что выводить вперёд)
  └── tone_instructions  (технический / управленческий)

GeneratedResume
  ├── profile_id, template_id
  ├── vacancy_text  (текст вакансии с hh.ru)
  ├── result_markdown / result_html
  └── created_at
```

---

## Этапы MVP (10 шагов)

| # | Этап | Что получаем |
|---|------|-------------|
| 1 | Scaffolding проекта | Структура папок, зависимости, .env, запуск |
| 2 | База данных | SQLAlchemy модели, Alembic миграции, seed |
| 3 | Профиль и личные данные | CRUD страница профиля |
| 4 | Опыт работы | CRUD компаний со вложенными проектами |
| 5 | Загрузка резюме | Upload PDF/DOCX → парсинг → заполнение БД |
| 6 | Навыки, образование, заметки | Остальные разделы базы знаний |
| 7 | Шаблоны ролей | CRUD ролей (Техлид, Фулстек и т.д.) |
| 8 | ИИ-агент: проверка базы | Анализ → список вопросов и рекомендаций |
| 9 | ИИ-агент: генерация резюме | Роль + вакансия → красивое резюме (MD/PDF) |
| 10 | Полировка MVP | Навигация, UX, экспорт PDF, финальный тест |

**После MVP:** hh.ru API, LinkedIn экспорт, дашборд откликов.

---

## Файловая структура проекта

```
career-portal/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models/
│   │   └── models.py
│   ├── routers/
│   │   ├── profile.py
│   │   ├── jobs.py
│   │   ├── skills.py
│   │   ├── upload.py
│   │   ├── templates_router.py
│   │   ├── agent.py
│   │   └── resumes.py
│   ├── services/
│   │   ├── parser.py        # PDF/DOCX parsing
│   │   └── ai_agent.py      # Claude API calls
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── profile.html
│   │   ├── jobs.html
│   │   ├── job_detail.html
│   │   ├── skills.html
│   │   ├── resume_templates.html
│   │   ├── generate.html
│   │   └── partials/
│   │       ├── project_card.html
│   │       └── nav.html
│   └── static/
│       ├── css/
│       │   └── main.css
│       └── js/
│           └── main.js
├── uploads/           # временные файлы резюме
├── .env.example
├── requirements.txt
├── alembic.ini
└── alembic/
    └── versions/
```

---

## Принципы для Claude Code

1. **Никаких SPA** — каждая страница рендерится сервером через Jinja2
2. **Vanilla JS только для UX** — inline редактирование, HTMX-style fetch, без фреймворков
3. **Сырые данные священны** — никогда не перезаписывать `raw_*` поля автоматически
4. **Один профиль** — это личный инструмент, не мультиюзер
5. **Claude API модель:** всегда `claude-sonnet-4-20250514`
6. **Комментарии в коде** — на русском, для владельца
