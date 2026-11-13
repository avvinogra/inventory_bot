"""Импорт данных из Excel в БД — только для админов.

Сценарий:
  1. В админ-меню пользователь жмёт «📥 Импорт из Excel»
  2. Бот просит прислать .xlsx файл
  3. Пользователь присылает документ
  4. Бот скачивает, парсит, добавляет записи в БД
  5. Бот присылает отчёт: сколько добавлено, сколько пропущено,
     какие поликлиники распознаны, какие листы не распознаны
"""

import asyncio
import logging
import os
import tempfile

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_core.access import admin_only
from bot_core.flow import delete_user_message, upsert_ui_message
from bot_core.keyboards import get_admin_keyboard
from bot_core.states import InventoryForm
from config import CLINICS
from excel_import import import_from_excel

router = Router()
logger = logging.getLogger(__name__)


def _safe_unlink(path: str):
    """Удаляет временный файл, игнорируя ошибки (уже удалён/недоступен)."""
    try:
        os.unlink(path)
    except OSError:
        pass


@router.callback_query(F.data == "admin_import_excel")
@admin_only
async def admin_import_excel_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало импорта — просим прислать .xlsx файл."""
    await callback.answer()

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
    await upsert_ui_message(
        callback.message,
        state,
        "⚙️ Администрирование\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.message(F.document, InventoryForm.admin_import_waiting_file)
@admin_only
async def process_excel_import(message: types.Message, state: FSMContext):
    """Обработка присланного .xlsx файла."""
    await delete_user_message(message)

    doc = message.document
    file_name = (doc.file_name or "").lower()

    # Только .xlsx: openpyxl не умеет читать старый бинарный .xls.
    # Раньше .xls принимался, а потом падал с невнятной ошибкой парсинга.
    if not file_name.endswith(".xlsx"):
        await upsert_ui_message(
            message,
            state,
            "❌ Нужно прислать файл в формате .xlsx (старый .xls не поддерживается). "
            "Пересохраните файл в Excel как «Книга Excel (*.xlsx)» и попробуйте ещё раз.",
        )
        return

    # Скачиваем файл во временный путь.
    # mkstemp (а не запрещённый mktemp!) — файл создаётся атомарно
    # с O_CREAT|O_EXCL и правами 0600, что закрывает symlink-уязвимость.
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)  # закрываем дескриптор: bot.download запишет файл сам
    try:
        await message.bot.download(doc, destination=tmp_path)
    except Exception as e:  # noqa: BLE001 — скачивание может упасть по десятку
        # сетевых причин Telegram; пользователь должен увидеть отчёт, а не молчание
        await upsert_ui_message(
            message,
            state,
            f"❌ Не удалось скачать файл: {e}",
        )
        _safe_unlink(tmp_path)
        return

    # Предупреждаем, что идёт обработка
    await upsert_ui_message(
        message,
        state,
        "⏳ Импортирую данные, подождите…",
    )

    try:
        # Парсинг xlsx — тяжёлая CPU-работа (openpyxl), уводим из event loop
        result = await asyncio.to_thread(import_from_excel, tmp_path)
    except Exception as e:
        logger.exception("Ошибка импорта из Excel")
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
        await state.clear()
        return
    finally:
        _safe_unlink(tmp_path)

    # Формируем отчёт
    text = (
        "📥 Импорт завершён\n\n"
        f"✅ Добавлено записей: {result['imported']}\n"
        f"⏭️ Пропущено строк: {result['skipped']}\n"
    )

    if result["by_clinic"]:
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
@admin_only
async def process_excel_import_wrong_input(message: types.Message, state: FSMContext):
    """Если в режиме ожидания файла пользователь прислал НЕ документ."""
    await delete_user_message(message)
    await upsert_ui_message(
        message,
        state,
        "❌ Пришлите .xlsx файл как документ (не фото, не текст). Или нажмите «Отмена».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_import_cancel")],
            ]
        ),
    )
