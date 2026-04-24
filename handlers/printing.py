import os
import time

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

import config
import database as db
from barcode_generator import create_label_pdf
from bot_core.flow import delete_user_message, send_barcode_to_telegram, upsert_ui_message
from bot_core.keyboards import (
    get_after_print_keyboard,
    get_clinic_print_keyboard,
    get_items_from_clinic_keyboard,
    get_print_input_keyboard,
    get_recent_items_keyboard,
)
from bot_core.states import InventoryForm
from config import CLINICS

router = Router()


async def _render_recent_page(target_message: types.Message, page: int):
    items = db.get_all_items(limit=10, offset=page * 10)
    if not items:
        await target_message.answer("❌ Больше записей нет", reply_markup=get_after_print_keyboard())
        return
    text = "📂 Последние добавленные записи:\nВыберите для печати:"
    markup = get_recent_items_keyboard(items, page=page)
    try:
        await target_message.edit_text(text, reply_markup=markup)
    except Exception:
        await target_message.answer(text, reply_markup=markup)


async def _render_clinic_page(target_message: types.Message, clinic_code: str, page: int):
    items = db.get_all_items(clinic=clinic_code, limit=15, offset=page * 15)
    if not items:
        await target_message.answer("❌ Больше записей нет", reply_markup=get_after_print_keyboard())
        return
    text = f"🏥 {CLINICS[clinic_code]}\nВыберите устройство для печати:"
    markup = get_items_from_clinic_keyboard(items, page=page)
    try:
        await target_message.edit_text(text, reply_markup=markup)
    except Exception:
        await target_message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "print_last_label")
async def print_last_label(callback: types.CallbackQuery):
    await callback.answer()
    last_item = db.get_last_item()
    if not last_item:
        await callback.message.answer("❌ В базе нет данных", reply_markup=get_after_print_keyboard())
        return
    await send_barcode_to_telegram(
        callback.message,
        inv_number=last_item["inv_number"],
        tech=last_item["tech"],
        cabinet=last_item["cabinet"],
        serial=last_item["serial"],
        clinic=last_item["clinic"],
    )
    await callback.message.answer("Выберите действие:", reply_markup=get_after_print_keyboard())


@router.callback_query(F.data == "print_recent_10")
async def print_recent_10(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(print_page=0, print_source="recent")
    await _render_recent_page(callback.message, page=0)


@router.callback_query(F.data == "print_by_clinic")
async def print_by_clinic_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await upsert_ui_message(
        callback.message,
        state,
        "🏥 Выберите поликлинику для печати этикеток:",
        reply_markup=get_clinic_print_keyboard(),
        preferred_message_id=callback.message.message_id,
    )


@router.callback_query(F.data.startswith("print_clinic_"))
async def print_clinic_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        clinic_code = callback.data.split("_", 2)[2]
    except (AttributeError, IndexError):
        await callback.answer("❌ Ошибка выбора поликлиники", show_alert=True)
        return
    if clinic_code not in CLINICS:
        await callback.answer("❌ Неизвестная поликлиника", show_alert=True)
        return
    await state.update_data(print_page=0, print_source="clinic", print_clinic=clinic_code)
    await _render_clinic_page(callback.message, clinic_code=clinic_code, page=0)


@router.callback_query(F.data.startswith("print_recent_page_"))
async def print_recent_page(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        page = max(int(callback.data.split("_")[3]), 0)
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Ошибка пагинации", show_alert=True)
        return
    await state.update_data(print_page=page, print_source="recent")
    await _render_recent_page(callback.message, page=page)


@router.callback_query(F.data.startswith("print_clinic_page_"))
async def print_clinic_page(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    clinic_code = data.get("print_clinic")
    if not clinic_code:
        await callback.answer("❌ Сначала выберите поликлинику", show_alert=True)
        return
    try:
        page = max(int(callback.data.split("_")[3]), 0)
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Ошибка пагинации", show_alert=True)
        return
    await state.update_data(print_page=page, print_source="clinic")
    await _render_clinic_page(callback.message, clinic_code=clinic_code, page=page)


@router.callback_query(F.data.startswith("print_item_"))
async def print_selected_item(callback: types.CallbackQuery):
    await callback.answer()
    try:
        item_id = int(callback.data.split("_", 2)[2])
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Ошибка выбора записи", show_alert=True)
        return
    item = db.get_item_by_id(item_id)
    if not item:
        await callback.message.answer("❌ Запись не найдена", reply_markup=get_after_print_keyboard())
        return
    await send_barcode_to_telegram(
        callback.message, item["inv_number"], item["tech"], item["cabinet"], item["serial"], item["clinic"]
    )
    await callback.message.answer("Выберите действие:", reply_markup=get_after_print_keyboard())


@router.callback_query(F.data == "print_by_inv")
async def print_by_inv(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(print_mode="single")
    await upsert_ui_message(
        callback.message,
        state,
        "🔍 Введите инвентарный номер:",
        reply_markup=get_print_input_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(InventoryForm.waiting_for_inv_print)


@router.callback_query(F.data == "print_multiple_labels")
async def print_multiple_labels(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(print_mode="multiple")
    await upsert_ui_message(
        callback.message,
        state,
        "📑 Введите номера через запятую:\nПример: 034143020201024,034143020201025",
        reply_markup=get_print_input_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(InventoryForm.waiting_for_inv_print)


@router.message(InventoryForm.waiting_for_inv_print)
async def process_print_request(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    data = await state.get_data()
    print_mode = data.get("print_mode", "single")
    text = message.text.strip()

    if print_mode == "single":
        item = db.find_by_inv(text)
        if not item:
            await message.answer(
                f"❌ ИНВ № {text} не найден.\nПопробуйте ещё раз или нажмите «Назад».",
                reply_markup=get_print_input_keyboard(),
            )
            return
        await send_barcode_to_telegram(
            message, item["inv_number"], item["tech"], item["cabinet"], item["serial"], item["clinic"]
        )
        await message.answer("Выберите действие:", reply_markup=get_after_print_keyboard())
    else:
        inv_numbers = [x.strip() for x in text.split(",") if x.strip()]
        if not inv_numbers:
            await message.answer(
                "❌ Не указаны номера.\nВведите номера через запятую или нажмите «Назад».",
                reply_markup=get_print_input_keyboard(),
            )
            return

        await message.answer("⏳ Генерирую PDF...")
        items = []
        for inv in inv_numbers:
            item = db.find_by_inv(inv)
            if item:
                items.append(
                    {
                        "clinic": CLINICS.get(item["clinic"], item["clinic"]),
                        "cabinet": item["cabinet"],
                        "tech": item["tech"],
                        "serial": item["serial"],
                        "inv": item["inv_number"],
                    }
                )

        if not items:
            await message.answer(
                "❌ Ни одна запись не найдена.\nПроверьте номера или нажмите «Назад».",
                reply_markup=get_print_input_keyboard(),
            )
            return

        timestamp = int(time.time())
        pdf_path = os.path.join(config.LABELS_DIR, f"labels_{timestamp}.pdf")
        if create_label_pdf(items, pdf_path):
            with open(pdf_path, "rb") as pdf_file:
                await message.answer_document(
                    types.BufferedInputFile(pdf_file.read(), filename=f"etiketki_{len(items)}.pdf"),
                    caption=f"📑 Этикетки ({len(items)} шт.)",
                )
            os.remove(pdf_path)
            await message.answer("✅ PDF отправлен!", reply_markup=get_after_print_keyboard())
        else:
            await message.answer("❌ Ошибка генерации PDF", reply_markup=get_after_print_keyboard())
            return

    await state.clear()

