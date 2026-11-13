"""JSON API (/health, /api/*) и защищённый Swagger UI."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

import database as db
from web.context import AUDIT_CATEGORIES, get_db_connection
from web.security import require_auth

router = APIRouter()


@router.get("/health")
def health():
    """Healthcheck для Docker/K8s — БЕЗ авторизации.

    Раньше docker healthcheck бил в /api/stats, который закрыт паролем:
    curl получал 303 на /login, -f не срабатывал на редиректе, и контейнер
    помечался healthy случайно. /health лёгкий и честный: 200 + проверка БД.
    """
    if not db.ping():
        return JSONResponse({"status": "degraded", "db": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok"})


@router.get("/api/stats")
def api_stats(request: Request):
    require_auth(request)
    return JSONResponse(db.get_db_stats())


@router.get("/api/items")
def api_items(
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


@router.get("/api/items/{item_id}")
def api_item(item_id: int, request: Request):
    require_auth(request)
    item = db.get_item_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return JSONResponse(item)


@router.get("/api/audit/{category}")
def api_audit(category: str, request: Request):
    require_auth(request)
    label_dict = {k: lbl for k, lbl, _d in AUDIT_CATEGORIES}
    if category not in label_dict:
        raise HTTPException(status_code=400, detail="Неизвестная категория")
    items = db.find_problematic_items(category, limit=500)
    # Настоящее количество — COUNT(*), не обрезанное limit'ом выборки
    count = db.count_problematic_items(category)
    return JSONResponse(
        {"category": category, "label": label_dict[category], "count": count, "items": items}
    )


# ============================================================
# SWAGGER UI / OPENAPI — защищённые кастомные маршруты
# ============================================================
# По умолчанию FastAPI отдаёт /api/docs и /api/openapi.json без авторизации.
# Чтобы закрыть их под пароль — дефолтные отключены при создании app
# (docs_url=None, openapi_url=None в web_app.py), здесь свои маршруты.
@router.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html(request: Request):
    require_auth(request)
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="Инвентаризация — API",
        oauth2_redirect_url="/api/docs/oauth2-redirect",
    )


@router.get("/api/openapi.json", include_in_schema=False)
async def custom_openapi(request: Request):
    require_auth(request)
    app = request.app
    if not app.openapi_schema:
        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
    return app.openapi_schema
