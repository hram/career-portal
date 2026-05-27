FROM node:22-bookworm-slim AS ai-cli

RUN npm install -g @anthropic-ai/claude-code@latest @openai/codex@latest && \
    npm cache clean --force


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    DATABASE_URL=sqlite:////data/career-portal/career_portal.db \
    CAREER_PORTAL_UPLOAD_DIR=/data/career-portal/uploads \
    HOME=/data/career-portal \
    CLAUDE_CLI_PATH=/usr/local/bin/claude \
    CODEX_HOME=/data/career-portal/.codex \
    CODEX_CLI_PATH=codex

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends bubblewrap curl && \
    rm -rf /var/lib/apt/lists/* && \
    addgroup --system app && \
    adduser --system --ingroup app --home /app app && \
    mkdir -p /data/career-portal/uploads && \
    chown -R app:app /app /data/career-portal

COPY --from=ai-cli /usr/local/bin/node /usr/local/bin/node
COPY --from=ai-cli /usr/local/bin/claude /usr/local/bin/claude
COPY --from=ai-cli /usr/local/lib/node_modules/@anthropic-ai /usr/local/lib/node_modules/@anthropic-ai
COPY --from=ai-cli /usr/local/lib/node_modules/@openai /usr/local/lib/node_modules/@openai
RUN ln -sf /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex

COPY requirements.txt alembic.ini README.md ./
COPY alembic ./alembic
COPY app ./app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/', timeout=3).read(1)"

CMD ["sh", "-c", "mkdir -p \"$(dirname \"${DATABASE_URL#sqlite:///}\")\" \"$CAREER_PORTAL_UPLOAD_DIR\" \"$CODEX_HOME\" && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
