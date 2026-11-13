"""Экраны аудиторского фильтра: меню категорий и список проблемных записей."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_core.keyboards._shared import _item_short

AUDIT_CATEGORIES = [
    ("no_pc_name", "💻 Без имени компьютера"),
    ("no_ip", "🌐 Без IP-адреса"),
    ("no_mac", "📡 Без MAC-адресов"),
    ("drweb_problem", "🛡️ Dr.Web: проблема"),
    ("mac_mismatch", "⚠️ Физ. MAC ≠ Реал. MAC"),
    ("no_specs", "⚙️ Без характеристик"),
]


def get_audit_keyboard():
    """Меню категорий аудиторского фильтра."""
    rows = []
    for key, label in AUDIT_CATEGORIES:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"audit_cat_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_audit_results_keyboard(
    items, total: int, category: str, page: int = 0, page_size: int = 10
):
    """Список найденных проблемных записей."""
    keyboard = []
    for item in items:
        keyboard.append(
            [InlineKeyboardButton(text=_item_short(item), callback_data=f"edit_open_{item['id']}")]
        )

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"audit_page_{category}_{page - 1}")
        )
    nav_row.append(InlineKeyboardButton(text="🔍 Другая категория", callback_data="audit_menu"))
    if (page + 1) * page_size < total:
        nav_row.append(
            InlineKeyboardButton(text="➡️", callback_data=f"audit_page_{category}_{page + 1}")
        )
    keyboard.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
