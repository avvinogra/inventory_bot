"""Карточка «проверьте данные» перед сохранением новой записи.

Пользователь может поправить любое поле (review_field_*) и сохранить
(confirm_save). Ошибки БД не сбрасывают состояние — данные не теряются.
"""

import asyncio
import logging
import sqlite3

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from bot_core.flow import (
    FIELD_PROMPTS,
    FIELD_TO_STATE,
    show_confirmation,
    upsert_ui_message,
)
from bot_core.keyboards import (
    get_after_save_keyboard,
    get_arm_after_save_keyboard,
    get_drweb_choice_keyboard,
    get_os_choice_keyboard,
)
from bot_core.states import InventoryForm

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("review_field_"), InventoryForm.confirming_save)
async def review_field_selected(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь нажал на поле в карточке "проверьте данные" —
    хотим его отредактировать перед сохранением.
    """
    await callback.answer()
    try:
        field_name = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка редактирования поля", show_alert=True)
        return

    if field_name not in FIELD_TO_STATE:
        await callback.answer("❌ Неизвестное поле", show_alert=True)
        return

    # Поле Dr.Web — показываем inline-меню выбора
    if field_name == "drweb":
        prompt = FIELD_PROMPTS.get("drweb")
        await state.update_data(editing_field=field_name, editing_mode="new_record")
        await upsert_ui_message(
            callback.message,
            state,
            prompt,
            reply_markup=get_drweb_choice_keyboard(),
        )
        await state.set_state(InventoryForm.entering_drweb)
        return

    # Поле ОС — показываем inline-меню выбора
    if field_name == "os":
        prompt = FIELD_PROMPTS.get("os")
        await state.update_data(editing_field=field_name, editing_mode="new_record")
        await upsert_ui_message(
            callback.message,
            state,
            prompt,
            reply_markup=get_os_choice_keyboard(),
        )
        await state.set_state(InventoryForm.entering_os)
        return

    prompt = FIELD_PROMPTS.get(field_name, "Введите новое значение:")

    await state.update_data(editing_field=field_name, editing_mode="new_record")
    await upsert_ui_message(
        callback.message,
        state,
        prompt,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад к проверке", callback_data="back_to_confirm")]
            ]
        ),
    )
    await state.set_state(FIELD_TO_STATE[field_name])


@router.callback_query(F.data == "back_to_confirm")
async def back_to_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(editing_field=None, editing_mode=None)
    await show_confirmation(callback.message, state)


@router.callback_query(F.data == "confirm_save", InventoryForm.confirming_save)
async def confirm_save(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()

    # save_item бросает sqlite3.Error при неудаче (раньше возвращал -1,
    # и пользователь видел «✅ Сохранено. ID: -1» при потере данных).
    # to_thread — не блокируем event loop бота на время записи в БД.
    try:
        item_id = await asyncio.to_thread(db.save_item, data["clinic"], data)
    except sqlite3.Error as e:
        logger.exception("Не удалось сохранить запись")
        # Состояние НЕ сбрасываем — данные живы, можно повторить сохранение.
        await upsert_ui_message(
            callback.message,
            state,
            f"❌ Не удалось сохранить запись (ошибка БД: {e}).\n\n"
            "Данные не потеряны — попробуйте ещё раз.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔄 Повторить сохранение", callback_data="confirm_save"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад к проверке", callback_data="back_to_confirm"
                        )
                    ],
                ]
            ),
        )
        return

    # Проверяем режим АРМ
    if data.get("arm_mode") and data.get("arm_id"):
        arm_id = data["arm_id"]
        clinic_name = data.get("clinic_name", "")
        cabinet = data.get("cabinet", "")
        # Считаем сколько уже сохранено в этом АРМ
        arm_items = await asyncio.to_thread(db.get_arm_items, arm_id)
        await state.update_data(editing_field=None, editing_mode=None)
        await upsert_ui_message(
            callback.message,
            state,
            f"✅ Сохранено. ID: {item_id}\n\n"
            f"🔗 АРМ #{arm_id} — {clinic_name}, каб. {cabinet}\n"
            f"Устройств в АРМ: {len(arm_items)}\n\n"
            "Добавить ещё устройство в АРМ?",
            reply_markup=get_arm_after_save_keyboard(),
        )
        await state.set_state(InventoryForm.arm_after_save)
        return

    # Обычный режим
    await state.clear()
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ Сохранено.\n\n📝 ID записи: {item_id}\n\n📋 Что делаем дальше?",
        reply_markup=get_after_save_keyboard(),
    )
