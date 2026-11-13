"""Подтверждение предупреждений: дубликаты серийного/инвентарного номера
и несовпадение физического/реального MAC.

Сами предупреждения показывает fields.py (process_serial / process_inv /
process_mac_real) — здесь обрабатываются кнопки «продолжить всё равно /
ввести заново / пропустить».
"""

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot_core.flow import next_field, upsert_ui_message
from bot_core.keyboards import get_skip_cancel_keyboard
from bot_core.states import InventoryForm
from handlers.inventory.fields import _after_field_input

router = Router()


@router.callback_query(
    F.data == "confirm_serial_continue", InventoryForm.confirming_serial_duplicate
)
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
    await _after_field_input(callback.message, state, "mac_real", "")
