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
COPY database.py .
COPY excel_export.py .
COPY excel_import.py .
COPY web_app.py .

COPY bot_core ./bot_core
COPY handlers ./handlers
COPY templates ./templates
COPY static ./static

# Папки для данных и логов (volume mount из docker-compose)
RUN mkdir -p /app/data /app/logs /app/labels

# Healthcheck для веб-панели (если запускается как web-сервис)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${WEB_PANEL_PORT:-5000}/api/stats || exit 1

# По умолчанию — Telegram-бот. Сервис в docker-compose.yml может переопределить.
CMD ["python", "bot.py"]
