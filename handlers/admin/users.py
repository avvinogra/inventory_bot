"""Экраны админки: список пользователей с доступом и их роли."""

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

import config
from bot_core.access import admin_only
from bot_core.flow import upsert_ui_message
from bot_core.keyboards import get_admin_back_keyboard

router = Router()


@router.callback_query(F.data == "admin_users")
@admin_only
async def admin_users(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    users = config.ALLOWED_CHAT_IDS
    admins = config.ADMIN_CHAT_IDS
    text = "👥 Пользователи с доступом:\n\n"
    for i, user_id in enumerate(users, 1):
        role = "👑 Администратор" if user_id in admins else "👤 Пользователь"
        text += f"{i}. ID: {user_id} — {role}\n"
    text += f"\n📌 Всего пользователей: {len(users)}\n📌 Администраторов: {len(admins)}"

    await upsert_ui_message(
        callback.message,
        state,
        text,
        reply_markup=get_admin_back_keyboard(),
        preferred_message_id=callback.message.message_id,
    )
