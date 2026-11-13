"""Экраны админки: меню, статистика, последние записи."""

import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from bot_core.access import admin_only
from bot_core.flow import delete_user_message, upsert_ui_message
from bot_core.keyboards import get_admin_back_keyboard, get_admin_keyboard
from bot_core.states import InventoryForm
from config import CLINICS

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_menu")
@admin_only
async def admin_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    # Сбрасываем любое активное состояние (например, при отмене импорта)
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    await state.update_data(ui_message_id=ui_message_id)
    await upsert_ui_message(
        callback.message,
        state,
        "⚙️ Администрирование\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.callback_query(F.data == "admin_stats")
@admin_only
async def admin_stats(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    stats = db.get_db_stats()
    total = stats.get("total_items", 0)
    by_clinic = stats.get("by_clinic", {})
    stats_text = f"📊 Статистика базы данных\n\n📌 Всего записей: {total}\n\n"
    if by_clinic:
        stats_text += "По поликлиникам:\n"
        for clinic, count in sorted(by_clinic.items()):
            stats_text += f"  • {CLINICS.get(clinic, clinic)}: {count}\n"

    await upsert_ui_message(
        callback.message,
        state,
        stats_text,
        reply_markup=get_admin_back_keyboard(),
        preferred_message_id=callback.message.message_id,
    )


@router.callback_query(F.data == "admin_view_last")
@admin_only
async def admin_view_last(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(InventoryForm.admin_view_count)
    await upsert_ui_message(
        callback.message,
        state,
        "📋 Введите количество записей для просмотра (1-100):\nПо умолчанию: 20",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")]]
        ),
        preferred_message_id=callback.message.message_id,
    )


@router.message(InventoryForm.admin_view_count)
@admin_only
async def admin_show_records(message: types.Message, state: FSMContext):
    await delete_user_message(message)

    try:
        count = max(1, min(int(message.text.strip()), 100))
    except ValueError:
        count = 20

    items = db.get_all_items(limit=count)
    if not items:
        await upsert_ui_message(message, state, "❌ В базе нет записей")
        await state.clear()
        return

    text = f"📋 Последние {len(items)} записей:\n\n"
    for i, item in enumerate(items, 1):
        text += (
            f"{i}. ID: {item['id']} | Инвентарный номер: {item['inv_number']}\n"
            f"   🏥 {item['clinic']} | 🏢 Номер кабинета: {item['cabinet']}\n"
            f"   🔧 Марка, модель: {item['tech']}\n"
            f"   🔢 Серийный номер: {item['serial']}\n\n"
        )

    await upsert_ui_message(message, state, text)
    await state.clear()
