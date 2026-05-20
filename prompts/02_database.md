# Шаг 2 — База данных: модели и миграции

## Контекст
Продолжаем строить карьерный портал. Шаг 1 выполнен — проект запускается.  
Теперь создаём все SQLAlchemy модели и настраиваем Alembic.

---

## Задача
Создай полную схему БД и настрой миграции.

---

## `app/models/models.py`

Создай следующие модели:

### Profile
```python
id, full_name, email, phone, location
linkedin_url, github_url, telegram
summary_raw  # свободный текст — кто я, чего хочу (заметки)
created_at, updated_at
```
Связи: has_many Jobs, Skills, Education, ExtraNotes, GeneratedResumes, ResumeTemplates

### Job (место работы)
```python
id, profile_id (FK)
company, position, location
start_date (str), end_date (str)  # "март 2021", "present" — строки, не даты
is_current (bool)
raw_notes  # свободные заметки про это место работы
sort_order (int, default=0)  # для ручной сортировки
created_at, updated_at
```
Связи: belongs_to Profile, has_many Projects

### Project (проект внутри работы)
```python
id, job_id (FK)
name
raw_description  # главное поле — сюда льём всё без ограничений
tech_stack       # свободный текст: "Python, FastAPI, Redis, AWS"
results_raw      # результаты как есть: "ускорили в 2 раза, кажется"
my_role          # "тех лид", "бэкенд разработчик"
team_size        # "3 человека", "10+ чел"
sort_order (int, default=0)
created_at, updated_at
```
Связи: belongs_to Job

### Skill
```python
id, profile_id (FK)
raw_dump   # сюда всё свалить: "Python Django REST GRPC Kafka Docker k8s"
category   # необязательно: "languages", "infra", "soft"
created_at
```

### Education
```python
id, profile_id (FK)
institution, degree, field
start_year (str), end_year (str)
raw_notes  # "не доучился", "онлайн курс", "красный диплом"
```

### ExtraNote
```python
id, profile_id (FK)
category  # "сертификат", "хобби", "достижение", "публикация"
title
raw_content  # свободный текст
```

### ResumeTemplate (роль)
```python
id, profile_id (FK)
name           # "Техлид Android", "Фулстек разработчик"
description    # пара слов о роли
focus_areas    # что выводить вперёд (свободный текст)
tone           # "технический", "управленческий", "смешанный"
is_default (bool)
created_at, updated_at
```

### GeneratedResume
```python
id, profile_id (FK), template_id (FK, nullable)
title          # "Яндекс — Техлид Android, май 2025"
vacancy_text   # вставленный текст вакансии
vacancy_url    # ссылка на вакансию (необязательно)
company_name   # куда подаём
result_markdown  # сгенерированное резюме в markdown
ai_feedback    # комментарии агента к этому резюме
created_at
```

---

## Настройка Alembic

1. Инициализируй alembic: `alembic init alembic`
2. В `alembic/env.py` подключи `Base.metadata` из `app.models.models`
3. Создай первую миграцию: `alembic revision --autogenerate -m "initial"`
4. Применяй через: `alembic upgrade head`

---

## Seed данные (`app/database.py` или отдельный `seed.py`)

При первом запуске (если БД пустая) создай:
- Один пустой Profile с `full_name = ""`
- Четыре ResumeTemplate:
  - "Техлид Android" — focus: Android, Kotlin, команда, архитектура
  - "Руководитель отдела разработки" — focus: управление, процессы, найм
  - "Лид бэкенд разработки" — focus: бэкенд, API, масштабирование
  - "Фулстек разработчик" — focus: фронтенд + бэкенд, продуктовый подход

---

## Обнови `app/main.py`
- При старте вызывай `Base.metadata.create_all(bind=engine)`
- Вызывай seed функцию если профиль не существует
- Обнови главную страницу (`GET /`) — передавай реальную статистику:
  - количество Jobs
  - количество Projects (через join)
  - количество GeneratedResumes

---

## Критерии готовности
- [ ] `alembic upgrade head` выполняется без ошибок
- [ ] Все таблицы созданы в `career_portal.db`
- [ ] Приложение стартует и показывает статистику (0/0/0)
- [ ] Seed создаёт 4 шаблона ролей при первом запуске
