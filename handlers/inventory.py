import re

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from bot_core.constants import TECH_TYPES
from bot_core.flow import (
    delete_user_message,
    next_field,
    show_confirmation,
    upsert_ui_message,
)
from bot_core.keyboards import get_after_save_keyboard, get_skip_cancel_keyboard, get_tech_type_keyboard
from bot_core.states import InventoryForm
from config import CLINICS

router = Router()


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
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ Выбрана: {CLINICS[clinic_code]}\n🏢 Введите номер кабинета:",
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

    tech_examples = {
        "pc": "Системный блок Dell OptiPlex",
        "monitor": 'Монитор Samsung 24"',
        "printer": "Принтер HP LaserJet Pro",
        "laptop": "Ноутбук Lenovo ThinkPad",
        "other": "Устройство",
    }
    example = tech_examples.get(tech_key, "Устройство")

    await state.update_data(tech_type=tech_key, tech_type_name=tech_info["name"], tech_fields=tech_info["fields"])
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ {tech_info['name']}\n🔧 Введите наименование техники (например, {example}):",
        reply_markup=get_skip_cancel_keyboard(),
        preferred_message_id=callback.message.message_id,
    )

    await state.set_state(InventoryForm.entering_tech)


@router.callback_query(F.data.startswith("edit_field_"), InventoryForm.confirming_save)
async def edit_field_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        field_name = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка редактирования поля", show_alert=True)
        return
    data = await state.get_data()
    tech_type = data.get("tech_type", "other")

    tech_examples = {
        "pc": "Системный блок Dell",
        "monitor": "Монитор Samsung",
        "printer": "Принтер HP",
        "laptop": "Ноутбук Lenovo",
        "other": "Устройство",
    }
    tech_example = tech_examples.get(tech_type, "Устройство")

    field_to_state = {
        "cabinet": InventoryForm.entering_cabinet,
        "tech": InventoryForm.entering_tech,
        "serial": InventoryForm.entering_serial,
        "inv": InventoryForm.entering_inv,
        "ip": InventoryForm.entering_ip,
        "mac": InventoryForm.entering_mac,
        "os": InventoryForm.entering_os,
        "drweb": InventoryForm.entering_drweb,
        "office": InventoryForm.entering_office,
        "note": InventoryForm.entering_note,
    }
    prompts = {
        "cabinet": "🏢 Введите НОВЫЙ номер кабинета:",
        "tech": f"🔧 Введите НОВОЕ наименование техники (например, {tech_example}):",
        "serial": "🔢 Введите НОВЫЙ серийный номер:",
        "inv": "🏷️ Введите НОВЫЙ инвентарный номер:",
        "ip": '🌐 Введите НОВЫЙ IP-адрес (или "Пропустить"):',
        "mac": '📡 Введите НОВЫЙ MAC-адрес (или "Пропустить"):',
        "os": "🖥️ Введите НОВУЮ операционную систему:",
        "drweb": "🛡️ Установлен Dr.Web? (да/нет):",
        "office": "📄 Установлен Office? (да/нет):",
        "note": "💬 Введите НОВОЕ примечание:",
    }
    if field_name not in field_to_state:
        await callback.answer("❌ Неизвестное поле", show_alert=True)
        return

    await state.update_data(editing_field=field_name)
    await upsert_ui_message(
        callback.message,
        state,
        prompts.get(field_name, "Введите новое значение:"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад к проверке", callback_data="back_to_confirm")]]
        ),
    )
    await state.set_state(field_to_state.get(field_name))


@router.callback_query(F.data == "back_to_confirm")
async def back_to_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(editing_field=None)
    await show_confirmation(callback.message, state)


@router.callback_query(F.data == "confirm_save", InventoryForm.confirming_save)
async def confirm_save(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    item_id = db.save_item(data["clinic"], data)
    await state.clear()
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ **Сохранено!**\n\n📝 **ID записи:** {item_id}\n\n📋 **Что делаем дальше?**",
        parse_mode="Markdown",
        reply_markup=get_after_save_keyboard(),
    )


@router.message(InventoryForm.entering_cabinet)
async def process_cabinet(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if not text:
        await upsert_ui_message(
            message,
            state,
            '❌ Поле "Кабинет" не может быть пустым!\n🏢 Введите номер кабинета (101) или название (Регистратура):',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return

    if text.lower() in ["пропустить", "skip"]:
        await upsert_ui_message(
            message,
            state,
            '❌ Поле "Кабинет" обязательно для заполнения!\n🏢 Введите номер или название:',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return

    await state.update_data(cabinet=text)
    await upsert_ui_message(message, state, "🔧 Выберите тип техники:", reply_markup=get_tech_type_keyboard())
    await state.set_state(InventoryForm.selecting_tech_type)


@router.message(InventoryForm.entering_tech)
async def process_tech(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(tech=message.text.strip())
    data = await state.get_data()
    if data.get("editing_field") == "tech":
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, "tech")


@router.message(InventoryForm.entering_serial)
async def process_serial(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if not text:
        await upsert_ui_message(
            message,
            state,
            "❌ Серийный номер не может быть пустым.\n🔢 Введите серийный номер:",
            reply_markup=get_skip_cancel_keyboard(),
        )
        return

    await state.update_data(serial=text)
    data = await state.get_data()
    if data.get("editing_field") == "serial":
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, "serial")


@router.message(InventoryForm.entering_inv)
async def process_inv(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if not text:
        await upsert_ui_message(
            message,
            state,
            "❌ Инвентарный номер не может быть пустым.\n🏷️ Введите инвентарный номер:",
            reply_markup=get_skip_cancel_keyboard(),
        )
        return

    await state.update_data(inv=text)
    data = await state.get_data()
    if data.get("editing_field") == "inv":
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, "inv")


@router.message(InventoryForm.entering_ip)
async def process_ip(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if text.lower() in ["пропустить", "skip", ""]:
        await state.update_data(ip="")
        data = await state.get_data()
        if data.get("editing_field") == "ip":
            await show_confirmation(message, state)
        else:
            await next_field(message, state, data, "ip")
        return

    if not re.match(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$", text):
        await upsert_ui_message(
            message,
            state,
            '❌ Неверный IP. Пример: 192.168.1.10\n🌐 Введите IP-адрес или "Пропустить":',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return

    await state.update_data(ip=text)
    data = await state.get_data()
    if data.get("editing_field") == "ip":
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, "ip")


@router.message(InventoryForm.entering_mac)
async def process_mac(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if text.lower() in ["пропустить", "skip", ""]:
        await state.update_data(mac="")
        data = await state.get_data()
        if data.get("editing_field") == "mac":
            await show_confirmation(message, state)
        else:
            await next_field(message, state, data, "mac")
        return

    if not re.match(r"^([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2})$|^([0-9A-Fa-f]{2}[-]){5}([0-9A-Fa-f]{2})$", text):
        await upsert_ui_message(
            message,
            state,
            '❌ Неверный MAC. Пример: 00:1A:2B:3C:4D:5E\n📡 Введите MAC-адрес или "Пропустить":',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return

    await state.update_data(mac=text)
    data = await state.get_data()
    if data.get("editing_field") == "mac":
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, "mac")


@router.message(InventoryForm.entering_os)
async def process_os(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(os=message.text.strip())
    data = await state.get_data()
    if data.get("editing_field") == "os":
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, "os")


@router.message(InventoryForm.entering_drweb)
async def process_drweb(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(drweb=message.text.strip())
    data = await state.get_data()
    if data.get("editing_field") == "drweb":
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, "drweb")


@router.message(InventoryForm.entering_office)
async def process_office(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(office=message.text.strip())
    data = await state.get_data()
    if data.get("editing_field") == "office":
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, "office")


@router.message(InventoryForm.entering_note)
async def process_note(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(note=message.text.strip())
    await show_confirmation(message, state)

