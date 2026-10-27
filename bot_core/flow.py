import logging

from aiogram import Bot, types
from aiogram.fsm.context import FSMContext

from bot_core.constants import EDITABLE_FIELDS, INVENTORY_FIELDS, REQUIRED_FIELDS, display_drweb
from bot_core.keyboards import get_confirm_edit_keyboard, get_nav_keyboard
from bot_core.states import InventoryForm
from config import CLINICS

logger = logging.getLogger(__name__)

TECH_EXAMPLES = {
    "pc": "Системный блок Dell OptiPlex",
    "monitor": 'Монитор Samsung 24"',
    "printer": "Принтер HP LaserJet Pro",
    "laptop": "Ноутбук Lenovo ThinkPad",
    "other": "Устройство",
}

# Подсказки для каждого поля. Без сокращений, без «+», без «нет лиц».
# Поле "drweb" обрабатывается отдельно — для него показывается inline-меню выбора,
# поэтому здесь стоит заглушка "Выберите статус Dr.Web:" (выбор через кнопки).
FIELD_PROMPTS = {
    "cabinet":   "🏢 Введите номер кабинета (например, 101):",
    "tech":      "🔧 Введите марку и модель техники (например, Dell OptiPlex 3090):",
    "serial":    "🔢 Введите серийный номер (или нажмите «Отсутствует», если его нет):",
    "inv":       "🏷️ Введите инвентарный номер (или нажмите «Отсутствует», если его нет):",
    "os":        (
        "🖥️ Выберите операционную систему из списка ниже:\n"
        "💡 Если нужной ОС нет — выберите «Другая ОС», а название укажите в «Дополнительно»\n"
        "⚠️ Ввод текстом не поддерживается — только выбор из кнопок"
    ),
    "drweb":     (
        "🛡️ Выберите статус антивируса Dr.Web из списка ниже:\n\n"
        "⚠️ Ввод текстом не поддерживается — только выбор из кнопок"
    ),
    "ip":        '🌐 Введите IP-адрес (или нажмите «Пропустить»):',
    "pc_name":   "💻 Введите имя компьютера. Для РЕД ОС: RedOS-1Pol. Для Windows: KEMDC-PC-814-1:",
    "mac_phys":  "📡 Введите физический MAC-адрес из настроек сетевого интерфейса (или «Пропустить»):",
    "mac_real":  "📡 Введите реальный MAC-адрес из вывода ifconfig (или «Пропустить»):",
    "specs":     "⚙️ Введите характеристики: процессор, объём оперативной памяти, накопитель. Пример: i3-10100, 8 ГБ, 240 ГБ SSD:",
    "note":      "💬 Введите дополнительные сведения (на складе, требуется чистка, наличие SafeBoot и т. п.):",
}

# Маппинг "state-ключ" → FSM-состояние ввода этого поля
FIELD_TO_STATE = {
    "cabinet":   InventoryForm.entering_cabinet,
    "tech":      InventoryForm.entering_tech,
    "serial":    InventoryForm.entering_serial,
    "inv":       InventoryForm.entering_inv,
    "os":        InventoryForm.entering_os,
    "drweb":     InventoryForm.entering_drweb,
    "ip":        InventoryForm.entering_ip,
    "pc_name":   InventoryForm.entering_pc_name,
    "mac_phys":  InventoryForm.entering_mac_phys,
    "mac_real":  InventoryForm.entering_mac_real,
    "specs":     InventoryForm.entering_specs,
    "note":      InventoryForm.entering_note,
}


def get_tech_prompt(field: str, tech_type: str) -> str:
    if field == "tech":
        return f"🔧 Введите марку и модель техники (например, {TECH_EXAMPLES.get(tech_type, 'Устройство')}):"
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


def _format_record_card(data: dict, clinic_name: str, tech_type_name: str) -> str:
    """Форматирует карточку записи (новая или существующая) —
    единый вид для show_confirmation и для режима редактирования.

    Без сокращений, с нормальными подписями Dr.Web.
    """
    summary = (
        "📋 ПРОВЕРЬТЕ ДАННЫЕ ПЕРЕД СОХРАНЕНИЕМ\n\n"
        f"🏥 Поликлиника: {clinic_name}\n"
        f"📦 Тип: {tech_type_name}\n"
        f"🏢 Номер кабинета: {data.get('cabinet', '—')}\n"
        f"🏷️ Марка, модель: {data.get('tech', '—')}\n"
        f"🔢 Серийный номер: {data.get('serial', '—')}\n"
        f"🏷️ Инвентарный номер: {data.get('inv', '—')}\n"
    )

    if data.get("os"):
        summary += f"🖥️ Операционная система: {data.get('os')}\n"
    if data.get("drweb"):
        summary += f"🛡️ Dr.Web: {display_drweb(data.get('drweb'))}\n"
    if data.get("ip"):
        summary += f"🌐 IP-адрес: {data.get('ip')}\n"
    if data.get("pc_name"):
        summary += f"💻 Имя компьютера: {data.get('pc_name')}\n"
    if data.get("mac_phys"):
        summary += f"📡 Физический MAC: {data.get('mac_phys')}\n"
    if data.get("mac_real"):
        summary += f"📡 Реальный MAC: {data.get('mac_real')}\n"
    if data.get("specs"):
        summary += f"⚙️ Характеристики: {data.get('specs')}\n"
    if data.get("note"):
        summary += f"💬 Дополнительно: {data.get('note')}\n"

    return summary


async def show_confirmation(message: types.Message, state: FSMContext):
    """Карточка "проверьте данные" перед сохранением НОВОЙ записи"""
    data = await state.get_data()
    clinic_name = CLINICS.get(data.get("clinic", ""), data.get("clinic", "Неизвестно"))
    tech_type_name = data.get("tech_type_name", "Не указан")

    summary = _format_record_card(data, clinic_name, tech_type_name)
    summary += "\n⚠️ Если есть ошибки — нажмите на поле для редактирования."
    await upsert_ui_message(
        message,
        state,
        summary,
        reply_markup=get_confirm_edit_keyboard(data),
    )
    await state.set_state(InventoryForm.confirming_save)


async def next_field(message: types.Message, state: FSMContext, data: dict, current_field: str):
    """Перейти к следующему полю согласно tech_fields."""
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
        can_absent = next_field_name in ("inv", "serial")

        # Для Dr.Web показываем inline-меню вместо текстовой подсказки
        if next_field_name == "drweb":
            from bot_core.keyboards import get_drweb_choice_keyboard
            reply_markup = get_drweb_choice_keyboard()
        # Для ОС тоже показываем inline-меню выбора
        elif next_field_name == "os":
            from bot_core.keyboards import get_os_choice_keyboard
            reply_markup = get_os_choice_keyboard()
        else:
            reply_markup = get_nav_keyboard(can_back=True, can_skip=can_skip, can_absent=can_absent)

        await upsert_ui_message(message, state, text, reply_markup=reply_markup)
        await state.set_state(FIELD_TO_STATE.get(next_field_name))
        return

    await show_confirmation(message, state)


# ✅ send_barcode_to_telegram удалена — печать штрих-кода вырезана из бота.
