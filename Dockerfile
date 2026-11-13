# ============================================================
# Dockerfile для бота инвентаризации
# ============================================================
# Один образ — два сервиса:
#   • bot.py — Telegram-бот (дефолтная команда)
#   • web_app.py — FastAPI веб-панель (переопределяется в docker-compose.yml)
# ============================================================

FROM python:3.11-slim

ENV TZ=Europe/Moscow \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Системные зависимости (минимум, без шрифтов — печать штрих-кодов вырезана)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
        curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY bot.py .
COPY config.py .
COPY validators.py .
COPY excel_export.py .
COPY excel_import.py .
COPY web_app.py .

COPY bot_core ./bot_core
COPY database ./database
COPY handlers ./handlers
COPY templates ./templates
COPY static ./static
COPY web ./web

# Папки для данных и логов (volume mount из docker-compose)
# /app/labels удалён в фазе 2 — печать штрих-кодов вырезана, каталог не использовался
RUN mkdir -p /app/data /app/logs

# Healthcheck для веб-панели (если запускается как web-сервис).
# /health — публичный эндпоинт (не требует пароля, в отличие от /api/stats).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${WEB_PANEL_PORT:-5000}/health || exit 1

# По умолчанию — Telegram-бот. Сервис в docker-compose.yml может переопределить.
CMD ["python", "bot.py"]
