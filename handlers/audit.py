"""Аудиторский фильтр — поиск проблемных записей в БД.

Доступно только админам из админ-меню (кнопка «🔍 Проблемные записи»).

Категории аудита:
  • Без имени компьютера       — записи (ПК/ноутбук/принтер) без pc_name
  • Без IP-адреса              — записи (ПК/ноутбук/принтер) без ip
  • Без MAC-адресов            — записи (ПК/ноутбук/принтер) без физ. и реал. MAC
  • Dr.Web: проблема           — со статусом «Нет лицензии» или «Нет соединения»
  • Физ. MAC ≠ Реал. MAC       — расхождение физических и реальных MAC
  • Без характеристик          — записи (ПК/ноутбук) без поля specs

Список результатов — кликабельный: при выборе записи открывается её карточка
(через handlers.editing.show_record_card).
"""
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

import database as db
from bot_core.access import is_admin
from bot_core.constants import EDITABLE_FIELDS, display_drweb
from bot_core.flow import upsert_ui_message
from bot_core.keyboards import (
    AUDIT_CATEGORIES,
    get_audit_keyboard,
    get_audit_results_keyboard,
    get_edit_record_keyboard,
)
from bot_core.states import InventoryForm
from config import CLINICS

router = Router()
PAGE_SIZE = 10


# ============================================================
# ТОЧКА ВХОДА — открытие меню категорий аудита
# ============================================================
@router.callback_query(F.data == "audit_menu")
async def audit_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    data = await state.get_data()
    ui_message_id = data.get("ui_message_id")
    await state.clear()
    await state.update_data(ui_message_id=ui_message_id)
    await state.set_state(InventoryForm.audit_select_category)

    await upsert_ui_message(
        callback.message,
        state,
        "🔍 Аудиторский фильтр\n\n"
        "Выберите категорию — покажу все записи с этой проблемой.\n"
        "Клик по записи открывает её карточку для правки.",
        reply_markup=get_audit_keyboard(),
        preferred_message_id=ui_message_id or callback.message.message_id,
    )


# ============================================================
# ВЫБОР КАТЕГОРИИ → ПОКАЗАТЬ РЕЗУЛЬТАТЫ (1-я страница)
# ============================================================
@router.callback_query(F.data.startswith("audit_cat_"), InventoryForm.audit_select_category)
async def audit_show_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    try:
        category = callback.data.split("audit_cat_", 1)[1]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка категории", show_alert=True)
        return

    label_dict = dict(AUDIT_CATEGORIES)
    if category not in label_dict:
        await callback.answer("❌ Неизвестная категория", show_alert=True)
        return

    items = db.find_problematic_items(category, limit=200)
    total = len(items)

    await state.update_data(audit_category=category)

    # Берём только первую страницу для показа
    page_items = items[:PAGE_SIZE]

    if not page_items:
        await upsert_ui_message(
            callback.message,
            state,
            f"✅ Записей с проблемой «{label_dict.get(category, category)}» не найдено.\n"
            f"Всё в порядке!",
            reply_markup=get_audit_keyboard(),
        )
        return

    await _render_audit_results(callback.message, state, page_items, total, category, page=0)


# ============================================================
# ПАГИНАЦИЯ РЕЗУЛЬТАТОВ
# ============================================================
@router.callback_query(F.data.startswith("audit_page_"))
async def audit_results_page(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    try:
        # формат: audit_page_{category}_{page}
        rest = callback.data.split("audit_page_", 1)[1]
        parts = rest.rsplit("_", 1)
        if len(parts) != 2:
            raise ValueError
        category = parts[0]
        page = max(int(parts[1]), 0)
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Ошибка пагинации", show_alert=True)
        return

    items = db.find_problematic_items(category, limit=200)
    total = len(items)

    start = page * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]

    if not page_items:
        await upsert_ui_message(
            callback.message,
            state,
            "❌ Больше записей нет",
            reply_markup=get_audit_keyboard(),
        )
        return

    await _render_audit_results(callback.message, state, page_items, total, category, page=page)


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ — рендер страницы результатов аудита
# ============================================================
async def _render_audit_results(message, state, items, total, category, page):
    label_dict = dict(AUDIT_CATEGORIES)
    label = label_dict.get(category, category)

    # Сводка по проблеме
    summary = f"🔍 Аудит: {label}\nНайдено записей: {total}\n\nВыберите запись для правки:"

    await upsert_ui_message(
        message,
        state,
        summary,
        reply_markup=get_audit_results_keyboard(items, total, category, page=page, page_size=PAGE_SIZE),
    )
    # Состояние — edit_select_item, чтобы обработчики handlers/editing.py
    # открыли карточку при клике на edit_open_<id>
    await state.set_state(InventoryForm.edit_select_item)
    await state.update_data(audit_category=category, edit_clinic=None)
