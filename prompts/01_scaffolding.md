# Шаг 1 — Scaffolding проекта

## Контекст
Создаём личный карьерный портал. Один пользователь, без авторизации на старте.  
Стек: FastAPI + Jinja2 + vanilla JS + SQLite.

## Задача
Создай полную структуру проекта с нуля, готовую к запуску.

---

## Что нужно создать

### 1. Файловая структура
```
career-portal/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models/
│   │   └── __init__.py
│   ├── routers/
│   │   └── __init__.py
│   ├── services/
│   │   └── __init__.py
│   ├── templates/
│   │   ├── base.html
│   │   └── index.html
│   └── static/
│       ├── css/
│       │   └── main.css
│       └── js/
│           └── main.js
├── uploads/
├── .env.example
├── .gitignore
└── requirements.txt
```

### 2. `requirements.txt`
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
python-multipart==0.0.12
sqlalchemy==2.0.35
alembic==1.13.3
anthropic==0.34.2
python-dotenv==1.0.1
aiofiles==24.1.0
pdfplumber==0.11.4
python-docx==1.1.2
```

### 3. `.env.example`
```
ANTHROPIC_API_KEY=your_key_here
DATABASE_URL=sqlite:///./career_portal.db
```

### 4. `app/main.py`
- Создай FastAPI приложение
- Подключи статику (`/static`) и шаблоны (`/templates`)
- Один роут `GET /` → рендерит `index.html`
- При старте выводи в консоль: `🚀 Career Portal запущен: http://localhost:8000`

### 5. `app/database.py`
- SQLAlchemy engine с поддержкой SQLite
- `SessionLocal`, `Base`, функция `get_db()`
- Читает `DATABASE_URL` из `.env`

### 6. `app/templates/base.html`
Базовый HTML шаблон со следующими требованиями:

**Дизайн:** тёмная тема, профессиональный минимализм. Не корпоративный, не стартаперский — как рабочий инструмент разработчика.

**Шрифты** (подключить через Google Fonts или Bunny Fonts):
- Заголовки: `JetBrains Mono` (моноширинный, технический)
- Текст: `Inter` или `IBM Plex Sans`

**CSS переменные:**
```css
--bg: #0f1117
--bg-card: #1a1d27
--bg-hover: #21263a
--border: #2a2e3e
--text: #e2e8f0
--text-muted: #64748b
--accent: #6366f1   /* indigo */
--accent-hover: #818cf8
--success: #22c55e
--warning: #f59e0b
--danger: #ef4444
```

**Навигация (левый сайдбар, фиксированный):**
```
[ Career Portal ]    ← логотип/название

  База знаний
  ─────────────
  👤 Профиль
  💼 Опыт и проекты
  🛠 Навыки
  🎓 Образование
  📝 Заметки

  Резюме
  ─────────────
  🎭 Роли
  ✨ Создать резюме
  📄 Мои резюме

  Инструменты
  ─────────────
  🤖 ИИ-агент
  📤 Загрузить резюме
```

**Основная область:** `margin-left: 240px`, padding, скроллится независимо.

**Блок для flash-сообщений** (успех/ошибка) — вверху контента.

**Jinja2 блоки:** `{% block title %}`, `{% block content %}`, `{% block scripts %}`

### 7. `app/templates/index.html`
Дашборд — главная страница. Наследует `base.html`.

Содержимое:
- Приветствие: `Привет! Это твой личный карьерный портал.`
- Три карточки-статуса (пока заглушки с нулями):
  - Мест работы в базе: 0
  - Проектов: 0  
  - Сгенерировано резюме: 0
- Кнопка `Загрузить резюме` → `/upload`
- Кнопка `Заполнить профиль` → `/profile`

### 8. `app/static/css/main.css`
Стили для:
- Сайдбар (ширина 240px, фиксированный, тёмный)
- Навигационные ссылки (с активным состоянием `.active`)
- Карточки `.card` (bg-card, border-radius 8px, border)
- Кнопки `.btn`, `.btn-primary`, `.btn-danger`, `.btn-ghost`
- Flash сообщения `.flash-success`, `.flash-error`
- Таблицы, формы, инпуты — в общем стиле тёмной темы

### 9. `app/static/js/main.js`
- Функция `flash(message, type)` — показывает уведомление 3 секунды
- Функция `confirmDelete(url, name)` — диалог подтверждения удаления → fetch DELETE → reload
- Автоматически скрывать flash сообщения через 4 секунды

---

## Как запустить (добавь в README.md)
```bash
cd career-portal
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Вставь ANTHROPIC_API_KEY в .env
uvicorn app.main:app --reload
```

---

## Критерии готовности
- [ ] `uvicorn app.main:app --reload` запускается без ошибок
- [ ] `http://localhost:8000` открывается и показывает дашборд
- [ ] Сайдбар виден, навигация присутствует
- [ ] Тёмная тема применена
- [ ] Нет ошибок в консоли браузера
