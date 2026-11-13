"""Структурные инварианты клавиатур (пакет bot_core.keyboards, фаза 4).

Билдеры клавиатур — чистые функции: проверяем сетку, подписи и
callback-данные кнопок, которые парсят хендлеры. Сломанный callback
(например переименованный префикс) роняет хендлер молча — эти тесты
ловят его дёшево, без Telegram.

Расположение кнопок — исходный дизайн (компактные 2-колоночные сетки,
навигация одним рядом). Из редизайна закреплены только точечные
исправления: имя типа техники вместо кода «pc», уникальные иконки типов.
"""

import config
from bot_core.constants import (
    DRWEB_CHOICES,
    EDITABLE_FIELDS,
    OS_CHOICES,
    TECH_TYPES,
)
from bot_core.keyboards import (
    AUDIT_CATEGORIES,
    get_admin_keyboard,
    get_after_save_keyboard,
    get_arm_after_save_keyboard,
    get_arm_list_keyboard,
    get_arm_menu_keyboard,
    get_arm_mode_keyboard,
    get_arm_select_items_keyboard,
    get_arm_view_keyboard,
    get_audit_keyboard,
    get_audit_results_keyboard,
    get_clinic_keyboard,
    get_confirm_edit_keyboard,
    get_delete_method_keyboard,
    get_drweb_choice_keyboard,
    get_duplicate_inv_keyboard,
    get_duplicate_serial_keyboard,
    get_edit_clinic_keyboard,
    get_edit_items_keyboard,
    get_edit_method_keyboard,
    get_edit_record_keyboard,
    get_exit_confirm_keyboard,
    get_mac_mismatch_keyboard,
    get_main_keyboard,
    get_nav_keyboard,
    get_os_choice_keyboard,
    get_skip_cancel_keyboard,
    get_tech_type_keyboard,
)
from config import CLINICS


def _buttons(keyboard):
    return [b for row in keyboard.inline_keyboard for b in row]


def _texts(keyboard):
    return [b.text for b in _buttons(keyboard)]


def _callbacks(keyboard):
    return [b.callback_data for b in _buttons(keyboard)]


# ============================================================
# Экран «ввод новой записи»: клиника / тип / АРМ
# ============================================================
def test_clinic_keyboard_has_all_clinics_and_two_columns():
    kb = get_clinic_keyboard()
    for code in CLINICS:
        assert f"clinic_{code}" in _callbacks(kb)
    assert "cancel_process" in _callbacks(kb)
    for row in kb.inline_keyboard[:-1]:  # последний ряд — отмена из 1 кнопки
        assert len(row) <= 2


def test_tech_type_keyboard_has_all_types():
    kb = get_tech_type_keyboard()
    for key in TECH_TYPES:
        assert f"tech_type_{key}" in _callbacks(kb)
    assert "cancel_process" in _callbacks(kb)
    # уникальные иконки: раньше «Системный блок» и «Ноутбук» делили 💻
    icons = [t.split(" ", 1)[0] for t in _texts(kb) if " " in t]
    assert len(icons) == len(set(icons))


def test_arm_mode_and_after_save_keyboards():
    assert _callbacks(get_arm_mode_keyboard())[:2] == ["arm_mode_yes", "arm_mode_no"]
    after_save = _callbacks(get_arm_after_save_keyboard())
    assert "arm_add_another" in after_save and "arm_finish" in after_save


def test_skip_cancel_and_nav_keyboards():
    assert set(_callbacks(get_skip_cancel_keyboard())) == {"skip_current_field", "cancel_process"}

    # навигация: [Назад][Пропустить] парой, «Отсутствует» и «Отменить» —
    # отдельными строками на всю ширину (в общем ряду обрезались)
    nav_full = get_nav_keyboard(can_back=True, can_skip=True, can_absent=True)
    assert [[b.callback_data for b in row] for row in nav_full.inline_keyboard] == [
        ["back_prev_step", "skip_current_field"],
        ["field_absent"],
        ["cancel_process"],
    ]
    nav_min = get_nav_keyboard(can_back=False, can_skip=False)
    assert [[b.callback_data for b in row] for row in nav_min.inline_keyboard] == [
        ["cancel_process"],
    ]


# ============================================================
# Выбор Dr.Web / ОС
# ============================================================
def test_drweb_choice_keyboard_covers_all_statuses():
    kb = get_drweb_choice_keyboard()
    for key in DRWEB_CHOICES:
        assert f"drweb_choice_{key}" in _callbacks(kb)
    assert "skip_current_field" in _callbacks(kb)
    assert "back_prev_step" in _callbacks(kb)
    # по 1 кнопке в ряд — подписи длинные
    assert all(len(row) == 1 for row in kb.inline_keyboard)


def test_os_choice_keyboard_two_columns_and_other():
    kb = get_os_choice_keyboard()
    for key in OS_CHOICES:
        assert f"os_choice_{key}" in _callbacks(kb)
    # «Другая ОС» — отдельный ряд
    other_row = next(
        row
        for row in kb.inline_keyboard
        if len(row) == 1 and row[0].callback_data == "os_choice_other"
    )
    assert other_row[0].text == "🔧 Другая ОС"
    # основные кнопки — по 2 в ряд
    main_rows = [
        row for row in kb.inline_keyboard if row and row[0].callback_data != "os_choice_other"
    ]
    assert all(len(row) == 2 for row in main_rows[:-2])  # кроме «Пропустить»/«Назад»


# ============================================================
# Карточка «проверьте данные» и карточка записи
# ============================================================
def test_confirm_edit_keyboard_all_fields_with_values():
    data = {"cabinet": "101", "tech": "Dell OptiPlex 3090 с очень длинным названием модели"}
    kb = get_confirm_edit_keyboard(data)
    callbacks = _callbacks(kb)
    for field_key, _label in EDITABLE_FIELDS:
        assert f"review_field_{field_key}" in callbacks
    assert "confirm_save" in callbacks and "cancel_process" in callbacks

    texts = _texts(kb)
    assert any("101" in t for t in texts)  # значение подставлено
    assert any(t.endswith("...)") for t in texts)  # длинное значение обрезано
    assert any("(—)" in t for t in texts)  # пустое поле


def test_confirm_edit_keyboard_drweb_uses_display_map():
    kb = get_confirm_edit_keyboard({"drweb": "+"})
    assert any("Установлен" in t for t in _texts(kb))  # legacy «+» → человекочитаемо


def test_field_buttons_show_tech_type_name_not_raw_code():
    # в кнопке «Тип» — человекочитаемое имя, а не сырой код «pc» из state/БД
    kb = get_confirm_edit_keyboard({"tech_type": "pc"})
    type_button = next(b for b in _buttons(kb) if b.callback_data == "review_field_tech_type")
    assert "Системный блок" in type_button.text
    assert "(pc)" not in type_button.text


def test_edit_record_keyboard_prefix_and_delete():
    item = {"id": 7, "cabinet": "5", "tech": "HP", "drweb": "нет"}
    kb = get_edit_record_keyboard(item)
    callbacks = _callbacks(kb)
    for field_key, _label in EDITABLE_FIELDS:
        assert f"edit_field_{field_key}" in callbacks
    assert "edit_delete_7" in callbacks
    assert "edit_back_to_list" in callbacks

    # явный item_id приоритетнее item["id"]
    kb2 = get_edit_record_keyboard({"id": 7}, item_id=99)
    assert "edit_delete_99" in _callbacks(kb2)


def test_edit_items_keyboard_pagination():
    items = [{"id": i, "inv_number": f"INV-{i}", "cabinet": "1", "tech": "T"} for i in range(3)]
    kb_first = get_edit_items_keyboard(items, page=0, total=25, page_size=10)
    nav = [b.callback_data for b in kb_first.inline_keyboard[-1]]
    assert nav[0] == "edit_start" and nav[1] == "edit_page_1"  # первая страница: без «⬅️»
    assert all(f"edit_open_{i}" in _callbacks(kb_first) for i in range(3))

    kb_mid = get_edit_items_keyboard(items, page=2, total=35, page_size=10)
    nav = [b.callback_data for b in kb_mid.inline_keyboard[-1]]
    assert nav == ["edit_page_1", "edit_start", "edit_page_3"]

    kb_last = get_edit_items_keyboard(items, page=2, total=21, page_size=10)
    nav = [b.callback_data for b in kb_last.inline_keyboard[-1]]
    assert nav == ["edit_page_1", "edit_start"]  # дальше страниц нет


def test_edit_clinic_keyboard_and_method_keyboard():
    kb = get_edit_clinic_keyboard()
    for code in CLINICS:
        assert f"edit_clinic_{code}" in _callbacks(kb)
    assert "edit_start" in _callbacks(kb)

    method_callbacks = set(_callbacks(get_edit_method_keyboard()))
    assert {
        "edit_method_inv",
        "edit_method_id",
        "edit_method_clinic",
        "edit_method_pc",
        "edit_method_global",
        "back_to_menu",
    } <= method_callbacks


# ============================================================
# Предупреждения: дубликаты и MAC
# ============================================================
def test_duplicate_and_mac_mismatch_keyboards():
    inv = set(_callbacks(get_duplicate_inv_keyboard()))
    assert {"confirm_inv_continue", "confirm_inv_cancel", "cancel_process"} <= inv

    serial = set(_callbacks(get_duplicate_serial_keyboard()))
    assert {"confirm_serial_continue", "confirm_serial_cancel", "cancel_process"} <= serial

    mac = _callbacks(get_mac_mismatch_keyboard())
    assert {
        "mac_mismatch_continue",
        "mac_mismatch_reenter",
        "mac_mismatch_skip",
        "cancel_process",
    } == set(mac)


# ============================================================
# Меню
# ============================================================
def test_main_keyboard_admin_button(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_CHAT_IDS", {111})
    kb_admin = get_main_keyboard(111)
    assert any("Администрирование" in t for t in _texts(kb_admin))

    kb_user = get_main_keyboard(222)
    assert not any("Администрирование" in t for t in _texts(kb_user))
    assert "start_inventory" in _callbacks(kb_user)


def test_after_save_and_exit_confirm_keyboards():
    after = _callbacks(get_after_save_keyboard())
    assert after == ["new_inventory", "back_to_menu"]
    exit_kb = _callbacks(get_exit_confirm_keyboard())
    assert exit_kb == ["confirm_exit_yes", "confirm_exit_no"]


# ============================================================
# Аудит
# ============================================================
def test_audit_keyboards():
    kb = get_audit_keyboard()
    for key, _label in AUDIT_CATEGORIES:
        assert f"audit_cat_{key}" in _callbacks(kb)
    assert "admin_menu" in _callbacks(kb)
    assert len(AUDIT_CATEGORIES) == 6

    items = [{"id": 1, "inv_number": "X", "cabinet": "1", "tech": "T"}]
    kb_res = get_audit_results_keyboard(items, total=15, category="no_ip", page=0, page_size=10)
    nav = [b.callback_data for b in kb_res.inline_keyboard[-1]]
    assert nav == ["audit_menu", "audit_page_no_ip_1"]


# ============================================================
# Админка и АРМ
# ============================================================
def test_admin_and_delete_method_keyboards():
    admin_callbacks = set(_callbacks(get_admin_keyboard()))
    assert {
        "admin_stats",
        "admin_view_last",
        "admin_arm_menu",
        "audit_menu",
        "admin_delete",
        "admin_export_db",
        "admin_export_excel",
        "admin_import_excel",
        "admin_users",
        "back_to_menu",
    } <= admin_callbacks

    del_callbacks = set(_callbacks(get_delete_method_keyboard()))
    assert {"admin_delete_by_id", "admin_delete_by_inv", "admin_menu"} <= del_callbacks


def test_arm_keyboards():
    assert "admin_arm_create" in _callbacks(get_arm_menu_keyboard())

    arms = [{"arm_id": 3, "clinic": "1пл", "cabinet": "12", "count": 2}]
    kb_list = get_arm_list_keyboard(arms)
    assert "admin_arm_view_3" in _callbacks(kb_list)
    assert any("АРМ #3" in t for t in _texts(kb_list))

    items = [
        {"id": 10, "tech": "Dell", "inv_number": "INV-10"},
        {"id": 11, "tech": "HP", "inv_number": None},
    ]
    kb_view = get_arm_view_keyboard(3, items)
    view_callbacks = _callbacks(kb_view)
    assert "edit_open_10" in view_callbacks and "admin_arm_remove_10" in view_callbacks
    assert "admin_arm_remove_11" in view_callbacks  # кнопка «Убрать» и без инв. номера
    assert "admin_arm_delete_3" in view_callbacks and "admin_arm_menu" in view_callbacks

    kb_select = get_arm_select_items_keyboard(items, selected_ids={10})
    select_callbacks = _callbacks(kb_select)
    assert "admin_arm_toggle_10" in select_callbacks and "admin_arm_toggle_11" in select_callbacks
    texts = _texts(kb_select)
    assert any(t.startswith("✅") for t in texts) and any(t.startswith("⬜") for t in texts)
    assert "admin_arm_confirm_create" in select_callbacks
