import re

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from bot_core.constants import DRWEB_CHOICES, TECH_TYPES
from bot_core.flow import (
    FIELD_PROMPTS,
    FIELD_TO_STATE,
    delete_user_message,
    next_field,
    show_confirmation,
    upsert_ui_message,
)
from bot_core.keyboards import (
    get_drweb_choice_keyboard,
    get_duplicate_inv_keyboard,
    get_duplicate_serial_keyboard,
    get_edit_field_input_keyboard,
    get_mac_mismatch_keyboard,
    get_nav_keyboard,
    get_skip_cancel_keyboard,
    get_tech_type_keyboard,
)
from bot_core.states import InventoryForm
from config import CLINICS

router = Router()

PAGE_SIZE = 10


# ============================================================
# ВВОД НОВОЙ ЗАПИСИ — выбор поликлиники / типа техники
# ============================================================
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


# ============================================================
# ПРОВЕРКА ДАННЫХ НОВОЙ ЗАПИСИ — правка отдельных полей
# ============================================================
@router.callback_query(F.data.startswith("review_field_"), InventoryForm.confirming_save)
async def review_field_selected(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь нажал на поле в карточке "проверьте данные" —
    хотим его отредактировать перед сохранением.
    """
    await callback.answer()
    try:
        field_name = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка редактирования поля", show_alert=True)
        return

    if field_name not in FIELD_TO_STATE:
        await callback.answer("❌ Неизвестное поле", show_alert=True)
        return

    data = await state.get_data()

    # Поле Dr.Web — показываем inline-меню выбора
    if field_name == "drweb":
        prompt = FIELD_PROMPTS.get("drweb")
        await state.update_data(editing_field=field_name, editing_mode="new_record")
        await upsert_ui_message(
            callback.message,
            state,
            prompt,
            reply_markup=get_drweb_choice_keyboard(),
        )
        await state.set_state(InventoryForm.entering_drweb)
        return

    tech_type = data.get("tech_type", "other")
    prompt = FIELD_PROMPTS.get(field_name, "Введите новое значение:")

    await state.update_data(editing_field=field_name, editing_mode="new_record")
    await upsert_ui_message(
        callback.message,
        state,
        prompt,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад к проверке", callback_data="back_to_confirm")]
            ]
        ),
    )
    await state.set_state(FIELD_TO_STATE[field_name])


@router.callback_query(F.data == "back_to_confirm")
async def back_to_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(editing_field=None, editing_mode=None)
    await show_confirmation(callback.message, state)


@router.callback_query(F.data == "confirm_save", InventoryForm.confirming_save)
async def confirm_save(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    item_id = db.save_item(data["clinic"], data)
    await state.clear()
    from bot_core.keyboards import get_after_save_keyboard
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ Сохранено.\n\n📝 ID записи: {item_id}\n\n📋 Что делаем дальше?",
        reply_markup=get_after_save_keyboard(),
    )


# ============================================================
# ВЫБОР Dr.Web — кнопки
# ============================================================
@router.callback_query(F.data.startswith("drweb_choice_"), InventoryForm.entering_drweb)
async def drweb_choice_selected(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора статуса Dr.Web из inline-меню.
    Работает и в режиме new_record, и в режиме existing (правка записи).
    """
    await callback.answer()
    try:
        choice_key = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка выбора статуса Dr.Web", show_alert=True)
        return

    if choice_key not in DRWEB_CHOICES:
        await callback.answer("❌ Неизвестный статус Dr.Web", show_alert=True)
        return

    _label, db_value = DRWEB_CHOICES[choice_key]
    await state.update_data(drweb=db_value)

    data = await state.get_data()
    mode = data.get("editing_mode")

    # Режим правки существующей записи — сохраняем в БД и возвращаемся к карточке
    if mode == "existing":
        item_id = data.get("editing_item_id")
        if not item_id:
            await upsert_ui_message(callback.message, state, "❌ Ошибка: не указана запись для редактирования")
            await state.clear()
            return
        ok = db.update_item(item_id, "drweb", db_value)
        if not ok:
            await upsert_ui_message(callback.message, state, "❌ Не удалось обновить поле Dr.Web")
            return
        await state.update_data(editing_field=None, editing_mode=None)
        from handlers.editing import show_record_card
        await show_record_card(callback.message, state, item_id, just_saved_field=("drweb", db_value))
        return

    # Режим правки поля НОВОЙ записи (из карточки подтверждения)
    if mode == "new_record":
        await state.update_data(editing_field=None, editing_mode=None)
        await show_confirmation(callback.message, state)
        return

    # Обычный поток ввода новой записи
    await next_field(callback.message, state, data, "drweb")


# ============================================================
# ОБРАБОТЧИКИ ВВОДА ПОЛЕЙ (новая запись ИЛИ правка существующей)
# ============================================================
# Логика:
#   - state.editing_mode == "new_record"  → после ввода → show_confirmation
#   - state.editing_mode == "existing"    → после ввода → UPDATE в БД → карточка записи
#   - state.editing_mode is None          → обычный поток new_record
#
# Поле Dr.Web НЕ принимает текст — только выбор из кнопок (см. drweb_choice_selected).
# ============================================================

async def _after_field_input(message: types.Message, state: FSMContext, field: str, value: str):
    """Общая логика после ввода значения поля"""
    data = await state.get_data()
    mode = data.get("editing_mode")

    # ----- Режим редактирования СУЩЕСТВУЮЩЕЙ записи -----
    if mode == "existing":
        item_id = data.get("editing_item_id")
        if not item_id:
            await upsert_ui_message(message, state, "❌ Ошибка: не указана запись для редактирования")
            await state.clear()
            return
        ok = db.update_item(item_id, field, value)
        if not ok:
            await upsert_ui_message(message, state, f"❌ Не удалось обновить поле «{field}»")
            return
        await state.update_data(editing_field=None, editing_mode=None)
        from handlers.editing import show_record_card
        await show_record_card(message, state, item_id, just_saved_field=(field, value))
        return

    # ----- Режим правки поля НОВОЙ записи (из карточки подтверждения) -----
    if mode == "new_record":
        await state.update_data(editing_field=None, editing_mode=None)
        await show_confirmation(message, state)
        return

    # ----- Обычный поток ввода новой записи -----
    await next_field(message, state, data, field)


@router.message(InventoryForm.entering_cabinet)
async def process_cabinet(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if not text:
        await upsert_ui_message(
            message,
            state,
            '❌ Поле "Номер кабинета" не может быть пустым.\n🏢 Введите номер кабинета (например, 101) или название (например, Регистратура):',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return

    if text.lower() in ["пропустить", "skip"]:
        await upsert_ui_message(
            message,
            state,
            '❌ Поле "Номер кабинета" обязательно для заполнения.\n🏢 Введите номер или название:',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return

    await state.update_data(cabinet=text)
    data = await state.get_data()

    if data.get("editing_field") == "cabinet":
        await _after_field_input(message, state, "cabinet", text)
        return

    await upsert_ui_message(message, state, "🔧 Выберите тип техники:", reply_markup=get_tech_type_keyboard())
    await state.set_state(InventoryForm.selecting_tech_type)


@router.message(InventoryForm.entering_tech)
async def process_tech(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    await state.update_data(tech=text)
    await _after_field_input(message, state, "tech", text)


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

    # Если мы в режиме правки поля НОВОЙ записи (из карточки подтверждения) —
    # проверка дубликатов не нужна.
    if data.get("editing_field") == "serial":
        await _after_field_input(message, state, "serial", text)
        return

    # Проверка дубликатов по серийному номеру.
    # Серийный номер должен быть уникальным — дубли почти всегда ошибка.
    duplicates = db.find_duplicates_by_serial(text)
    if duplicates:
        from bot_core.constants import TECH_TYPES
        dup_text = (
            f"⚠️ Серийный номер «{text}» уже есть в "
            f"{len(duplicates)} {'записи' if len(duplicates) == 1 else 'записях'}:\n\n"
        )
        for i, d in enumerate(duplicates[:5], 1):
            tech_info = TECH_TYPES.get(d.get("tech_type", ""), {})
            tech_name = tech_info.get("name", d.get("tech", "—"))
            clinic_name = CLINICS.get(d.get("clinic", ""), d.get("clinic", "—"))
            dup_text += (
                f"  {i}. #{d['id']} — {tech_name}\n"
                f"     🏥 {clinic_name} • 🏢 Номер кабинета: {d.get('cabinet') or '—'}\n"
                f"     🏷️ Инвентарный номер: {d.get('inv_number') or '—'}\n"
            )
        if len(duplicates) > 5:
            dup_text += f"  … и ещё {len(duplicates) - 5}\n"
        dup_text += (
            "\nСерийный номер должен быть уникальным для каждого устройства.\n"
            "Если вы уверены, что это не дубликат — продолжите.\n"
            "Иначе отмените и проверьте."
        )
        await upsert_ui_message(
            message,
            state,
            dup_text,
            reply_markup=get_duplicate_serial_keyboard(),
        )
        await state.set_state(InventoryForm.confirming_serial_duplicate)
        return

    await next_field(message, state, data, "serial")


@router.callback_query(F.data == "confirm_serial_continue", InventoryForm.confirming_serial_duplicate)
async def confirm_serial_continue(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь подтвердил: «Продолжить всё равно»."""
    await callback.answer()
    await state.update_data(editing_field=None, editing_mode=None)
    data = await state.get_data()
    await next_field(callback.message, state, data, "serial")


@router.callback_query(F.data == "confirm_serial_cancel", InventoryForm.confirming_serial_duplicate)
async def confirm_serial_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь решил ввести серийный номер заново."""
    await callback.answer()
    await state.update_data(serial=None, editing_field=None, editing_mode=None)
    await upsert_ui_message(
        callback.message,
        state,
        "🔁 Введите серийный номер заново:",
        reply_markup=get_skip_cancel_keyboard(),
    )
    await state.set_state(InventoryForm.entering_serial)


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

    # Если мы в режиме правки поля НОВОЙ записи (из карточки подтверждения) —
    # проверка дубликатов не нужна.
    if data.get("editing_field") == "inv":
        await _after_field_input(message, state, "inv", text)
        return

    # Проверка дубликатов по инв. номеру.
    # ВАЖНО: дубликаты по инв. номеру — это НЕ ошибка в нашей организации
    # (АРМ: монитор + системный блок + принтер под одним инв. номером).
    # Поэтому НЕ блокируем, а только информируем.
    duplicates = db.find_duplicates_by_inv(text)
    if duplicates:
        from bot_core.constants import TECH_TYPES
        dup_text = (
            f"ℹ️ Инвентарный номер «{text}» уже используется в "
            f"{len(duplicates)} {'записи' if len(duplicates) == 1 else 'записях'}:\n\n"
        )
        for i, d in enumerate(duplicates[:5], 1):
            tech_info = TECH_TYPES.get(d.get("tech_type", ""), {})
            tech_name = tech_info.get("name", d.get("tech", "—"))
            clinic_name = CLINICS.get(d.get("clinic", ""), d.get("clinic", "—"))
            dup_text += (
                f"  {i}. #{d['id']} — {tech_name}\n"
                f"     🏥 {clinic_name} • 🏢 Номер кабинета: {d.get('cabinet') or '—'}\n"
            )
        if len(duplicates) > 5:
            dup_text += f"  … и ещё {len(duplicates) - 5}\n"
        dup_text += (
            "\nЕсли это разные устройства одного АРМ — продолжайте.\n"
            "Если вы ввели инвентарный номер по ошибке — отмените и проверьте."
        )
        await upsert_ui_message(
            message,
            state,
            dup_text,
            reply_markup=get_duplicate_inv_keyboard(),
        )
        await state.set_state(InventoryForm.confirming_inv_duplicate)
        return

    # Дубликатов нет — продолжаем
    await next_field(message, state, data, "inv")


@router.callback_query(F.data == "confirm_inv_continue", InventoryForm.confirming_inv_duplicate)
async def confirm_inv_continue(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь подтвердил: «Продолжить (это АРМ)»."""
    await callback.answer()
    await state.update_data(editing_field=None, editing_mode=None)
    data = await state.get_data()
    await next_field(callback.message, state, data, "inv")


@router.callback_query(F.data == "confirm_inv_cancel", InventoryForm.confirming_inv_duplicate)
async def confirm_inv_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь решил ввести инв. номер заново."""
    await callback.answer()
    await state.update_data(inv=None, editing_field=None, editing_mode=None)
    await upsert_ui_message(
        callback.message,
        state,
        "🔁 Введите инвентарный номер заново:",
        reply_markup=get_skip_cancel_keyboard(),
    )
    await state.set_state(InventoryForm.entering_inv)


@router.message(InventoryForm.entering_ip)
async def process_ip(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if text.lower() in ["пропустить", "skip", ""]:
        await state.update_data(ip="")
        await _after_field_input(message, state, "ip", "")
        return

    if not re.match(
        r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
        text,
    ):
        await upsert_ui_message(
            message,
            state,
            '❌ Неверный формат IP-адреса. Пример: 192.168.1.10\n🌐 Введите IP-адрес или нажмите «Пропустить»:',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return
    await state.update_data(ip=text)
    await _after_field_input(message, state, "ip", text)


_MAC_RE = re.compile(
    r"^([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2})$"
    r"|^([0-9A-Fa-f]{2}[-]){5}([0-9A-Fa-f]{2})$"
    r"|^[0-9A-Fa-f]{12}$"
)


@router.message(InventoryForm.entering_mac_phys)
async def process_mac_phys(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if text.lower() in ["пропустить", "skip", ""]:
        await state.update_data(mac_phys="")
        await _after_field_input(message, state, "mac_phys", "")
        return
    if not _MAC_RE.match(text):
        await upsert_ui_message(
            message,
            state,
            '❌ Неверный формат MAC-адреса. Пример: 00:1A:2B:3C:4D:5E\n📡 Введите физический MAC-адрес или нажмите «Пропустить»:',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return
    await state.update_data(mac_phys=text)
    await _after_field_input(message, state, "mac_phys", text)


@router.message(InventoryForm.entering_mac_real)
async def process_mac_real(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if text.lower() in ["пропустить", "skip", ""]:
        await state.update_data(mac_real="")
        await _after_field_input(message, state, "mac_real", "")
        return
    if not _MAC_RE.match(text):
        await upsert_ui_message(
            message,
            state,
            '❌ Неверный формат MAC-адреса. Пример: 00:1A:2B:3C:4D:5E\n📡 Введите реальный MAC-адрес или нажмите «Пропустить»:',
            reply_markup=get_skip_cancel_keyboard(),
        )
        return
    await state.update_data(mac_real=text)
    data = await state.get_data()

    # Если мы в режиме правки поля НОВОЙ записи (из карточки подтверждения) —
    # проверку несовпадения MAC не делаем (карточка это и так подтверждает).
    if data.get("editing_field") == "mac_real":
        await _after_field_input(message, state, "mac_real", text)
        return

    # Проверка: физический MAC должен совпадать с реальным MAC.
    # По нормативу организации (xlsx-пояснение 4):
    # «В идеале, на всех ПК физический MAC должен быть одинаковым с реальным MAC»
    mac_phys = data.get("mac_phys", "")
    if mac_phys and mac_phys.lower() != text.lower():
        mismatch_text = (
            "⚠️ Физический и реальный MAC-адреса не совпадают:\n\n"
            f"  📡 Физический MAC: {mac_phys}\n"
            f"  📡 Реальный MAC:  {text}\n\n"
            "По нормативу они должны совпадать.\n"
            "Если это сделано намеренно — продолжите.\n"
            "Если опечатка — введите реальный MAC заново."
        )
        await upsert_ui_message(
            message,
            state,
            mismatch_text,
            reply_markup=get_mac_mismatch_keyboard(),
        )
        await state.set_state(InventoryForm.confirming_mac_mismatch)
        return

    await _after_field_input(message, state, "mac_real", text)


@router.callback_query(F.data == "mac_mismatch_continue", InventoryForm.confirming_mac_mismatch)
async def mac_mismatch_continue(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь подтвердил: «Продолжить» с несовпадающими MAC."""
    await callback.answer()
    await state.update_data(editing_field=None, editing_mode=None)
    data = await state.get_data()
    mac_real = data.get("mac_real", "")
    await _after_field_input(callback.message, state, "mac_real", mac_real)


@router.callback_query(F.data == "mac_mismatch_reenter", InventoryForm.confirming_mac_mismatch)
async def mac_mismatch_reenter(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь хочет ввести реальный MAC заново."""
    await callback.answer()
    await state.update_data(mac_real=None, editing_field=None, editing_mode=None)
    await upsert_ui_message(
        callback.message,
        state,
        "🔁 Введите реальный MAC-адрес заново (или нажмите «Пропустить»):",
        reply_markup=get_skip_cancel_keyboard(),
    )
    await state.set_state(InventoryForm.entering_mac_real)


@router.callback_query(F.data == "mac_mismatch_skip", InventoryForm.confirming_mac_mismatch)
async def mac_mismatch_skip(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь решил пропустить реальный MAC."""
    await callback.answer()
    await state.update_data(mac_real="", editing_field=None, editing_mode=None)
    data = await state.get_data()
    await _after_field_input(callback.message, state, "mac_real", "")


@router.message(InventoryForm.entering_os)
async def process_os(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    await state.update_data(os=text)
    await _after_field_input(message, state, "os", text)


# Поле Dr.Web НЕ принимает текстовый ввод — только выбор из inline-меню.
# Если пользователь случайно ввёл текст в этом состоянии —
# подсказываем, что нужно выбрать из кнопок.
@router.message(InventoryForm.entering_drweb)
async def process_drweb_text_fallback(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await upsert_ui_message(
        message,
        state,
        "🛡️ Выберите статус антивируса Dr.Web из списка ниже (ввод текстом не поддерживается):",
        reply_markup=get_drweb_choice_keyboard(),
    )


@router.message(InventoryForm.entering_pc_name)
async def process_pc_name(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    await state.update_data(pc_name=text)
    await _after_field_input(message, state, "pc_name", text)


@router.message(InventoryForm.entering_specs)
async def process_specs(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    await state.update_data(specs=text)
    await _after_field_input(message, state, "specs", text)


@router.message(InventoryForm.entering_note)
async def process_note(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    await state.update_data(note=text)
    await _after_field_input(message, state, "note", text)
