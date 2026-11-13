"""Excel-импорт/экспорт: алиасы, функциональный импорт, round-trip."""

from openpyxl import Workbook, load_workbook

import config
import database as db
from excel_export import export_to_excel
from excel_import import DRWEB_ALIASES, import_from_excel


def _make_xlsx(path, rows, sheet_title="1 пол"):
    """Собирает тестовый файл в формате шаблона «Инвентаризация.xlsx»."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(
        ["№ кабинета", "Тип", "Марка, модель", "Инв №", "Сер №", "IP-адрес", "Физический MAC"]
    )
    for row in rows:
        ws.append(row)
    return wb


# ============================================================
# АЛИАСЫ (после дедупликации словарей фазы 2)
# ============================================================
def test_drweb_alias_coverage_after_dedup():
    """Слияние 4 копий словаря не сузило набор распознаваемых значений."""
    expected = {
        "установлен": "Установлен",
        "не установлен": "Не установлен",
        "нет лицензии": "Нет лицензии",
        "нет лиц": "Нет лицензии",
        "нет соед": "Нет соединения с сервером",
        "нет соединения": "Нет соединения с сервером",
        "+": "Установлен",
        "да": "Установлен",
        "yes": "Установлен",
        "нет": "Не установлен",
        "no": "Не установлен",
    }
    missing = {k: v for k, v in expected.items() if DRWEB_ALIASES.get(k) != v}
    assert not missing, f"потерянные алиасы: {missing}"


# ============================================================
# ИМПОРТ
# ============================================================
def test_import_from_excel_functional(db_path, tmp_path):
    xlsx = tmp_path / "import.xlsx"
    wb = _make_xlsx(
        xlsx,
        [
            ["101", "сист блок", "Dell 3070", "INV-X1", "SN-X1", "10.1.1.5", "00:11:22:33:44:55"],
            ["102", "монитор", "Samsung", "INV-X2", "SN-X2", "", ""],
            ["", "", "", "", "", "", ""],  # пустая строка — пропуск
        ],
    )
    ws2 = wb.create_sheet("Нераспознанный лист")
    ws2.append(["мусор"])
    wb.save(xlsx)

    result = import_from_excel(str(xlsx))

    assert result["imported"] == 2
    assert result["by_clinic"].get("1пл") == 2
    assert "Нераспознанный лист" in result["unrecognized_clinics"]

    item = db.find_by_inv("INV-X1")
    assert item is not None
    assert item["tech_type"] == "pc", "«сист блок» → pc"
    assert item["ip"] == "10.1.1.5"
    assert item["mac_phys"] == "00:11:22:33:44:55"
    assert db.find_by_inv("INV-X2")["tech_type"] == "monitor"


def test_import_normalizes_legacy_drweb(db_path, tmp_path):
    xlsx = tmp_path / "drweb.xlsx"
    _make_xlsx(
        xlsx,
        [
            ["1", "сист блок", "Dell", "INV-DR1", "", "", ""],
        ],
    ).save(xlsx)
    # Дописываем колонку Dr.Web (заголовок распознаётся автоматом)
    wb = load_workbook(xlsx)
    ws = wb["1 пол"]
    ws.cell(row=1, column=8, value="Dr Web")
    ws.cell(row=2, column=8, value="нет лиц")
    wb.save(xlsx)

    import_from_excel(str(xlsx))
    assert db.find_by_inv("INV-DR1")["drweb"] == "Нет лицензии"


def test_import_garbage_file_reports_error(db_path, tmp_path):
    """Битый файл — понятная ошибка в отчёте, а не падение бота."""
    bad = tmp_path / "broken.xlsx"
    bad.write_bytes("это не excel-файл".encode())
    result = import_from_excel(str(bad))
    assert result["imported"] == 0
    assert result["errors"], "ошибка должна попасть в отчёт"


def test_import_skips_rows_without_inv_and_serial(db_path, tmp_path):
    """Строки без инв. и серийного номера — черновики, пропускаются."""
    xlsx = tmp_path / "draft.xlsx"
    _make_xlsx(
        xlsx,
        [
            ["101", "сист блок", "Dell", "", "", "", ""],  # нет inv и serial
            ["102", "сист блок", "HP", "INV-FULL", "", "", ""],
        ],
    ).save(xlsx)

    result = import_from_excel(str(xlsx))
    assert result["imported"] == 1
    assert db.find_by_inv("INV-FULL") is not None


# ============================================================
# ЭКСПОРТ
# ============================================================
def test_export_to_excel_explicit_path(db_path, tmp_path):
    db.save_item(
        "1пл", {"cabinet": "101", "tech": "Dell", "inv": "E1", "tech_type": "pc", "ip": "10.0.0.1"}
    )
    db.save_item("2пл", {"cabinet": "202", "tech": "HP", "inv": "E2"})

    target = tmp_path / "export.xlsx"
    result_path = export_to_excel(str(target))

    assert result_path == str(target)
    wb = load_workbook(target)
    assert set(wb.sheetnames) == {"1пл", "2пл"}


def test_export_empty_db_returns_none(db_path, tmp_path):
    assert export_to_excel(str(tmp_path / "empty.xlsx")) is None


# ============================================================
# ROUND-TRIP: экспорт → импорт
# ============================================================
def test_export_import_roundtrip(db_path, tmp_path, monkeypatch):
    """Файл, выгруженный панелью/ботом, должен импортироваться обратно.

    export_to_excel называет листы КОДАМИ поликлиник («1пл»), а импорт
    до фазы 3 распознавал только полные названия («1 поликлиника») —
    round-trip молча терял все данные.
    """
    for i in range(3):
        db.save_item(
            "1пл",
            {
                "cabinet": "10",
                "tech": f"Dell {i}",
                "inv": f"RT-{i}",
                "serial": f"SN-RT-{i}",
                "tech_type": "pc",
                "ip": f"10.0.0.{i + 1}",
            },
        )

    export_file = tmp_path / "roundtrip.xlsx"
    assert export_to_excel(str(export_file)) is not None

    # Свежая БД: импортируем выгруженный файл в «новую инсталляцию»
    fresh_db = tmp_path / "fresh" / "inventory.db"
    fresh_db.parent.mkdir()
    monkeypatch.setattr(config, "DB_PATH", str(fresh_db))
    db.init_db()

    result = import_from_excel(str(export_file))

    assert result["unrecognized_clinics"] == [], "листы-коды обязаны распознаваться"
    assert result["imported"] == 3
    assert result["by_clinic"].get("1пл") == 3
    restored = db.find_by_inv("RT-1")
    assert restored is not None and restored["ip"] == "10.0.0.2"
