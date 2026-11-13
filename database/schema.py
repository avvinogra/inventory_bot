"""Схема БД: создание таблиц, миграции, сидирование счётчиков."""

import os
import sqlite3

import config
from database.connection import get_db

# Список всех "пользовательских" полей инвентаризации (без id/clinic/created_at).
# Должен совпадать с bot_core/constants.py → INVENTORY_FIELDS
INVENTORY_FIELDS_DB = [
    "cabinet",
    "tech_type",
    "tech",
    "serial",
    "inv_number",
    "os",
    "drweb",
    "ip",
    "pc_name",
    "mac_phys",
    "mac_real",
    "specs",
    "note",
]

# Старые поля (для совместимости со старой схемой БД).
# Не показываем в UI, но сохраняем столбцы, чтобы не потерять данные старых записей.
LEGACY_FIELDS_DB = ["mac", "office"]


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
                "pc_name": "TEXT DEFAULT ''",
                "mac_phys": "TEXT DEFAULT ''",
                "mac_real": "TEXT DEFAULT ''",
                "specs": "TEXT DEFAULT ''",
                "arm_id": "INTEGER DEFAULT NULL",
            }
            for col, decl in migrations.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE inventory ADD COLUMN {col} {decl}")
                    print(f"➕ Добавлено поле: {col}")

            # ---- МИГРАЦИЯ (фаза 2): таблица user_states удалена ----
            # Она никогда не заполнялась (set_user_state не вызывался ни разу),
            # бот хранит состояния в aiogram FSM. Чистим старые БД.
            conn.execute("DROP TABLE IF EXISTS user_states")

            # Счётчики для атомарной выдачи идентификаторов (arm_id).
            # Счётчик живёт в БД, а не вычисляется как MAX(arm_id)+1 —
            # это устраняет гонку между ботом и веб-панелью.
            conn.execute("""
            CREATE TABLE IF NOT EXISTS counters (
                name  TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            )
            """)
            # Сидируем счётчик arm_id текущим максимумом (миграция старых БД).
            # ON CONFLICT DO NOTHING — не трогаем счётчик, если он уже есть.
            max_arm = conn.execute("SELECT COALESCE(MAX(arm_id), 0) FROM inventory").fetchone()[0]
            conn.execute(
                "INSERT INTO counters (name, value) VALUES ('arm_id', ?) "
                "ON CONFLICT(name) DO NOTHING",
                (max_arm,),
            )

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
