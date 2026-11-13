"""CRUD и поиск записей инвентаризации (database.items)."""

import sqlite3

import config
import database as db


def _save(**data) -> int:
    """Хелпер: сохранить запись в 1-й поликлинике."""
    return db.save_item("1пл", data)


# ============================================================
# СОХРАНЕНИЕ
# ============================================================
def test_save_item_returns_valid_id(db_path):
    item_id = _save(cabinet="101", tech="Dell OptiPlex", serial="SN1")
    assert isinstance(item_id, int) and item_id > 0


def test_save_item_roundtrip_fields(db_path):
    """Короткие ключи state маппятся на колонки БД (inv → inv_number и т.д.)."""
    item_id = _save(
        cabinet="101",
        tech="HP",
        tech_type="pc",
        serial="SN-9",
        inv="INV-9",
        os="Windows 10 x64",
        drweb="Установлен",
        ip="10.0.0.1",
        pc_name="PC-01",
        mac_phys="00:11:22:33:44:55",
        mac_real="00:11:22:33:44:55",
        specs="i5/16GB",
        note="тест",
    )
    item = db.get_item_by_id(item_id)
    assert item["inv_number"] == "INV-9"
    assert item["tech_type"] == "pc"
    assert item["ip"] == "10.0.0.1"
    assert item["mac_phys"] == "00:11:22:33:44:55"
    assert item["specs"] == "i5/16GB"
    assert item["arm_id"] is None


def test_save_item_with_arm_id(db_path):
    arm_id = db.next_arm_id()
    item_id = _save(cabinet="101", tech="HP", arm_id=arm_id)
    assert db.get_item_by_id(item_id)["arm_id"] == arm_id


def test_save_item_raises_on_db_error(db_path, monkeypatch):
    """Регрессия фазы 0: ошибка БД бросает исключение, а не возвращает -1."""
    monkeypatch.setattr(config, "DB_PATH", "/nonexistent_dir_xyz/inventory.db")
    try:
        db.save_item("1пл", {"tech": "X"})
    except sqlite3.Error:
        pass  # ожидаемое поведение
    else:
        raise AssertionError("save_item обязан бросать sqlite3.Error при сбое БД")


def test_save_items_batch(db_path):
    """Массовый INSERT: одна транзакция, порядок результатов сохраняется."""
    rows = [("2пл", {"cabinet": "10", "tech": "HP", "inv": f"B{i}"}) for i in range(50)]
    outcomes = db.save_items(rows)
    assert len(outcomes) == 50
    assert all(new_id is not None and err is None for new_id, err in outcomes)
    assert db.get_db_stats()["total_items"] == 50


def test_save_items_empty_list(db_path):
    assert db.save_items([]) == []


def test_save_items_row_error_does_not_break_batch(db_path):
    """Неудачная строка не прерывает пакет: (None, причина) на своём месте."""
    outcomes = db.save_items(
        [
            ("1пл", {"cabinet": "1", "tech": "OK", "inv": "GOOD"}),
            (None, {"cabinet": "2", "tech": "BAD", "inv": "BAD"}),  # clinic NOT NULL
            ("1пл", {"cabinet": "3", "tech": "OK-2", "inv": "GOOD-2"}),
        ]
    )
    assert outcomes[0][0] is not None
    assert outcomes[1][0] is None and outcomes[1][1], "неудачная строка возвращает (None, причина)"
    assert outcomes[2][0] is not None
    assert db.get_db_stats()["total_items"] == 2, "должны сохраниться только валидные строки"


# ============================================================
# ПОИСК
# ============================================================
def test_find_by_inv(db_path):
    _save(cabinet="1", tech="PC", inv="INV-FIND")
    assert db.find_by_inv("INV-FIND") is not None
    assert db.find_by_inv("нет такого") is None


def test_find_by_serial_case_insensitive(db_path):
    _save(cabinet="1", tech="PC", serial="Sn-AbC-123")
    assert db.find_by_serial("sn-abc-123") is not None


def test_find_by_pc_name_case_insensitive(db_path):
    _save(cabinet="1", tech="PC", pc_name="Pc-Server-01")
    assert db.find_by_pc_name("pc-server-01") is not None


def test_get_last_item(db_path):
    first = _save(cabinet="1", tech="First")
    second = db.save_item("2пл", {"cabinet": "2", "tech": "Second"})
    assert db.get_last_item()["id"] == second
    assert db.get_last_item(clinic="1пл")["id"] == first


def test_get_item_by_id_missing(db_path):
    assert db.get_item_by_id(99999) is None


def test_global_search_partial_match(db_path):
    _save(cabinet="101", tech="Dell OptiPlex 3070", inv="INV-G1", note="кабель утерян")
    assert len(db.global_search("OptiPlex")) == 1  # по марке
    assert len(db.global_search("INV-G")) == 1  # по инв. номеру (частичное)
    assert len(db.global_search("утерян")) == 1  # по примечанию
    assert db.global_search("нет совпадений") == []
    assert db.global_search("") == []


def test_get_all_items_pagination_and_clinic_filter(db_path):
    for i in range(7):
        db.save_item("1пл", {"cabinet": str(i), "tech": "PC"})
    db.save_item("2пл", {"cabinet": "99", "tech": "Monitor"})

    assert len(db.get_all_items(limit=3)) == 3
    assert len(db.get_all_items()) == 8
    only_1pl = db.get_all_items(clinic="1пл")
    assert len(only_1pl) == 7
    assert all(item["clinic"] == "1пл" for item in only_1pl)


def test_get_db_stats(db_path):
    _save(cabinet="1", tech="PC", inv="S1")
    db.save_item("2пл", {"cabinet": "2", "tech": "PC", "inv": "S2"})
    stats = db.get_db_stats()
    assert stats["total_items"] == 2
    assert stats["by_clinic"] == {"1пл": 1, "2пл": 1}


# ============================================================
# ДУБЛИКАТЫ
# ============================================================
def test_find_duplicates_by_serial(db_path):
    id1 = _save(cabinet="9", tech="Монитор X", inv="DUP1", serial="SN-DUP")
    _save(cabinet="9", tech="ПК Y", inv="DUP2", serial="SN-DUP")
    assert len(db.find_duplicates_by_serial("SN-DUP")) == 2
    assert len(db.find_duplicates_by_serial("SN-DUP", exclude_id=id1)) == 1


def test_find_duplicates_ignores_placeholder_values(db_path):
    """«Отсутствует»/«нет» — не дубликаты (это осознанное отсутствие номера)."""
    _save(cabinet="1", tech="PC", serial="нет")
    _save(cabinet="2", tech="PC", serial="Отсутствует")
    _save(cabinet="3", tech="PC", serial="")
    assert db.find_duplicates_by_serial("нет") == []
    assert db.find_duplicates_by_serial("Отсутствует") == []
    assert db.find_duplicates_by_serial("") == []
    assert db.find_duplicates_by_inv("нет") == []


def test_find_duplicates_by_pc_name(db_path):
    _save(cabinet="1", tech="PC", pc_name="PC-DUP")
    _save(cabinet="2", tech="PC", pc_name="pc-dup")  # регистр не важен
    assert len(db.find_duplicates_by_pc_name("PC-DUP")) == 2


# ============================================================
# ОБНОВЛЕНИЕ / УДАЛЕНИЕ
# ============================================================
def test_update_item_whitelist(db_path):
    item_id = _save(cabinet="1", tech="PC", inv="U1", ip="10.0.0.1")
    assert db.update_item(item_id, "ip", "10.0.0.2")
    assert db.get_item_by_id(item_id)["ip"] == "10.0.0.2"
    # Короткий ключ state тоже принимается (inv → inv_number)
    assert db.update_item(item_id, "inv", "U1-NEW")
    assert db.get_item_by_id(item_id)["inv_number"] == "U1-NEW"


def test_update_item_rejects_unknown_fields(db_path):
    """Whitelist полей — защита от SQL-инъекций через имя поля."""
    item_id = _save(cabinet="1", tech="PC", inv="U2")
    assert db.update_item(item_id, "tech; DROP TABLE inventory; --", "x") is False
    assert db.update_item(item_id, "id", "999") is False, "PK нельзя менять"
    assert db.update_item(item_id, "created_at", "2000-01-01") is False
    # Таблица не пострадала, запись на месте
    assert db.get_item_by_id(item_id)["inv_number"] == "U2"
    assert db.get_db_stats()["total_items"] == 1


def test_update_item_missing_record(db_path):
    assert db.update_item(99999, "ip", "1.2.3.4") is False


def test_delete_item(db_path):
    item_id = _save(cabinet="1", tech="PC", inv="DEL")
    assert db.delete_item(item_id) is True
    assert db.get_item_by_id(item_id) is None
    assert db.delete_item(item_id) is False, "повторное удаление — False"
