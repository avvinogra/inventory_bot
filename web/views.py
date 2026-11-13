"""HTML-маршруты веб-панели: дашборд, список, аудит, карточка, АРМ, логин."""

import asyncio
import secrets
import sqlite3
import time

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import HTMLResponse, RedirectResponse

import config
import database as db
from bot_core.constants import display_drweb
from validators import is_valid_ip, is_valid_mac
from web.context import (
    AUDIT_CATEGORIES,
    TECH_TYPE_LABELS,
    _base_context,
    _recent_items,
    get_db_connection,
    templates,
)
from web.security import (
    _check_rate_limit,
    _clear_attempts,
    _get_client_ip,
    _record_failed_login,
    csrf_protect,
    require_auth,
    verify_password,
)

router = APIRouter()

# ⚠️ Эндпоинты с обращением к БД объявлены как ОБЫЧНЫЕ def (не async def):
# FastAPI выполняет их в threadpool, а не в event loop.
# Раньше sync-sqlite3 внутри async def блокировал весь event loop —
# панель «замерзала» для всех пользователей на время каждого запроса.


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
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
        recent_items = conn.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT 10").fetchall()

    # Нормализуем Dr.Web (единая реализация display_drweb — как у бота)
    drweb_groups = {}
    for row in drweb_stats_raw:
        label = display_drweb(row["d"]) if row["d"] != "Не указано" else "Не указано"
        drweb_groups[label] = drweb_groups.get(label, 0) + row["c"]

    # Аудит — счётчики через COUNT(*) на стороне БД
    # (раньше: len(find_problematic_items(limit=500)) — тянули до 500
    # полных строк ради числа, и «больше 500» показывалось как «500»)
    audit_summary = []
    for key, label, _desc in AUDIT_CATEGORIES:
        count = db.count_problematic_items(key)
        audit_summary.append({"key": key, "label": label, "count": count})

    ctx = _base_context(request)
    ctx.update(
        {
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
        }
    )
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@router.get("/inventory", response_class=HTMLResponse)
def inventory(
    request: Request,
    search: str = Query(""),
    clinic: str = Query(""),
    tech_type: str = Query(""),
    sort: str = Query("id"),
    order: str = Query("desc"),
):
    require_auth(request)

    # Whitelist для сортировки (защита от SQL injection)
    allowed_sort = {
        "id",
        "cabinet",
        "tech",
        "inv_number",
        "serial",
        "os",
        "drweb",
        "ip",
        "pc_name",
        "clinic",
    }
    sort = sort if sort in allowed_sort else "id"
    order = "asc" if order.lower() == "asc" else "desc"

    # Маппинг коротких имён полей на колонки БД
    sort_column = {
        "id": "id",
        "cabinet": "cabinet",
        "tech": "tech",
        "inv_number": "inv_number",
        "serial": "serial",
        "os": "os",
        "drweb": "drweb",
        "ip": "ip",
        "pc_name": "pc_name",
        "clinic": "clinic",
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
    ctx.update(
        {
            "items": items,
            "search": search,
            "clinic_filter": clinic,
            "tech_type_filter": tech_type,
            "sort": sort,
            "order": order,
        }
    )
    # Если это HTMX-запрос — отдаём только таблицу (partial)
    if request.headers.get("Hx-Request") == "true":
        return templates.TemplateResponse(request, "inventory_table.html", ctx)
    return templates.TemplateResponse(request, "inventory.html", ctx)


@router.get("/audit", response_class=HTMLResponse)
def audit(
    request: Request,
    cat: str = Query(""),
    page: int = Query(1, ge=1),
):
    require_auth(request)

    page_size = 25
    label_dict = {k: lbl for k, lbl, _d in AUDIT_CATEGORIES}

    if cat and cat in label_dict:
        all_items = db.find_problematic_items(cat, limit=500)
        total = db.count_problematic_items(cat)
        start = (page - 1) * page_size
        page_items = all_items[start : start + page_size]
        ctx = _base_context(request)
        ctx.update(
            {
                "mode": "category",
                "category": cat,
                "category_label": label_dict[cat],
                "items": page_items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "audit_categories": AUDIT_CATEGORIES,
            }
        )
        return templates.TemplateResponse(request, "audit.html", ctx)

    # Сводка — счётчики через COUNT(*) (см. dashboard)
    audit_summary = [
        {"key": key, "label": label, "desc": desc, "count": db.count_problematic_items(key)}
        for key, label, desc in AUDIT_CATEGORIES
    ]
    ctx = _base_context(request)
    ctx.update(
        {
            "mode": "summary",
            "audit_summary": audit_summary,
            "audit_categories": AUDIT_CATEGORIES,
        }
    )
    return templates.TemplateResponse(request, "audit.html", ctx)


@router.get("/item/{item_id}", response_class=HTMLResponse)
def item_detail(item_id: int, request: Request):
    require_auth(request)
    with get_db_connection() as conn:
        item = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    # Преобразовать sqlite3.Row в dict (для .get())
    item = dict(item)

    # Если запись в АРМ — получить список других записей этого АРМ
    arm_items = []
    if item.get("arm_id"):
        arm_items = db.get_arm_items(item["arm_id"])

    ctx = _base_context(request)
    ctx.update(
        {
            "item": item,
            "arm_items": arm_items,
        }
    )
    return templates.TemplateResponse(request, "item_detail.html", ctx)


# ============================================================
# АРМ (группы устройств)
# ============================================================
@router.get("/arm", response_class=HTMLResponse)
def arm_list(request: Request):
    """Страница АРМ — список всех АРМ."""
    require_auth(request)
    arms = db.get_all_arms()
    ctx = _base_context(request)
    ctx.update({"arms": arms})
    return templates.TemplateResponse(request, "arm.html", ctx)


@router.get("/arm/create", response_class=HTMLResponse)
def arm_create_form(request: Request):
    """Форма создания АРМ — список всех записей с чекбоксами."""
    require_auth(request)
    items = _recent_items()
    ctx = _base_context(request)
    ctx.update({"items": items})
    return templates.TemplateResponse(request, "arm_create.html", ctx)


@router.post("/arm/create")
async def arm_create_submit(
    request: Request,
    _: None = Depends(csrf_protect),
):
    """Создание АРМ из выбранных записей (POST-форма с чекбоксами)."""
    require_auth(request)
    form = await request.form()
    selected = form.getlist("item_ids")
    ids = []
    for s in selected:
        try:
            ids.append(int(s))
        except (TypeError, ValueError):
            continue

    if not ids:
        items = await asyncio.to_thread(_recent_items)
        ctx = _base_context(request)
        ctx.update({"items": items, "error": "Не выбрано ни одной записи"})
        return templates.TemplateResponse(request, "arm_create.html", ctx, status_code=400)

    # create_arm бросает исключение при ошибке (раньше возвращал -1,
    # что приводило к редиректу на несуществующий АРМ #0)
    try:
        arm_id = await asyncio.to_thread(db.create_arm, ids)
    except (ValueError, sqlite3.Error) as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания АРМ: {e}") from e
    return RedirectResponse(request.url_for("arm_detail", arm_id=arm_id), status_code=303)


@router.get("/arm/{arm_id}", response_class=HTMLResponse)
def arm_detail(arm_id: int, request: Request):
    """Просмотр конкретного АРМ."""
    require_auth(request)
    items = db.get_arm_items(arm_id)
    if not items:
        raise HTTPException(status_code=404, detail="АРМ не найден")
    ctx = _base_context(request)
    ctx.update(
        {
            "arm_id": arm_id,
            "items": items,
        }
    )
    return templates.TemplateResponse(request, "arm_detail.html", ctx)


@router.get("/arm/{arm_id}/add", response_class=HTMLResponse)
def arm_add_items(arm_id: int, request: Request):
    """Страница добавления записей в существующий АРМ."""
    require_auth(request)
    items = db.get_arm_items(arm_id)
    if not items:
        raise HTTPException(status_code=404, detail="АРМ не найден")
    # Записи, не входящие ни в один АРМ
    free_items = db.get_items_without_arm(limit=200)
    ctx = _base_context(request)
    ctx.update(
        {
            "arm_id": arm_id,
            "items": items,
            "free_items": free_items,
        }
    )
    return templates.TemplateResponse(request, "arm_add.html", ctx)


@router.post("/arm/{arm_id}/add", response_class=HTMLResponse)
async def arm_add_submit(
    arm_id: int,
    request: Request,
    _: None = Depends(csrf_protect),
):
    """Добавление выбранных записей в АРМ."""
    require_auth(request)
    form = await request.form()
    item_ids = form.getlist("item_ids")
    if not item_ids:
        raise HTTPException(status_code=400, detail="Не выбрано ни одной записи")
    added = 0
    for item_id_str in item_ids:
        # Раньше: except (ValueError, Exception): pass — молча глотал ошибки БД
        # (ValueError и так покрывает int(), а Exception глотало всё остальное).
        # Теперь парсинг и ошибка БД обрабатываются отдельно и честно.
        try:
            item_id = int(item_id_str)
        except (TypeError, ValueError):
            continue
        if await asyncio.to_thread(db.add_to_arm, item_id, arm_id):
            added += 1
    if not added:
        raise HTTPException(status_code=400, detail="Не удалось добавить записи в АРМ")
    return RedirectResponse(request.url_for("arm_detail", arm_id=arm_id), status_code=303)


@router.delete("/arm/{arm_id}/disband")
def arm_disband(arm_id: int, request: Request, _: None = Depends(csrf_protect)):
    """Расформировать АРМ."""
    require_auth(request)
    db.delete_arm(arm_id)
    return RedirectResponse(request.url_for("arm_list"), status_code=303)


@router.delete("/arm/item/{item_id}")
def arm_remove_item(item_id: int, request: Request, _: None = Depends(csrf_protect)):
    """Убрать запись из АРМ (HTMX)."""
    require_auth(request)
    db.remove_from_arm(item_id)
    # Возвращаем пустую строку — HTMX уберёт строку из DOM
    return Response(status_code=200, content="")


# ============================================================
# ЛОГИН / ЛОГАУТ
# ============================================================
@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if not config.WEB_PANEL_PASSWORD:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", _base_context(request))


@router.post("/login")
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

    # bcrypt.checkpw намеренно медленный (~100-250 мс) — это CPU-bound,
    # в event loop он подвешивал ВСЕ запросы панели на время проверки.
    password_ok = await asyncio.to_thread(verify_password, password, config.WEB_PANEL_PASSWORD)

    if not password_ok:
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


@router.post("/logout")
async def logout(request: Request, _: None = Depends(csrf_protect)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ============================================================
# УДАЛЕНИЕ / ОБНОВЛЕНИЕ ЗАПИСЕЙ
# ============================================================
@router.delete("/delete/{item_id}")
def delete_item(item_id: int, request: Request, _: None = Depends(csrf_protect)):
    require_auth(request)
    db.delete_item(item_id)
    return Response(status_code=200)


@router.post("/update/{item_id}", response_class=HTMLResponse)
def update_item(
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

    # Маппинг полей формы → колонки БД (ключи фиксированы — это whitelist)
    fields = {
        "clinic": clinic,
        "cabinet": cabinet,
        "tech_type": tech_type,
        "tech": tech,
        "inv_number": inv_number,
        "serial": serial,
        "os": os,
        "drweb": drweb,
        "ip": ip,
        "pc_name": pc_name,
        "mac_phys": mac_phys,
        "mac_real": mac_real,
        "specs": specs,
        "note": note,
    }

    # Валидация IP/MAC — та же, что в боте (validators.py).
    # Раньше веб-форма принимала любой текст в эти поля.
    errors = []
    if not is_valid_ip(fields["ip"]):
        errors.append(f"Неверный формат IP-адреса: «{fields['ip']}». Пример: 192.168.1.10")
    if not is_valid_mac(fields["mac_phys"]):
        errors.append(
            f"Неверный формат физического MAC: «{fields['mac_phys']}». Пример: 00:1A:2B:3C:4D:5E"
        )
    if not is_valid_mac(fields["mac_real"]):
        errors.append(
            f"Неверный формат реального MAC: «{fields['mac_real']}». Пример: 00:1A:2B:3C:4D:5E"
        )

    def _re_render(error_messages: list):
        """Показать форму снова с введёнными значениями и ошибками.

        За основу берём запись из БД (id, arm_id, created_at и пр.),
        поверх — отправленные значения формы: пользователь не теряет ввод.
        """
        item = db.get_item_by_id(item_id) or {}
        item.update(fields)
        item["id"] = item_id
        arm_items = db.get_arm_items(item.get("arm_id")) if item.get("arm_id") else []
        ctx = _base_context(request)
        ctx.update(
            {
                "item": item,
                "arm_items": arm_items,
                "form_errors": error_messages,
            }
        )
        return templates.TemplateResponse(request, "item_detail.html", ctx, status_code=400)

    if errors:
        return _re_render(errors)

    try:
        with get_db_connection() as conn:
            # Один UPDATE вместо 14 раздельных: раньше между одиночными
            # UPDATE-ами без общей транзакции запись могла остаться
            # «наполовину отредактированной» при ошибке в середине.
            # Имена колонок — из фиксированного whitelist выше.
            assignments = ", ".join(f"{col} = ?" for col in fields)
            conn.execute(
                f"UPDATE inventory SET {assignments} WHERE id = ?",
                (*fields.values(), item_id),
            )
            conn.commit()
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обновления: {e}") from e

    return RedirectResponse(request.url_for("item_detail", item_id=item_id), status_code=303)
