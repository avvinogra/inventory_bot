"""
Веб-панель инвентаризации — FastAPI приложение.

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

Запуск:
    uvicorn web_app:app --host 127.0.0.1 --port 5000
    # или
    python web_app.py
    # Сгенерировать bcrypt-хэш пароля:
    python web_app.py --hash-password

Маршруты (HTML):
  GET  /                  — дашборд со статистикой
  GET  /inventory         — список записей (HTMX-поиск без перезагрузки)
  GET  /audit             — аудит: список категорий
  GET  /audit?cat=X       — записи конкретной категории
  GET  /item/{id}         — полная карточка записи
  GET  /login             — форма входа
  POST /login             — авторизация
  POST /logout            — выход
  GET  /export            — выгрузка в Excel

API (JSON):
  GET /api/stats          — общая статистика
  GET /api/items?...      — список записей с фильтрами
  GET /api/items/{id}     — одна запись
  GET /api/audit/{cat}    — записи категории аудита
"""
import os
import secrets
import sqlite3
import sys
import time
import warnings
from collections import defaultdict
from contextlib import contextmanager
from typing import Optional

import bcrypt
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import config
import database as db
from excel_export import export_to_excel

# ============================================================
# КОНСТАНТЫ
# ============================================================
TECH_TYPE_LABELS = {
    "pc":      "Системный блок",
    "monitor": "Монитор",
    "printer": "Принтер / МФУ",
    "laptop":  "Ноутбук",
    "other":   "Другое",
}

AUDIT_CATEGORIES = [
    ("no_pc_name",    "Без имени компьютера",       "ПК / ноутбук / принтер без имени компьютера"),
    ("no_ip",         "Без IP-адреса",              "ПК / ноутбук / принтер без IP-адреса"),
    ("no_mac",        "Без MAC-адресов",            "ПК / ноутбук / принтер без физических и реальных MAC-адресов"),
    ("drweb_problem", "Dr.Web: проблема",           "Dr.Web: «Нет лицензии» или «Нет соединения» (включая старые «нет лиц»/«нет соед»)"),
    ("mac_mismatch",  "Физ. MAC ≠ Реал. MAC",       "Физический MAC ≠ Реальный MAC (оба заполнены)"),
    ("no_specs",      "Без характеристик",          "ПК / ноутбук без поля «Характеристики»"),
]

DRWEB_DISPLAY_MAP = {
    "Установлен":                "Установлен",
    "Нет лицензии":              "Нет лицензии",
    "Нет соединения с сервером": "Нет соединения с сервером",
    "Не установлен":             "Не установлен",
    "+":        "Установлен",
    "да":       "Установлен",
    "yes":      "Установлен",
    "нет лиц":  "Нет лицензии",
    "нет соед": "Нет соединения с сервером",
    "нет":      "Не установлен",
    "no":       "Не установлен",
}


def drweb_display(value: Optional[str]) -> str:
    if not value:
        return "—"
    return DRWEB_DISPLAY_MAP.get(str(value).strip().lower(), str(value))


# ============================================================
# БД
# ============================================================
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# ПРИЛОЖЕНИЕ
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(
    title="Инвентаризация",
    docs_url=None,           # Swagger UI — кастомный маршрут ниже (с авторизацией)
    redoc_url=None,
    openapi_url=None,        # OpenAPI JSON — тоже кастомный
)

# Cookie-сессии (для авторизации). Секрет — из BOT_TOKEN или генерируется случайно.
SESSION_SECRET = config.BOT_TOKEN or os.urandom(24).hex()
# ⚠️ Если секрет генерируется случайно — при перезапуске все сессии слетают.
# Для прод-режима задайте BOT_TOKEN в .env.

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


# ============================================================
# SWAGGER UI / OPENAPI — защищённые кастомные маршруты
# ============================================================
# По умолчанию FastAPI отдаёт /api/docs и /api/openapi.json без авторизации.
# Чтобы закрыть их под пароль — отключаем дефолтные (docs_url=None, openapi_url=None)
# и делаем свои маршруты с require_auth.
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html


@app.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html(request: Request):
    require_auth(request)
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="Инвентаризация — API",
        oauth2_redirect_url="/api/docs/oauth2-redirect",
    )


@app.get("/api/openapi.json", include_in_schema=False)
async def custom_openapi(request: Request):
    require_auth(request)
    if not app.openapi_schema:
        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
    return app.openapi_schema


# ============================================================
# БЕЗОПАСНОСТЬ: ПАРОЛЬ (BCRYPT)
# ============================================================
def verify_password(plain: str, stored: str) -> bool:
    """Сравнивает введённый пароль с хранимым значением.

    Поддерживает:
    - bcrypt-хэш (начинается с $2a$, $2b$, $2y$) — рекомендуется
    - plain text (для совместимости — выводит warning при запуске)
    """
    if not plain or not stored:
        return False
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False
    # Plain text — для совместимости (используем constant-time comparison)
    return secrets.compare_digest(plain, stored)


def _warn_plain_password():
    """Выводит предупреждение, если WEB_PANEL_PASSWORD — plain text."""
    if not config.WEB_PANEL_PASSWORD:
        return
    if not config.WEB_PANEL_PASSWORD.startswith(("$2a$", "$2b$", "$2y$")):
        warnings.warn(
            "⚠️ WEB_PANEL_PASSWORD хранится в открытом виде (plain text). "
            "Сгенерируйте bcrypt-хэш: python web_app.py --hash-password — "
            "и пропишите его в .env. Это защитит пароль при утечке .env."
        )


_warn_plain_password()


# ============================================================
# БЕЗОПАСНОСТЬ: RATE LIMITING НА /login
# ============================================================
# Хранилище в памяти: {ip: [timestamp, timestamp, ...]}
# При перезапуске бота сбрасывается — для production лучше Redis,
# но для внутреннего использования этого достаточно.
_login_attempts: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 60         # секунд: 5 попыток за 60 сек
RATE_LIMIT_BLOCK = 300        # 5 минут блокировки после превышения


def _get_client_ip(request: Request) -> str:
    """Учитывает X-Forwarded-For от reverse proxy."""
    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> Optional[int]:
    """Проверяет, можно ли ещё пытаться войти.
    Возвращает None, если можно. Иначе — сколько секунд до разблокировки.
    """
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    # Чистим старые записи (старше RATE_LIMIT_BLOCK)
    _login_attempts[ip] = [t for t in attempts if now - t < RATE_LIMIT_BLOCK]
    attempts = _login_attempts[ip]

    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        oldest = attempts[0]
        wait = int(RATE_LIMIT_BLOCK - (now - oldest))
        return max(wait, 1)
    return None


def _record_failed_login(ip: str):
    _login_attempts[ip].append(time.time())


def _clear_attempts(ip: str):
    _login_attempts.pop(ip, None)


# ============================================================
# БЕЗОПАСНОСТЬ: CSRF-ТОКЕНЫ
# ============================================================
def _get_csrf_token(request: Request) -> str:
    """Получает CSRF-токен из сессии. Если нет — генерирует новый."""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        request.session["csrf_token"] = token
    return token


async def csrf_protect(request: Request):
    """Зависимость для POST/DELETE/PATCH эндпоинтов.
    Проверяет CSRF-токен в заголовке X-CSRF-Token (HTMX) или в форме (csrf_token).
    """
    if not config.WEB_PANEL_PASSWORD:
        return  # авторизация не нужна — CSRF не нужен

    expected = request.session.get("csrf_token")
    if not expected:
        raise HTTPException(status_code=403, detail="CSRF-токен не найден в сессии")

    token = request.headers.get("X-CSRF-Token")
    if not token:
        # Пытаемся достать из form data (для обычных POST-форм)
        try:
            form = await request.form()
            token = form.get("csrf_token")
        except Exception:
            token = None

    if not token or not secrets.compare_digest(str(token), str(expected)):
        raise HTTPException(status_code=403, detail="Неверный CSRF-токен")


# Статика и шаблоны
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
# Jinja2 фильтр для нормализации значений Dr.Web (без эмодзи)
templates.env.filters["drweb_display"] = drweb_display


# ============================================================
# АВТОРИЗАЦИЯ
# ============================================================
def is_authenticated(request: Request) -> bool:
    """Проверяет, авторизован ли пользователь в текущей сессии."""
    if not config.WEB_PANEL_PASSWORD:
        return True  # пароль не задан — панель открыта
    return bool(request.session.get("authed"))


def require_auth(request: Request):
    """Если не авторизован — выбрасывает 401 / редирект на /login."""
    if not is_authenticated(request):
        # Для HTMX-запросов (Hx-Request: true) — отдаём 401, чтобы JS показал логин
        if request.headers.get("Hx-Request") == "true":
            raise HTTPException(status_code=401, detail="Требуется авторизация")
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )


# ============================================================
# КОНТЕКСТ ДЛЯ ШАБЛОНОВ
# ============================================================
def _base_context(request: Request) -> dict:
    return {
        "request": request,
        "authed": is_authenticated(request),
        "needs_password": bool(config.WEB_PANEL_PASSWORD),
        "csrf_token": _get_csrf_token(request),
        # Глобальные данные для всех шаблонов
        "CLINICS": config.CLINICS,
        "TECH_TYPE_LABELS": TECH_TYPE_LABELS,
        "AUDIT_CATEGORIES": AUDIT_CATEGORIES,
    }


# ============================================================
# HTML МАРШРУТЫ
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    require_auth(request)

    with get_db_connection() as conn:
        # Общая статистика
        total_items = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]

        # По поликлиникам
        clinic_stats = conn.execute(
            "SELECT clinic, COUNT(*) as count FROM inventory GROUP BY clinic ORDER BY count DESC"
        ).fetchall()

        # По типам техники
        tech_stats_raw = conn.execute(
            """
            SELECT
                CASE WHEN tech_type IS NOT NULL AND tech_type != '' THEN tech_type ELSE 'other' END as t,
                COUNT(*) as c
            FROM inventory GROUP BY t
            """
        ).fetchall()

        # По ОС (топ-15)
        os_stats_raw = conn.execute(
            """
            SELECT CASE WHEN os IS NULL OR os = '' THEN 'Не указано' ELSE os END as os_name,
                   COUNT(*) as c
            FROM inventory GROUP BY os_name ORDER BY c DESC LIMIT 15
            """
        ).fetchall()

        # Dr.Web — 4 категории + «Не указано»
        drweb_stats_raw = conn.execute(
            """
            SELECT CASE WHEN drweb IS NULL OR drweb = '' THEN 'Не указано' ELSE drweb END as d,
                   COUNT(*) as c
            FROM inventory GROUP BY d
            """
        ).fetchall()

        # KPI
        with_pc_name = conn.execute(
            "SELECT COUNT(*) FROM inventory WHERE pc_name IS NOT NULL AND pc_name != ''"
        ).fetchone()[0]
        with_ip = conn.execute(
            "SELECT COUNT(*) FROM inventory WHERE ip IS NOT NULL AND ip != ''"
        ).fetchone()[0]
        with_mac_phys = conn.execute(
            "SELECT COUNT(*) FROM inventory WHERE mac_phys IS NOT NULL AND mac_phys != ''"
        ).fetchone()[0]
        with_mac_real = conn.execute(
            "SELECT COUNT(*) FROM inventory WHERE mac_real IS NOT NULL AND mac_real != ''"
        ).fetchone()[0]
        with_specs = conn.execute(
            "SELECT COUNT(*) FROM inventory WHERE specs IS NOT NULL AND specs != ''"
        ).fetchone()[0]
        with_os = conn.execute(
            "SELECT COUNT(*) FROM inventory WHERE os IS NOT NULL AND os != ''"
        ).fetchone()[0]

        # Последние записи
        recent_items = conn.execute(
            "SELECT * FROM inventory ORDER BY id DESC LIMIT 10"
        ).fetchall()

    # Нормализуем Dr.Web
    drweb_groups = {}
    for row in drweb_stats_raw:
        label = drweb_display(row["d"]) if row["d"] != "Не указано" else "Не указано"
        drweb_groups[label] = drweb_groups.get(label, 0) + row["c"]

    # Аудит
    audit_summary = []
    for key, label, _desc in AUDIT_CATEGORIES:
        count = len(db.find_problematic_items(key, limit=500))
        audit_summary.append({"key": key, "label": label, "count": count})

    ctx = _base_context(request)
    ctx.update({
        "total_items": total_items,
        "with_pc_name": with_pc_name,
        "with_ip": with_ip,
        "with_mac_phys": with_mac_phys,
        "with_mac_real": with_mac_real,
        "with_specs": with_specs,
        "with_os": with_os,
        "clinic_count": len(clinic_stats),
        # Графики
        "clinic_labels": [config.CLINICS.get(r["clinic"], r["clinic"]) for r in clinic_stats],
        "clinic_data": [r["count"] for r in clinic_stats],
        "tech_type_labels": [TECH_TYPE_LABELS.get(r["t"], r["t"]) for r in tech_stats_raw],
        "tech_type_data": [r["c"] for r in tech_stats_raw],
        "os_labels": [r["os_name"] for r in os_stats_raw],
        "os_data": [r["c"] for r in os_stats_raw],
        "drweb_labels": list(drweb_groups.keys()),
        "drweb_data": list(drweb_groups.values()),
        # Таблицы
        "recent_items": recent_items,
        # Аудит
        "audit_summary": audit_summary,
        "audit_total_problems": sum(a["count"] for a in audit_summary),
    })
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.get("/inventory", response_class=HTMLResponse)
async def inventory(
    request: Request,
    search: str = Query(""),
    clinic: str = Query(""),
    tech_type: str = Query(""),
    sort: str = Query("id"),
    order: str = Query("desc"),
):
    require_auth(request)

    # Whitelist для сортировки (защита от SQL injection)
    allowed_sort = {"id", "cabinet", "tech", "inv_number", "serial", "os", "drweb", "ip", "pc_name", "clinic"}
    sort = sort if sort in allowed_sort else "id"
    order = "asc" if order.lower() == "asc" else "desc"

    # Маппинг коротких имён полей на колонки БД
    sort_column = {
        "id": "id", "cabinet": "cabinet", "tech": "tech",
        "inv_number": "inv_number", "serial": "serial",
        "os": "os", "drweb": "drweb", "ip": "ip",
        "pc_name": "pc_name", "clinic": "clinic",
    }.get(sort, "id")

    query = "SELECT * FROM inventory WHERE 1=1"
    params = []

    if search:
        query += (
            " AND (inv_number LIKE ? OR tech LIKE ? OR cabinet LIKE ? "
            "      OR serial LIKE ? OR pc_name LIKE ? OR specs LIKE ? "
            "      OR note LIKE ? OR os LIKE ?)"
        )
        q = f"%{search}%"
        params.extend([q] * 8)
    if clinic:
        query += " AND clinic = ?"
        params.append(clinic)
    if tech_type:
        query += " AND tech_type = ?"
        params.append(tech_type)

    query += f" ORDER BY {sort_column} {order.upper()} LIMIT 200"

    with get_db_connection() as conn:
        items = conn.execute(query, params).fetchall()

    ctx = _base_context(request)
    ctx.update({
        "items": items,
        "search": search,
        "clinic_filter": clinic,
        "tech_type_filter": tech_type,
        "sort": sort,
        "order": order,
    })
    # Если это HTMX-запрос — отдаём только таблицу (partial)
    if request.headers.get("Hx-Request") == "true":
        return templates.TemplateResponse(request, "inventory_table.html", ctx)
    return templates.TemplateResponse(request, "inventory.html", ctx)


@app.get("/audit", response_class=HTMLResponse)
async def audit(
    request: Request,
    cat: str = Query(""),
    page: int = Query(1, ge=1),
):
    require_auth(request)

    page_size = 25
    label_dict = {k: l for k, l, _d in AUDIT_CATEGORIES}

    if cat and cat in label_dict:
        all_items = db.find_problematic_items(cat, limit=500)
        total = len(all_items)
        start = (page - 1) * page_size
        page_items = all_items[start:start + page_size]
        ctx = _base_context(request)
        ctx.update({
            "mode": "category",
            "category": cat,
            "category_label": label_dict[cat],
            "items": page_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "audit_categories": AUDIT_CATEGORIES,
        })
        return templates.TemplateResponse(request, "audit.html", ctx)

    # Сводка
    audit_summary = [
        {"key": key, "label": label, "desc": desc, "count": len(db.find_problematic_items(key, limit=500))}
        for key, label, desc in AUDIT_CATEGORIES
    ]
    ctx = _base_context(request)
    ctx.update({
        "mode": "summary",
        "audit_summary": audit_summary,
        "audit_categories": AUDIT_CATEGORIES,
    })
    return templates.TemplateResponse(request, "audit.html", ctx)


@app.get("/item/{item_id}", response_class=HTMLResponse)
async def item_detail(item_id: int, request: Request):
    require_auth(request)
    with get_db_connection() as conn:
        item = conn.execute(
            "SELECT * FROM inventory WHERE id = ?", (item_id,)
        ).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    # Преобразовать sqlite3.Row в dict (для .get())
    item = dict(item)

    # Если запись в АРМ — получить список других записей этого АРМ
    arm_items = []
    if item.get("arm_id"):
        arm_items = db.get_arm_items(item["arm_id"])

    ctx = _base_context(request)
    ctx.update({
        "item": item,
        "arm_items": arm_items,
    })
    return templates.TemplateResponse(request, "item_detail.html", ctx)


@app.get("/arm", response_class=HTMLResponse)
async def arm_list(request: Request):
    """Страница АРМ — список всех АРМ."""
    require_auth(request)
    arms = db.get_all_arms()
    ctx = _base_context(request)
    ctx.update({"arms": arms})
    return templates.TemplateResponse(request, "arm.html", ctx)


@app.get("/arm/{arm_id}", response_class=HTMLResponse)
async def arm_detail(arm_id: int, request: Request):
    """Просмотр конкретного АРМ."""
    require_auth(request)
    items = db.get_arm_items(arm_id)
    if not items:
        raise HTTPException(status_code=404, detail="АРМ не найден")
    ctx = _base_context(request)
    ctx.update({
        "arm_id": arm_id,
        "items": items,
    })
    return templates.TemplateResponse(request, "arm_detail.html", ctx)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if not config.WEB_PANEL_PASSWORD:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", _base_context(request))


@app.post("/login")
async def login_submit(
    request: Request,
    password: str = Form(...),
):
    if not config.WEB_PANEL_PASSWORD:
        return RedirectResponse("/", status_code=303)

    ip = _get_client_ip(request)

    # Rate limit: 5 попыток за 60 сек, потом блок на 5 мин
    wait = _check_rate_limit(ip)
    if wait:
        ctx = _base_context(request)
        ctx.update({"error": f"Слишком много попыток входа. Попробуйте через {wait} сек."})
        return templates.TemplateResponse(request, "login.html", ctx, status_code=429)

    if not verify_password(password, config.WEB_PANEL_PASSWORD):
        _record_failed_login(ip)
        ctx = _base_context(request)
        ctx.update({"error": "Неверный пароль"})
        return templates.TemplateResponse(request, "login.html", ctx, status_code=401)

    # Успешный вход — сбрасываем счётчик попыток
    _clear_attempts(ip)
    request.session["authed"] = True
    request.session["authed_at"] = time.time()
    # Перегенерируем CSRF-токен после входа
    request.session["csrf_token"] = secrets.token_hex(32)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
async def logout(request: Request, _: None = Depends(csrf_protect)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/export")
async def export(request: Request):
    require_auth(request)
    try:
        path = export_to_excel()
        if not path:
            raise HTTPException(status_code=400, detail="База пуста")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="inventory.xlsx",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка экспорта: {e}")


@app.delete("/delete/{item_id}")
async def delete_item(item_id: int, request: Request, _: None = Depends(csrf_protect)):
    require_auth(request)
    db.delete_item(item_id)
    return Response(status_code=200)


@app.post("/update/{item_id}", response_class=HTMLResponse)
async def update_item(
    item_id: int,
    request: Request,
    _: None = Depends(csrf_protect),
    clinic: str = Form(""),
    cabinet: str = Form(""),
    tech_type: str = Form(""),
    tech: str = Form(""),
    inv_number: str = Form(""),
    serial: str = Form(""),
    os: str = Form(""),
    drweb: str = Form(""),
    ip: str = Form(""),
    pc_name: str = Form(""),
    mac_phys: str = Form(""),
    mac_real: str = Form(""),
    specs: str = Form(""),
    note: str = Form(""),
):
    """Обновление всех полей записи через веб-форму."""
    require_auth(request)

    # Маппинг полей формы → колонки БД
    fields = {
        "clinic": clinic, "cabinet": cabinet, "tech_type": tech_type,
        "tech": tech, "inv_number": inv_number, "serial": serial,
        "os": os, "drweb": drweb, "ip": ip, "pc_name": pc_name,
        "mac_phys": mac_phys, "mac_real": mac_real,
        "specs": specs, "note": note,
    }
    try:
        with get_db_connection() as conn:
            for col, val in fields.items():
                conn.execute(
                    f"UPDATE inventory SET {col} = ? WHERE id = ?",
                    (val, item_id)
                )
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обновления: {e}")

    return RedirectResponse(url_for('item_detail', item_id=item_id), status_code=303)


# ============================================================
# JSON API
# ============================================================
@app.get("/api/stats")
async def api_stats(request: Request):
    require_auth(request)
    return JSONResponse(db.get_db_stats())


@app.get("/api/items")
async def api_items(
    request: Request,
    search: str = Query(""),
    clinic: str = Query(""),
    tech_type: str = Query(""),
    limit: int = Query(100, le=500),
):
    require_auth(request)
    query = "SELECT * FROM inventory WHERE 1=1"
    params = []
    if search:
        query += (
            " AND (inv_number LIKE ? OR tech LIKE ? OR cabinet LIKE ? "
            "      OR serial LIKE ? OR pc_name LIKE ? OR specs LIKE ? "
            "      OR note LIKE ? OR os LIKE ?)"
        )
        q = f"%{search}%"
        params.extend([q] * 8)
    if clinic:
        query += " AND clinic = ?"
        params.append(clinic)
    if tech_type:
        query += " AND tech_type = ?"
        params.append(tech_type)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return JSONResponse([dict(r) for r in rows])


@app.get("/api/items/{item_id}")
async def api_item(item_id: int, request: Request):
    require_auth(request)
    item = db.get_item_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return JSONResponse(item)


@app.get("/api/audit/{category}")
async def api_audit(category: str, request: Request):
    require_auth(request)
    label_dict = {k: l for k, l, _d in AUDIT_CATEGORIES}
    if category not in label_dict:
        raise HTTPException(status_code=400, detail="Неизвестная категория")
    items = db.find_problematic_items(category, limit=500)
    return JSONResponse({"category": category, "label": label_dict[category], "count": len(items), "items": items})


# ============================================================
# ЗАПУСК
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
            print(f"🌐 Веб-панель: http://{host}:{port}/ (⚠️ plain-text пароль — см. --hash-password)")
    else:
        print(f"🌐 Веб-панель: http://{host}:{port}/ (без авторизации)")
    print(f"   Swagger UI:  http://{host}:{port}/api/docs")
    if config.WEB_PANEL_FORCE_HTTPS:
        print(f"🔒 HTTPS включён (cookie Secure + HSTS)")
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
