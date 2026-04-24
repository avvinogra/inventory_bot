import logging
import os

from aiogram import Bot, types
from aiogram.fsm.context import FSMContext

from barcode_generator import generate_barcode_image
from bot_core.constants import INVENTORY_FIELDS
from bot_core.keyboards import get_confirm_edit_keyboard, get_nav_keyboard
from bot_core.states import InventoryForm
from config import CLINICS

logger = logging.getLogger(__name__)

TECH_EXAMPLES = {
    "pc": "Системный блок Dell",
    "monitor": "Монитор Samsung",
    "printer": "Принтер HP",
    "laptop": "Ноутбук Lenovo",
    "other": "Устройство",
}

FIELD_PROMPTS = {
    "cabinet": "🏢 Введите номер кабинета (например, 101):",
    "serial": "🔢 Введите серийный номер:",
    "inv": "🏷️ Введите инвентарный номер:",
    "ip": '🌐 Введите IP-адрес (или "Пропустить"):',
    "mac": '📡 Введите MAC-адрес (или "Пропустить"):',
    "os": "🖥️ Введите Операционную систему:",
    "drweb": "🛡️ Установлен Dr.Web? (да/нет):",
    "office": "📄 Установлен Office? (да/нет):",
    "note": "💬 Введите примечание (или нажмите Enter):",
}

FIELD_TO_STATE = {
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

REQUIRED_FIELDS = ["cabinet", "tech", "serial", "inv"]


def get_tech_prompt(field: str, tech_type: str) -> str:
    if field == "tech":
        return f"🔧 Введите наименование техники (например, {TECH_EXAMPLES.get(tech_type, 'Устройство')}):"
    return FIELD_PROMPTS.get(field, "Введите значение:")


async def delete_user_message(message: types.Message):
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение: {e}")


async def safe_edit_message(
    bot: Bot, message_id: int, chat_id: int, text: str, reply_markup=None, parse_mode=None
) -> bool:
    try:
        if reply_markup:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        else:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
            )
        return True
    except Exception as e:
        logger.debug(f"Не удалось отредактировать сообщение: {e}")
        return False


async def upsert_ui_message(
    message: types.Message,
    state: FSMContext,
    text: str,
    reply_markup=None,
    parse_mode=None,
    preferred_message_id: int | None = None,
) -> int:
    data = await state.get_data()
    ui_message_id = preferred_message_id or data.get("ui_message_id")
    if ui_message_id:
        ok = await safe_edit_message(
            bot=message.bot,
            message_id=ui_message_id,
            chat_id=message.chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        if ok:
            await state.update_data(ui_message_id=ui_message_id)
            return ui_message_id

    sent = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    await state.update_data(ui_message_id=sent.message_id)
    return sent.message_id


async def show_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    clinic_name = CLINICS.get(data.get("clinic", ""), data.get("clinic", "Неизвестно"))
    tech_type_name = data.get("tech_type_name", "Не указан")

    summary = (
        "📋 **ПРОВЕРЬТЕ ДАННЫЕ ПЕРЕД СОХРАНЕНИЕМ**\n\n"
        f"🏥 **Поликлиника:** {clinic_name}\n"
        f"🔧 **Тип:** {tech_type_name}\n"
        f"🏢 **Кабинет:** {data.get('cabinet', '—')}\n"
        f"🔧 **Техника:** {data.get('tech', '—')}\n"
        f"🔢 **Серийный номер:** {data.get('serial', '—')}\n"
        f"🏷️ **ИНВ номер:** {data.get('inv', '—')}\n"
    )

    if data.get("ip"):
        summary += f"🌐 **IP-адрес:** {data.get('ip')}\n"
    if data.get("mac"):
        summary += f"📡 **MAC-адрес:** {data.get('mac')}\n"
    if data.get("os"):
        summary += f"🖥️ **ОС:** {data.get('os')}\n"
    if data.get("drweb"):
        summary += f"🛡️ **Dr.Web:** {data.get('drweb')}\n"
    if data.get("office"):
        summary += f"📄 **Office:** {data.get('office')}\n"
    if data.get("note"):
        summary += f"💬 **Примечание:** {data.get('note')}\n"

    summary += "\n⚠️ Если есть ошибки - нажмите на поле для редактирования"
    await upsert_ui_message(
        message,
        state,
        summary,
        reply_markup=get_confirm_edit_keyboard(data),
        parse_mode="Markdown",
    )
    await state.set_state(InventoryForm.confirming_save)


async def next_field(message: types.Message, state: FSMContext, data: dict, current_field: str):
    fields = data.get("tech_fields", INVENTORY_FIELDS)
    tech_type = data.get("tech_type", "other")

    try:
        field_index = fields.index(current_field)
    except ValueError:
        field_index = -1

    if 0 <= field_index < len(fields) - 1:
        next_field_name = fields[field_index + 1]
        text = get_tech_prompt(next_field_name, tech_type)
        can_skip = next_field_name not in REQUIRED_FIELDS
        await upsert_ui_message(
            message,
            state,
            text,
            reply_markup=get_nav_keyboard(can_back=True, can_skip=can_skip),
        )

        await state.set_state(FIELD_TO_STATE.get(next_field_name))
        return

    await show_confirmation(message, state)


async def send_barcode_to_telegram(
    message: types.Message, inv_number: str, tech: str, cabinet: str, serial: str, clinic: str
):
    barcode_path = generate_barcode_image(inv_number)
    if not barcode_path or not os.path.exists(barcode_path):
        await message.answer("❌ Ошибка генерации штрих-кода")
        return

    label_text = (
        f"🏥 {clinic}\n📦 Устройство: {tech}\n"
        f"🏢 Кабинет: {cabinet}\n🔢 Сер. №: {serial}\n"
        f"🏷️ ИНВ №: {inv_number}"
    )
    await message.answer(label_text, parse_mode="HTML")

    with open(barcode_path, "rb") as img_file:
        await message.answer_photo(
            types.BufferedInputFile(img_file.read(), filename="barcode.png"),
            caption=f"🏷️ ИНВ № {inv_number}",
        )

