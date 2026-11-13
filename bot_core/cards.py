"""Карточка существующей записи — общий UI-компонент.

Раньше функция жила в handlers/editing.py, а handlers/inventory.py и
handlers/common.py импортировали её лениво внутри тела (5 сайтов),
порождая связь «хендлер → хендлер». Здесь она доступна всем хендлерам
как обычный импорт с bot_core-уровня — без циклов и без ленивых импортов.
"""

from aiogram import types
from aiogram.fsm.context import FSMContext

import database as db
from bot_core.constants import EDITABLE_FIELDS, TECH_TYPES, display_drweb
from bot_core.flow import upsert_ui_message
from bot_core.keyboards import get_edit_record_keyboard
from bot_core.states import InventoryForm
from config import CLINICS


async def show_record_card(
    message: types.Message,
    state: FSMContext,
    item_id: int,
    just_saved_field: tuple | None = None,
):
    """Показать карточку записи со всеми полями и кнопками правки"""
    item = db.get_item_by_id(item_id)
    if not item:
        await upsert_ui_message(message, state, f"❌ Запись с ID {item_id} не найдена")
        return

    await state.update_data(
        editing_item_id=item_id,
        editing_clinic=item.get("clinic", ""),
    )

    # Если запись пришла через режим "правка поля" — сохраняем режим
    is_in_edit_mode = (await state.get_state()) == InventoryForm.edit_choose_field
    if not is_in_edit_mode:
        await state.set_state(InventoryForm.edit_choose_field)

    clinic_name = CLINICS.get(item.get("clinic", ""), item.get("clinic", "—"))

    # Маппинг DB-колонок на короткие ключи state
    state_data = {
        "cabinet": item.get("cabinet", ""),
        "tech_type": item.get("tech_type", ""),
        "tech": item.get("tech", ""),
        "serial": item.get("serial", ""),
        "inv": item.get("inv_number", ""),
        "os": item.get("os", ""),
        "drweb": item.get("drweb", ""),
        "ip": item.get("ip", ""),
        "pc_name": item.get("pc_name", ""),
        "mac_phys": item.get("mac_phys", "") or item.get("mac", ""),  # fallback на legacy mac
        "mac_real": item.get("mac_real", ""),
        "specs": item.get("specs", ""),
        "note": item.get("note", ""),
    }

    # Имя типа техники (через tech_type ключ)
    tech_type_name = "—"
    if state_data["tech_type"]:
        info = TECH_TYPES.get(state_data["tech_type"])
        tech_type_name = info["name"] if info else state_data["tech_type"]

    text = (
        f"📋 КАРТОЧКА ЗАПИСИ\n\n"
        f"🆔 ID: {item['id']}\n"
        f"🏥 Поликлиника: {clinic_name}\n\n"
        f"📦 Тип: {tech_type_name}\n"
        f"🏢 Номер кабинета: {state_data['cabinet'] or '—'}\n"
        f"🏷️ Марка, модель: {state_data['tech'] or '—'}\n"
        f"🔢 Серийный номер: {state_data['serial'] or '—'}\n"
        f"🏷️ Инвентарный номер: {state_data['inv'] or '—'}\n"
        f"🖥️ Операционная система: {state_data['os'] or '—'}\n"
        f"🛡️ Dr.Web: {display_drweb(state_data['drweb'])}\n"
        f"🌐 IP-адрес: {state_data['ip'] or '—'}\n"
        f"💻 Имя компьютера: {state_data['pc_name'] or '—'}\n"
        f"📡 Физический MAC: {state_data['mac_phys'] or '—'}\n"
        f"📡 Реальный MAC: {state_data['mac_real'] or '—'}\n"
        f"⚙️ Характеристики: {state_data['specs'] or '—'}\n"
        f"💬 Дополнительно: {state_data['note'] or '—'}\n"
    )

    if just_saved_field:
        field, value = just_saved_field
        label_dict = dict(EDITABLE_FIELDS)
        # Если поле — Dr.Web, показываем красивую подпись вместо значения
        shown_value = display_drweb(value) if field == "drweb" else value
        banner = f"✅ Поле «{label_dict.get(field, field)}» обновлено: «{shown_value[:30]}»"

        # Проверка дубликатов при изменении inv / serial
        # (исключаем саму текущую запись через exclude_id=item_id)
        # ВАЖНО: имя компьютера НЕ проверяем — в организации одно имя
        # может быть на нескольких устройствах (АРМ).
        warning = ""
        if field in ("inv", "serial") and value:
            if field == "inv":
                dups = db.find_duplicates_by_inv(value, exclude_id=item_id)
                if dups:
                    warning = (
                        f"\n⚠️ Такой инвентарный номер уже есть в "
                        f"{len(dups)} {'записи' if len(dups) == 1 else 'записях'} "
                        f"(возможно, это АРМ — несколько устройств под одним номером)."
                    )
            elif field == "serial":
                dups = db.find_duplicates_by_serial(value, exclude_id=item_id)
                if dups:
                    warning = (
                        f"\n⚠️ Такой серийный номер уже есть в записи "
                        f"#{dups[0]['id']} — возможно, дубликат."
                    )

        text = banner + warning + "\n\n" + text

    await upsert_ui_message(
        message,
        state,
        text,
        reply_markup=get_edit_record_keyboard(state_data, item_id=item_id),
    )
