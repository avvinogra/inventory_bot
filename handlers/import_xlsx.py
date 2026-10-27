"""Импорт данных из Excel в БД — только для админов.

Сценарий:
  1. В админ-меню пользователь жмёт «📥 Импорт из Excel»
  2. Бот просит прислать .xlsx файл
  3. Пользователь присылает документ
  4. Бот скачивает, парсит, добавляет записи в БД
  5. Бот присылает отчёт: сколько добавлено, сколько пропущено,
     какие поликлиники распознаны, какие листы не распознаны
"""
import os
import tempfile

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_core.access import is_admin
from bot_core.flow import delete_user_message, upsert_ui_message
from bot_core.states import InventoryForm

router = Router()


@router.callback_query(F.data == "admin_import_excel")
async def admin_import_excel_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало импорта — просим прислать .xlsx файл."""
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    await state.update_data(ui_message_id=ui_message_id)
    await state.set_state(InventoryForm.admin_import_waiting_file)

    await upsert_ui_message(
        callback.message,
        state,
        "📥 Импорт данных из Excel\n\n"
        "Пришлите файл .xlsx с инвентаризацией одним сообщением.\n\n"
        "Правила:\n"
        "  • Каждый лист — одна поликлиника. Имя листа должно быть «1 пол», "
        "«2 пол», «10 пол», «ДЦ», «ЦМР», «Травмпункт», «Дарвина» и т. п.\n"
        "  • Шапка колонок должна соответствовать шаблону "
        "«Инвентаризация.xlsx» (№ кабинета, Тип, Марка-модель, Инв №, Сер №, "
        "ОС, Dr.Web, IP-адрес, Имя ПК, Физический MAC, Реальный MAC, "
        "Характеристики, Дополнительно).\n"
        "  • Лист «Пояснения» игнорируется.\n"
        "  • Нераспознанные листы будут пропущены (с предупреждением в отчёте).\n"
        "  • Существующие записи не обновляются — только добавляются новые.\n"
        "  • Дубликаты по инв. номеру разрешены (это АРМ — монитор + ПК + принтер "
        "под одним инв. номером).",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_import_cancel")],
            ]
        ),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.callback_query(F.data == "admin_import_cancel")
async def admin_import_excel_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Отмена импорта."""
    await callback.answer()
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    await state.update_data(ui_message_id=ui_message_id)
    # возвращаемся в админку
    from bot_core.keyboards import get_admin_keyboard
    await upsert_ui_message(
        callback.message,
        state,
        "⚙️ Администрирование\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.message(F.document, InventoryForm.admin_import_waiting_file)
async def process_excel_import(message: types.Message, state: FSMContext):
    """Обработка присланного .xlsx файла."""
    if not is_admin(message.chat.id):
        return

    await delete_user_message(message)

    doc = message.document
    file_name = (doc.file_name or "").lower()

    if not file_name.endswith((".xlsx", ".xls")):
        await upsert_ui_message(
            message,
            state,
            "❌ Нужно прислать файл в формате .xlsx. Попробуйте ещё раз.",
        )
        return

    # Скачиваем файл во временный путь
    tmp_path = tempfile.mktemp(suffix=".xlsx")
    try:
        await message.bot.download(doc, destination=tmp_path)
    except Exception as e:
        await upsert_ui_message(
            message,
            state,
            f"❌ Не удалось скачать файл: {e}",
        )
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return

    # Предупреждаем, что идёт обработка
    await upsert_ui_message(
        message,
        state,
        "⏳ Импортирую данные, подождите…",
    )

    try:
        from excel_import import import_from_excel
        result = import_from_excel(tmp_path)
    except Exception as e:
        await upsert_ui_message(
            message,
            state,
            f"❌ Ошибка импорта: {e}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_menu")],
                    [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
                ]
            ),
        )
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        await state.clear()
        return
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Формируем отчёт
    text = (
        "📥 Импорт завершён\n\n"
        f"✅ Добавлено записей: {result['imported']}\n"
        f"⏭️ Пропущено строк: {result['skipped']}\n"
    )

    if result["by_clinic"]:
        from config import CLINICS
        text += "\nПо поликлиникам:\n"
        for clinic_code, count in sorted(result["by_clinic"].items()):
            clinic_name = CLINICS.get(clinic_code, clinic_code)
            text += f"  • {clinic_name}: {count}\n"

    if result["unrecognized_clinics"]:
        text += "\n⚠️ Не распознаны листы (пропущены):\n"
        for sheet_name in result["unrecognized_clinics"]:
            text += f"  • {sheet_name}\n"
        text += "Переименуйте листы в «1 пол», «2 пол», и т. п.\n"

    if result["errors"]:
        text += f"\nОшибки ({len(result['errors'])}):\n"
        for err in result["errors"][:10]:
            text += f"  • {err}\n"
        if len(result["errors"]) > 10:
            text += f"  … и ещё {len(result['errors']) - 10}\n"

    await state.clear()
    await upsert_ui_message(
        message,
        state,
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_menu")],
                [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
            ]
        ),
    )


@router.message(InventoryForm.admin_import_waiting_file)
async def process_excel_import_wrong_input(message: types.Message, state: FSMContext):
    """Если в режиме ожидания файла пользователь прислал НЕ документ."""
    if not is_admin(message.chat.id):
        return
    await delete_user_message(message)
    await upsert_ui_message(
        message,
        state,
        "❌ Пришлите .xlsx файл как документ (не фото, не текст). "
        "Или нажмите «Отмена».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_import_cancel")],
            ]
        ),
    )
