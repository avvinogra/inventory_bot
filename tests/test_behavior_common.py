"""Поведенческие тесты общих хендлеров (commands, меню, отмена, skip).

Мок-полигон (фикстура ui) подменяет Message.answer / CallbackQuery.answer
рекордером: хендлеры вызываются напрямую с настоящим FSMContext и
настоящими aiogram-объектами — без Telegram и без запуска бота.
"""

import database as db
from bot_core.states import InventoryForm
from handlers.common import (
    BOT_COMMANDS,
    back_to_menu,
    cancel_process,
    cmd_cancel,
    cmd_help,
    cmd_start,
    cmd_stats,
    confirm_exit_no,
    confirm_exit_yes,
    field_absent,
    skip_field,
)

ADMIN_ID = 111  # задаётся в conftest: ADMIN_CHAT_IDS=111
REGULAR_ID = 222  # ALLOWED_CHAT_IDS=111,222
STRANGER_ID = 999  # ни админ, ни разрешённый

# Поля ПК-сценария (для next_field-переходов)
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


async def _seed_state(fsm_state, **kwargs):
    """Заполнить state как после выбора клиники и типа «Системный блок»."""
    base = {
        "clinic": "1пл",
        "clinic_name": "1 Поликлиника",
        "arm_mode": False,
        "tech_type": "pc",
        "tech_type_name": "💻 Системный блок",
        "tech_fields": PC_FIELDS,
    }
    base.update(kwargs)
    await fsm_state.update_data(**base)


# ============================================================
# Команды: /start, /help, /stats, /cancel
# ============================================================
async def test_cmd_start_welcomes_allowed_user(make_message, fsm_state, ui):
    await cmd_start(make_message(REGULAR_ID), fsm_state)
    assert ui.text_with("БОТ ИНВЕНТАРИЗАЦИИ")
    assert "start_inventory" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) is None  # state сброшен


async def test_cmd_start_denies_stranger(make_message, fsm_state, ui):
    await cmd_start(make_message(STRANGER_ID), fsm_state)
    assert ui.text_with("Доступ запрещён")
    assert len(ui.messages) == 1


async def test_cmd_help_lists_commands(make_message, fsm_state, ui):
    await cmd_help(make_message(REGULAR_ID), fsm_state)
    assert ui.text_with("СПРАВКА")
    assert ui.text_with("/stats")
    assert ui.text_with("/cancel")


async def test_cmd_help_does_not_reset_active_input(make_message, fsm_state, ui):
    await _seed_state(fsm_state, cabinet="101")
    await fsm_state.set_state(InventoryForm.entering_tech)
    await cmd_help(make_message(REGULAR_ID), fsm_state)
    assert (await fsm_state.get_state()) == InventoryForm.entering_tech
    data = await fsm_state.get_data()
    assert data["cabinet"] == "101"  # ввод не потерян


async def test_cmd_help_denies_stranger(make_message, fsm_state, ui):
    await cmd_help(make_message(STRANGER_ID), fsm_state)
    assert not ui.messages


async def test_cmd_stats_counts_records(make_message, fsm_state, ui, db_path):
    db.save_item("1пл", {"cabinet": "1", "tech": "Dell", "tech_type": "pc"})
    db.save_item("1пл", {"cabinet": "2", "tech": "HP", "tech_type": "monitor"})
    db.save_item("2пл", {"cabinet": "3", "tech": "Epson", "tech_type": "printer"})

    await cmd_stats(make_message(REGULAR_ID), fsm_state)
    assert ui.text_with("Всего записей: 3")
    assert ui.text_with("1 Поликлиника: 2")
    assert ui.text_with("2 Поликлиника: 1")


async def test_cmd_stats_on_empty_db(make_message, fsm_state, ui, db_path):
    await cmd_stats(make_message(REGULAR_ID), fsm_state)
    assert ui.text_with("Всего записей: 0")


async def test_cmd_cancel_returns_to_menu(make_message, fsm_state, ui):
    await _seed_state(fsm_state, cabinet="101")
    await fsm_state.set_state(InventoryForm.entering_tech)
    await cmd_cancel(make_message(REGULAR_ID), fsm_state)
    assert ui.text_with("Процесс отменён")
    assert "start_inventory" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) is None


def test_bot_commands_menu_registered():
    """Меню команд Telegram содержит новые /help и /stats."""
    commands = {c.command for c in BOT_COMMANDS}
    assert {"start", "menu", "help", "stats", "cancel"} <= commands


# ============================================================
# Выход в меню с несохранёнными данными
# ============================================================
async def test_back_to_menu_with_unsaved_data_asks_confirmation(make_callback, fsm_state, ui):
    await _seed_state(fsm_state, cabinet="101")
    await fsm_state.set_state(InventoryForm.entering_tech)
    await back_to_menu(make_callback(REGULAR_ID, data="back_to_menu"), fsm_state)
    assert ui.text_with("несохранённые данные")
    assert "confirm_exit_yes" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.confirming_exit


async def test_back_to_menu_without_data_goes_straight(make_callback, fsm_state, ui):
    await back_to_menu(make_callback(REGULAR_ID, data="back_to_menu"), fsm_state)
    assert ui.text_with("БОТ ИНВЕНТАРИЗАЦИИ")
    assert (await fsm_state.get_state()) is None


async def test_cancel_process_with_data_asks_confirmation(make_callback, fsm_state, ui):
    await _seed_state(fsm_state, cabinet="101")
    await fsm_state.set_state(InventoryForm.entering_tech)
    await cancel_process(make_callback(REGULAR_ID, data="cancel_process"), fsm_state)
    assert ui.text_with("Точно отменить процесс?")
    assert (await fsm_state.get_state()) == InventoryForm.confirming_exit


async def test_confirm_exit_yes_clears_state(make_callback, fsm_state, ui):
    await _seed_state(fsm_state, cabinet="101")
    await confirm_exit_yes(make_callback(REGULAR_ID, data="confirm_exit_yes"), fsm_state)
    assert ui.text_with("БОТ ИНВЕНТАРИЗАЦИИ")
    data = await fsm_state.get_data()
    assert not data.get("cabinet")  # данные новой записи потеряны


async def test_confirm_exit_no_returns_to_confirmation_card(make_callback, fsm_state, ui):
    await _seed_state(fsm_state, cabinet="101", tech="Dell OptiPlex 3090")
    await confirm_exit_no(make_callback(REGULAR_ID, data="confirm_exit_no"), fsm_state)
    assert ui.text_with("ПРОВЕРЬТЕ ДАННЫЕ")
    assert "confirm_save" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.confirming_save


# ============================================================
# skip / «Отсутствует»
# ============================================================
async def test_skip_required_field_alerts(make_callback, fsm_state, ui):
    await _seed_state(fsm_state)
    await fsm_state.set_state(InventoryForm.entering_cabinet)
    await skip_field(make_callback(REGULAR_ID, data="skip_current_field"), fsm_state)
    assert any("обязательно" in a for a in ui.alerts)


async def test_skip_optional_field_moves_next(make_callback, fsm_state, ui):
    await _seed_state(fsm_state)
    await fsm_state.set_state(InventoryForm.entering_serial)
    await skip_field(make_callback(REGULAR_ID, data="skip_current_field"), fsm_state)
    data = await fsm_state.get_data()
    assert data["serial"] == ""
    assert (await fsm_state.get_state()) == InventoryForm.entering_inv
    assert ui.text_with("инвентарный номер")


async def test_field_absent_stores_marker_and_moves_next(make_callback, fsm_state, ui):
    await _seed_state(fsm_state)
    await fsm_state.set_state(InventoryForm.entering_inv)
    await field_absent(make_callback(REGULAR_ID, data="field_absent"), fsm_state)
    data = await fsm_state.get_data()
    assert data["inv"] == "Отсутствует"
    # следующее поле после inv в ПК-сценарии — ОС (кнопочное меню)
    assert "os_choice_other" in ui.last_markup_callbacks()


async def test_field_absent_in_new_record_mode_returns_to_card(make_callback, fsm_state, ui):
    await _seed_state(fsm_state, inv="старое", editing_mode="new_record")
    await fsm_state.set_state(InventoryForm.entering_inv)
    await field_absent(make_callback(REGULAR_ID, data="field_absent"), fsm_state)
    data = await fsm_state.get_data()
    assert data["inv"] == "Отсутствует"
    assert ui.text_with("ПРОВЕРЬТЕ ДАННЫЕ")
