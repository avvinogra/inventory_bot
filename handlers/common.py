from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

import database as db
from bot_core.access import is_allowed
from bot_core.constants import INVENTORY_FIELDS
from bot_core.flow import REQUIRED_FIELDS, get_tech_prompt, next_field, safe_edit_message, show_confirmation, upsert_ui_message
from bot_core.keyboards import (
    get_clinic_keyboard,
    get_exit_confirm_keyboard,
    get_main_keyboard,
    get_nav_keyboard,
)
from bot_core.states import InventoryForm

router = Router()

# state → короткое имя поля (для skip / back)
STATE_TO_FIELD = {
    "InventoryForm:entering_cabinet":  "cabinet",
    "InventoryForm:entering_tech":     "tech",
    "InventoryForm:entering_serial":   "serial",
    "InventoryForm:entering_inv":      "inv",
    "InventoryForm:entering_os":       "os",
    "InventoryForm:entering_drweb":     "drweb",
    "InventoryForm:entering_ip":       "ip",
    "InventoryForm:entering_pc_name":  "pc_name",
    "InventoryForm:entering_mac_phys": "mac_phys",
    "InventoryForm:entering_mac_real": "mac_real",
    "InventoryForm:entering_specs":    "specs",
    "InventoryForm:entering_note":     "note",
    "InventoryForm:selecting_tech_type": "tech_type",
    "InventoryForm:selecting_clinic":    "clinic",
}


# Состояния, в которых у пользователя могут быть несохранённые данные
# (создание новой записи или режим правки поля новой записи).
_ACTIVE_INPUT_STATES = {
    "InventoryForm:entering_cabinet",
    "InventoryForm:entering_tech",
    "InventoryForm:entering_serial",
    "InventoryForm:entering_inv",
    "InventoryForm:entering_os",
    "InventoryForm:entering_drweb",
    "InventoryForm:entering_ip",
    "InventoryForm:entering_pc_name",
    "InventoryForm:entering_mac_phys",
    "InventoryForm:entering_mac_real",
    "InventoryForm:entering_specs",
    "InventoryForm:entering_note",
    "InventoryForm:selecting_tech_type",
    "InventoryForm:confirming_save",
    "InventoryForm:confirming_inv_duplicate",
    "InventoryForm:confirming_serial_duplicate",
    "InventoryForm:confirming_pc_name_duplicate",
    "InventoryForm:confirming_mac_mismatch",
}


def _welcome_text(name: str) -> str:
    """Приветственное сообщение с описанием возможностей бота."""
    return (
        f"👋 Привет, {name}!\n\n"
        "🏥 БОТ ИНВЕНТАРИЗАЦИИ ИТ-ОБОРУДОВАНИЯ\n\n"
        "📋 ЧТО УМЕЕТ ЭТОТ БОТ?\n\n"
        "➕ Добавление записей — системные блоки, мониторы, принтеры, ноутбуки\n"
        "✏️ Редактирование — поиск по инв. номеру, ID, поликлинике, имени ПК\n"
        "🔍 Глобальный поиск — один запрос по всем полям\n"
        "📥 Импорт из Excel — массовое добавление из .xlsx\n"
        "📊 Экспорт в Excel — выгрузка базы по поликлиникам\n"
        "🔎 Аудит — поиск проблемных записей (без IP, MAC, имени ПК)\n\n"
        "👇 Выберите действие:"
    )


async def _has_unsaved_data(state: FSMContext) -> bool:
    """Проверяет, есть ли в state введённые данные новой записи
    (не из режима редактирования существующей)."""
    data = await state.get_data()
    # Если мы в режиме редактирования существующей записи — выхода нет,
    # всё уже в БД.
    if data.get("editing_mode") == "existing":
        return False
    # Признак несохранённых данных — хотя бы одно из обязательных/необязательных полей
    for key in ("cabinet", "tech", "serial", "inv", "os", "drweb",
                "ip", "pc_name", "mac_phys", "mac_real", "specs", "note"):
        if data.get(key):
            return True
    return False


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    if not is_allowed(message.chat.id):
        await message.answer("❌ Доступ запрещён!")
        return

    db.clear_user_state(message.chat.id)
    await state.clear()
    welcome_text = _welcome_text(message.from_user.first_name)
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
        _welcome_text(message.from_user.first_name),
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


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Выход в главное меню — с подтверждением, если есть несохранённые данные."""
    await callback.answer()
    current_state = await state.get_state()

    if current_state in _ACTIVE_INPUT_STATES and await _has_unsaved_data(state):
        # Есть несохранённые данные — спросить подтверждение
        await state.set_state(InventoryForm.confirming_exit)
        await upsert_ui_message(
            callback.message,
            state,
            "⚠️ У вас есть несохранённые данные.\n"
            "Если вы выйдете сейчас — они будут потеряны.\n\n"
            "Точно выйти в главное меню?",
            reply_markup=get_exit_confirm_keyboard(),
        )
        return

    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    db.clear_user_state(callback.message.chat.id)
    await upsert_ui_message(
        callback.message,
        state,
        _welcome_text(callback.from_user.first_name),
        reply_markup=get_main_keyboard(callback.message.chat.id),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.callback_query(F.data == "cancel_process")
async def cancel_process(callback: types.CallbackQuery, state: FSMContext):
    """Отмена процесса — с подтверждением, если есть несохранённые данные."""
    await callback.answer()
    current_state = await state.get_state()

    if current_state in _ACTIVE_INPUT_STATES and await _has_unsaved_data(state):
        await state.set_state(InventoryForm.confirming_exit)
        await upsert_ui_message(
            callback.message,
            state,
            "⚠️ У вас есть несохранённые данные.\n"
            "Если вы отмените сейчас — они будут потеряны.\n\n"
            "Точно отменить процесс?",
            reply_markup=get_exit_confirm_keyboard(),
        )
        return

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


@router.callback_query(F.data == "confirm_exit_yes")
async def confirm_exit_yes(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь подтвердил выход — выходим, теряем данные."""
    await callback.answer()
    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    db.clear_user_state(callback.message.chat.id)
    await upsert_ui_message(
        callback.message,
        state,
        _welcome_text(callback.from_user.first_name),
        reply_markup=get_main_keyboard(callback.message.chat.id),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.callback_query(F.data == "confirm_exit_no")
async def confirm_exit_no(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь решил продолжить ввод — вернуть его к предыдущему состоянию."""
    await callback.answer()
    data = await state.get_data()
    item_id = data.get("editing_item_id")

    # Если была активна правка СУЩЕСТВУЮЩЕЙ записи — вернуть карточку
    if item_id and data.get("editing_mode") == "existing":
        from handlers.editing import show_record_card
        await show_record_card(callback.message, state, item_id)
        return

    # Иначе — вернуть карточку подтверждения (show_confirmation)
    # Карточка покажет все уже введённые поля и позволит продолжить.
    if any(data.get(k) for k in ("cabinet", "tech", "serial", "inv")):
        await show_confirmation(callback.message, state)
        return

    # Если данных ещё нет — вернуть в главное меню без подтверждения
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    await upsert_ui_message(
        callback.message,
        state,
        _welcome_text(callback.from_user.first_name),
        reply_markup=get_main_keyboard(callback.message.chat.id),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


@router.callback_query(F.data == "skip_current_field")
async def skip_field(callback: types.CallbackQuery, state: FSMContext):
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


@router.callback_query(F.data == "field_absent")
async def field_absent(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь нажал «Отсутствует» — нет инв. номера / серийного.
    Сохраняет значение «Отсутствует» БЕЗ проверки дубликатов.
    """
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()
    current_field = STATE_TO_FIELD.get(current_state)

    if not current_field:
        await callback.answer("⚠️ Неизвестное поле", show_alert=True)
        return

    mode = data.get("editing_mode")

    if mode == "existing":
        item_id = data.get("editing_item_id")
        if item_id:
            db.update_item(item_id, current_field, "Отсутствует")
            await state.update_data(editing_field=None, editing_mode=None)
            from handlers.editing import show_record_card
            await show_record_card(callback.message, state, item_id,
                                   just_saved_field=(current_field, "Отсутствует"))
            return

    if mode == "new_record":
        data[current_field] = "Отсутствует"
        await state.update_data(**data, editing_field=None, editing_mode=None)
        await show_confirmation(callback.message, state)
        return

    data[current_field] = "Отсутствует"
    await state.update_data(**data)
    await next_field(callback.message, state, data, current_field)


@router.callback_query(F.data == "back_prev_step")
async def back_prev_step(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    data = await state.get_data()

    if not current_state:
        await back_to_menu(callback, state)
        return

    # В режиме правки существующей записи — кнопка "Назад" не действует
    if data.get("editing_mode") == "existing":
        await callback.answer("⚠️ В режиме правки используйте «Назад к карточке»", show_alert=True)
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


# ✅ start_edit теперь полноценная функция — реализация в handlers/editing.py.
# Здесь оставлен только делегирующий handler как точка входа
# (на случай если потребуется переопределение на уровне common).
