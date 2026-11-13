"""Схема БД: init_db, WAL, миграции со старых версий, сидирование счётчиков."""

import os
import sqlite3

import config
import database as db


def test_init_db_creates_tables_and_is_idempotent(db_path):
    db.init_db()  # повторный вызов не должен падать и ничего терять
    with sqlite3.connect(config.DB_PATH) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"inventory", "counters"} <= tables
    assert "user_states" not in tables, "фаза 2: мёртвая таблица user_states удалена"


def test_wal_mode_enabled(db_path):
    """WAL обязателен: бот и веб-панель пишут в одну БД из двух процессов."""
    with sqlite3.connect(config.DB_PATH) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_ping(db_path):
    assert db.ping() is True


def test_ping_failed_on_broken_db(db_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", "/nonexistent_dir_xyz/inventory.db")
    assert db.ping() is False


def test_legacy_database_is_migrated(db_path, monkeypatch):
    """Старая схема (без tech_type/pc_name/mac_*/specs/arm_id) мигрирует,
    данные сохраняются, мёртвая user_states удаляется."""
    # Подменяем БД «доюнитовской» версии с данными
    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    os.unlink(db_path)
    legacy = sqlite3.connect(db_path)
    legacy.execute("""
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clinic TEXT NOT NULL, cabinet TEXT, tech TEXT, serial TEXT,
            inv_number TEXT, ip TEXT, mac TEXT, os TEXT, office TEXT,
            drweb TEXT, note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    legacy.execute(
        "INSERT INTO inventory (clinic, cabinet, tech, inv_number, ip, os, drweb) "
        "VALUES ('1пл', '101', 'Dell 3070', 'INV-OLD', '10.0.0.1', 'Windows 10 x64', 'нет лиц')"
    )
    legacy.execute("CREATE TABLE user_states (user_id INTEGER, state TEXT)")
    legacy.execute("INSERT INTO user_states VALUES (1, 'stale')")
    legacy.commit()
    legacy.close()

    db.init_db()  # миграция

    item = db.find_by_inv("INV-OLD")
    assert item is not None, "данные старой записи должны сохраниться"
    assert item["tech"] == "Dell 3070"
    assert item["cabinet"] == "101"
    assert item["ip"] == "10.0.0.1"
    assert item["drweb"] == "нет лиц"  # значение не переписывается миграцией
    # Новые колонки добавлены с пустыми значениями по умолчанию
    assert item["tech_type"] == "" and item["pc_name"] == ""

    with sqlite3.connect(config.DB_PATH) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "user_states" not in tables


def test_counter_seeded_from_legacy_arm_ids(db_path, monkeypatch):
    """БД эпохи «MAX(arm_id)+1» (есть arm_id, нет counters) — счётчик
    сеется текущим максимумом, новые id продолжают нумерацию."""
    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    os.unlink(db_path)
    legacy = sqlite3.connect(db_path)
    legacy.execute("""
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clinic TEXT NOT NULL, cabinet TEXT, tech TEXT, serial TEXT,
            inv_number TEXT, ip TEXT, mac TEXT, os TEXT, office TEXT,
            drweb TEXT, note TEXT, tech_type TEXT DEFAULT '',
            pc_name TEXT DEFAULT '', mac_phys TEXT DEFAULT '',
            mac_real TEXT DEFAULT '', specs TEXT DEFAULT '',
            arm_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    legacy.execute(
        "INSERT INTO inventory (clinic, tech, inv_number, arm_id) VALUES ('1пл', 'PC', 'INV-1', 5)"
    )
    legacy.commit()
    legacy.close()

    db.init_db()
    assert db.next_arm_id() == 6, "нумерация продолжается с максимума старой БД"


def test_counter_self_healing_when_behind(db_path):
    """Счётчик отстал от MAX(arm_id) (БД правили вручную) — берём максимум."""
    item_id = db.save_item("1пл", {"tech": "PC", "inv": "X1", "arm_id": 5})
    assert item_id > 0
    with db.connect() as conn:  # намеренно портим счётчик
        conn.execute("UPDATE counters SET value = 1 WHERE name = 'arm_id'")
        conn.commit()
    assert db.next_arm_id() == 6, "max(счётчик, MAX(arm_id)) + 1"
