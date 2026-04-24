from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

import database as db
from bot_core.access import is_allowed
from bot_core.constants import INVENTORY_FIELDS
from bot_core.flow import REQUIRED_FIELDS, get_tech_prompt, next_field, safe_edit_message, upsert_ui_message
from bot_core.keyboards import (
    get_clinic_keyboard,
    get_main_keyboard,
    get_nav_keyboard,
    get_print_menu_keyboard,
)
from bot_core.states import InventoryForm

router = Router()

STATE_TO_FIELD = {
    "InventoryForm:entering_cabinet": "cabinet",
    "InventoryForm:entering_tech": "tech",
    "InventoryForm:entering_serial": "serial",
    "InventoryForm:entering_inv": "inv",
    "InventoryForm:entering_ip": "ip",
    "InventoryForm:entering_mac": "mac",
    "InventoryForm:entering_os": "os",
    "InventoryForm:entering_drweb": "drweb",
    "InventoryForm:entering_office": "office",
    "InventoryForm:entering_note": "note",
    "InventoryForm:selecting_tech_type": "tech_type",
    "InventoryForm:selecting_clinic": "clinic",
}


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    if not is_allowed(message.chat.id):
        await message.answer("❌ Доступ запрещён!")
        return

    db.clear_user_state(message.chat.id)
    await state.clear()
    welcome_text = f"👋 Привет, {message.from_user.first_name}!\n🏥 Бот инвентаризации\nВыберите действие:"
    await upsert_ui_message(
        message, state, welcome_text, reply_markup=get_main_keyboard(message.chat.id), parse_mode="HTML"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    if not is_allowed(message.chat.id):
        return
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    db.clear_user_state(message.chat.id)
    await state.clear()
    await upsert_ui_message(
        message,
        state,
        "❌ Процесс отменён.",
        reply_markup=get_main_keyboard(message.chat.id),
        preferred_message_id=ui_message_id,
    )


@router.message(Command("menu"))
async def cmd_menu(message: types.Message, state: FSMContext):
    if not is_allowed(message.chat.id):
        return
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    db.clear_user_state(message.chat.id)
    await state.clear()
    await upsert_ui_message(
        message,
        state,
        "📋 Главное меню:",
        reply_markup=get_main_keyboard(message.chat.id),
        preferred_message_id=ui_message_id,
    )


@router.callback_query(F.data == "start_inventory")
async def start_inventory(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    db.clear_user_state(callback.message.chat.id)
    await state.clear()
    await upsert_ui_message(
        callback.message,
        state,
        "🏥 Выберите поликлинику:",
        reply_markup=get_clinic_keyboard(),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )
    await state.set_state(InventoryForm.selecting_clinic)


@router.callback_query(F.data == "print_barcode")
async def print_barcode_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    await upsert_ui_message(
        callback.message,
        state,
        "🏷️ Печать штрих-кода\nВыберите опцию:",
        reply_markup=get_print_menu_keyboard(),
        parse_mode="HTML",
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    db.clear_user_state(callback.message.chat.id)
    await upsert_ui_message(
        callback.message,
        state,
        "👋 Главное меню:",
        reply_markup=get_main_keyboard(callback.message.chat.id),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.callback_query(F.data == "cancel_process")
async def cancel_process(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    db.clear_user_state(callback.message.chat.id)
    await upsert_ui_message(
        callback.message,
        state,
        "❌ Процесс отменён.",
        reply_markup=get_main_keyboard(callback.message.chat.id),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.callback_query(F.data == "skip_current_field")
async def skip_field(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()
    current_field = STATE_TO_FIELD.get(current_state)

    if current_field in REQUIRED_FIELDS:
        await callback.answer(f'⚠️ Поле "{current_field}" обязательно для заполнения!', show_alert=True)
        return

    if current_field:
        data[current_field] = ""
        await state.update_data(**data)
        await next_field(callback.message, state, data, current_field)
        return

    await callback.answer("⚠️ Неизвестное поле", show_alert=True)


@router.callback_query(F.data == "back_prev_step")
async def back_prev_step(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()

    if not current_state:
        await back_to_menu(callback, state)
        return

    if current_state == "InventoryForm:selecting_tech_type":
        bot_msg_id = data.get("ui_message_id") or callback.message.message_id
        await safe_edit_message(
            bot=callback.bot,
            message_id=bot_msg_id,
            chat_id=callback.message.chat.id,
            text="🏢 Введите номер кабинета:",
            reply_markup=get_nav_keyboard(can_back=True, can_skip=False),
        )
        await state.set_state(InventoryForm.entering_cabinet)
        await state.update_data(ui_message_id=bot_msg_id)
        return

    if current_state == "InventoryForm:entering_cabinet":
        await upsert_ui_message(callback.message, state, "🏥 Выберите поликлинику:", reply_markup=get_clinic_keyboard())
        await state.set_state(InventoryForm.selecting_clinic)
        return

    field = STATE_TO_FIELD.get(current_state)
    fields = data.get("tech_fields", INVENTORY_FIELDS)
    tech_type = data.get("tech_type", "other")
    bot_msg_id = data.get("ui_message_id") or callback.message.message_id

    if not field or field not in fields:
        await callback.answer("⚠️ Нельзя вернуться назад отсюда", show_alert=True)
        return

    idx = fields.index(field)
    if idx <= 0:
        await callback.answer("⚠️ Это первый шаг", show_alert=True)
        return

    prev_field = fields[idx - 1]
    can_skip = prev_field not in REQUIRED_FIELDS
    prompt = get_tech_prompt(prev_field, tech_type)

    ok = await safe_edit_message(
        bot=callback.bot,
        message_id=bot_msg_id,
        chat_id=callback.message.chat.id,
        text=prompt,
        reply_markup=get_nav_keyboard(can_back=True, can_skip=can_skip),
    )
    if not ok:
        sent = await callback.message.answer(prompt, reply_markup=get_nav_keyboard(can_back=True, can_skip=can_skip))
        bot_msg_id = sent.message_id

    await state.update_data(ui_message_id=bot_msg_id, editing_field=None)
    await state.set_state(getattr(InventoryForm, f"entering_{prev_field}", InventoryForm.entering_note))


@router.callback_query(F.data == "new_inventory")
async def new_inventory(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    db.clear_user_state(callback.message.chat.id)
    await state.clear()
    await upsert_ui_message(
        callback.message,
        state,
        "🏥 Выберите поликлинику:",
        reply_markup=get_clinic_keyboard(),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )
    await state.set_state(InventoryForm.selecting_clinic)


@router.callback_query(F.data == "start_edit")
async def start_edit(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await upsert_ui_message(callback.message, state, "⚠️ Функция редактирования в разработке")

