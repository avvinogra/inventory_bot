"""Аудиторские фильтры — поиск проблемных записей.

Каждая функция возвращает записи с указанной проблемой.
Фильтрация по типу техники: для сетевых полей (IP, MAC, имя ПК)
имеет смысл проверять только у устройств, у которых эти поля есть
(системный блок, ноутбук, принтер). Монитор без IP — это нормально.
Характеристики есть только у ПК и ноутбуков.
"""

import sqlite3

from bot_core.constants import DRWEB_PROBLEM_VALUES
from database.connection import get_db

_NETWORKED_TYPES = ("pc", "laptop")  # у ПК и ноутбуков есть IP/MAC/имя ПК
_SPECS_TYPES = ("pc", "laptop")  # у них есть характеристики


def _placeholders_for(values):
    """Возвращает строку вида '?,?,?' для использования в SQL IN."""
    return ",".join("?" * len(values))


def _problematic_where(category: str):
    """Условие WHERE для категории аудита — единый источник логики.

    Возвращает (sql_условие, параметры) или None для неизвестной категории.
    Используется и find_problematic_items (выборка строк),
    и count_problematic_items (COUNT(*)) — условие всегда синхронно.
    """
    if category == "no_pc_name":
        return (
            f"tech_type IN ({_placeholders_for(_NETWORKED_TYPES)}) "
            "AND (pc_name IS NULL OR pc_name = '')",
            _NETWORKED_TYPES,
        )
    if category == "no_ip":
        return (
            f"tech_type IN ({_placeholders_for(_NETWORKED_TYPES)}) AND (ip IS NULL OR ip = '')",
            _NETWORKED_TYPES,
        )
    if category == "no_mac":
        return (
            f"tech_type IN ({_placeholders_for(_NETWORKED_TYPES)}) "
            "AND (mac_phys IS NULL OR mac_phys = '') "
            "AND (mac_real IS NULL OR mac_real = '') "
            "AND (mac IS NULL OR mac = '')",
            _NETWORKED_TYPES,
        )
    if category == "drweb_problem":
        # Список значений — из bot_core.constants.DRWEB_PROBLEM_VALUES
        # (раньше дублировался здесь и в описаниях категорий веб-панели)
        return (
            f"drweb IN ({_placeholders_for(DRWEB_PROBLEM_VALUES)})",
            DRWEB_PROBLEM_VALUES,
        )
    if category == "mac_mismatch":
        return (
            "mac_phys IS NOT NULL AND mac_phys != '' "
            "AND mac_real IS NOT NULL AND mac_real != '' "
            "AND LOWER(mac_phys) != LOWER(mac_real)",
            (),
        )
    if category == "no_specs":
        return (
            f"tech_type IN ({_placeholders_for(_SPECS_TYPES)}) AND (specs IS NULL OR specs = '')",
            _SPECS_TYPES,
        )
    return None


def find_problematic_items(category: str, limit: int = 200) -> list[dict]:
    """Возвращает записи с указанной проблемой.

    Категории:
        - 'no_pc_name'      — нет имени компьютера (только ПК/ноутбук)
        - 'no_ip'           — нет IP-адреса (только ПК/ноутбук)
        - 'no_mac'          — нет ни физ. ни реал. MAC (только ПК/ноутбук)
        - 'drweb_problem'   — Dr.Web: «Нет лицензии» или «Нет соединения»
                              (включая старые значения «нет лиц»/«нет соед»)
        - 'mac_mismatch'    — физ. MAC ≠ реал. MAC (оба заполнены)
        - 'no_specs'        — нет характеристик (только ПК/ноутбук)
    """
    where = _problematic_where(category)
    if where is None:
        return []
    cond, params = where
    try:
        with get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM inventory WHERE {cond} ORDER BY id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка аудиторского фильтра «{category}»: {e}")
        return []


def count_problematic_items(category: str) -> int:
    """Количество записей с проблемой — через COUNT(*) на стороне БД.

    Раньше вызывающий код делал len(find_problematic_items(limit=500)):
    тянул до 500 полных строк ради одного числа И показывал «500»
    при большем количестве проблемных записей.
    """
    where = _problematic_where(category)
    if where is None:
        return 0
    cond, params = where
    try:
        with get_db() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM inventory WHERE {cond}", params).fetchone()
            return row[0]
    except sqlite3.Error as e:
        print(f"❌ Ошибка подсчёта аудиторского фильтра «{category}»: {e}")
        return 0
