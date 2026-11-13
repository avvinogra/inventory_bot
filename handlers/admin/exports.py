"""Экраны админки: экспорт базы (SQLite-файл) и экспорт в Excel.

Импорт из Excel живёт отдельно — handlers/import_xlsx.py (свой FSM-сценарий).
"""

import asyncio
import logging
import os
import shutil
import time

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

import config
from bot_core.access import admin_only
from bot_core.flow import upsert_ui_message
from bot_core.keyboards import get_admin_back_keyboard
from excel_export import export_to_excel

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_export_db")
@admin_only
async def admin_export_db(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
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
            reply_markup=get_admin_back_keyboard(),
            preferred_message_id=callback.message.message_id,
        )
    except Exception as e:
        logger.exception("Ошибка экспорта БД")
        await upsert_ui_message(
            callback.message,
            state,
            f"❌ Ошибка экспорта: {e}",
            reply_markup=get_admin_back_keyboard(),
            preferred_message_id=callback.message.message_id,
        )


@router.callback_query(F.data == "admin_export_excel")
@admin_only
async def admin_export_excel(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        timestamp = int(time.time())
        excel_path = f"data/inventory_export_{timestamp}.xlsx"
        os.makedirs("data", exist_ok=True)
        await upsert_ui_message(
            callback.message,
            state,
            "⏳ Генерирую Excel файл...",
            preferred_message_id=callback.message.message_id,
        )

        # Генерация xlsx (openpyxl) — тяжёлая CPU-работа, уводим из event loop
        result_path = await asyncio.to_thread(export_to_excel, excel_path)
        if result_path and os.path.exists(result_path):
            # Чтение файла тоже выносим из event loop (файл может быть на NFS/volume)
            def _read_file(path: str) -> bytes:
                with open(path, "rb") as f:
                    return f.read()

            file_bytes = await asyncio.to_thread(_read_file, result_path)
            await callback.message.answer_document(
                types.BufferedInputFile(file_bytes, filename="inventory.xlsx"),
                caption="📊 Экспорт инвентаризации в Excel\n\n"
                f"📅 Дата экспорта: {time.strftime('%d.%m.%Y %H:%M')}",
            )
            os.remove(result_path)
            await upsert_ui_message(
                callback.message,
                state,
                "✅ Файл отправлен!",
                reply_markup=get_admin_back_keyboard(),
                preferred_message_id=callback.message.message_id,
            )
        else:
            await upsert_ui_message(
                callback.message,
                state,
                "❌ Ошибка генерации Excel файла",
                reply_markup=get_admin_back_keyboard(),
                preferred_message_id=callback.message.message_id,
            )
    except Exception as e:  # noqa: BLE001 — пользователь должен увидеть отчёт
        # о любой ошибке генерации/отправки Excel, а не молчание бота
        await upsert_ui_message(
            callback.message,
            state,
            f"❌ Ошибка экспорта: {e}",
            reply_markup=get_admin_back_keyboard(),
            preferred_message_id=callback.message.message_id,
        )
        logger.error(f"Ошибка экспорта Excel: {e}")
