"""Экраны админки: удаление записи (по ID / по инвентарному номеру)."""

import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from bot_core.access import admin_only
from bot_core.flow import delete_user_message, upsert_ui_message
from bot_core.keyboards import get_delete_method_keyboard
from bot_core.states import InventoryForm
from config import CLINICS

logger = logging.getLogger(__name__)
router = Router()


def _delete_confirm_keyboard() -> InlineKeyboardMarkup:
    """Карточка записи перед удалением: [✅ Удалить][❌ Отмена]."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Удалить", callback_data="admin_confirm_delete"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_delete"),
            ]
        ]
    )


def _delete_card_text(item: dict) -> str:
    """Текст карточки записи, которую собираются удалить (общий для двух способов)."""
    clinic_name = CLINICS.get(item.get("clinic", ""), item.get("clinic", "—"))
    return (
        "🗑️ Удалить запись?\n\n"
        f"🆔 ID: {item['id']}\n"
        f"🏷️ Инвентарный номер: {item['inv_number']}\n"
        f"🏷️ Марка, модель: {item['tech']}\n"
        f"🏥 Поликлиника: {clinic_name}\n"
        f"🏢 Номер кабинета: {item['cabinet']}\n\n"
        "⚠️ Это действие нельзя отменить!"
    )


@router.callback_query(F.data == "admin_delete")
@admin_only
async def admin_delete_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await upsert_ui_message(
        callback.message,
        state,
        "🗑️ Удаление записи\n\nВыберите способ:",
        reply_markup=get_delete_method_keyboard(),
        preferred_message_id=callback.message.message_id,
    )


@router.callback_query(F.data == "admin_delete_by_id")
@admin_only
async def admin_delete_by_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(InventoryForm.admin_delete_id)
    await upsert_ui_message(
        callback.message,
        state,
        "🗑️ Введите ID записи для удаления:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_delete")]]
        ),
        preferred_message_id=callback.message.message_id,
    )


@router.message(InventoryForm.admin_delete_id)
@admin_only
async def admin_confirm_delete_id(message: types.Message, state: FSMContext):
    await delete_user_message(message)

    try:
        item_id = int(message.text.strip())
    except ValueError:
        await upsert_ui_message(message, state, "❌ Неверный формат ID. Введите число.")
        return

    item = db.get_item_by_id(item_id)
    if not item:
        await upsert_ui_message(message, state, f"❌ Запись с ID {item_id} не найдена")
        await state.clear()
        return

    await state.update_data(delete_id=item_id)
    await upsert_ui_message(
        message,
        state,
        _delete_card_text(item),
        reply_markup=_delete_confirm_keyboard(),
    )


@router.callback_query(F.data == "admin_delete_by_inv")
@admin_only
async def admin_delete_by_inv(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(InventoryForm.admin_delete_inv)
    await upsert_ui_message(
        callback.message,
        state,
        "🗑️ Введите инвентарный номер для удаления:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_delete")]]
        ),
        preferred_message_id=callback.message.message_id,
    )


@router.message(InventoryForm.admin_delete_inv)
@admin_only
async def admin_confirm_delete_inv(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    inv_number = message.text.strip()
    item = db.find_by_inv(inv_number)
    if not item:
        await upsert_ui_message(
            message, state, f"❌ Запись с инвентарным номером {inv_number} не найдена"
        )
        await state.clear()
        return

    await state.update_data(delete_id=item["id"])
    await upsert_ui_message(
        message,
        state,
        _delete_card_text(item),
        reply_markup=_delete_confirm_keyboard(),
    )


@router.callback_query(F.data == "admin_confirm_delete")
@admin_only
async def admin_execute_delete(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    item_id = data.get("delete_id")
    if not item_id:
        await upsert_ui_message(callback.message, state, "❌ Ошибка: ID записи не найден")
        await state.clear()
        return
    deleted = db.delete_item(item_id)
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ Запись ID {item_id} успешно удалена!"
        if deleted
        else f"❌ Ошибка при удалении записи ID {item_id}",
        preferred_message_id=callback.message.message_id,
    )
    await state.clear()
