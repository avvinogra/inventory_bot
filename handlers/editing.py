"""Редактирование СУЩЕСТВУЮЩИХ записей об инвентаре.

Сценарий:
  1. Пользователь жмёт "✏️ Редактировать" → видит способы поиска:
       - По инвентарному номеру
       - По ID
       - По поликлинике (список)
       - По имени компьютера
  2. Находит запись → видит карточку со всеми полями и кнопками правки.
  3. Нажимает на поле → вводит новое значение → поле сохраняется в БД
     через database.update_item → возврат к карточке.
  4. Может удалить запись (с подтверждением).
"""
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

import database as db
from bot_core.constants import EDITABLE_FIELDS, display_drweb
from bot_core.flow import (
    FIELD_PROMPTS,
    FIELD_TO_STATE,
    TECH_EXAMPLES,
    delete_user_message,
    upsert_ui_message,
)
from bot_core.keyboards import (
    get_drweb_choice_keyboard,
    get_edit_back_keyboard,
    get_edit_clinic_keyboard,
    get_edit_delete_confirm_keyboard,
    get_edit_field_input_keyboard,
    get_edit_items_keyboard,
    get_edit_method_keyboard,
    get_edit_record_keyboard,
    get_os_choice_keyboard,
)
from bot_core.states import InventoryForm
from config import CLINICS

router = Router()
PAGE_SIZE = 10


# ============================================================
# ТОЧКА ВХОДА
# ============================================================
@router.callback_query(F.data == "start_edit")
async def start_edit(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    db.clear_user_state(callback.message.chat.id)
    await state.clear()
    await state.update_data(ui_message_id=ui_message_id)
    await upsert_ui_message(
        callback.message,
        state,
        "✏️ Редактирование записи\n\nВыберите способ поиска записи:",
        reply_markup=get_edit_method_keyboard(),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )
    await state.set_state(InventoryForm.edit_select_method)


# Псевдоним для кнопок "назад" в под-режимах
@router.callback_query(F.data == "edit_start")
async def edit_back_to_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_edit(callback, state)


# ============================================================
# ВЫБОР МЕТОДА ПОИСКА
# ============================================================
@router.callback_query(F.data == "edit_method_inv", InventoryForm.edit_select_method)
async def edit_method_inv(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await upsert_ui_message(
        callback.message,
        state,
        "🏷️ Введите инвентарный номер записи:",
        reply_markup=get_edit_back_keyboard(),
    )
    await state.set_state(InventoryForm.edit_enter_inv)


@router.callback_query(F.data == "edit_method_id", InventoryForm.edit_select_method)
async def edit_method_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await upsert_ui_message(
        callback.message,
        state,
        "🔢 Введите ID записи (число):",
        reply_markup=get_edit_back_keyboard(),
    )
    await state.set_state(InventoryForm.edit_enter_id)


@router.callback_query(F.data == "edit_method_clinic", InventoryForm.edit_select_method)
async def edit_method_clinic(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(InventoryForm.edit_select_clinic)
    await upsert_ui_message(
        callback.message,
        state,
        "🏥 Выберите поликлинику для показа списка записей:",
        reply_markup=get_edit_clinic_keyboard(),
    )


@router.callback_query(F.data == "edit_method_pc", InventoryForm.edit_select_method)
async def edit_method_pc(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await upsert_ui_message(
        callback.message,
        state,
        "💻 Введите имя компьютера (или его часть):",
        reply_markup=get_edit_back_keyboard(),
    )
    await state.set_state(InventoryForm.edit_enter_inv)  # переиспользуем стейт как "ввод строки поиска"
    await state.update_data(search_mode="pc_name")


@router.callback_query(F.data == "edit_method_global", InventoryForm.edit_select_method)
async def edit_method_global(callback: types.CallbackQuery, state: FSMContext):
    """Глобальный поиск — один запрос ищет сразу по нескольким полям."""
    await callback.answer()
    await upsert_ui_message(
        callback.message,
        state,
        "🔍 Глобальный поиск\n\n"
        "Введите запрос — поиск идёт сразу по:\n"
        "  • инвентарному номеру\n"
        "  • серийному номеру\n"
        "  • имени компьютера\n"
        "  • марке/модели\n"
        "  • номеру кабинета\n"
        "  • характеристикам\n"
        "  • операционной системе\n"
        "  • примечанию\n\n"
        "Введите запрос:",
        reply_markup=get_edit_back_keyboard(),
    )
    await state.set_state(InventoryForm.edit_enter_inv)  # переиспользуем стейт как "ввод строки поиска"
    await state.update_data(search_mode="global")


# ============================================================
# ВВОД ИНВЕНТАРНОГО НОМЕРА / ID / ИМЕНИ КОМПЬЮТЕРА
# ============================================================
@router.message(InventoryForm.edit_enter_inv)
async def edit_search_by_text(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = (message.text or "").strip()
    if not text:
        await upsert_ui_message(
            message,
            state,
            "❌ Пустой запрос. Введите значение:",
            reply_markup=get_edit_back_keyboard(),
        )
        return

    data = await state.get_data()
    mode = data.get("search_mode")

    if mode == "global":
        # Глобальный поиск по нескольким полям
        items = db.global_search(text, limit=50)
        if not items:
            await upsert_ui_message(
                message,
                state,
                f"❌ По запросу «{text}» ничего не найдено.",
                reply_markup=get_edit_back_keyboard(),
            )
            return
        await _show_items_list(
            message, state, items, page=0, total=len(items),
            title=f"🔍 Найдено записей: {len(items)}\nВыберите запись:"
        )
        return

    if mode == "pc_name":
        # Частичный поиск по имени компьютера через LIKE
        items = _search_by_pc_name(text)
        if not items:
            await upsert_ui_message(
                message,
                state,
                f"❌ Не найдено записей с именем компьютера, содержащим «{text}»",
                reply_markup=get_edit_back_keyboard(),
            )
            return
        await _show_items_list(message, state, items, page=0, total=len(items))
        return

    # По умолчанию — поиск по инвентарному номеру (точное совпадение)
    item = db.find_by_inv(text)
    if not item:
        await upsert_ui_message(
            message,
            state,
            f"❌ Запись с инвентарным номером {text} не найдена.\nПопробуйте ещё раз или нажмите «Назад».",
            reply_markup=get_edit_back_keyboard(),
        )
        return
    await show_record_card(message, state, item["id"])


@router.message(InventoryForm.edit_enter_id)
async def edit_search_by_id(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    raw = (message.text or "").strip()
    try:
        item_id = int(raw)
    except ValueError:
        await upsert_ui_message(
            message,
            state,
            "❌ Неверный формат ID. Введите число.",
            reply_markup=get_edit_back_keyboard(),
        )
        return
    item = db.get_item_by_id(item_id)
    if not item:
        await upsert_ui_message(
            message,
            state,
            f"❌ Запись с ID {item_id} не найдена.",
            reply_markup=get_edit_back_keyboard(),
        )
        return
    await show_record_card(message, state, item_id)


# ============================================================
# ВЫБОР ПОЛИКЛИНИКИ → СПИСОК ЗАПИСЕЙ
# ============================================================
@router.callback_query(F.data.startswith("edit_clinic_"), InventoryForm.edit_select_clinic)
async def edit_clinic_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        clinic_code = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка выбора поликлиники", show_alert=True)
        return
    if clinic_code not in CLINICS:
        await callback.answer("❌ Неизвестная поликлиника", show_alert=True)
        return
    await state.update_data(edit_clinic=clinic_code)
    items, total = _get_clinic_items(clinic_code, page=0)
    if not items:
        await upsert_ui_message(
            callback.message,
            state,
            f"❌ В поликлинике «{CLINICS[clinic_code]}» пока нет записей.",
            reply_markup=get_edit_clinic_keyboard(),
        )
        return
    await _show_items_list(callback.message, state, items, page=0, total=total, clinic=clinic_code)


@router.callback_query(F.data.startswith("edit_page_"))
async def edit_list_page(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        page = max(int(callback.data.split("_")[2]), 0)
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Ошибка пагинации", show_alert=True)
        return
    data = await state.get_data()
    clinic_code = data.get("edit_clinic")
    if not clinic_code:
        await callback.answer("❌ Сначала выберите поликлинику", show_alert=True)
        return
    items, total = _get_clinic_items(clinic_code, page=page)
    if not items:
        await upsert_ui_message(
            callback.message,
            state,
            "❌ Больше записей нет",
            reply_markup=get_edit_method_keyboard(),
        )
        return
    await _show_items_list(callback.message, state, items, page=page, total=total, clinic=clinic_code)


# ============================================================
# ВЫБОР ЗАПИСИ ИЗ СПИСКА → КАРТОЧКА ЗАПИСИ
# ============================================================
@router.callback_query(F.data.startswith("edit_open_"))
async def edit_open_item(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        item_id = int(callback.data.split("_", 2)[2])
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Ошибка выбора записи", show_alert=True)
        return
    await show_record_card(callback.message, state, item_id)


@router.callback_query(F.data == "edit_back_to_list")
async def edit_back_to_list(callback: types.CallbackQuery, state: FSMContext):
    """Из карточки записи — обратно к списку (по поликлинике или новый поиск)"""
    await callback.answer()
    data = await state.get_data()
    clinic_code = data.get("edit_clinic")
    if clinic_code:
        items, total = _get_clinic_items(clinic_code, page=0)
        if items:
            await _show_items_list(callback.message, state, items, page=0, total=total, clinic=clinic_code)
            return
    # иначе — к выбору метода
    await start_edit(callback, state)


# ============================================================
# КАРТОЧКА ЗАПИСИ
# ============================================================
async def show_record_card(message: types.Message, state: FSMContext, item_id: int, just_saved_field: tuple = None):
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
        "cabinet":   item.get("cabinet", ""),
        "tech_type": item.get("tech_type", ""),
        "tech":      item.get("tech", ""),
        "serial":    item.get("serial", ""),
        "inv":       item.get("inv_number", ""),
        "os":        item.get("os", ""),
        "drweb":     item.get("drweb", ""),
        "ip":        item.get("ip", ""),
        "pc_name":   item.get("pc_name", ""),
        "mac_phys":  item.get("mac_phys", "") or item.get("mac", ""),  # fallback на legacy mac
        "mac_real":  item.get("mac_real", ""),
        "specs":     item.get("specs", ""),
        "note":      item.get("note", ""),
    }

    # Имя типа техники (через tech_type ключ)
    tech_type_name = "—"
    if state_data["tech_type"]:
        from bot_core.constants import TECH_TYPES
        info = TECH_TYPES.get(state_data["tech_type"])
        if info:
            tech_type_name = info["name"]
        else:
            tech_type_name = state_data["tech_type"]

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
        if field == "drweb":
            shown_value = display_drweb(value)
        else:
            shown_value = value
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


# ============================================================
# ВЫБОР ПОЛЯ ДЛЯ ПРАВКИ (callback_data=f"edit_field_{field}")
# ============================================================
@router.callback_query(F.data.startswith("edit_field_"), InventoryForm.edit_choose_field)
async def edit_field_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        field_name = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка выбора поля", show_alert=True)
        return

    if field_name not in FIELD_TO_STATE:
        await callback.answer("❌ Неизвестное поле", show_alert=True)
        return

    data = await state.get_data()
    item_id = data.get("editing_item_id")
    if not item_id:
        await callback.answer("❌ Не выбрана запись", show_alert=True)
        return

    # Поле Dr.Web — показываем inline-меню выбора статуса
    if field_name == "drweb":
        prompt = FIELD_PROMPTS.get("drweb")
        await state.update_data(editing_field=field_name, editing_mode="existing")
        await upsert_ui_message(
            callback.message,
            state,
            prompt,
            reply_markup=get_drweb_choice_keyboard(),
        )
        await state.set_state(InventoryForm.entering_drweb)
        return

    # Поле ОС — показываем inline-меню выбора
    if field_name == "os":
        prompt = FIELD_PROMPTS.get("os")
        await state.update_data(editing_field=field_name, editing_mode="existing")
        await upsert_ui_message(
            callback.message,
            state,
            prompt,
            reply_markup=get_os_choice_keyboard(),
        )
        await state.set_state(InventoryForm.entering_os)
        return

    prompt = FIELD_PROMPTS.get(field_name, "Введите новое значение:")
    if field_name == "tech":
        tech_type_key = data.get("tech_type") or db.get_item_by_id(item_id).get("tech_type") if item_id else None
        if tech_type_key:
            example = TECH_EXAMPLES.get(tech_type_key, "Устройство")
        else:
            example = "Dell OptiPlex"
        prompt = f"🔧 Введите новую марку и модель (например, {example}):"

    await state.update_data(editing_field=field_name, editing_mode="existing")
    await upsert_ui_message(
        callback.message,
        state,
        prompt,
        reply_markup=get_edit_field_input_keyboard(),
    )
    await state.set_state(FIELD_TO_STATE[field_name])


@router.callback_query(F.data == "edit_back_to_card")
async def edit_back_to_card(callback: types.CallbackQuery, state: FSMContext):
    """Из режима ввода значения поля — обратно к карточке записи"""
    await callback.answer()
    data = await state.get_data()
    item_id = data.get("editing_item_id")
    if not item_id:
        await callback.answer("❌ Не выбрана запись", show_alert=True)
        return
    await state.update_data(editing_field=None, editing_mode=None)
    await show_record_card(callback.message, state, item_id)


# ============================================================
# УДАЛЕНИЕ ЗАПИСИ (из карточки)
# ============================================================
@router.callback_query(F.data.startswith("edit_delete_"))
async def edit_delete_request(callback: types.CallbackQuery, state: FSMContext):
    """Показать подтверждение удаления записи"""
    await callback.answer()
    data = callback.data
    if data.startswith("edit_delete_confirm_"):
        return  # обрабатывается в edit_delete_confirm
    try:
        item_id = int(data.split("_", 2)[2])
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Ошибка выбора записи", show_alert=True)
        return
    item = db.get_item_by_id(item_id)
    if not item:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    await upsert_ui_message(
        callback.message,
        state,
        "🗑️ Удалить запись?\n\n"
        f"🆔 ID: {item['id']}\n"
        f"🏷️ Инвентарный номер: {item.get('inv_number', '—')}\n"
        f"🏷️ Марка, модель: {item.get('tech', '—')}\n"
        f"🏥 Поликлиника: {CLINICS.get(item.get('clinic', ''), item.get('clinic', '—'))}\n"
        f"🏢 Номер кабинета: {item.get('cabinet', '—')}\n\n"
        "⚠️ Это действие нельзя отменить!",
        reply_markup=get_edit_delete_confirm_keyboard(item_id),
    )


@router.callback_query(F.data.startswith("edit_delete_confirm_"))
async def edit_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        item_id = int(callback.data.split("_", 3)[3])
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Ошибка удаления", show_alert=True)
        return
    ok = db.delete_item(item_id)
    await state.update_data(editing_item_id=None, editing_field=None, editing_mode=None)
    await upsert_ui_message(
        callback.message,
        state,
        f"✅ Запись ID {item_id} удалена" if ok else f"❌ Ошибка при удалении записи ID {item_id}",
        reply_markup=__import__(
            "bot_core.keyboards", fromlist=["get_edit_after_action_keyboard"]
        ).get_edit_after_action_keyboard(),
    )
    await state.set_state(InventoryForm.edit_select_method)


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ
# ============================================================
def _get_clinic_items(clinic_code: str, page: int = 0):
    """Возвращает (items, total) для поликлиники с пагинацией"""
    # total
    with db.get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM inventory WHERE clinic = ?", (clinic_code,)
        ).fetchone()[0]
    items = db.get_all_items(clinic=clinic_code, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    return items, total


def _search_by_pc_name(query: str):
    """Частичный поиск по имени компьютера (LIKE)"""
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM inventory WHERE pc_name LIKE ? ORDER BY id DESC LIMIT 50",
            (f"%{query}%",),
        ).fetchall()
        return [dict(r) for r in rows]


async def _show_items_list(message, state, items, page: int, total: int,
                           clinic: str = None, title: str = None):
    """Показать список записей для выбора"""
    if title is None:
        if clinic:
            title = f"🏥 {CLINICS.get(clinic, clinic)}\nНайдено записей: {total}\nВыберите запись:"
        else:
            title = f"Найдено записей: {total}\nВыберите запись:"
    await upsert_ui_message(
        message,
        state,
        title,
        reply_markup=get_edit_items_keyboard(items, page=page, total=total, page_size=PAGE_SIZE),
    )
    await state.set_state(InventoryForm.edit_select_item)
