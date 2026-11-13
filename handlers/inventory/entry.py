"""Начало ввода новой записи: выбор поликлиники → режим АРМ → тип техники.

Каждый хендлер только валидирует выбор и переводит FSM в следующее
состояние; логика полей — в fields.py, сохранение — в review.py.
"""

import asyncio
import logging
import sqlite3

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

import database as db
from bot_core.constants import TECH_TYPES
from bot_core.flow import upsert_ui_message
from bot_core.keyboards import (
    get_arm_mode_keyboard,
    get_skip_cancel_keyboard,
)
from bot_core.states import InventoryForm
from config import CLINICS

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("clinic_"), InventoryForm.selecting_clinic)
async def clinic_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        clinic_code = callback.data.split("_", 1)[1]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка выбора поликлиники", show_alert=True)
        return
    if clinic_code not in CLINICS:
        await callback.answer("❌ Неизвестная поликлиника", show_alert=True)
        return
    await state.update_data(clinic=clinic_code, clinic_name=CLINICS[clinic_code])
    # Спросить: Создать АРМ?
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ Выбрана: {CLINICS[clinic_code]}\n\nСформировать АРМ? "
        "(АРМ объединяет несколько устройств в один комплект)",
        reply_markup=get_arm_mode_keyboard(),
    )
    await state.set_state(InventoryForm.selecting_arm_mode)


@router.callback_query(F.data == "arm_mode_yes", InventoryForm.selecting_arm_mode)
async def arm_mode_yes(callback: types.CallbackQuery, state: FSMContext):
    """Создать АРМ — резервируем arm_id, просим ввести кабинет.

    arm_id выделяется атомарно (БД-счётчик) — при одновременном создании
    АРМ двумя пользователями они получат разные номера.
    """
    await callback.answer()
    try:
        arm_id = await asyncio.to_thread(db.next_arm_id)
    except sqlite3.Error as e:
        logger.exception("Не удалось выделить arm_id")
        await callback.answer(f"❌ Ошибка БД: {e}", show_alert=True)
        return
    await state.update_data(arm_mode=True, arm_id=arm_id)
    data = await state.get_data()
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ АРМ #{arm_id} создан\n🏥 {data.get('clinic_name')}\n\n"
        "🏢 Введите номер кабинета (общий для всех устройств АРМ):",
        reply_markup=get_skip_cancel_keyboard(),
    )
    await state.set_state(InventoryForm.entering_cabinet)


@router.callback_query(F.data == "arm_mode_no", InventoryForm.selecting_arm_mode)
async def arm_mode_no(callback: types.CallbackQuery, state: FSMContext):
    """Обычный ввод — без АРМ."""
    await callback.answer()
    await state.update_data(arm_mode=False, arm_id=None)
    data = await state.get_data()
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ Выбрана: {data.get('clinic_name')}\n\n🏢 Введите номер кабинета:",
        reply_markup=get_skip_cancel_keyboard(),
    )
    await state.set_state(InventoryForm.entering_cabinet)


@router.callback_query(F.data.startswith("tech_type_"), InventoryForm.selecting_tech_type)
async def tech_type_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        tech_key = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка выбора типа", show_alert=True)
        return
    if tech_key not in TECH_TYPES:
        await callback.answer("❌ Неизвестный тип техники", show_alert=True)
        return
    tech_info = TECH_TYPES[tech_key]

    await state.update_data(
        tech_type=tech_key,
        tech_type_name=tech_info["name"],
        tech_fields=tech_info["fields"],
    )
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ {tech_info['name']}\n🔧 Введите марку и модель (например, Dell OptiPlex 3090):",
        reply_markup=get_skip_cancel_keyboard(),
        preferred_message_id=callback.message.message_id,
    )
    await state.set_state(InventoryForm.entering_tech)
