"""Поведенческие тесты сценария ввода новой записи (пакет handlers/inventory).

Полный путь: клиника → режим АРМ → тип техники → поля (cabinet/tech/
serial+дубликат/inv+дубликат/ip) → выбор Dr.Web/ОС → подтверждения →
сохранение (обычное и АРМ-режим).
"""

import sqlite3

import database as db
from bot_core.states import InventoryForm
from handlers.inventory.choices import (
    drweb_choice_selected,
    os_choice_selected,
    process_os_text_fallback,
)
from handlers.inventory.confirmations import (
    confirm_inv_continue,
    confirm_serial_cancel,
    confirm_serial_continue,
    mac_mismatch_skip,
)
from handlers.inventory.entry import (
    arm_mode_no,
    arm_mode_yes,
    clinic_selected,
    tech_type_selected,
)
from handlers.inventory.fields import (
    process_cabinet,
    process_inv,
    process_ip,
    process_serial,
    process_tech,
)
from handlers.inventory.review import confirm_save

REGULAR_ID = 222

PC_FIELDS = [
    "cabinet",
    "tech",
    "serial",
    "inv",
    "os",
    "drweb",
    "ip",
    "pc_name",
    "mac_phys",
    "mac_real",
    "specs",
    "note",
]


async def _seed_entry_state(fsm_state, **kwargs):
    """State как после выбора «1пл» + «Системный блок»."""
    base = {
        "clinic": "1пл",
        "clinic_name": "1 Поликлиника",
        "arm_mode": False,
        "arm_id": None,
        "tech_type": "pc",
        "tech_type_name": "Системный блок",
        "tech_fields": PC_FIELDS,
    }
    base.update(kwargs)
    await fsm_state.update_data(**base)


# ============================================================
# Выбор поликлиники и режима АРМ
# ============================================================
async def test_clinic_selected_leads_to_arm_mode_question(make_callback, fsm_state, ui):
    await fsm_state.set_state(InventoryForm.selecting_clinic)
    await clinic_selected(make_callback(REGULAR_ID, data="clinic_1пл"), fsm_state)
    assert ui.text_with("Сформировать АРМ")
    assert {"arm_mode_yes", "arm_mode_no"} <= set(ui.last_markup_callbacks())
    data = await fsm_state.get_data()
    assert data["clinic"] == "1пл"
    assert (await fsm_state.get_state()) == InventoryForm.selecting_arm_mode


async def test_clinic_selected_unknown_code_alerts(make_callback, fsm_state, ui):
    await fsm_state.set_state(InventoryForm.selecting_clinic)
    await clinic_selected(make_callback(REGULAR_ID, data="clinic_нет такой"), fsm_state)
    assert any("Неизвестная поликлиника" in a for a in ui.alerts)
    assert not ui.messages


async def test_arm_mode_no_starts_regular_input(make_callback, fsm_state, ui):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.selecting_arm_mode)
    await arm_mode_no(make_callback(REGULAR_ID, data="arm_mode_no"), fsm_state)
    assert ui.text_with("Введите номер кабинета")
    data = await fsm_state.get_data()
    assert data["arm_mode"] is False
    assert (await fsm_state.get_state()) == InventoryForm.entering_cabinet


async def test_arm_mode_yes_allocates_arm_id(make_callback, fsm_state, ui, db_path):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.selecting_arm_mode)
    await arm_mode_yes(make_callback(REGULAR_ID, data="arm_mode_yes"), fsm_state)
    data = await fsm_state.get_data()
    assert data["arm_mode"] is True and data["arm_id"] >= 1
    assert f"АРМ #{data['arm_id']}" in ui.last_text


# ============================================================
# Тип техники и текстовые поля
# ============================================================
async def test_tech_type_selected_stores_fields(make_callback, fsm_state, ui):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.selecting_tech_type)
    await tech_type_selected(make_callback(REGULAR_ID, data="tech_type_pc"), fsm_state)
    data = await fsm_state.get_data()
    assert data["tech_fields"] == PC_FIELDS
    assert ui.text_with("марку и модель")
    assert (await fsm_state.get_state()) == InventoryForm.entering_tech


async def test_tech_type_selected_unknown_alerts(make_callback, fsm_state, ui):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.selecting_tech_type)
    await tech_type_selected(make_callback(REGULAR_ID, data="tech_type_xyz"), fsm_state)
    assert any("Неизвестный тип" in a for a in ui.alerts)


async def test_process_cabinet_rejects_empty_and_skip(make_message, fsm_state, ui):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.entering_cabinet)
    await process_cabinet(make_message(REGULAR_ID, text="   "), fsm_state)
    assert ui.text_with("не может быть пустым")
    await process_cabinet(make_message(REGULAR_ID, text="пропустить"), fsm_state)
    assert ui.text_with("обязательно для заполнения")


async def test_process_cabinet_valid_moves_to_tech_type(make_message, fsm_state, ui):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.entering_cabinet)
    await process_cabinet(make_message(REGULAR_ID, text="101"), fsm_state)
    data = await fsm_state.get_data()
    assert data["cabinet"] == "101"
    assert "tech_type_pc" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.selecting_tech_type


async def test_process_tech_moves_to_serial(make_message, fsm_state, ui):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.entering_tech)
    await process_tech(make_message(REGULAR_ID, text="Dell OptiPlex 3090"), fsm_state)
    data = await fsm_state.get_data()
    assert data["tech"] == "Dell OptiPlex 3090"
    assert ui.text_with("серийный номер")
    assert "field_absent" in ui.last_markup_callbacks()


async def test_process_serial_duplicate_warns(make_message, fsm_state, ui, db_path):
    db.save_item("1пл", {"cabinet": "1", "tech": "Dell", "serial": "SN-777", "tech_type": "pc"})
    await _seed_entry_state(fsm_state, cabinet="101")
    await fsm_state.set_state(InventoryForm.entering_serial)

    await process_serial(make_message(REGULAR_ID, text="SN-777"), fsm_state)
    assert ui.text_with("уже есть")
    assert "confirm_serial_continue" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.confirming_serial_duplicate


async def test_process_serial_absent_word_skips_check(make_message, fsm_state, ui, db_path):
    db.save_item("1пл", {"cabinet": "1", "tech": "Dell", "serial": "нет", "tech_type": "pc"})
    await _seed_entry_state(fsm_state, cabinet="101")
    await fsm_state.set_state(InventoryForm.entering_serial)
    await process_serial(make_message(REGULAR_ID, text="нет"), fsm_state)
    assert not any("уже есть" in t for t in ui.texts)  # «нет» не проверяем на дубликаты
    assert (await fsm_state.get_state()) == InventoryForm.entering_inv


async def test_process_inv_duplicate_informs_not_blocks(make_message, fsm_state, ui, db_path):
    db.save_item("1пл", {"cabinet": "1", "tech": "Dell", "inv": "INV-1", "tech_type": "pc"})
    await _seed_entry_state(fsm_state, cabinet="101", serial="SN-1")
    await fsm_state.set_state(InventoryForm.entering_inv)

    await process_inv(make_message(REGULAR_ID, text="INV-1"), fsm_state)
    assert ui.text_with("уже используется")
    assert "confirm_inv_continue" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.confirming_inv_duplicate


async def test_process_inv_unique_moves_to_os(make_message, fsm_state, ui, db_path):
    await _seed_entry_state(fsm_state, cabinet="101", serial="SN-unique")
    await fsm_state.set_state(InventoryForm.entering_inv)
    await process_inv(make_message(REGULAR_ID, text="INV-unique"), fsm_state)
    assert "os_choice_win10_x64" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.entering_os


async def test_process_ip_rejects_invalid_format(make_message, fsm_state, ui):
    await _seed_entry_state(fsm_state, cabinet="101", serial="S", inv="I")
    await fsm_state.set_state(InventoryForm.entering_ip)
    await process_ip(make_message(REGULAR_ID, text="999.999.1.1"), fsm_state)
    assert ui.text_with("Неверный формат IP")


async def test_process_ip_valid_moves_to_pc_name(make_message, fsm_state, ui):
    await _seed_entry_state(fsm_state, cabinet="101", serial="S", inv="I")
    await fsm_state.set_state(InventoryForm.entering_ip)
    await process_ip(make_message(REGULAR_ID, text="192.168.1.10"), fsm_state)
    data = await fsm_state.get_data()
    assert data["ip"] == "192.168.1.10"
    assert ui.text_with("имя компьютера")


# ============================================================
# Выбор Dr.Web / ОС из кнопок
# ============================================================
async def test_drweb_choice_stores_db_value_and_advances(make_callback, fsm_state, ui):
    await _seed_entry_state(
        fsm_state, cabinet="101", tech="Dell", serial="S", inv="I", os="Windows 10 x64"
    )
    await fsm_state.set_state(InventoryForm.entering_drweb)
    await drweb_choice_selected(
        make_callback(REGULAR_ID, data="drweb_choice_no_license"), fsm_state
    )
    data = await fsm_state.get_data()
    assert data["drweb"] == "Нет лицензии"  # в state — значение для БД, не ключ
    assert ui.text_with("IP-адрес")


async def test_drweb_choice_unknown_key_alerts(make_callback, fsm_state, ui):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.entering_drweb)
    await drweb_choice_selected(make_callback(REGULAR_ID, data="drweb_choice_hack"), fsm_state)
    assert any("Неизвестный статус" in a for a in ui.alerts)


async def test_os_choice_advances_to_drweb(make_callback, fsm_state, ui):
    await _seed_entry_state(fsm_state, cabinet="101", tech="Dell", serial="S", inv="I")
    await fsm_state.set_state(InventoryForm.entering_os)
    await os_choice_selected(make_callback(REGULAR_ID, data="os_choice_redos73"), fsm_state)
    data = await fsm_state.get_data()
    assert data["os"] == "РЕД ОС 7.3"
    assert "drweb_choice_installed" in ui.last_markup_callbacks()


async def test_os_text_fallback_rejects_typing(make_message, fsm_state, ui):
    await _seed_entry_state(fsm_state)
    await fsm_state.set_state(InventoryForm.entering_os)
    await process_os_text_fallback(make_message(REGULAR_ID, text="Хочу Windows"), fsm_state)
    assert ui.text_with("не поддерживается")


# ============================================================
# Подтверждения предупреждений
# ============================================================
async def test_confirm_serial_continue_advances(make_callback, fsm_state, ui):
    await _seed_entry_state(fsm_state, cabinet="101", serial="SN-777")
    await fsm_state.set_state(InventoryForm.confirming_serial_duplicate)
    await confirm_serial_continue(
        make_callback(REGULAR_ID, data="confirm_serial_continue"), fsm_state
    )
    assert (await fsm_state.get_state()) == InventoryForm.entering_inv


async def test_confirm_serial_cancel_returns_to_serial(make_callback, fsm_state, ui):
    await _seed_entry_state(fsm_state, cabinet="101", serial="SN-777")
    await fsm_state.set_state(InventoryForm.confirming_serial_duplicate)
    await confirm_serial_cancel(make_callback(REGULAR_ID, data="confirm_serial_cancel"), fsm_state)
    data = await fsm_state.get_data()
    assert data["serial"] is None
    assert (await fsm_state.get_state()) == InventoryForm.entering_serial
    assert ui.text_with("заново")


async def test_confirm_inv_continues_to_os(make_callback, fsm_state, ui):
    await _seed_entry_state(fsm_state, cabinet="101", serial="S", inv="INV-1")
    await fsm_state.set_state(InventoryForm.confirming_inv_duplicate)
    await confirm_inv_continue(make_callback(REGULAR_ID, data="confirm_inv_continue"), fsm_state)
    assert (await fsm_state.get_state()) == InventoryForm.entering_os


async def test_mac_mismatch_skip_clears_and_advances(make_callback, fsm_state, ui):
    await _seed_entry_state(
        fsm_state,
        cabinet="101",
        tech="Dell",
        serial="S",
        inv="I",
        os="Windows 10 x64",
        drweb="Установлен",
        ip="10.0.0.1",
        pc_name="KEMDC-PC-1",
        mac_phys="AA:BB:CC:DD:EE:FF",
        mac_real="11:22:33:44:55:66",
    )
    await fsm_state.set_state(InventoryForm.confirming_mac_mismatch)
    await mac_mismatch_skip(make_callback(REGULAR_ID, data="mac_mismatch_skip"), fsm_state)
    data = await fsm_state.get_data()
    assert data["mac_real"] == ""
    assert (await fsm_state.get_state()) == InventoryForm.entering_specs


# ============================================================
# Сохранение
# ============================================================
def _full_record(**extra):
    record = {
        "clinic": "1пл",
        "clinic_name": "1 Поликлиника",
        "arm_mode": False,
        "arm_id": None,
        "tech_type": "pc",
        "tech_type_name": "Системный блок",
        "tech_fields": PC_FIELDS,
        "cabinet": "101",
        "tech": "Dell OptiPlex 3090",
        "serial": "SN-42",
        "inv": "INV-42",
        "os": "Windows 10 x64",
        "drweb": "Установлен",
        "ip": "192.168.1.10",
        "pc_name": "KEMDC-PC-42",
        "mac_phys": "AA:BB:CC:DD:EE:FF",
        "mac_real": "AA:BB:CC:DD:EE:FF",
        "specs": "i5, 8GB, 256GB SSD",
        "note": "",
    }
    record.update(extra)
    return record


async def test_confirm_save_persists_item(make_callback, fsm_state, ui, db_path):
    await fsm_state.update_data(**_full_record())
    await fsm_state.set_state(InventoryForm.confirming_save)
    await confirm_save(make_callback(REGULAR_ID, data="confirm_save"), fsm_state)

    item = db.find_by_inv("INV-42")
    assert item and item["tech"] == "Dell OptiPlex 3090"
    assert item["drweb"] == "Установлен"
    assert ui.text_with("Сохранено")
    assert f"ID записи: {item['id']}" in ui.last_text
    assert "new_inventory" in ui.last_markup_callbacks()


async def test_confirm_save_arm_mode_offers_continue(make_callback, fsm_state, ui, db_path):
    await fsm_state.update_data(**_full_record(arm_mode=True, arm_id=5))
    await fsm_state.set_state(InventoryForm.confirming_save)
    await confirm_save(make_callback(REGULAR_ID, data="confirm_save"), fsm_state)

    item = db.find_by_inv("INV-42")
    assert item["arm_id"] == 5  # запись привязана к АРМ
    assert "arm_add_another" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.arm_after_save


async def test_confirm_save_db_error_keeps_state(
    make_callback, fsm_state, ui, db_path, monkeypatch
):
    """Ошибка БД не сбрасывает state — данные не теряются (фаза 0)."""

    def _broken_save(clinic, data):
        raise sqlite3.Error("disk full")

    monkeypatch.setattr(db, "save_item", _broken_save)
    await fsm_state.update_data(**_full_record())
    await fsm_state.set_state(InventoryForm.confirming_save)

    await confirm_save(make_callback(REGULAR_ID, data="confirm_save"), fsm_state)
    assert ui.text_with("Не удалось сохранить")
    assert "confirm_save" in ui.last_markup_callbacks()  # можно повторить
    data = await fsm_state.get_data()
    assert data["tech"] == "Dell OptiPlex 3090"  # ввод жив
    assert (await fsm_state.get_state()) == InventoryForm.confirming_save
