from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
from config import CLINICS
from bot_core.constants import (
    DRWEB_CHOICES,
    EDITABLE_FIELDS,
    OS_CHOICES,
    TECH_TYPES,
    display_drweb,
)


def is_admin(chat_id: int) -> bool:
    return chat_id in config.ADMIN_CHAT_IDS


# ============================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================
def get_main_keyboard(chat_id: int = None):
    keyboard = [
        [
            InlineKeyboardButton(text="📋 Начать инвентаризацию", callback_data="start_inventory"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data="start_edit"),
        ],
    ]
    if chat_id and is_admin(chat_id):
        keyboard.append([InlineKeyboardButton(text="⚙️ Администрирование", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ============================================================
# ВВОД НОВОЙ ЗАПИСИ
# ============================================================
def get_clinic_keyboard():
    rows = []
    clinic_list = list(CLINICS.items())
    for i in range(0, len(clinic_list), 2):
        row = [
            InlineKeyboardButton(
                text=f"{clinic_list[i][0]} — {clinic_list[i][1]}",
                callback_data=f"clinic_{clinic_list[i][0]}",
            )
        ]
        if i + 1 < len(clinic_list):
            row.append(
                InlineKeyboardButton(
                    text=f"{clinic_list[i + 1][0]} — {clinic_list[i + 1][1]}",
                    callback_data=f"clinic_{clinic_list[i + 1][0]}",
                )
            )
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_process")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_tech_type_keyboard():
    keyboard = []
    tech_list = list(TECH_TYPES.items())
    for i in range(0, len(tech_list), 2):
        row = [
            InlineKeyboardButton(text=tech_list[i][1]["name"], callback_data=f"tech_type_{tech_list[i][0]}")
        ]
        if i + 1 < len(tech_list):
            row.append(
                InlineKeyboardButton(text=tech_list[i + 1][1]["name"], callback_data=f"tech_type_{tech_list[i + 1][0]}")
            )
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_process")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_skip_cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process"),
            ]
        ]
    )


def get_nav_keyboard(*, can_back: bool, can_skip: bool, can_absent: bool = False):
    """can_absent — показывать кнопку «Отсутствует» (для инв. и серийного номера)"""
    row = []
    if can_back:
        row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_prev_step"))
    if can_absent:
        row.append(InlineKeyboardButton(text="❓ Отсутствует", callback_data="field_absent"))
    if can_skip:
        row.append(InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field"))
    row.append(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


# ============================================================
# ВЫБОР Dr.Web
# ============================================================
def get_drweb_choice_keyboard():
    """Inline-меню выбора статуса Dr.Web. Без сокращений, без «+».
    Кнопки: Установлен / Нет лицензии / Нет соединения с сервером / Не установлен +
    Пропустить + Назад.
    """
    rows = []
    # По 1 кнопке в ряд — длинные подписи
    for key, (label, _value) in DRWEB_CHOICES.items():
        rows.append([InlineKeyboardButton(text=label, callback_data=f"drweb_choice_{key}")])

    rows.append([
        InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field"),
    ])
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_prev_step"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# ВЫБОР ОПЕРАЦИОННОЙ СИСТЕМЫ
# ============================================================
def get_os_choice_keyboard():
    """Inline-меню выбора ОС. 8 вариантов в 2 колонки + «Другая ОС».
    """
    rows = []
    keys = list(OS_CHOICES.keys())
    # Все кнопки, кроме "other" — по 2 в ряд
    main_keys = [k for k in keys if k != "other"]
    for i in range(0, len(main_keys), 2):
        row = []
        for j in range(2):
            if i + j < len(main_keys):
                key = main_keys[i + j]
                row.append(InlineKeyboardButton(
                    text=OS_CHOICES[key],
                    callback_data=f"os_choice_{key}",
                ))
        rows.append(row)

    # «Другая ОС» — в отдельном ряду
    rows.append([InlineKeyboardButton(
        text="🔧 Другая ОС",
        callback_data="os_choice_other",
    )])
    # Пропустить + Назад
    rows.append([
        InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field"),
    ])
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_prev_step"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# КАРТОЧКА НОВОЙ ЗАПИСИ (перед сохранением) — выбор поля для правки
# ============================================================
def _format_field_value_for_button(field_key: str, value) -> str:
    """Форматирует значение для показа в кнопке карточки/редактирования.
    Для Dr.Web применяет display_drweb.
    """
    raw = str(value or "")
    if not raw:
        return "—"
    if field_key == "drweb":
        return display_drweb(raw)
    return raw


def get_confirm_edit_keyboard(data: dict):
    """Карточка "проверьте данные" → кнопки для правки каждого поля.

    Список полей берём из EDITABLE_FIELDS (constants.py).
    Для Dr.Web показываем нормальную подпись вместо «+»/«нет».
    """
    keyboard = []
    for i in range(0, len(EDITABLE_FIELDS), 2):
        row = []
        for j in range(2):
            if i + j < len(EDITABLE_FIELDS):
                field_key, label = EDITABLE_FIELDS[i + j]
                value = _format_field_value_for_button(field_key, data.get(field_key, ""))
                if value != "—" and len(value) > 20:
                    btn_text = f"{label} ({value[:20]}...)"
                elif value != "—":
                    btn_text = f"{label} ({value})"
                else:
                    btn_text = f"{label} (—)"
                row.append(InlineKeyboardButton(text=btn_text, callback_data=f"review_field_{field_key}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton(text="✅ Подтвердить и сохранить", callback_data="confirm_save")])
    keyboard.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_after_save_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Ввести ещё", callback_data="new_inventory"),
                InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu"),
            ]
        ]
    )


# ============================================================
# РЕДАКТИРОВАНИЕ СУЩЕСТВУЮЩЕЙ ЗАПИСИ
# ============================================================
def get_edit_method_keyboard():
    """Выбор способа поиска записи для редактирования"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏷️ По инвентарному номеру", callback_data="edit_method_inv"),
                InlineKeyboardButton(text="🔢 По ID", callback_data="edit_method_id"),
            ],
            [
                InlineKeyboardButton(text="🏥 По поликлинике", callback_data="edit_method_clinic"),
                InlineKeyboardButton(text="💻 По имени компьютера", callback_data="edit_method_pc"),
            ],
            [InlineKeyboardButton(text="🔍 Глобальный поиск", callback_data="edit_method_global")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")],
        ]
    )


def get_edit_back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="edit_start")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")],
        ]
    )


def get_edit_clinic_keyboard():
    """Выбор поликлиники для отображения списка записей"""
    rows = []
    clinic_list = list(CLINICS.items())
    for i in range(0, len(clinic_list), 2):
        row = [
            InlineKeyboardButton(
                text=f"{clinic_list[i][0]} — {clinic_list[i][1]}",
                callback_data=f"edit_clinic_{clinic_list[i][0]}",
            )
        ]
        if i + 1 < len(clinic_list):
            row.append(
                InlineKeyboardButton(
                    text=f"{clinic_list[i + 1][0]} — {clinic_list[i + 1][1]}",
                    callback_data=f"edit_clinic_{clinic_list[i + 1][0]}",
                )
            )
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="edit_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _item_short(item: dict) -> str:
    """Короткое описание записи для кнопок списка"""
    inv = item.get("inv_number") or "—"
    if len(inv) > 14:
        inv = inv[:14] + "…"
    cab = item.get("cabinet") or "—"
    tech = item.get("tech") or "—"
    if len(tech) > 18:
        tech = tech[:18] + "…"
    return f"#{item['id']} • {inv} • {cab} • {tech}"


def get_edit_items_keyboard(items, page: int = 0, total: int = 0, page_size: int = 10):
    """Список записей для выбора при редактировании"""
    keyboard = []
    for item in items:
        keyboard.append(
            [InlineKeyboardButton(text=_item_short(item), callback_data=f"edit_open_{item['id']}")]
        )

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"edit_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text="🔍 Новый поиск", callback_data="edit_start"))
    if (page + 1) * page_size < total:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"edit_page_{page + 1}"))
    keyboard.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_record_keyboard(item: dict, item_id: int = None):
    """Карточка записи → кнопки для правки каждого поля (как в XLSX).

    item_id нужен для кнопок «Удалить запись». Если item_id не передан,
    пытаемся взять item['id'] (для обратной совместимости).
    Для Dr.Web показываем нормальную подпись вместо «+»/«нет».
    """
    if item_id is None:
        item_id = item.get("id")
    keyboard = []
    for i in range(0, len(EDITABLE_FIELDS), 2):
        row = []
        for j in range(2):
            if i + j < len(EDITABLE_FIELDS):
                field_key, label = EDITABLE_FIELDS[i + j]
                value = _format_field_value_for_button(field_key, item.get(field_key, ""))
                if value != "—" and len(value) > 20:
                    btn_text = f"{label} ({value[:20]}...)"
                elif value != "—":
                    btn_text = f"{label} ({value})"
                else:
                    btn_text = f"{label} (—)"
                row.append(InlineKeyboardButton(text=btn_text, callback_data=f"edit_field_{field_key}"))
        keyboard.append(row)

    delete_cb = f"edit_delete_{item_id}" if item_id is not None else "edit_delete_0"
    keyboard.append([InlineKeyboardButton(text="🗑️ Удалить запись", callback_data=delete_cb)])
    keyboard.append([InlineKeyboardButton(text="⬅️ К списку", callback_data="edit_back_to_list")])
    keyboard.append([InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_field_input_keyboard():
    """Клавиатура во время ввода нового значения поля"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к карточке", callback_data="edit_back_to_card")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")],
        ]
    )


def get_edit_delete_confirm_keyboard(item_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Удалить", callback_data=f"edit_delete_confirm_{item_id}"),
                InlineKeyboardButton(text="❌ Не удалять", callback_data="edit_back_to_card"),
            ]
        ]
    )


def get_edit_after_action_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Другая запись", callback_data="edit_start"),
                InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu"),
            ]
        ]
    )


# ============================================================
# ПОДТВЕРЖДЕНИЕ ДУБЛИКАТОВ / НЕСОВПАДЕНИЯ MAC
# ============================================================
def get_duplicate_inv_keyboard():
    """Инвентарный номер уже есть в БД — это может быть АРМ (нормально)
    или дубликат (ошибка). Не блокируем, просто уточняем.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Продолжить (это АРМ)", callback_data="confirm_inv_continue"),
                InlineKeyboardButton(text="❌ Ввести заново", callback_data="confirm_inv_cancel"),
            ],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")],
        ]
    )


def get_duplicate_serial_keyboard():
    """Серийный номер уже есть в БД — почти всегда ошибка (серийник уникален).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Продолжить всё равно", callback_data="confirm_serial_continue"),
                InlineKeyboardButton(text="❌ Ввести заново", callback_data="confirm_serial_cancel"),
            ],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")],
        ]
    )


def get_mac_mismatch_keyboard():
    """Физический MAC ≠ реальному MAC — должно совпадать по нормативу.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Продолжить", callback_data="mac_mismatch_continue")],
            [InlineKeyboardButton(text="✏️ Ввести реальный MAC заново", callback_data="mac_mismatch_reenter")],
            [InlineKeyboardButton(text="⏭️ Пропустить реальный MAC", callback_data="mac_mismatch_skip")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")],
        ]
    )


# ============================================================
# ПОДТВЕРЖДЕНИЕ ВЫХОДА ВО ВРЕМЯ ВВОДА
# ============================================================
def get_exit_confirm_keyboard():
    """Спрашиваем «точно выйти? есть несохранённые данные»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑️ Да, выйти (потерять данные)", callback_data="confirm_exit_yes"),
                InlineKeyboardButton(text="✏️ Продолжить ввод", callback_data="confirm_exit_no"),
            ],
        ]
    )


# ============================================================
# АУДИТОРСКИЙ ФИЛЬТР
# ============================================================
AUDIT_CATEGORIES = [
    ("no_pc_name",    "💻 Без имени компьютера"),
    ("no_ip",         "🌐 Без IP-адреса"),
    ("no_mac",        "📡 Без MAC-адресов"),
    ("drweb_problem", "🛡️ Dr.Web: проблема"),
    ("mac_mismatch",  "⚠️ Физ. MAC ≠ Реал. MAC"),
    ("no_specs",      "⚙️ Без характеристик"),
]


def get_audit_keyboard():
    """Меню категорий аудиторского фильтра."""
    rows = []
    for key, label in AUDIT_CATEGORIES:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"audit_cat_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_audit_results_keyboard(items, total: int, category: str, page: int = 0, page_size: int = 10):
    """Список найденных проблемных записей."""
    keyboard = []
    for item in items:
        keyboard.append(
            [InlineKeyboardButton(text=_item_short(item), callback_data=f"edit_open_{item['id']}")]
        )

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"audit_page_{category}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text="🔍 Другая категория", callback_data="audit_menu"))
    if (page + 1) * page_size < total:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"audit_page_{category}_{page + 1}"))
    keyboard.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ============================================================
# АДМИНКА
# ============================================================
def get_admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика базы", callback_data="admin_stats"),
                InlineKeyboardButton(text="📋 Последние записи", callback_data="admin_view_last"),
            ],
            [
                InlineKeyboardButton(text="🔗 АРМ", callback_data="admin_arm_menu"),
                InlineKeyboardButton(text="🔍 Проблемные записи", callback_data="audit_menu"),
            ],
            [
                InlineKeyboardButton(text="🗑️ Удалить запись", callback_data="admin_delete"),
                InlineKeyboardButton(text="💾 Скачать базу", callback_data="admin_export_db"),
            ],
            [
                InlineKeyboardButton(text="📊 Скачать Excel", callback_data="admin_export_excel"),
                InlineKeyboardButton(text="📥 Импорт из Excel", callback_data="admin_import_excel"),
            ],
            [
                InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
        ]
    )


def get_delete_method_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 По ID", callback_data="admin_delete_by_id"),
                InlineKeyboardButton(text="🏷️ По инвентарному номеру", callback_data="admin_delete_by_inv"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
        ]
    )


# ============================================================
# АРМ (Автоматизированное рабочее место)
# ============================================================
def get_arm_menu_keyboard():
    """Меню АРМ: список + создание."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать АРМ", callback_data="admin_arm_create")],
            [InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_menu")],
        ]
    )


def get_arm_list_keyboard(arms):
    """Список существующих АРМ."""
    keyboard = []
    from config import CLINICS
    for arm in arms:
        clinic_name = CLINICS.get(arm.get("clinic", ""), arm.get("clinic", "—"))
        cab = arm.get("cabinet") or "—"
        text = f"АРМ #{arm['arm_id']} • {clinic_name} • каб. {cab} • {arm['count']} шт."
        keyboard.append([
            InlineKeyboardButton(text=text, callback_data=f"admin_arm_view_{arm['arm_id']}")
        ])
    keyboard.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_arm_view_keyboard(arm_id, items):
    """Просмотр конкретного АРМ — список записей + управление."""
    keyboard = []
    for item in items:
        tech_short = item.get("tech", "—")
        if len(tech_short) > 20:
            tech_short = tech_short[:20] + "…"
        inv = item.get("inv_number") or "—"
        text = f"#{item['id']} • {tech_short} • {inv}"
        keyboard.append([
            InlineKeyboardButton(text=f"🔗 {text}", callback_data=f"edit_open_{item['id']}"),
            InlineKeyboardButton(text="➖ Убрать", callback_data=f"admin_arm_remove_{item['id']}"),
        ])

    keyboard.append([InlineKeyboardButton(text="🗑️ Расформировать АРМ", callback_data=f"admin_arm_delete_{arm_id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ К списку АРМ", callback_data="admin_arm_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_arm_select_items_keyboard(items, selected_ids: set, clinic: str = ""):
    """Выбор записей для создания АРМ — переключатели."""
    keyboard = []
    for item in items:
        tech_short = item.get("tech", "—")
        if len(tech_short) > 25:
            tech_short = tech_short[:25] + "…"
        inv = item.get("inv_number") or "—"
        is_selected = item["id"] in selected_ids
        prefix = "✅" if is_selected else "⬜"
        text = f"{prefix} #{item['id']} • {tech_short} • {inv}"
        keyboard.append([
            InlineKeyboardButton(text=text, callback_data=f"admin_arm_toggle_{item['id']}")
        ])

    keyboard.append([InlineKeyboardButton(text="✅ Создать АРМ", callback_data="admin_arm_confirm_create")])
    keyboard.append([InlineKeyboardButton(text="❌ Отменить", callback_data="admin_arm_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
