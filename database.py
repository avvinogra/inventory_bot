import sqlite3
import json
import os
from contextlib import contextmanager
from typing import Optional, Dict, List
import config

# ✅ УБРАЛИ дублирование CLINICS. Используем из config.py
# Если нужно, можно импортировать: from config import CLINICS

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
def init_db():
    """Создание всех необходимых таблиц"""
    try:
        with get_db() as conn:
            # Таблица инвентаризации
            conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clinic TEXT NOT NULL,
                cabinet TEXT,
                tech TEXT NOT NULL,
                serial TEXT NOT NULL,
                inv_number TEXT NOT NULL,
                ip TEXT,
                mac TEXT,
                os TEXT,
                office TEXT,
                drweb TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
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
    """Сохранение записи об оборудовании"""
    try:
        with get_db() as conn:
            cursor = conn.execute("""
            INSERT INTO inventory
            (clinic, cabinet, tech, serial, inv_number, ip, mac, os, office, drweb, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                clinic,
                data.get('cabinet', ''),
                data.get('tech', ''),
                data.get('serial', ''),
                data.get('inv', ''),
                data.get('ip', ''),
                data.get('mac', ''),
                data.get('os', ''),
                data.get('office', ''),  # ✅ ИСПРАВЛЕНО: было 'offi ce'
                data.get('drweb', ''),
                data.get('note', '')
            ))
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"❌ Ошибка сохранения: {e}")
        return -1

def get_all_items(clinic: str = None, limit: int = 100) -> List[Dict]:
    """Получение всех записей"""
    try:
        with get_db() as conn:
            if clinic:
                query = "SELECT * FROM inventory WHERE clinic = ? ORDER BY id DESC LIMIT ?"
                params = (clinic, limit)
            else:
                query = "SELECT * FROM inventory ORDER BY id DESC LIMIT ?"
                params = (limit,)
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

def update_item(item_id: int, field: str, value: str) -> bool:
    """Обновление поля в записи (защита от SQL Injection через whitelist)"""
    allowed_fields = [
        'cabinet', 'tech', 'serial', 'inv_number',
        'ip', 'mac', 'os', 'office', 'drweb', 'note'
    ]
    if not field.isidentifier() or field not in allowed_fields:
        print(f"⚠️ Попытка обновления недопустимого поля: {field}")
        return False

    try:
        with get_db() as conn:
            conn.execute(
                f"UPDATE inventory SET {field} = ? WHERE id = ?",
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