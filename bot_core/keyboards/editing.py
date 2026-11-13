"""Экраны поиска и правки существующей записи.

Способ поиска → список найденных записей → карточка записи с кнопками
полей → ввод нового значения → подтверждение удаления.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_core.keyboards._shared import (
    _field_buttons_rows,
    _item_short,
    _two_column_rows,
)
from config import CLINICS


def get_edit_method_keyboard():
    """Выбор способа поиска записи для редактирования"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏷️ По инвентарному номеру", callback_data="edit_method_inv"
                ),
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
    rows = _two_column_rows(
        [(f"{code} — {name}", f"edit_clinic_{code}") for code, name in CLINICS.items()]
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="edit_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def get_edit_record_keyboard(item: dict, item_id: int | None = None):
    """Карточка записи → кнопки для правки каждого поля (как в XLSX).

    item_id нужен для кнопок «Удалить запись». Если item_id не передан,
    пытаемся взять item['id'] (для обратной совместимости).
    Для Dr.Web показываем нормальную подпись вместо «+»/«нет».
    """
    if item_id is None:
        item_id = item.get("id")
    keyboard = _field_buttons_rows(item, "edit_field_")

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
                InlineKeyboardButton(
                    text="✅ Удалить", callback_data=f"edit_delete_confirm_{item_id}"
                ),
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
