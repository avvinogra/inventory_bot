from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
from config import CLINICS
from bot_core.constants import TECH_TYPES


def is_admin(chat_id: int) -> bool:
    return chat_id in config.ADMIN_CHAT_IDS


def get_main_keyboard(chat_id: int = None):
    keyboard = [
        [
            InlineKeyboardButton(text="📋 Начать инвентаризацию", callback_data="start_inventory"),
            InlineKeyboardButton(text="🏷️ Печать штрих-кода", callback_data="print_barcode"),
        ],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="start_edit")],
    ]
    if chat_id and is_admin(chat_id):
        keyboard.append([InlineKeyboardButton(text="⚙️ Администрирование", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_clinic_keyboard():
    rows = []
    clinic_list = list(CLINICS.items())
    for i in range(0, len(clinic_list), 2):
        row = [
            InlineKeyboardButton(
                text=f"{clinic_list[i][0]} - {clinic_list[i][1]}",
                callback_data=f"clinic_{clinic_list[i][0]}",
            )
        ]
        if i + 1 < len(clinic_list):
            row.append(
                InlineKeyboardButton(
                    text=f"{clinic_list[i + 1][0]} - {clinic_list[i + 1][1]}",
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


def get_nav_keyboard(*, can_back: bool, can_skip: bool):
    row = []
    if can_back:
        row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_prev_step"))
    if can_skip:
        row.append(InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field"))
    row.append(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def get_print_input_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="print_barcode"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process"),
            ]
        ]
    )


def get_print_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 Последний", callback_data="print_last_label"),
                InlineKeyboardButton(text="📂 Последние 10", callback_data="print_recent_10"),
            ],
            [
                InlineKeyboardButton(text="🏥 По поликлинике", callback_data="print_by_clinic"),
                InlineKeyboardButton(text="📑 Несколько", callback_data="print_multiple_labels"),
            ],
            [
                InlineKeyboardButton(text="🔍 По ИНВ номеру", callback_data="print_by_inv"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu"),
            ],
        ]
    )


def get_after_print_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏷️ Ещё печать", callback_data="print_barcode"),
                InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu"),
            ]
        ]
    )


def get_recent_items_keyboard(items, page=0):
    keyboard = []
    for item in items:
        inv_short = item["inv_number"][:12] + "..." if len(item["inv_number"]) > 12 else item["inv_number"]
        tech_short = item["tech"][:20] if len(item["tech"]) > 20 else item["tech"]
        keyboard.append(
            [InlineKeyboardButton(text=f"🏷️ {inv_short} | {tech_short}", callback_data=f"print_item_{item['id']}")]
        )

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Страница", callback_data=f"print_recent_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text="⬅️ В меню печати", callback_data="print_barcode"))
    if len(items) == 10:
        nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"print_recent_page_{page + 1}"))
    keyboard.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_clinic_print_keyboard():
    rows = []
    clinic_list = list(CLINICS.items())
    for i in range(0, len(clinic_list), 2):
        row = [
            InlineKeyboardButton(
                text=f"{clinic_list[i][0]} - {clinic_list[i][1]}",
                callback_data=f"print_clinic_{clinic_list[i][0]}",
            )
        ]
        if i + 1 < len(clinic_list):
            row.append(
                InlineKeyboardButton(
                    text=f"{clinic_list[i + 1][0]} - {clinic_list[i + 1][1]}",
                    callback_data=f"print_clinic_{clinic_list[i + 1][0]}",
                )
            )
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="print_barcode")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_items_from_clinic_keyboard(items, page=0):
    keyboard = []
    for item in items:
        inv_short = item["inv_number"][:12] + "..." if len(item["inv_number"]) > 12 else item["inv_number"]
        text = f"🏷️ {inv_short} | {item['cabinet']} | {item['tech'][:15]}"
        keyboard.append([InlineKeyboardButton(text=text, callback_data=f"print_item_{item['id']}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Страница", callback_data=f"print_clinic_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text="⬅️ В меню печати", callback_data="print_barcode"))
    if len(items) == 15:
        nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"print_clinic_page_{page + 1}"))
    keyboard.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика БД", callback_data="admin_stats"),
                InlineKeyboardButton(text="📋 Последние записи", callback_data="admin_view_last"),
            ],
            [
                InlineKeyboardButton(text="🗑️ Удалить запись", callback_data="admin_delete"),
                InlineKeyboardButton(text="💾 Скачать БД", callback_data="admin_export_db"),
            ],
            [
                InlineKeyboardButton(text="📊 Скачать Excel", callback_data="admin_export_excel"),
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
                InlineKeyboardButton(text="🏷️ По ИНВ номеру", callback_data="admin_delete_by_inv"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
        ]
    )


def get_confirm_edit_keyboard(data: dict):
    keyboard = []
    field_buttons = [
        ("🏢 Кабинет", "cabinet"),
        ("🔧 Техника", "tech"),
        ("🔢 Сер. номер", "serial"),
        ("🏷️ ИНВ номер", "inv"),
        ("🌐 IP", "ip"),
        ("📡 MAC", "mac"),
        ("🖥️ ОС", "os"),
        ("🛡️ Dr.Web", "drweb"),
        ("📄 Office", "office"),
        ("💬 Примечание", "note"),
    ]

    for i in range(0, len(field_buttons), 2):
        row = []
        for j in range(2):
            if i + j < len(field_buttons):
                text, field = field_buttons[i + j]
                value = str(data.get(field, ""))
                if value and len(value) > 15:
                    btn_text = f"{text} ({value[:15]}...)"
                elif value:
                    btn_text = f"{text} ({value})"
                else:
                    btn_text = f"{text} (—)"
                row.append(InlineKeyboardButton(text=btn_text, callback_data=f"edit_field_{field}"))
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

