"""Аудиторские фильтры: единый WHERE для find/count (фаза 1)."""

import sqlite3

import config
import database as db


def _seed_problematic_items():
    """12 ПК без IP (проблемные) + 3 ПК с IP (нормальные)."""
    for i in range(12):
        db.save_item(
            "1пл",
            {"cabinet": str(100 + i), "tech": "PC", "tech_type": "pc", "inv": f"NOP{i}", "ip": ""},
        )
    for i in range(3):
        db.save_item(
            "1пл",
            {
                "cabinet": str(200 + i),
                "tech": "PC",
                "tech_type": "pc",
                "inv": f"OK{i}",
                "ip": "10.0.0.1",
            },
        )


def test_count_is_exact_not_capped_by_limit(db_path):
    """Регрессия фазы 1: раньше len(find(limit=500)) показывал «500» при >500."""
    _seed_problematic_items()
    assert db.count_problematic_items("no_ip") == 12
    assert len(db.find_problematic_items("no_ip", limit=5)) == 5


def test_count_matches_direct_sql(db_path):
    _seed_problematic_items()
    with sqlite3.connect(config.DB_PATH) as conn:
        direct = conn.execute(
            "SELECT COUNT(*) FROM inventory "
            "WHERE tech_type IN ('pc','laptop') AND (ip IS NULL OR ip='')"
        ).fetchone()[0]
    assert db.count_problematic_items("no_ip") == direct


def test_count_and_find_are_consistent(db_path):
    """find и count используют один _problematic_where — результаты совпадают."""
    _seed_problematic_items()
    db.save_item("1пл", {"cabinet": "1", "tech": "NB", "tech_type": "laptop", "inv": "L1"})
    assert db.count_problematic_items("no_ip") == len(
        db.find_problematic_items("no_ip", limit=1000)
    )


def test_unknown_category(db_path):
    assert db.count_problematic_items("no_such_category") == 0
    assert db.find_problematic_items("no_such_category") == []


def test_monitor_without_ip_is_not_a_problem(db_path):
    """У монитора нет сетевых полей по определению — в фильтре только ПК/ноутбуки."""
    db.save_item("1пл", {"cabinet": "1", "tech": "Samsung", "tech_type": "monitor", "inv": "M1"})
    assert db.count_problematic_items("no_ip") == 0
    assert db.count_problematic_items("no_pc_name") == 0


def test_drweb_problem_includes_legacy_values(db_path):
    for i, value in enumerate(["Нет лицензии", "нет лиц", "Нет соединения с сервером", "нет соед"]):
        db.save_item(
            "1пл",
            {"cabinet": str(i), "tech": "PC", "tech_type": "pc", "inv": f"D{i}", "drweb": value},
        )
    db.save_item(
        "1пл",
        {"cabinet": "9", "tech": "PC", "tech_type": "pc", "inv": "D-OK", "drweb": "Установлен"},
    )
    assert db.count_problematic_items("drweb_problem") == 4


def test_mac_mismatch_requires_both_filled(db_path):
    db.save_item(
        "1пл",
        {
            "cabinet": "1",
            "tech": "PC",
            "tech_type": "pc",
            "inv": "MM1",
            "mac_phys": "00:11:22:33:44:55",
            "mac_real": "66:77:88:99:AA:BB",
        },
    )
    db.save_item(
        "1пл",
        {
            "cabinet": "2",
            "tech": "PC",
            "tech_type": "pc",
            "inv": "MM2",
            "mac_phys": "00:11:22:33:44:55",
            "mac_real": "",
        },
    )
    assert db.count_problematic_items("mac_mismatch") == 1


def test_no_specs_only_for_pc_and_laptop(db_path):
    db.save_item("1пл", {"cabinet": "1", "tech": "PC", "tech_type": "pc", "inv": "SP1"})
    db.save_item("1пл", {"cabinet": "2", "tech": "NB", "tech_type": "laptop", "inv": "SP2"})
    db.save_item("1пл", {"cabinet": "3", "tech": "Prn", "tech_type": "printer", "inv": "SP3"})
    db.save_item(
        "1пл", {"cabinet": "4", "tech": "PC", "tech_type": "pc", "inv": "SP4", "specs": "i5/8GB"}
    )
    assert db.count_problematic_items("no_specs") == 2


def test_no_mac_counts_when_all_mac_fields_empty(db_path):
    db.save_item("1пл", {"cabinet": "1", "tech": "PC", "tech_type": "pc", "inv": "NM1"})
    db.save_item(
        "1пл",
        {
            "cabinet": "2",
            "tech": "PC",
            "tech_type": "pc",
            "inv": "NM2",
            "mac_phys": "00:11:22:33:44:55",
        },
    )
    assert db.count_problematic_items("no_mac") == 1


def test_every_web_category_is_supported_by_db_filter(db_path):
    """Страж синхронизации слоёв: каждая категория веб-панели должна иметь
    ветку в database.audit._problematic_where (иначе на сайте вечный 0)."""
    from database.audit import _problematic_where
    from web.context import AUDIT_CATEGORIES

    for key, _label, _desc in AUDIT_CATEGORIES:
        assert _problematic_where(key) is not None, f"нет SQL-условия для категории {key!r}"
