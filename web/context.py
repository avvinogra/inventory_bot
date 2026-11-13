"""Общий контекст веб-панели: шаблоны, каталоги, константы страниц."""

import os
from contextlib import contextmanager

from fastapi import Request
from fastapi.templating import Jinja2Templates

import config
import database as db
from bot_core.constants import (
    DRWEB_DB_VALUES,
    OS_UI_VALUES,
    TECH_TYPE_LABELS,
    display_drweb,
)
from web.security import _get_csrf_token, is_authenticated

# Каталоги относительно КОРНЯ проекта (web/ лежит на уровень ниже)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
# Jinja2 фильтр для нормализации значений Dr.Web (без эмодзи).
# Единая реализация — bot_core.constants.display_drweb (используется и ботом).
# Раньше здесь была локальная копия с .lower(): значения нового формата
# («Установлен») не находились в словаре и показывались с маленькой буквы.
templates.env.filters["drweb_display"] = display_drweb

# Категории аудита для веб-интерфейса: (ключ, заголовок, описание).
# Ключи обязаны совпадать с ветками database.audit._problematic_where —
# семантика категорий определена в слое БД, здесь только представление.
AUDIT_CATEGORIES = [
    ("no_pc_name", "Без имени компьютера", "ПК / ноутбук / принтер без имени компьютера"),
    ("no_ip", "Без IP-адреса", "ПК / ноутбук / принтер без IP-адреса"),
    ("no_mac", "Без MAC-адресов", "ПК / ноутбук / принтер без физических и реальных MAC-адресов"),
    (
        "drweb_problem",
        "Dr.Web: проблема",
        "Dr.Web: «Нет лицензии» или «Нет соединения» (включая старые «нет лиц»/«нет соед»)",
    ),
    ("mac_mismatch", "Физ. MAC ≠ Реал. MAC", "Физический MAC ≠ Реальный MAC (оба заполнены)"),
    ("no_specs", "Без характеристик", "ПК / ноутбук без поля «Характеристики»"),
]


@contextmanager
def get_db_connection():
    """Подключение через database.connect() — единая точка
    с WAL + busy_timeout (бот и веб-панель пишут в одну БД из двух процессов)."""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _recent_items(limit: int = 500):
    """Последние записи — для формы создания АРМ."""
    with get_db_connection() as conn:
        return conn.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def _base_context(request: Request) -> dict:
    """Контекст, доступный всем шаблонам."""
    return {
        "request": request,
        "authed": is_authenticated(request),
        "needs_password": bool(config.WEB_PANEL_PASSWORD),
        "csrf_token": _get_csrf_token(request),
        # Глобальные данные для всех шаблонов
        "CLINICS": config.CLINICS,
        "TECH_TYPE_LABELS": TECH_TYPE_LABELS,
        "AUDIT_CATEGORIES": AUDIT_CATEGORIES,
        # Значения для селектов формы редактирования
        # (раньше эти списки были захардкожены в item_detail.html)
        "DRWEB_DB_VALUES": DRWEB_DB_VALUES,
        "OS_UI_VALUES": OS_UI_VALUES,
    }
