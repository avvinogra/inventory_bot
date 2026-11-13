"""АРМ (автоматизированное рабочее место).

АРМ — это группа записей (системный блок + монитор + принтер),
которые физически находятся в одном кабинете.
Записи объединяются через поле arm_id (INTEGER, NULL = не в АРМ).
"""

import sqlite3

from database.connection import get_db


def _allocate_arm_id(conn: sqlite3.Connection) -> int:
    """Выделяет следующий arm_id ВНУТРИ транзакции вызывающего.

    Требование: вызывающий уже взял блокировку записи (BEGIN IMMEDIATE),
    поэтому два процесса не могут получить одинаковый id.

    Самовосстановление: если счётчик отстал от реального MAX(arm_id)
    (например, БД правили вручную), берём максимум из обоих значений.
    """
    row = conn.execute("SELECT value FROM counters WHERE name = 'arm_id'").fetchone()
    counter_val = row["value"] if row else 0
    max_used = conn.execute("SELECT COALESCE(MAX(arm_id), 0) FROM inventory").fetchone()[0]
    next_val = max(counter_val, max_used) + 1
    conn.execute(
        "INSERT INTO counters (name, value) VALUES ('arm_id', ?) "
        "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
        (next_val,),
    )
    return next_val


def next_arm_id() -> int:
    """Атомарно выделяет новый arm_id.

    Раньше: SELECT MAX(arm_id)+1 отдельным запросом — при одновременном
    создании АРМ в боте и веб-панели оба процесса получали одинаковый id
    (гонка). Теперь: BEGIN IMMEDIATE + счётчик в таблице counters —
    выделение атомарно на уровне БД.

    ⚠️ Выделенный id «сгорает», если пользователь отменил создание АРМ —
    это нормально: уникальность важнее непрерывности нумерации.
    """
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        new_id = _allocate_arm_id(conn)
        conn.commit()
        return new_id


def create_arm(item_ids: list) -> int:
    """Создаёт новый АРМ из списка записей.
    Атомарно выделяет arm_id и присваивает его всем записям одной транзакцией.

    Возвращает созданный arm_id.
    Бросает ValueError (пустой список) или sqlite3.Error (ошибка БД) —
    вызывающий код обязан обработать (раньше молча возвращался -1).
    """
    if not item_ids:
        raise ValueError("Для создания АРМ нужна хотя бы одна запись")
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        new_arm_id = _allocate_arm_id(conn)
        # Присваиваем arm_id всем указанным записям — одной транзакцией
        for item_id in item_ids:
            conn.execute("UPDATE inventory SET arm_id = ? WHERE id = ?", (new_arm_id, item_id))
        conn.commit()
        print(f"✅ Создан АРМ #{new_arm_id} из {len(item_ids)} записей")
        return new_arm_id


def get_arm_items(arm_id: int) -> list[dict]:
    """Возвращает все записи, входящие в указанный АРМ."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM inventory WHERE arm_id = ? ORDER BY id", (arm_id,)
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения АРМ: {e}")
        return []


def get_all_arms() -> list[dict]:
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
            conn.execute("UPDATE inventory SET arm_id = ? WHERE id = ?", (arm_id, item_id))
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as e:
        print(f"❌ Ошибка добавления в АРМ: {e}")
        return False


def remove_from_arm(item_id: int) -> bool:
    """Убирает запись из АРМ (arm_id = NULL)."""
    try:
        with get_db() as conn:
            conn.execute("UPDATE inventory SET arm_id = NULL WHERE id = ?", (item_id,))
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as e:
        print(f"❌ Ошибка удаления из АРМ: {e}")
        return False


def delete_arm(arm_id: int) -> bool:
    """Расформирует АРМ — убирает arm_id у всех записей."""
    try:
        with get_db() as conn:
            conn.execute("UPDATE inventory SET arm_id = NULL WHERE arm_id = ?", (arm_id,))
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as e:
        print(f"❌ Ошибка расформирования АРМ: {e}")
        return False


def get_items_without_arm(clinic: str | None = None, limit: int = 50) -> list[dict]:
    """Возвращает записи, не входящие ни в один АРМ."""
    try:
        with get_db() as conn:
            if clinic:
                rows = conn.execute(
                    "SELECT * FROM inventory WHERE arm_id IS NULL AND clinic = ? ORDER BY id DESC LIMIT ?",
                    (clinic, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM inventory WHERE arm_id IS NULL ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"❌ Ошибка получения записей без АРМ: {e}")
        return []
