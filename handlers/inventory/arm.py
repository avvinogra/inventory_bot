"""Цикл АРМ после сохранения устройства: добавить ещё (сбрасываем только
поля устройства, оставляя клинику/кабинет/arm_id) или завершить (сводка
всех устройств АРМ)."""

import asyncio

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

import database as db
from bot_core.constants import TECH_TYPES
from bot_core.flow import upsert_ui_message
from bot_core.keyboards import get_after_save_keyboard, get_tech_type_keyboard
from bot_core.states import InventoryForm

router = Router()


@router.callback_query(F.data == "arm_add_another", InventoryForm.arm_after_save)
async def arm_add_another(callback: types.CallbackQuery, state: FSMContext):
    """Добавить ещё устройство в АРМ — сбросить поля техники, оставить кабинет/клинику/arm_id."""
    await callback.answer()
    data = await state.get_data()
    arm_id = data.get("arm_id")
    clinic_name = data.get("clinic_name", "")
    cabinet = data.get("cabinet", "")

    # Сбросить только поля устройства, оставить clinic/cabinet/arm_id/arm_mode
    reset_fields = [
        "tech_type",
        "tech_type_name",
        "tech_fields",
        "tech",
        "serial",
        "inv",
        "os",
        "drweb",
        "ip",
        "pc_name",
        "mac_phys",
        "mac_real",
        "specs",
        "note",
        "editing_field",
        "editing_mode",
    ]
    await state.update_data(**{f: "" for f in reset_fields})

    await upsert_ui_message(
        callback.message,
        state,
        f"🔗 АРМ #{arm_id} — {clinic_name}, каб. {cabinet}\n\n"
        "Выберите тип техники для нового устройства:",
        reply_markup=get_tech_type_keyboard(),
    )
    await state.set_state(InventoryForm.selecting_tech_type)


@router.callback_query(F.data == "arm_finish", InventoryForm.arm_after_save)
async def arm_finish(callback: types.CallbackQuery, state: FSMContext):
    """Завершить создание АРМ — показать сводку."""
    await callback.answer()
    data = await state.get_data()
    arm_id = data.get("arm_id")
    clinic_name = data.get("clinic_name", "")
    cabinet = data.get("cabinet", "")

    # to_thread — не блокируем event loop бота на время чтения из БД
    arm_items = await asyncio.to_thread(db.get_arm_items, arm_id) if arm_id else []
    summary = f"✅ АРМ #{arm_id} завершён\n\n"
    summary += f"🏥 {clinic_name} • Каб. {cabinet}\n"
    summary += f"Устройств: {len(arm_items)}\n\n"
    for i, item in enumerate(arm_items, 1):
        tech_info = TECH_TYPES.get(item.get("tech_type", ""), {})
        tech_name = tech_info.get("name", item.get("tech", "—"))
        summary += f"  {i}. {tech_name} — {item.get('tech', '—')}\n"
    summary += "\n📋 Что делаем дальше?"

    await state.clear()
    await upsert_ui_message(
        callback.message,
        state,
        summary,
        reply_markup=get_after_save_keyboard(),
    )
