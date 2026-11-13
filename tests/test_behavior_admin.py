"""Поведенческие тесты админки (пакет handlers/admin) и аудита.

Меню/статистика/последние записи, удаление по ID и по инв. №, пользователи,
АРМ (создание → просмотр → убрать запись → расформировать), экспорт БД.
"""

from pathlib import Path

import database as db
from bot_core.states import InventoryForm
from handlers.admin.arms import (
    admin_arm_clinic_selected,
    admin_arm_confirm_create,
    admin_arm_create_start,
    admin_arm_delete,
    admin_arm_menu,
    admin_arm_remove_item,
    admin_arm_toggle_item,
    admin_arm_view,
)
from handlers.admin.delete import (
    admin_confirm_delete_id,
    admin_delete_by_id,
    admin_delete_menu,
    admin_execute_delete,
)
from handlers.admin.exports import admin_export_db
from handlers.admin.menu import (
    admin_menu,
    admin_show_records,
    admin_stats,
    admin_view_last,
)
from handlers.admin.users import admin_users
from handlers.audit import audit_menu, audit_results_page, audit_show_category

ADMIN_ID = 111
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


# ============================================================
# Меню и статистика
# ============================================================
async def test_admin_menu_shows_keyboard(make_callback, fsm_state, ui):
    await admin_menu(make_callback(ADMIN_ID, data="admin_menu"), fsm_state)
    assert ui.text_with("Администрирование")
    assert "admin_stats" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) is None  # state сброшен


async def test_admin_menu_denies_regular_user(make_callback, fsm_state, ui):
    await admin_menu(make_callback(REGULAR_ID, data="admin_menu"), fsm_state)
    assert any("запрещ" in a.lower() for a in ui.alerts)
    assert not ui.messages


async def test_admin_stats_counts_by_clinic(make_callback, fsm_state, ui, db_path):
    await _seed_item()
    await _seed_item(inv="INV-101")
    await admin_stats(make_callback(ADMIN_ID, data="admin_stats"), fsm_state)
    assert ui.text_with("Всего записей: 2")
    assert ui.text_with("1 Поликлиника: 2")


async def test_admin_view_last_prompts_for_count(make_callback, fsm_state, ui, db_path):
    await admin_view_last(make_callback(ADMIN_ID, data="admin_view_last"), fsm_state)
    assert ui.text_with("количество записей")
    assert (await fsm_state.get_state()) == InventoryForm.admin_view_count


async def test_admin_show_records_parses_count(make_message, fsm_state, ui, db_path):
    for i in range(3):
        await _seed_item(inv=f"INV-{i}", serial=f"SN-{i}")
    await fsm_state.set_state(InventoryForm.admin_view_count)

    await admin_show_records(make_message(ADMIN_ID, text="2"), fsm_state)
    assert ui.text_with("Последние 2 запис")
    assert (await fsm_state.get_state()) is None


async def test_admin_show_records_garbage_defaults(make_message, fsm_state, ui, db_path):
    await _seed_item()
    await fsm_state.set_state(InventoryForm.admin_view_count)
    await admin_show_records(make_message(ADMIN_ID, text="двадцать"), fsm_state)
    assert ui.text_with("Последние 1 запис")


# ============================================================
# Удаление записи админом
# ============================================================
async def test_admin_delete_by_id_full_flow(make_callback, make_message, fsm_state, ui, db_path):
    item_id = await _seed_item()

    await admin_delete_menu(make_callback(ADMIN_ID, data="admin_delete"), fsm_state)
    assert "admin_delete_by_id" in ui.last_markup_callbacks()

    await admin_delete_by_id(make_callback(ADMIN_ID, data="admin_delete_by_id"), fsm_state)
    assert ui.text_with("Введите ID записи")

    await admin_confirm_delete_id(make_message(ADMIN_ID, text=str(item_id)), fsm_state)
    assert ui.text_with("Удалить запись?")
    assert f"ID: {item_id}" in ui.last_text
    assert "admin_confirm_delete" in ui.last_markup_callbacks()

    await admin_execute_delete(make_callback(ADMIN_ID, data="admin_confirm_delete"), fsm_state)
    assert db.get_item_by_id(item_id) is None
    assert ui.text_with("успешно удалена")


async def test_admin_delete_invalid_id_reprompts(make_message, fsm_state, ui, db_path):
    await fsm_state.set_state(InventoryForm.admin_delete_id)
    await admin_confirm_delete_id(make_message(ADMIN_ID, text="abc"), fsm_state)
    assert ui.text_with("Неверный формат ID")


async def test_admin_delete_not_found(make_message, fsm_state, ui, db_path):
    await fsm_state.set_state(InventoryForm.admin_delete_id)
    await admin_confirm_delete_id(make_message(ADMIN_ID, text="99999"), fsm_state)
    assert ui.text_with("не найдена")


# ============================================================
# Пользователи
# ============================================================
async def test_admin_users_lists_roles(make_callback, fsm_state, ui):
    await admin_users(make_callback(ADMIN_ID, data="admin_users"), fsm_state)
    assert ui.text_with("Администратор")
    assert ui.text_with("Пользователь")
    assert ui.text_with("Всего пользователей")


# ============================================================
# АРМ: полный цикл
# ============================================================
async def test_arm_menu_empty_db(make_callback, fsm_state, ui, db_path):
    await admin_arm_menu(make_callback(ADMIN_ID, data="admin_arm_menu"), fsm_state)
    assert ui.text_with("Нет созданных АРМ")
    assert "admin_arm_create" in ui.last_markup_callbacks()


async def test_arm_create_full_flow(make_callback, fsm_state, ui, db_path):
    id1 = await _seed_item(inv="INV-1", serial="SN-1")
    id2 = await _seed_item(inv="INV-2", serial="SN-2")

    # старт — выбор поликлиники
    await admin_arm_create_start(make_callback(ADMIN_ID, data="admin_arm_create"), fsm_state)
    assert "clinic_1пл" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.admin_arm_select_clinic

    # выбрана поликлиника — список записей без АРМ
    await admin_arm_clinic_selected(make_callback(ADMIN_ID, data="clinic_1пл"), fsm_state)
    assert "admin_arm_toggle_1" in ui.last_markup_callbacks()

    # переключатели: выбрать обе записи
    await admin_arm_toggle_item(make_callback(ADMIN_ID, data=f"admin_arm_toggle_{id1}"), fsm_state)
    data = await fsm_state.get_data()
    assert data["arm_selected_ids"] == [id1]
    await admin_arm_toggle_item(make_callback(ADMIN_ID, data=f"admin_arm_toggle_{id2}"), fsm_state)
    data = await fsm_state.get_data()
    assert set(data["arm_selected_ids"]) == {id1, id2}

    # повторный клик снимает выбор
    await admin_arm_toggle_item(make_callback(ADMIN_ID, data=f"admin_arm_toggle_{id2}"), fsm_state)
    assert (await fsm_state.get_data())["arm_selected_ids"] == [id1]

    # подтверждение — АРМ создан в БД
    await admin_arm_toggle_item(make_callback(ADMIN_ID, data=f"admin_arm_toggle_{id2}"), fsm_state)
    await admin_arm_confirm_create(
        make_callback(ADMIN_ID, data="admin_arm_confirm_create"), fsm_state
    )
    arms = db.get_all_arms()
    assert len(arms) == 1 and arms[0]["count"] == 2
    arm_id = arms[0]["arm_id"]
    assert f"Создан АРМ #{arm_id}" in ui.last_text
    assert db.get_item_by_id(id1)["arm_id"] == arm_id


async def test_arm_clinic_without_free_items(make_callback, fsm_state, ui, db_path):
    # все записи уже в АРМ — свободных нет
    item_id = await _seed_item()
    db.create_arm([item_id])

    await fsm_state.update_data(arm_creating=True)
    await fsm_state.set_state(InventoryForm.admin_arm_select_clinic)
    await admin_arm_clinic_selected(make_callback(ADMIN_ID, data="clinic_1пл"), fsm_state)
    assert ui.text_with("Нет записей без АРМ")


async def test_arm_view_lists_items(make_callback, fsm_state, ui, db_path):
    item_id = await _seed_item()
    arm_id = db.create_arm([item_id])

    await admin_arm_view(make_callback(ADMIN_ID, data=f"admin_arm_view_{arm_id}"), fsm_state)
    assert f"АРМ #{arm_id}" in ui.last_text
    assert f"admin_arm_remove_{item_id}" in ui.last_markup_callbacks()


async def test_arm_remove_item(make_callback, fsm_state, ui, db_path):
    item_id = await _seed_item()
    db.create_arm([item_id])

    await admin_arm_remove_item(
        make_callback(ADMIN_ID, data=f"admin_arm_remove_{item_id}"), fsm_state
    )
    assert db.get_item_by_id(item_id)["arm_id"] is None
    assert ui.text_with("убрана")


async def test_arm_delete_disbands(make_callback, fsm_state, ui, db_path):
    item_id = await _seed_item()
    arm_id = db.create_arm([item_id])

    await admin_arm_delete(make_callback(ADMIN_ID, data=f"admin_arm_delete_{arm_id}"), fsm_state)
    assert db.get_all_arms() == []
    assert db.get_item_by_id(item_id)["arm_id"] is None
    assert ui.text_with("расформирован")


async def test_arm_toggle_bad_callback_alerts(make_callback, fsm_state, ui, db_path):
    await admin_arm_toggle_item(make_callback(ADMIN_ID, data="admin_arm_toggle_abc"), fsm_state)
    assert any("Ошибка" in a for a in ui.alerts)


# ============================================================
# Экспорт БД
# ============================================================
async def test_admin_export_db_sends_document(make_callback, fsm_state, ui, db_path, monkeypatch):
    await _seed_item()
    # экспорт пишет временный файл в CWD — уводим во временный каталог,
    # чтобы не мусорить в репозитории
    tmp_dir = Path(db_path).parent
    monkeypatch.chdir(tmp_dir)

    await admin_export_db(make_callback(ADMIN_ID, data="admin_export_db"), fsm_state)
    assert ui.documents == ["inventory.db"]
    assert not list(tmp_dir.glob("inventory_backup_*.db"))  # временный файл удалён


# ============================================================
# Аудит
# ============================================================
async def test_audit_menu_lists_categories(make_callback, fsm_state, ui, db_path):
    await audit_menu(make_callback(ADMIN_ID, data="audit_menu"), fsm_state)
    assert ui.text_with("Аудиторский фильтр")
    assert "audit_cat_no_ip" in ui.last_markup_callbacks()
    assert (await fsm_state.get_state()) == InventoryForm.audit_select_category


async def test_audit_category_shows_problematic(make_callback, fsm_state, ui, db_path):
    await _seed_item(ip="", pc_name="")  # запись без IP — попадёт в no_ip
    await fsm_state.set_state(InventoryForm.audit_select_category)

    await audit_show_category(make_callback(ADMIN_ID, data="audit_cat_no_ip"), fsm_state)
    assert ui.text_with("Найдено записей: 1")
    assert any(c.startswith("edit_open_") for c in ui.last_markup_callbacks())


async def test_audit_category_clean(make_callback, fsm_state, ui, db_path):
    await _seed_item()  # все поля заполнены — проблем нет
    await fsm_state.set_state(InventoryForm.audit_select_category)
    await audit_show_category(make_callback(ADMIN_ID, data="audit_cat_no_ip"), fsm_state)
    assert ui.text_with("не найдено")


async def test_audit_page_navigation(make_callback, fsm_state, ui, db_path):
    for i in range(12):
        await _seed_item(inv=f"INV-{i}", serial=f"SN-{i}", ip="", pc_name="")
    # первая страница: есть «дальше»; индикатора N/M в исходном дизайне нет
    await audit_results_page(make_callback(ADMIN_ID, data="audit_page_no_ip_0"), fsm_state)
    callbacks = ui.last_markup_callbacks()
    assert "audit_page_no_ip_1" in callbacks  # ➡️ на вторую страницу
    nav_texts = [b.text for row in ui.messages[-1][1].inline_keyboard for b in row]
    assert any("Другая категория" in t for t in nav_texts)  # смена категории из ряда пагинации

    # вторая (последняя) страница: «дальше» нет, есть ⬅️ на первую
    await audit_results_page(make_callback(ADMIN_ID, data="audit_page_no_ip_1"), fsm_state)
    callbacks = ui.last_markup_callbacks()
    assert "audit_page_no_ip_2" not in callbacks  # страниц больше нет
    assert "audit_page_no_ip_0" in callbacks  # ⬅️ на первую


async def test_audit_denies_regular_user(make_callback, fsm_state, ui, db_path):
    await audit_menu(make_callback(REGULAR_ID, data="audit_menu"), fsm_state)
    assert any("запрещ" in a.lower() for a in ui.alerts)
    assert not ui.messages
