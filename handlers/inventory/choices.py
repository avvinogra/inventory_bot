"""Выбор Dr.Web и операционной системы из inline-кнопок.

Работает во всех трёх режимах (обычный ввод новой записи, правка поля
новой записи из карточки подтверждения, правка существующей записи) —
общая логика в _after_field_input (fields.py).

Текстовый ввод для этих полей не поддерживается — фолбэки ниже
подсказывают выбрать из кнопок.
"""

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot_core.constants import DRWEB_CHOICES, OS_CHOICES
from bot_core.flow import delete_user_message, upsert_ui_message
from bot_core.keyboards import get_drweb_choice_keyboard, get_os_choice_keyboard
from bot_core.states import InventoryForm
from handlers.inventory.fields import _after_field_input

router = Router()


@router.callback_query(F.data.startswith("drweb_choice_"), InventoryForm.entering_drweb)
async def drweb_choice_selected(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора статуса Dr.Web из inline-меню."""
    await callback.answer()
    try:
        choice_key = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка выбора статуса Dr.Web", show_alert=True)
        return

    if choice_key not in DRWEB_CHOICES:
        await callback.answer("❌ Неизвестный статус Dr.Web", show_alert=True)
        return

    _label, db_value = DRWEB_CHOICES[choice_key]
    await state.update_data(drweb=db_value)
    await _after_field_input(callback.message, state, "drweb", db_value)


@router.callback_query(F.data.startswith("os_choice_"), InventoryForm.entering_os)
async def os_choice_selected(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора операционной системы из inline-меню."""
    await callback.answer()
    try:
        choice_key = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка выбора ОС", show_alert=True)
        return

    if choice_key not in OS_CHOICES:
        await callback.answer("❌ Неизвестная ОС", show_alert=True)
        return

    os_value = OS_CHOICES[choice_key]
    await state.update_data(os=os_value)
    await _after_field_input(callback.message, state, "os", os_value)


# Поле ОС НЕ принимает текстовый ввод — только выбор из кнопок.
@router.message(InventoryForm.entering_os)
async def process_os_text_fallback(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await upsert_ui_message(
        message,
        state,
        "⚠️ Ввод текстом не поддерживается — выберите ОС из кнопок ниже:",
        reply_markup=get_os_choice_keyboard(),
    )


# Поле Dr.Web НЕ принимает текстовый ввод — только выбор из кнопок.
@router.message(InventoryForm.entering_drweb)
async def process_drweb_text_fallback(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await upsert_ui_message(
        message,
        state,
        "⚠️ Ввод текстом не поддерживается — выберите статус Dr.Web из кнопок ниже:",
        reply_markup=get_drweb_choice_keyboard(),
    )
