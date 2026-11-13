"""Экраны админки: меню администрирования, удаление записей
и управление АРМ (список, просмотр, сборка нового АРМ).

Расположение кнопок — исходный дизайн. Из рефакторинга пункта 4
осталась общая клавиатура get_admin_back_keyboard (раньше та же
клавиатура собиралась инлайном в 8 местах handlers/admin)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import CLINICS


def get_admin_back_keyboard():
    """Хвостовой ряд экранов админки: [⬅️ Назад][📋 В меню].

    Раньше эта клавиатура собиралась инлайном в 8 местах handlers/admin.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu"),
                InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu"),
            ]
        ]
    )


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
                InlineKeyboardButton(
                    text="🏷️ По инвентарному номеру", callback_data="admin_delete_by_inv"
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
        ]
    )


def get_arm_menu_keyboard():
    """Меню АРМ: список + создание."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать АРМ", callback_data="admin_arm_create")],
            [InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_arm_menu")],
        ]
    )


def get_arm_list_keyboard(arms):
    """Список существующих АРМ."""
    keyboard = []
    for arm in arms:
        clinic_name = CLINICS.get(arm.get("clinic", ""), arm.get("clinic", "—"))
        cab = arm.get("cabinet") or "—"
        text = f"АРМ #{arm['arm_id']} • {clinic_name} • каб. {cab} • {arm['count']} шт."
        keyboard.append(
            [InlineKeyboardButton(text=text, callback_data=f"admin_arm_view_{arm['arm_id']}")]
        )
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
        keyboard.append(
            [
                InlineKeyboardButton(text=f"🔗 {text}", callback_data=f"edit_open_{item['id']}"),
                InlineKeyboardButton(
                    text="➖ Убрать", callback_data=f"admin_arm_remove_{item['id']}"
                ),
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text="🗑️ Расформировать АРМ", callback_data=f"admin_arm_delete_{arm_id}"
            )
        ]
    )
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
        keyboard.append(
            [InlineKeyboardButton(text=text, callback_data=f"admin_arm_toggle_{item['id']}")]
        )

    keyboard.append(
        [InlineKeyboardButton(text="✅ Создать АРМ", callback_data="admin_arm_confirm_create")]
    )
    keyboard.append([InlineKeyboardButton(text="❌ Отменить", callback_data="admin_arm_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
