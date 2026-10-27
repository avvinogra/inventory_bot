import sqlite3
import json
import os
from contextlib import contextmanager
from typing import Optional, Dict, List
import config

# ✅ УБРАЛИ дублирование CLINICS. Используем из config.py
# Если нужно, можно импортировать: from config import CLINICS

# Список всех "пользовательских" полей инвентаризации (без id/clinic/created_at).
# Должен совпадать с bot_core/constants.py → INVENTORY_FIELDS
INVENTORY_FIELDS_DB = [
    "cabinet", "tech_type", "tech", "serial", "inv_number",
    "os", "drweb", "ip", "pc_name", "mac_phys", "mac_real",
    "specs", "note",
]

# Старые поля (для совместимости со старой схемой БД).
# Не показываем в UI, но сохраняем столбцы, чтобы не потерять данные старых записей.
LEGACY_FIELDS_DB = ["mac", "office"]

""""============================================
КОНТЕКСТНЫЙ МЕНЕДЖЕР ДЛЯ ПОДКЛЮЧЕНИЯ К БД
============================================"""
@contextmanager
def get_db():
    """Контекстный менеджер для подключения к БД"""
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        print(f"❌ Ошибка БД: {e}")
        raise
    finally:
        if conn:
            conn.close()

""""============================================
ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
============================================"""
def _get_existing_columns(conn) -> set:
    rows = conn.execute("PRAGMA table_info(inventory)").fetchall()
    return {row["name"] for row in rows}


def init_db():
    """Создание всех необходимых таблиц + миграция схемы при необходимости"""
    try:
        with get_db() as conn:
            # Таблица инвентаризации
            conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clinic TEXT NOT NULL,
                cabinet TEXT,
                tech TEXT,
                serial TEXT,
                inv_number TEXT,
                ip TEXT,
                mac TEXT,
                os TEXT,
                office TEXT,
                drweb TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # ---- МИГРАЦИЯ: добавляем новые поля, если их ещё нет ----
            existing = _get_existing_columns(conn)
            migrations = {
                "tech_type": "TEXT DEFAULT ''",
                "pc_name":  "TEXT DEFAULT ''",
                "mac_phys": "TEXT DEFAULT ''",
                "mac_real": "TEXT DEFAULT ''",
                "specs":    "TEXT DEFAULT ''",
                "arm_id":   "INTEGER DEFAULT NULL",
            }
            for col, decl in migrations.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE inventory ADD COLUMN {col} {decl}")
                    print(f"➕ Добавлено поле: {col}")

            # Таблица состояний пользователей
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_states (
                    chat_id INTEGER PRIMARY KEY,
                    state TEXT DEFAULT 'idle',
                    data TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Индексы для быстрого поиска
            conn.execute("CREATE INDEX IF NOT EXISTS idx_serial ON inventory(serial)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inv ON inventory(inv_number)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clinic ON inventory(clinic)")

            conn.commit()
            print("✅ База данных инициализирована")

            # Права на файл БД: только владелец читает/пишет (chmod 600).
            # На Windows это noop (нет chmod как на Unix), но и не вредит.
            try:
                os.chmod(config.DB_PATH, 0o600)
            except (OSError, PermissionError):
                pass  # На Windows или при отсутствии прав — игнорируем
    except sqlite3.Error as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        raise

"""============================================
ФУНКЦИИ ДЛЯ РАБОТЫ С ИНВЕНТАРИЗАЦИЕЙ
============================================"""
def get_db_stats() -> dict:
    """Статистика по базе данных"""
    try:
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
            clinics = conn.execute(
                "SELECT clinic, COUNT(*) as count FROM inventory GROUP BY clinic ORDER BY count DESC"
            ).fetchall()
            recent = conn.execute(
                "SELECT COUNT(*) FROM inventory WHERE created_at >= datetime('now', '-1 day')"
            ).fetchone()[0]

            return {
                'total_items': total,
                'by_clinic': {row['clinic']: row['count'] for row in clinics},
                'added_today': recent
            }
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения статистики: {e}")
        return {'total_items': 0, 'by_clinic': {}, 'added_today': 0}


def save_item(clinic: str, data: dict) -> int:
    """Сохранение записи об оборудовании.

    Принимает state-data, в котором поля названы короткими ключами
    (cabinet, tech, serial, inv, ip, mac_phys, mac_real, os, drweb,
    pc_name, specs, note, tech_type). Делаем маппинг на колонки БД.
    """
    try:
        with get_db() as conn:
            cursor = conn.execute("""
            INSERT INTO inventory
                (clinic, cabinet, tech_type, tech, serial, inv_number,
                 os, drweb, ip, pc_name, mac_phys, mac_real, specs, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                clinic,
                data.get('cabinet', ''),
                data.get('tech_type', ''),
                data.get('tech', ''),
                data.get('serial', ''),
                data.get('inv', ''),
                data.get('os', ''),
                data.get('drweb', ''),
                data.get('ip', ''),
                data.get('pc_name', ''),
                data.get('mac_phys', ''),
                data.get('mac_real', ''),
                data.get('specs', ''),
                data.get('note', ''),
            ))
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"❌ Ошибка сохранения: {e}")
        return -1


def get_all_items(clinic: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
    """Получение записей (с пагинацией offset)"""
    try:
        with get_db() as conn:
            if clinic:
                query = (
                    "SELECT * FROM inventory WHERE clinic = ? "
                    "ORDER BY id DESC LIMIT ? OFFSET ?"
                )
                params = (clinic, limit, offset)
            else:
                query = "SELECT * FROM inventory ORDER BY id DESC LIMIT ? OFFSET ?"
                params = (limit, offset)
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения записей: {e}")
        return []


def get_item_by_id(item_id: int) -> Optional[Dict]:
    """Получение записи по ID"""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE id = ? LIMIT 1",
                (item_id,)
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения записи: {e}")
        return None


def find_by_serial(serial: str) -> Optional[Dict]:
    """Поиск по серийному номеру"""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE LOWER(serial) = LOWER(?) LIMIT 1",
                (serial.strip(),)
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска по серийному номеру: {e}")
        return None


def find_by_inv(inv_number: str, clinic: str = None) -> Optional[Dict]:
    """Поиск по инвентарному номеру"""
    try:
        with get_db() as conn:
            query = "SELECT * FROM inventory WHERE inv_number = ?"
            params = [inv_number.strip()]
            if clinic:
                query += " AND clinic = ?"
                params.append(clinic)
            query += " LIMIT 1"
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска по инв. номеру: {e}")
        return None


def find_by_pc_name(pc_name: str) -> Optional[Dict]:
    """Поиск по имени ПК"""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE LOWER(pc_name) = LOWER(?) LIMIT 1",
                (pc_name.strip(),)
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска по имени ПК: {e}")
        return None


def get_last_item(clinic: str = None) -> Optional[Dict]:
    """Последняя добавленная запись"""
    try:
        with get_db() as conn:
            if clinic:
                row = conn.execute(
                    "SELECT * FROM inventory WHERE clinic = ? ORDER BY id DESC LIMIT 1",
                    (clinic,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM inventory ORDER BY id DESC LIMIT 1"
                ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения последней записи: {e}")
        return None


# ============================================================
# ПОИСК ДУБЛИКАТОВ
# ============================================================
# ВАЖНО: в организации один инвентарный номер выдаётся на АРМ
# (монитор + системный блок + принтер под одним инв. номером — это нормально).
# Поэтому дубли по inv_number — НЕ ошибка, просто информируем пользователя.
# А вот дубли по serial и pc_name — это почти всегда ошибка (серийник уникален
# у производителя, имя ПК должно быть уникальным в сети).
# Все функции принимают exclude_id — чтобы при редактировании существующей
# записи не считать её саму дубликатом.
# ============================================================

def find_duplicates_by_inv(inv_number: str, exclude_id: int = None) -> List[Dict]:
    """Возвращает все записи с таким же инвентарным номером.
    Нормальная ситуация — это АРМ (несколько устройств под одним номером).
    Игнорирует значения «Отсутствует» / «нет» / пустые.
    """
    if not inv_number:
        return []
    if inv_number.strip().lower() in ("отсутствует", "нет", "без номера", "—", "-", ""):
        return []
    try:
        with get_db() as conn:
            if exclude_id:
                query = (
                    "SELECT * FROM inventory WHERE inv_number = ? AND id != ? "
                    "ORDER BY id DESC"
                )
                rows = conn.execute(query, (inv_number.strip(), exclude_id)).fetchall()
            else:
                query = "SELECT * FROM inventory WHERE inv_number = ? ORDER BY id DESC"
                rows = conn.execute(query, (inv_number.strip(),)).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска дубликатов по инв. номеру: {e}")
        return []


def find_duplicates_by_serial(serial: str, exclude_id: int = None) -> List[Dict]:
    """Возвращает записи с таким же серийным номером.
    Серийный номер должен быть уникальным — дубли почти всегда ошибка.
    Игнорирует значения «Отсутствует» / «нет» / пустые.
    """
    if not serial:
        return []
    if serial.strip().lower() in ("отсутствует", "нет", "без номера", "—", "-", ""):
        return []
    try:
        with get_db() as conn:
            if exclude_id:
                query = (
                    "SELECT * FROM inventory WHERE LOWER(serial) = LOWER(?) AND id != ? "
                    "ORDER BY id DESC"
                )
                rows = conn.execute(query, (serial.strip(), exclude_id)).fetchall()
            else:
                query = "SELECT * FROM inventory WHERE LOWER(serial) = LOWER(?) ORDER BY id DESC"
                rows = conn.execute(query, (serial.strip(),)).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска дубликатов по серийному номеру: {e}")
        return []


def find_duplicates_by_pc_name(pc_name: str, exclude_id: int = None) -> List[Dict]:
    """Возвращает записи с таким же именем компьютера.
    Имя ПК должно быть уникальным в сети — дубли почти всегда ошибка.
    """
    if not pc_name:
        return []
    try:
        with get_db() as conn:
            if exclude_id:
                query = (
                    "SELECT * FROM inventory WHERE LOWER(pc_name) = LOWER(?) AND id != ? "
                    "ORDER BY id DESC"
                )
                rows = conn.execute(query, (pc_name.strip(), exclude_id)).fetchall()
            else:
                query = "SELECT * FROM inventory WHERE LOWER(pc_name) = LOWER(?) ORDER BY id DESC"
                rows = conn.execute(query, (pc_name.strip(),)).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска дубликатов по имени компьютера: {e}")
        return []


# ============================================================
# ГЛОБАЛЬНЫЙ ПОИСК
# ============================================================
# Один запрос — поиск по нескольким полям одновременно:
# инвентарный номер, серийный, имя ПК, марка/модель, кабинет,
# характеристики, примечание.
# Используется для быстрого поиска записи без указания поля.
# ============================================================
def global_search(query: str, limit: int = 50) -> List[Dict]:
    """Глобальный поиск: частичное совпадение по нескольким полям."""
    if not query:
        return []
    q = f"%{query.strip()}%"
    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM inventory
                WHERE
                    inv_number LIKE ? OR
                    serial LIKE ? OR
                    pc_name LIKE ? OR
                    tech LIKE ? OR
                    cabinet LIKE ? OR
                    specs LIKE ? OR
                    note LIKE ? OR
                    os LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (q, q, q, q, q, q, q, q, limit)
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка глобального поиска: {e}")
        return []


# ============================================================
# АУДИТОРСКИЕ ФИЛЬТРЫ — поиск проблемных записей
# ============================================================
# Каждая функция возвращает записи с указанной проблемой.
# Фильтрация по типу техники: для сетевых полей (IP, MAC, имя ПК)
# имеет смысл проверять только у устройств, у которых эти поля есть
# (системный блок, ноутбук, принтер). Монитор без IP — это нормально.
# Характеристики есть только у ПК и ноутбуков.
# ============================================================
_NETWORKED_TYPES = ("pc", "laptop")  # у ПК и ноутбуков есть IP/MAC/имя ПК
_SPECS_TYPES = ("pc", "laptop")                  # у них есть характеристики


def _placeholders_for(values):
    """Возвращает строку вида '?,?,?' для использования в SQL IN."""
    return ",".join("?" * len(values))


def find_problematic_items(category: str, limit: int = 200) -> List[Dict]:
    """Возвращает записи с указанной проблемой.

    Категории:
        - 'no_pc_name'      — нет имени компьютера (только ПК/ноутбук/принтер)
        - 'no_ip'           — нет IP-адреса (только ПК/ноутбук/принтер)
        - 'no_mac'          — нет ни физ. ни реал. MAC (только ПК/ноутбук/принтер)
        - 'drweb_problem'   — Dr.Web: «Нет лицензии» или «Нет соединения»
                              (включая старые значения «нет лиц»/«нет соед»)
        - 'mac_mismatch'    — физ. MAC ≠ реал. MAC (оба заполнены)
        - 'no_specs'        — нет характеристик (только ПК/ноутбук)
    """
    if not category:
        return []
    try:
        with get_db() as conn:
            if category == "no_pc_name":
                rows = conn.execute(
                    f"""
                    SELECT * FROM inventory
                    WHERE tech_type IN ({_placeholders_for(_NETWORKED_TYPES)})
                      AND (pc_name IS NULL OR pc_name = '')
                    ORDER BY id DESC LIMIT ?
                    """,
                    (*_NETWORKED_TYPES, limit)
                ).fetchall()
            elif category == "no_ip":
                rows = conn.execute(
                    f"""
                    SELECT * FROM inventory
                    WHERE tech_type IN ({_placeholders_for(_NETWORKED_TYPES)})
                      AND (ip IS NULL OR ip = '')
                    ORDER BY id DESC LIMIT ?
                    """,
                    (*_NETWORKED_TYPES, limit)
                ).fetchall()
            elif category == "no_mac":
                rows = conn.execute(
                    f"""
                    SELECT * FROM inventory
                    WHERE tech_type IN ({_placeholders_for(_NETWORKED_TYPES)})
                      AND (mac_phys IS NULL OR mac_phys = '')
                      AND (mac_real IS NULL OR mac_real = '')
                      AND (mac IS NULL OR mac = '')
                    ORDER BY id DESC LIMIT ?
                    """,
                    (*_NETWORKED_TYPES, limit)
                ).fetchall()
            elif category == "drweb_problem":
                rows = conn.execute(
                    """
                    SELECT * FROM inventory
                    WHERE drweb IN (?, ?, ?, ?)
                    ORDER BY id DESC LIMIT ?
                    """,
                    ('Нет лицензии', 'Нет соединения с сервером',
                     'нет лиц', 'нет соед', limit)
                ).fetchall()
            elif category == "mac_mismatch":
                rows = conn.execute(
                    """
                    SELECT * FROM inventory
                    WHERE mac_phys IS NOT NULL AND mac_phys != ''
                      AND mac_real IS NOT NULL AND mac_real != ''
                      AND LOWER(mac_phys) != LOWER(mac_real)
                    ORDER BY id DESC LIMIT ?
                    """,
                    (limit,)
                ).fetchall()
            elif category == "no_specs":
                rows = conn.execute(
                    f"""
                    SELECT * FROM inventory
                    WHERE tech_type IN ({_placeholders_for(_SPECS_TYPES)})
                      AND (specs IS NULL OR specs = '')
                    ORDER BY id DESC LIMIT ?
                    """,
                    (*_SPECS_TYPES, limit)
                ).fetchall()
            else:
                return []
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка аудиторского фильтра «{category}»: {e}")
        return []


def update_item(item_id: int, field: str, value: str) -> bool:
    """Обновление одного поля записи (защита от SQL Injection через whitelist).

    Принимает короткие имена полей (как в state) и автоматически мапит
    их на имена колонок БД.
    """
    # Маппинг "state-ключ" → "колонка БД"
    field_to_column = {
        "cabinet":   "cabinet",
        "tech_type": "tech_type",
        "tech":      "tech",
        "serial":    "serial",
        "inv":       "inv_number",
        "os":        "os",
        "drweb":     "drweb",
        "ip":        "ip",
        "pc_name":   "pc_name",
        "mac_phys":  "mac_phys",
        "mac_real":  "mac_real",
        "specs":     "specs",
        "note":      "note",
        # legacy:
        "mac":       "mac",
        "office":    "office",
        # прямой доступ по имени колонки тоже разрешён:
        "inv_number": "inv_number",
    }

    column = field_to_column.get(field)
    if column is None:
        # Разрешаем только буквенные идентификаторы из whitelist
        if not field.isidentifier() or field not in field_to_column.values():
            print(f"⚠️ Попытка обновления недопустимого поля: {field}")
            return False
        column = field

    try:
        with get_db() as conn:
            conn.execute(
                f"UPDATE inventory SET {column} = ? WHERE id = ?",
                (value, item_id)
            )
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as e:
        print(f"❌ Ошибка обновления: {e}")
        return False


def delete_item(item_id: int) -> bool:
    """Удаление записи по ID"""
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as e:
        print(f"❌ Ошибка удаления: {e}")
        return False


# ============================================================
# АРМ (АВТОМАТИЗИРОВАННОЕ РАБОЧЕЕ МЕСТО)
# ============================================================
# АРМ — это группа записей (системный блок + монитор + принтер),
# которые физически находятся в одном кабинете.
# Записи объединяются через поле arm_id (INTEGER, NULL = не в АРМ).
# ============================================================

def create_arm(item_ids: list) -> int:
    """Создаёт новый АРМ из списка записей.
    Генерирует уникальный arm_id и присваивает всем указанным записям.
    Возвращает созданный arm_id или -1 при ошибке.
    """
    if not item_ids or len(item_ids) < 1:
        return -1
    try:
        with get_db() as conn:
            # Находим максимальный arm_id
            max_arm = conn.execute(
                "SELECT MAX(arm_id) FROM inventory"
            ).fetchone()[0]
            new_arm_id = (max_arm or 0) + 1

            # Присваиваем arm_id всем указанным записям
            for item_id in item_ids:
                conn.execute(
                    "UPDATE inventory SET arm_id = ? WHERE id = ?",
                    (new_arm_id, item_id)
                )
            conn.commit()
            print(f"✅ Создан АРМ #{new_arm_id} из {len(item_ids)} записей")
            return new_arm_id
    except sqlite3.Error as e:
        print(f"❌ Ошибка создания АРМ: {e}")
        return -1


def get_arm_items(arm_id: int) -> List[Dict]:
    """Возвращает все записи, входящие в указанный АРМ."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM inventory WHERE arm_id = ? ORDER BY id",
                (arm_id,)
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения АРМ: {e}")
        return []


def get_all_arms() -> List[Dict]:
    """Возвращает список всех АРМ с количеством записей.
    Каждый элемент: {arm_id, count, clinic, cabinet}
    """
    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT
                    arm_id,
                    COUNT(*) as count,
                    MIN(clinic) as clinic,
                    MIN(cabinet) as cabinet
                FROM inventory
                WHERE arm_id IS NOT NULL
                GROUP BY arm_id
                ORDER BY arm_id
                """
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения списка АРМ: {e}")
        return []


def add_to_arm(item_id: int, arm_id: int) -> bool:
    """Добавляет запись в существующий АРМ."""
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE inventory SET arm_id = ? WHERE id = ?",
                (arm_id, item_id)
            )
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as e:
        print(f"❌ Ошибка добавления в АРМ: {e}")
        return False


def remove_from_arm(item_id: int) -> bool:
    """Убирает запись из АРМ (arm_id = NULL)."""
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE inventory SET arm_id = NULL WHERE id = ?",
                (item_id,)
            )
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as e:
        print(f"❌ Ошибка удаления из АРМ: {e}")
        return False


def delete_arm(arm_id: int) -> bool:
    """Расформирует АРМ — убирает arm_id у всех записей."""
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE inventory SET arm_id = NULL WHERE arm_id = ?",
                (arm_id,)
            )
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as e:
        print(f"❌ Ошибка расформирования АРМ: {e}")
        return False


def get_items_without_arm(clinic: str = None, limit: int = 50) -> List[Dict]:
    """Возвращает записи, не входящие ни в один АРМ."""
    try:
        with get_db() as conn:
            if clinic:
                rows = conn.execute(
                    "SELECT * FROM inventory WHERE arm_id IS NULL AND clinic = ? ORDER BY id DESC LIMIT ?",
                    (clinic, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM inventory WHERE arm_id IS NULL ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения записей без АРМ: {e}")
        return []

"""============================================
ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ СОСТОЯНИЯМИ
============================================"""
def set_user_state(chat_id: int, state: str, data: dict = None):
    """Установка состояния пользователя"""
    try:
        with get_db() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO user_states (chat_id, state, data, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (chat_id, state, json.dumps(data or {})))
            conn.commit()
    except (sqlite3.Error, TypeError) as e:
        print(f"❌ Ошибка установки состояния: {e}")


def clear_user_state(chat_id: int):
    """Очистка состояния пользователя"""
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM user_states WHERE chat_id = ?", (chat_id,))
            conn.commit()
    except sqlite3.Error as e:
        print(f"❌ Ошибка очистки состояния: {e}")

# ✅ ФУНКЦИЯ export_to_excel УДАЛЕНА ОТСЮДА.
# Используйте версию из excel_export.py для лучшего качества.
