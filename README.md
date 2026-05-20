# Career Portal

Личный карьерный портал на FastAPI, Jinja2 и SQLite.

## Запуск

```bash
cd career-portal
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# При необходимости заполни переменные в .env
alembic upgrade head
uvicorn app.main:app --reload
```

После запуска дашборд доступен на `http://localhost:8000`.

## Миграции

```bash
alembic revision --autogenerate -m "описание"
alembic upgrade head
```

## Загрузка резюме

Парсинг PDF/DOCX использует локальный Claude CLI. Путь задаётся в `.env`:

```env
CLAUDE_CLI_PATH=claude
CLAUDE_PARSE_TIMEOUT_SECONDS=300
```
