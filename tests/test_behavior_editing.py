"""Поведенческие тесты сценария правки существующей записи.

Поиск (по инв. № / по ID / глобальный) → карточка → выбор поля →
ввод нового значения → UPDATE в БД → карточка с баннером → удаление.
"""

import database as db
from bot_core.states import InventoryForm
from handlers.editing import (
    edit_back_to_card,
    edit_delete_confirm,
    edit_delete_request,
    edit_field_selected,
    edit_method_global,
    edit_method_inv,
    edit_open_item,
    edit_search_by_id,
    edit_search_by_text,
    start_edit,
)
from handlers.inventory.fields import process_tech

REGULAR_ID = 222


async def _seed_item(**extra) -> int:
    data = {
        "cabinet": "101",
        "tech": "Dell OptiPlex 3090",
        "tech_type": "pc",
        "serial": "SN-100",
        "inv": "INV-100",
        "os": "Windows 10 x64",
        "drweb": "Установлен",
        "ip": "192.168.1.10",
        "pc_name": "KEMDC-PC-100",
    }
    data.update(extra)
    return db.save_item("1пл", data)


async def _open_card(fsm_state, item_id: int):
    """State как после открытия карточки записи (edit_choose_field)."""
    await fsm_state.update_data(editing_item_id=item_id, editing_mode=None)
    await fsm_state.set_state(InventoryForm.edit_choose_field)


# ============================================================
# Точка входа и выбор способа поиска
# ============================================================
async def test_start_edit_shows_search_methods(make_callback, fsm_state, ui):
    await start_edit(make_callback(REGULAR_ID, data="start_edit"), fsm_state)
    assert "edit_method_inv" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.edit_select_method


async def test_edit_method_inv_prompts_for_number(make_callback, fsm_state, ui):
    await fsm_state.set_state(InventoryForm.edit_select_method)
    await edit_method_inv(make_callback(REGULAR_ID, data="edit_method_inv"), fsm_state)
    assert ui.text_with("инвентарный номер")
    assert (await fsm_state.get_state()) == InventoryForm.edit_enter_inv


async def test_edit_method_global_prompts_for_query(make_callback, fsm_state, ui):
    await fsm_state.set_state(InventoryForm.edit_select_method)
    await edit_method_global(make_callback(REGULAR_ID, data="edit_method_global"), fsm_state)
    assert ui.text_with("Глобальный поиск")
    data = await fsm_state.get_data()
    assert data["search_mode"] == "global"


# ============================================================
# Поиск
# ============================================================
async def test_search_by_inv_opens_card(make_message, fsm_state, ui, db_path):
    item_id = await _seed_item()
    await fsm_state.set_state(InventoryForm.edit_enter_inv)

    await edit_search_by_text(make_message(REGULAR_ID, text="INV-100"), fsm_state)
    assert ui.text_with("КАРТОЧКА ЗАПИСИ")
    assert f"ID: {item_id}" in ui.last_text
    assert "edit_field_tech" in ui.last_markup_callbacks()
    data = await fsm_state.get_data()
    assert data["editing_item_id"] == item_id
    assert (await fsm_state.get_state()) == InventoryForm.edit_choose_field


async def test_search_by_inv_not_found(make_message, fsm_state, ui, db_path):
    await fsm_state.set_state(InventoryForm.edit_enter_inv)
    await edit_search_by_text(make_message(REGULAR_ID, text="INV-нет"), fsm_state)
    assert ui.text_with("не найдена")


async def test_search_by_empty_query_reprompts(make_message, fsm_state, ui, db_path):
    await fsm_state.set_state(InventoryForm.edit_enter_inv)
    await edit_search_by_text(make_message(REGULAR_ID, text="  "), fsm_state)
    assert ui.text_with("Пустой запрос")


async def test_global_search_lists_matches(make_message, fsm_state, ui, db_path):
    await _seed_item()
    await _seed_item(inv="INV-101", tech="HP EliteDesk")
    await fsm_state.update_data(search_mode="global")
    await fsm_state.set_state(InventoryForm.edit_enter_inv)

    await edit_search_by_text(make_message(REGULAR_ID, text="Dell OptiPlex"), fsm_state)
    assert ui.text_with("Найдено записей")
    assert any(c.startswith("edit_open_") for c in ui.last_markup_callbacks())


async def test_search_by_id_opens_card(make_message, fsm_state, ui, db_path):
    item_id = await _seed_item()
    await fsm_state.set_state(InventoryForm.edit_enter_id)

    await edit_search_by_id(make_message(REGULAR_ID, text=str(item_id)), fsm_state)
    assert ui.text_with("КАРТОЧКА ЗАПИСИ")


async def test_search_by_id_invalid_number(make_message, fsm_state, ui, db_path):
    await fsm_state.set_state(InventoryForm.edit_enter_id)
    await edit_search_by_id(make_message(REGULAR_ID, text="не число"), fsm_state)
    assert ui.text_with("Неверный формат ID")


# ============================================================
# Правка поля существующей записи
# ============================================================
async def test_edit_field_selected_prompts_with_mode_existing(
    make_callback, fsm_state, ui, db_path
):
    item_id = await _seed_item()
    await _open_card(fsm_state, item_id)

    await edit_field_selected(make_callback(REGULAR_ID, data="edit_field_tech"), fsm_state)
    data = await fsm_state.get_data()
    assert data["editing_field"] == "tech"
    assert data["editing_mode"] == "existing"
    assert ui.text_with("марку и модель")
    assert (await fsm_state.get_state()) == InventoryForm.entering_tech


async def test_edit_field_selected_drweb_shows_choice_menu(make_callback, fsm_state, ui, db_path):
    item_id = await _seed_item()
    await _open_card(fsm_state, item_id)

    await edit_field_selected(make_callback(REGULAR_ID, data="edit_field_drweb"), fsm_state)
    assert "drweb_choice_installed" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.entering_drweb


async def test_field_input_updates_db_and_returns_card(make_message, fsm_state, ui, db_path):
    """Ввод нового значения в режиме existing: UPDATE в БД + карточка с баннером."""
    item_id = await _seed_item()
    await fsm_state.update_data(
        editing_item_id=item_id, editing_field="tech", editing_mode="existing"
    )
    await fsm_state.set_state(InventoryForm.entering_tech)

    await process_tech(make_message(REGULAR_ID, text="HP EliteDesk 800 G6"), fsm_state)
    item = db.get_item_by_id(item_id)
    assert item["tech"] == "HP EliteDesk 800 G6"  # реально в БД
    assert ui.text_with("обновлено")  # баннер на карточке
    assert ui.text_with("КАРТОЧКА ЗАПИСИ")  # вернулись к карточке
    assert (await fsm_state.get_state()) == InventoryForm.edit_choose_field


async def test_edit_back_to_card_returns_to_card(make_callback, fsm_state, ui, db_path):
    item_id = await _seed_item()
    await fsm_state.update_data(
        editing_item_id=item_id, editing_field="tech", editing_mode="existing"
    )
    await fsm_state.set_state(InventoryForm.entering_tech)

    await edit_back_to_card(make_callback(REGULAR_ID, data="edit_back_to_card"), fsm_state)
    assert ui.text_with("КАРТОЧКА ЗАПИСИ")
    data = await fsm_state.get_data()
    assert data["editing_mode"] is None


# ============================================================
# Удаление из карточки
# ============================================================
async def test_delete_request_shows_confirmation(make_callback, fsm_state, ui, db_path):
    item_id = await _seed_item()
    await _open_card(fsm_state, item_id)

    await edit_delete_request(make_callback(REGULAR_ID, data=f"edit_delete_{item_id}"), fsm_state)
    assert ui.text_with("Удалить запись?")
    assert f"edit_delete_confirm_{item_id}" in ui.last_markup_callbacks()
    assert db.get_item_by_id(item_id)  # ещё жива


async def test_delete_confirm_removes_item(make_callback, fsm_state, ui, db_path):
    item_id = await _seed_item()
    await _open_card(fsm_state, item_id)

    await edit_delete_confirm(
        make_callback(REGULAR_ID, data=f"edit_delete_confirm_{item_id}"), fsm_state
    )
    assert db.get_item_by_id(item_id) is None
    assert ui.text_with("удалена")


async def test_edit_open_item_shows_card(make_callback, fsm_state, ui, db_path):
    item_id = await _seed_item()
    await edit_open_item(make_callback(REGULAR_ID, data=f"edit_open_{item_id}"), fsm_state)
    assert ui.text_with("КАРТОЧКА ЗАПИСИ")
    data = await fsm_state.get_data()
    assert data["editing_item_id"] == item_id
