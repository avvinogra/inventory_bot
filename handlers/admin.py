import logging
import os
import shutil
import time

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
import database as db
from bot_core.access import is_admin
from bot_core.flow import delete_user_message, upsert_ui_message
from bot_core.keyboards import get_admin_keyboard, get_delete_method_keyboard
from bot_core.states import InventoryForm
from config import CLINICS

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_menu")
async def admin_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
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
async def admin_stats(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

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
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
                [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
            ]
        ),
        preferred_message_id=callback.message.message_id,
    )


@router.callback_query(F.data == "admin_view_last")
async def admin_view_last(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
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
async def admin_show_records(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
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


@router.callback_query(F.data == "admin_delete")
async def admin_delete_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    await upsert_ui_message(
        callback.message,
        state,
        "🗑️ Удаление записи\n\nВыберите способ:",
        reply_markup=get_delete_method_keyboard(),
        preferred_message_id=callback.message.message_id,
    )


@router.callback_query(F.data == "admin_delete_by_id")
async def admin_delete_by_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
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
async def admin_confirm_delete_id(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
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
    clinic_name = CLINICS.get(item.get('clinic', ''), item.get('clinic', '—'))
    await upsert_ui_message(
        message,
        state,
        "🗑️ Удалить запись?\n\n"
        f"🆔 ID: {item['id']}\n"
        f"🏷️ Инвентарный номер: {item['inv_number']}\n"
        f"🏷️ Марка, модель: {item['tech']}\n"
        f"🏥 Поликлиника: {clinic_name}\n"
        f"🏢 Номер кабинета: {item['cabinet']}\n\n"
        "⚠️ Это действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Удалить", callback_data="admin_confirm_delete"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="admin_delete"),
                ]
            ]
        ),
    )


@router.callback_query(F.data == "admin_delete_by_inv")
async def admin_delete_by_inv(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
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
async def admin_confirm_delete_inv(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    await delete_user_message(message)
    inv_number = message.text.strip()
    item = db.find_by_inv(inv_number)
    if not item:
        await upsert_ui_message(message, state, f"❌ Запись с инвентарным номером {inv_number} не найдена")
        await state.clear()
        return

    await state.update_data(delete_id=item["id"])
    clinic_name = CLINICS.get(item.get('clinic', ''), item.get('clinic', '—'))
    await upsert_ui_message(
        message,
        state,
        "🗑️ Удалить запись?\n\n"
        f"🆔 ID: {item['id']}\n"
        f"🏷️ Инвентарный номер: {item['inv_number']}\n"
        f"🏷️ Марка, модель: {item['tech']}\n"
        f"🏥 Поликлиника: {clinic_name}\n"
        f"🏢 Номер кабинета: {item['cabinet']}\n\n"
        "⚠️ Это действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Удалить", callback_data="admin_confirm_delete"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="admin_delete"),
                ]
            ]
        ),
    )


@router.callback_query(F.data == "admin_confirm_delete")
async def admin_execute_delete(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    data = await state.get_data()
    item_id = data.get("delete_id")
    if not item_id:
        await upsert_ui_message(callback.message, state, "❌ Ошибка: ID записи не найден")
        await state.clear()
        return
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ Запись ID {item_id} успешно удалена!" if db.delete_item(item_id) else f"❌ Ошибка при удалении записи ID {item_id}",
        preferred_message_id=callback.message.message_id,
    )
    await state.clear()


@router.callback_query(F.data == "admin_export_db")
async def admin_export_db(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    try:
        backup_path = f"inventory_backup_{int(time.time())}.db"
        shutil.copy2(config.DB_PATH, backup_path)
        with open(backup_path, "rb") as db_file:
            await callback.message.answer_document(
                types.BufferedInputFile(db_file.read(), filename="inventory.db"),
                caption="💾 База данных инвентаризации",
            )
        os.remove(backup_path)
        await upsert_ui_message(
            callback.message,
            state,
            "⬅️ Вернуться в админ-меню:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
                    [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
                ]
            ),
            preferred_message_id=callback.message.message_id,
        )
    except Exception as e:
        await upsert_ui_message(
            callback.message,
            state,
            f"❌ Ошибка экспорта: {e}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
                    [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
                ]
            ),
            preferred_message_id=callback.message.message_id,
        )


@router.callback_query(F.data == "admin_export_excel")
async def admin_export_excel(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    try:
        timestamp = int(time.time())
        excel_path = f"data/inventory_export_{timestamp}.xlsx"
        os.makedirs("data", exist_ok=True)
        await upsert_ui_message(
            callback.message, state, "⏳ Генерирую Excel файл...", preferred_message_id=callback.message.message_id
        )
        from excel_export import export_to_excel

        result_path = export_to_excel(excel_path)
        if result_path and os.path.exists(result_path):
            with open(result_path, "rb") as excel_file:
                await callback.message.answer_document(
                    types.BufferedInputFile(excel_file.read(), filename="inventory.xlsx"),
                    caption="📊 Экспорт инвентаризации в Excel\n\n"
                    f"📅 Дата экспорта: {time.strftime('%d.%m.%Y %H:%M')}",
                )
            os.remove(result_path)
            await upsert_ui_message(
                callback.message,
                state,
                "✅ Файл отправлен!",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
                        [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
                    ]
                ),
                preferred_message_id=callback.message.message_id,
            )
        else:
            await upsert_ui_message(
                callback.message,
                state,
                "❌ Ошибка генерации Excel файла",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
                        [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
                    ]
                ),
                preferred_message_id=callback.message.message_id,
            )
    except Exception as e:
        await upsert_ui_message(
            callback.message,
            state,
            f"❌ Ошибка экспорта: {e}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
                    [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
                ]
            ),
            preferred_message_id=callback.message.message_id,
        )
        logger.error(f"Ошибка экспорта Excel: {e}")


@router.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

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
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
                [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
            ]
        ),
        preferred_message_id=callback.message.message_id,
    )

