"""Подключение к SQLite — единая точка для бота и веб-панели.

Оба процесса (bot.py и web_app.py) работают с одной БД-файлом, поэтому
все настройки соединения (WAL, busy_timeout, row_factory) живут здесь
один раз — раньше их копировали в каждом модуле.
"""

import sqlite3
from contextlib import contextmanager

import config

# Сколько секунд SQLite ждёт освобождения блокировки записи,
# прежде чем бросить "database is locked".
BUSY_TIMEOUT_SECONDS = 30


def connect() -> sqlite3.Connection:
    """Создаёт настроенное подключение к БД.

    - timeout / PRAGMA busy_timeout — при гонке двух писателей ждём,
      а не падаем сразу с "database is locked";
    - PRAGMA journal_mode = WAL — бот и веб-панель работают с одной БД
      из двух процессов: WAL разрешает параллельные чтения во время записи;
    - PRAGMA synchronous = NORMAL — безопасно в связке с WAL
      и заметно быстрее FULL.
    """
    conn = sqlite3.connect(config.DB_PATH, timeout=BUSY_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_SECONDS * 1000}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def get_db():
    """Контекстный менеджер для подключения к БД"""
    conn = None
    try:
        conn = connect()
        yield conn
    except sqlite3.Error as e:
        print(f"❌ Ошибка БД: {e}")
        raise
    finally:
        if conn:
            conn.close()


def ping() -> bool:
    """Проверка доступности БД (для healthcheck веб-панели)."""
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
