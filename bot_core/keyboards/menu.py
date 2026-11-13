"""Экраны главного меню: меню после /start, «что дальше» после сохранения,
подтверждение выхода во время ввода."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_core.access import is_admin


def get_main_keyboard(chat_id: int | None = None):
    keyboard = [
        [
            InlineKeyboardButton(text="📋 Начать инвентаризацию", callback_data="start_inventory"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data="start_edit"),
        ],
    ]
    if chat_id and is_admin(chat_id):
        keyboard.append(
            [InlineKeyboardButton(text="⚙️ Администрирование", callback_data="admin_menu")]
        )
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


def get_exit_confirm_keyboard():
    """Спрашиваем «точно выйти? есть несохранённые данные»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑️ Да, выйти (потерять данные)", callback_data="confirm_exit_yes"
                ),
                InlineKeyboardButton(text="✏️ Продолжить ввод", callback_data="confirm_exit_no"),
            ],
        ]
    )
