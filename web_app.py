"""
Веб-панель инвентаризации — FastAPI приложение (точка входа).

Современный стек:
  • FastAPI — асинхронные эндпоинты и API
  • Jinja2 — HTML-шаблоны
  • Tailwind CSS (CDN) — стили
  • HTMX — интерактивность без отдельного JS-фронтенда
  • Chart.js — графики
  • Cookie-сессии (itsdangerous) — авторизация по паролю

Безопасность:
  • Пароль хранится как bcrypt-хэш (или plain text с warning)
  • Cookie: HttpOnly + SameSite=Strict + Secure (если FORCE_HTTPS)
  • Сессия истекает через 8 часов
  • Rate limiting на /login (5 попыток/60 сек, блок на 5 мин)
  • CSRF-токены на всех POST/DELETE
  • Security headers (CSP, X-Frame-Options, X-Content-Type-Options,
    Referrer-Policy, HSTS при HTTPS)
  • /api/docs защищён авторизацией

Структура (фаза 2): логика разнесена по пакету web/ —
  web/context.py (шаблоны и контекст), web/security.py (авторизация,
  rate limit, CSRF), web/views.py (HTML-маршруты), web/api.py (JSON API),
  web/export.py (выгрузка Excel). Этот файл только собирает приложение.

Запуск:
    uvicorn web_app:app --host 127.0.0.1 --port 5000
    # или
    python web_app.py
    # Сгенерировать bcrypt-хэш пароля:
    python web_app.py --hash-password
"""

import os
import sys
import warnings

import bcrypt
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import config
from web import api as api_module
from web import export as export_module
from web import views as views_module
from web.context import STATIC_DIR, TEMPLATES_DIR
from web.security import _get_client_ip  # noqa: F401 — re-export для смоук-тестов

app = FastAPI(
    title="Инвентаризация",
    docs_url=None,  # Swagger UI — кастомный маршрут в web/api.py (с авторизацией)
    redoc_url=None,
    openapi_url=None,  # OpenAPI JSON — тоже кастомный
)

# Cookie-сессии (для авторизации).
# Приоритет секрета: WEB_SESSION_SECRET → BOT_TOKEN (совместимость) → случайный.
# ⚠️ Случайный секрет = все сессии слетают при каждом перезапуске процесса;
#    BOT_TOKEN как секрет — компромисс (лучше задать отдельный WEB_SESSION_SECRET).
SESSION_SECRET = config.WEB_SESSION_SECRET or config.BOT_TOKEN or os.urandom(24).hex()
if not config.WEB_SESSION_SECRET and not config.BOT_TOKEN:
    warnings.warn(
        "⚠️ WEB_SESSION_SECRET и BOT_TOKEN не заданы — секрет сессий случайный, "
        "все логины будут слетать при перезапуске. Задайте WEB_SESSION_SECRET в .env "
        '(сгенерировать: python -c "import secrets; print(secrets.token_hex(32))")',
        stacklevel=2,
    )

# Cookie флаги:
#   HttpOnly=True (встроено в Starlette) — cookie не доступна из JS (защита от XSS кражи)
#   same_site="strict" — cookie не отправляется на сторонние сайты (защита от CSRF)
#   https_only=config.WEB_PANEL_FORCE_HTTPS — cookie только по HTTPS
# Сессия истекает через 8 часов (рабочий день).
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="inventory_session",
    max_age=60 * 60 * 8,  # 8 часов
    same_site="strict",
    https_only=config.WEB_PANEL_FORCE_HTTPS,
)


# ============================================================
# БЕЗОПАСНОСТЬ: ЗАГОЛОВКИ (security headers)
# ============================================================
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Добавляет security headers ко всем ответам."""
    response = await call_next(request)

    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # HSTS — только при HTTPS (напрямую или за reverse proxy)
    if config.WEB_PANEL_FORCE_HTTPS:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

    # Content Security Policy — белый список источников
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "  https://cdn.tailwindcss.com "
        "  https://unpkg.com "
        "  https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' "
        "  https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net data:; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    )

    return response


# Статика и шаблоны
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Маршруты (порядок не влияет: пути не пересекаются)
app.include_router(api_module.router)
app.include_router(export_module.router)
app.include_router(views_module.router)


# ============================================================
# CLI
# ============================================================
def _print_hash_password_helper():
    """Утилита для генерации bcrypt-хэша пароля."""
    import getpass

    print("🔐 Генерация bcrypt-хэша пароля для .env")
    print("   (пароль не отображается при вводе)\n")
    pwd = getpass.getpass("Введите пароль: ")
    if not pwd:
        print("❌ Пароль не может быть пустым")
        sys.exit(1)
    pwd2 = getpass.getpass("Повторите пароль: ")
    if pwd != pwd2:
        print("❌ Пароли не совпадают")
        sys.exit(1)

    h = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    print("\n✅ Готово. Скопируйте эту строку в .env:\n")
    print(f"WEB_PANEL_PASSWORD={h}")
    print("\n💡 Также рекомендуем (если панель за HTTPS):")
    print("   WEB_PANEL_FORCE_HTTPS=true")
    sys.exit(0)


if __name__ == "__main__":
    # CLI-флаг: python web_app.py --hash-password
    if len(sys.argv) > 1 and sys.argv[1] in ("--hash-password", "-H"):
        _print_hash_password_helper()

    host = config.WEB_PANEL_HOST
    port = config.WEB_PANEL_PORT
    if config.WEB_PANEL_PASSWORD:
        if config.WEB_PANEL_PASSWORD.startswith(("$2a$", "$2b$", "$2y$")):
            print(f"🌐 Веб-панель: http://{host}:{port}/ (bcrypt-пароль)")
        else:
            print(
                f"🌐 Веб-панель: http://{host}:{port}/ (⚠️ plain-text пароль — см. --hash-password)"
            )
    else:
        print(f"🌐 Веб-панель: http://{host}:{port}/ (без авторизации)")
    print(f"   Swagger UI:  http://{host}:{port}/api/docs")
    if config.WEB_PANEL_FORCE_HTTPS:
        print("🔒 HTTPS включён (cookie Secure + HSTS)")
    uvicorn.run(app, host=host, port=port, log_level="info")
