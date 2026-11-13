"""CRUD и поиск по записям инвентаризации."""

import sqlite3

from database.connection import get_db


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
                "total_items": total,
                "by_clinic": {row["clinic"]: row["count"] for row in clinics},
                "added_today": recent,
            }
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения статистики: {e}")
        return {"total_items": 0, "by_clinic": {}, "added_today": 0}


def save_item(clinic: str, data: dict) -> int:
    """Сохранение записи об оборудовании. Возвращает id новой записи.

    Принимает state-data, в котором поля названы короткими ключами
    (cabinet, tech, serial, inv, ip, mac_phys, mac_real, os, drweb,
    pc_name, specs, note, tech_type). Делаем маппинг на колонки БД.
    Если в data есть arm_id — сохраняем и его.

    При ошибке БРОСАЕТ sqlite3.Error — вызывающий код обязан обработать.
    Раньше возвращался -1, вызывающие не проверяли его, и пользователь
    видел «✅ Сохранено. ID: -1» при фактической потере данных.
    """
    with get_db() as conn:
        cursor = conn.execute(_INSERT_ITEM_SQL, _item_values(clinic, data))
        conn.commit()
        return cursor.lastrowid


# Один INSERT для save_item и save_items (раньше — две копии запроса).
_INSERT_ITEM_SQL = """
    INSERT INTO inventory
        (clinic, cabinet, tech_type, tech, serial, inv_number,
         os, drweb, ip, pc_name, mac_phys, mac_real, specs, note, arm_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _item_values(clinic: str, data: dict) -> tuple:
    """Маппинг коротких ключей state на значения колонок БД."""
    return (
        clinic,
        data.get("cabinet", ""),
        data.get("tech_type", ""),
        data.get("tech", ""),
        data.get("serial", ""),
        data.get("inv", ""),
        data.get("os", ""),
        data.get("drweb", ""),
        data.get("ip", ""),
        data.get("pc_name", ""),
        data.get("mac_phys", ""),
        data.get("mac_real", ""),
        data.get("specs", ""),
        data.get("note", ""),
        # None → NULL: запись вне АРМ
        data.get("arm_id") or None,
    )


def save_items(rows: list) -> list:
    """Массовое сохранение записей в ОДНОЙ транзакции (импорт из Excel).

    Аргумент: список пар (clinic, data) — формат как у save_item.
    Возвращает список результатов в том же порядке:
    (id_новой_записи | None, сообщение_об_ошибке | None).

    Зачем: импорт вызывал save_item в цикле — построчная транзакция
    (connect + commit + fsync) на каждую строку Excel. Тысяча строк —
    тысяча транзакций. Здесь всё выполняется на одном подключении
    и фиксируется одним commit'ом; неудачная строка не прерывает
    остальные (ошибка откатывает только свой INSERT).
    """
    if not rows:
        return []
    outcomes = []
    with get_db() as conn:
        for clinic, data in rows:
            try:
                cur = conn.execute(_INSERT_ITEM_SQL, _item_values(clinic, data))
                outcomes.append((cur.lastrowid, None))
            except sqlite3.Error as e:
                outcomes.append((None, str(e)))
        try:
            conn.commit()
        except sqlite3.Error as e:
            # Не соврали в отчёте: если commit не прошёл — ничего не сохранено
            return [(None, f"Ошибка фиксации транзакции: {e}") for _ in rows]
    return outcomes


def get_all_items(clinic: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """Получение записей (с пагинацией offset)"""
    try:
        with get_db() as conn:
            if clinic:
                query = "SELECT * FROM inventory WHERE clinic = ? ORDER BY id DESC LIMIT ? OFFSET ?"
                params = (clinic, limit, offset)
            else:
                query = "SELECT * FROM inventory ORDER BY id DESC LIMIT ? OFFSET ?"
                params = (limit, offset)
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения записей: {e}")
        return []


def get_item_by_id(item_id: int) -> dict | None:
    """Получение записи по ID"""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE id = ? LIMIT 1", (item_id,)
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения записи: {e}")
        return None


def find_by_serial(serial: str) -> dict | None:
    """Поиск по серийному номеру"""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE LOWER(serial) = LOWER(?) LIMIT 1", (serial.strip(),)
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска по серийному номеру: {e}")
        return None


def find_by_inv(inv_number: str, clinic: str | None = None) -> dict | None:
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


def find_by_pc_name(pc_name: str) -> dict | None:
    """Поиск по имени ПК"""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE LOWER(pc_name) = LOWER(?) LIMIT 1",
                (pc_name.strip(),),
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска по имени ПК: {e}")
        return None


def get_last_item(clinic: str | None = None) -> dict | None:
    """Последняя добавленная запись"""
    try:
        with get_db() as conn:
            if clinic:
                row = conn.execute(
                    "SELECT * FROM inventory WHERE clinic = ? ORDER BY id DESC LIMIT 1", (clinic,)
                ).fetchone()
            else:
                row = conn.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT 1").fetchone()
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


def find_duplicates_by_inv(inv_number: str, exclude_id: int | None = None) -> list[dict]:
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
                query = "SELECT * FROM inventory WHERE inv_number = ? AND id != ? ORDER BY id DESC"
                rows = conn.execute(query, (inv_number.strip(), exclude_id)).fetchall()
            else:
                query = "SELECT * FROM inventory WHERE inv_number = ? ORDER BY id DESC"
                rows = conn.execute(query, (inv_number.strip(),)).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка поиска дубликатов по инв. номеру: {e}")
        return []


def find_duplicates_by_serial(serial: str, exclude_id: int | None = None) -> list[dict]:
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


def find_duplicates_by_pc_name(pc_name: str, exclude_id: int | None = None) -> list[dict]:
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
def global_search(query: str, limit: int = 50) -> list[dict]:
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
                (q, q, q, q, q, q, q, q, limit),
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка глобального поиска: {e}")
        return []


def update_item(item_id: int, field: str, value: str) -> bool:
    """Обновление одного поля записи (защита от SQL Injection через whitelist).

    Принимает короткие имена полей (как в state) и автоматически мапит
    их на имена колонок БД.
    """
    # Маппинг "state-ключ" → "колонка БД"
    field_to_column = {
        "cabinet": "cabinet",
        "tech_type": "tech_type",
        "tech": "tech",
        "serial": "serial",
        "inv": "inv_number",
        "os": "os",
        "drweb": "drweb",
        "ip": "ip",
        "pc_name": "pc_name",
        "mac_phys": "mac_phys",
        "mac_real": "mac_real",
        "specs": "specs",
        "note": "note",
        # legacy:
        "mac": "mac",
        "office": "office",
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
            conn.execute(f"UPDATE inventory SET {column} = ? WHERE id = ?", (value, item_id))
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
