"""Ввод текстовых полей новой записи (и правка полей существующей).

Единая трёхрежимная логика после ввода значения поля — _after_field_input
(раньше она же была продублирована в drweb/os-хендлерах choices):

  - editing_mode == "existing"   → UPDATE в БД → возврат к карточке записи
  - editing_mode == "new_record" → возврат к карточке «проверьте данные»
  - editing_mode is None         → обычный поток: следующее поле

Поле Dr.Web и поле ОС текстом не вводятся — только выбор из кнопок
(см. choices.py и текстовые фолбэки там же).
"""

import asyncio

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

import database as db
from bot_core.cards import show_record_card
from bot_core.constants import EDITABLE_FIELDS, TECH_TYPES
from bot_core.flow import (
    delete_user_message,
    next_field,
    show_confirmation,
    upsert_ui_message,
)
from bot_core.keyboards import (
    get_duplicate_inv_keyboard,
    get_duplicate_serial_keyboard,
    get_mac_mismatch_keyboard,
    get_skip_cancel_keyboard,
    get_tech_type_keyboard,
)
from bot_core.states import InventoryForm
from config import CLINICS
from validators import is_valid_ip, is_valid_mac

router = Router()

# Метки полей для сообщений об ошибках (единый источник — constants).
_FIELD_LABELS = dict(EDITABLE_FIELDS)


async def _after_field_input(message: types.Message, state: FSMContext, field: str, value: str):
    """Общая логика после ввода/выбора значения поля.

    Вызывается текстовыми хендлерами этого модуля, выбором Dr.Web/ОС
    (choices.py) и подтверждениями MAC-предупреждения (confirmations.py).
    """
    data = await state.get_data()
    mode = data.get("editing_mode")

    # ----- Режим редактирования СУЩЕСТВУЮЩЕЙ записи -----
    if mode == "existing":
        item_id = data.get("editing_item_id")
        if not item_id:
            await upsert_ui_message(
                message, state, "❌ Ошибка: не указана запись для редактирования"
            )
            await state.clear()
            return
        # to_thread — не блокируем event loop бота на время UPDATE (как в фазе 0)
        ok = await asyncio.to_thread(db.update_item, item_id, field, value)
        if not ok:
            label = _FIELD_LABELS.get(field, field)
            await upsert_ui_message(message, state, f"❌ Не удалось обновить поле «{label}»")
            return
        await state.update_data(editing_field=None, editing_mode=None)
        await show_record_card(message, state, item_id, just_saved_field=(field, value))
        return

    # ----- Режим правки поля НОВОЙ записи (из карточки подтверждения) -----
    if mode == "new_record":
        await state.update_data(editing_field=None, editing_mode=None)
        await show_confirmation(message, state)
        return

    # ----- Обычный поток ввода новой записи -----
    await next_field(message, state, data, field)


def _format_duplicate_list(duplicates: list[dict], *, with_inv: bool) -> str:
    """Нумерованный список записей-дубликатов для предупреждения.

    Общее для предупреждений по серийному (with_inv=True — строка
    с инвентарным номером) и по инвентарному номеру. Показываем
    максимум 5 записей.
    """
    parts: list[str] = []
    for i, d in enumerate(duplicates[:5], 1):
        tech_name = TECH_TYPES.get(d.get("tech_type", ""), {}).get("name", d.get("tech", "—"))
        clinic_name = CLINICS.get(d.get("clinic", ""), d.get("clinic", "—"))
        parts.append(f"  {i}. #{d['id']} — {tech_name}\n")
        parts.append(f"     🏥 {clinic_name} • 🏢 Номер кабинета: {d.get('cabinet') or '—'}\n")
        if with_inv:
            parts.append(f"     🏷️ Инвентарный номер: {d.get('inv_number') or '—'}\n")
    if len(duplicates) > 5:
        parts.append(f"  … и ещё {len(duplicates) - 5}\n")
    return "".join(parts)


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

    await upsert_ui_message(
        message, state, "🔧 Выберите тип техники:", reply_markup=get_tech_type_keyboard()
    )
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
        await state.update_data(serial="")
        await _after_field_input(message, state, "serial", "")
        return

    await state.update_data(serial=text)
    data = await state.get_data()

    if data.get("editing_field") == "serial":
        await _after_field_input(message, state, "serial", text)
        return

    # НЕ проверяем дубликаты для значений «Отсутствует» / «нет» / пустых
    text_lower = text.lower()
    if text_lower in ("отсутствует", "нет", "без номера", "—", "-"):
        await next_field(message, state, data, "serial")
        return

    # Проверка дубликатов по серийному номеру.
    # Серийный номер должен быть уникальным — дубли почти всегда ошибка.
    duplicates = await asyncio.to_thread(db.find_duplicates_by_serial, text)
    if duplicates:
        dup_text = (
            f"⚠️ Серийный номер «{text}» уже есть в "
            f"{len(duplicates)} {'записи' if len(duplicates) == 1 else 'записях'}:\n\n"
            + _format_duplicate_list(duplicates, with_inv=True)
            + "\nСерийный номер должен быть уникальным для каждого устройства.\n"
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


@router.message(InventoryForm.entering_inv)
async def process_inv(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if not text:
        await state.update_data(inv="")
        await _after_field_input(message, state, "inv", "")
        return

    await state.update_data(inv=text)
    data = await state.get_data()

    if data.get("editing_field") == "inv":
        await _after_field_input(message, state, "inv", text)
        return

    # НЕ проверяем дубликаты для значений «Отсутствует» / «нет» / пустых
    text_lower = text.lower()
    if text_lower in ("отсутствует", "нет", "без номера", "—", "-"):
        await next_field(message, state, data, "inv")
        return

    # Проверка дубликатов по инв. номеру.
    # ВАЖНО: дубликаты по инв. номеру — это НЕ ошибка в нашей организации
    # (АРМ: монитор + системный блок + принтер под одним инв. номером).
    # Поэтому НЕ блокируем, а только информируем.
    duplicates = await asyncio.to_thread(db.find_duplicates_by_inv, text)
    if duplicates:
        dup_text = (
            f"ℹ️ Инвентарный номер «{text}» уже используется в "
            f"{len(duplicates)} {'записи' if len(duplicates) == 1 else 'записях'}:\n\n"
            + _format_duplicate_list(duplicates, with_inv=False)
            + "\nЕсли это разные устройства одного АРМ — продолжайте.\n"
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


@router.message(InventoryForm.entering_ip)
async def process_ip(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if text.lower() in ["пропустить", "skip", ""]:
        await state.update_data(ip="")
        await _after_field_input(message, state, "ip", "")
        return

    if not is_valid_ip(text):
        await upsert_ui_message(
            message,
            state,
            "❌ Неверный формат IP-адреса. Пример: 192.168.1.10\n🌐 Введите IP-адрес или нажмите «Пропустить»:",
            reply_markup=get_skip_cancel_keyboard(),
        )
        return
    await state.update_data(ip=text)
    await _after_field_input(message, state, "ip", text)


@router.message(InventoryForm.entering_mac_phys)
async def process_mac_phys(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    if text.lower() in ["пропустить", "skip", ""]:
        await state.update_data(mac_phys="")
        await _after_field_input(message, state, "mac_phys", "")
        return
    if not is_valid_mac(text):
        await upsert_ui_message(
            message,
            state,
            "❌ Неверный формат MAC-адреса. Пример: 00:1A:2B:3C:4D:5E\n📡 Введите физический MAC-адрес или нажмите «Пропустить»:",
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
    if not is_valid_mac(text):
        await upsert_ui_message(
            message,
            state,
            "❌ Неверный формат MAC-адреса. Пример: 00:1A:2B:3C:4D:5E\n📡 Введите реальный MAC-адрес или нажмите «Пропустить»:",
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
