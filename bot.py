import logging
import json
import re
import os
import time
import shutil
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
from config import CLINICS
import database as db
from barcode_generator import generate_barcode_image, create_label_pdf

#============================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
#============================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#============================================
# ИНИЦИАЛИЗАЦИЯ БОТА
#============================================
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

#============================================
# ТИПЫ ТЕХНИКИ И ИХ ПОЛЯ
#============================================
TECH_TYPES = {
    'pc': {
        'name': '💻 Системный блок',
        'fields': ['cabinet', 'tech', 'serial', 'inv', 'ip', 'mac', 'os', 'drweb', 'office', 'note']
    },
    'monitor': {
        'name': '🖥️ Монитор',
        'fields': ['cabinet', 'tech', 'serial', 'inv', 'note']
    },
    'printer': {
        'name': '🖨️ Принтер/МФУ',
        'fields': ['cabinet', 'tech', 'serial', 'inv', 'ip', 'mac', 'note']
    },
    'laptop': {
        'name': '💻 Ноутбук',
        'fields': ['cabinet', 'tech', 'serial', 'inv', 'ip', 'mac', 'os', 'drweb', 'office', 'note']
    },
    'other': {
        'name': '📱 Другое',
        'fields': ['cabinet', 'tech', 'serial', 'inv', 'note']
    }
}

#============================================
# СПИСОК ПОЛЕЙ ИНВЕНТАРИЗАЦИИ
#============================================
INVENTORY_FIELDS = ['cabinet', 'tech', 'serial', 'inv', 'ip', 'mac', 'os', 'drweb', 'office', 'note']

#============================================
# ПРОВЕРКА ПРАВ ДОСТУПА
#============================================
def is_admin(chat_id: int) -> bool:
    return chat_id in config.ADMIN_CHAT_IDS

def is_allowed(chat_id: int) -> bool:
    return chat_id in config.ALLOWED_CHAT_IDS

#============================================
# МАШИНА СОСТОЯНИЙ (FSM)
#============================================
class InventoryForm(StatesGroup):
    selecting_clinic = State()
    selecting_tech_type = State()
    entering_cabinet = State()
    entering_tech = State()
    entering_serial = State()
    entering_inv = State()
    entering_ip = State()
    entering_mac = State()
    entering_os = State()
    entering_drweb = State()
    entering_office = State()
    entering_note = State()
    confirming_save = State()
    waiting_for_inv_print = State()
    admin_view_count = State()
    admin_delete_id = State()
    admin_delete_inv = State()

#============================================
# КЛАВИАТУРЫ
#============================================
def get_main_keyboard(chat_id: int = None):
    """Главное меню (с учётом прав доступа)"""
    keyboard = [
        [
            InlineKeyboardButton(text='📋 Начать инвентаризацию', callback_data='start_inventory'),
            InlineKeyboardButton(text='🏷️ Печать штрих-кода', callback_data='print_barcode')
        ],
        [
            InlineKeyboardButton(text='✏️ Редактировать', callback_data='start_edit')
        ]
    ]
    if chat_id and is_admin(chat_id):
        keyboard.append([
            InlineKeyboardButton(text='⚙️ Администрирование', callback_data='admin_menu')
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_clinic_keyboard():
    rows = []
    clinic_list = list(CLINICS.items())
    for i in range(0, len(clinic_list), 2):
        row = []
        row.append(InlineKeyboardButton(
            text=f"{clinic_list[i][0]} - {clinic_list[i][1]}",
            callback_data=f"clinic_{clinic_list[i][0]}"
        ))
        if i + 1 < len(clinic_list):
            row.append(InlineKeyboardButton(
                text=f"{clinic_list[i+1][0]} - {clinic_list[i+1][1]}",
                callback_data=f"clinic_{clinic_list[i+1][0]}"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_process')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_tech_type_keyboard():
    """Клавиатура выбора типа техники (2 колонки)"""
    keyboard = []
    tech_list = list(TECH_TYPES.items())
    
    for i in range(0, len(tech_list), 2):
        row = []
        tech_key, tech_info = tech_list[i]
        row.append(InlineKeyboardButton(
            text=tech_info['name'], 
            callback_data=f"tech_type_{tech_key}"
        ))
        
        if i + 1 < len(tech_list):
            tech_key, tech_info = tech_list[i + 1]
            row.append(InlineKeyboardButton(
                text=tech_info['name'], 
                callback_data=f"tech_type_{tech_key}"
            ))
        
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_process')])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_skip_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='⏭️ Пропустить', callback_data='skip_current_field'),
            InlineKeyboardButton(text='❌ Отменить', callback_data='cancel_process')
        ]
    ])

def get_nav_keyboard(*, can_back: bool, can_skip: bool):
    """Универсальная навигация для шагов ввода: Назад / Пропустить / Отмена."""
    row = []
    if can_back:
        row.append(InlineKeyboardButton(text='⬅️ Назад', callback_data='back_prev_step'))
    if can_skip:
        row.append(InlineKeyboardButton(text='⏭️ Пропустить', callback_data='skip_current_field'))
    row.append(InlineKeyboardButton(text='❌ Отменить', callback_data='cancel_process'))
    return InlineKeyboardMarkup(inline_keyboard=[row])

def get_print_input_keyboard():
    """Клавиатура для ввода ИНВ номера в режиме печати."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='⬅️ Назад', callback_data='print_barcode'),
            InlineKeyboardButton(text='❌ Отменить', callback_data='cancel_process')
        ]
    ])

def get_print_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='📄 Последний', callback_data='print_last_label'),
            InlineKeyboardButton(text='📂 Последние 10', callback_data='print_recent_10')
        ],
        [
            InlineKeyboardButton(text='🏥 По поликлинике', callback_data='print_by_clinic'),
            InlineKeyboardButton(text='📑 Несколько', callback_data='print_multiple_labels')
        ],
        [
            InlineKeyboardButton(text='🔍 По ИНВ номеру', callback_data='print_by_inv'),
            InlineKeyboardButton(text='⬅️ Назад', callback_data='back_to_menu')
        ]
    ])

def get_after_print_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='🏷️ Ещё печать', callback_data='print_barcode'),
            InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')
        ]
    ])

def get_multiple_labels_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='print_barcode')]
    ])

def get_recent_items_keyboard(items, page=0):
    keyboard = []
    for item in items:
        inv_short = item['inv_number'][:12] + '...' if len(item['inv_number']) > 12 else item['inv_number']
        tech_short = item['tech'][:20] if len(item['tech']) > 20 else item['tech']
        btn_text = f"🏷️ {inv_short} | {tech_short}"
        keyboard.append([InlineKeyboardButton(
            text=btn_text,
            callback_data=f"print_item_{item['id']}"
        )])
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text='⬅️ Страница', callback_data=f"print_recent_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text='⬅️ В меню печати', callback_data='print_barcode'))
    if len(items) == 10:
        nav_row.append(InlineKeyboardButton(text='Вперёд ➡️', callback_data=f"print_recent_page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_clinic_print_keyboard():
    rows = []
    clinic_list = list(CLINICS.items())
    for i in range(0, len(clinic_list), 2):
        row = []
        row.append(InlineKeyboardButton(
            text=f"{clinic_list[i][0]} - {clinic_list[i][1]}",
            callback_data=f"print_clinic_{clinic_list[i][0]}"
        ))
        if i + 1 < len(clinic_list):
            row.append(InlineKeyboardButton(
                text=f"{clinic_list[i+1][0]} - {clinic_list[i+1][1]}",
                callback_data=f"print_clinic_{clinic_list[i+1][0]}"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data='print_barcode')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_items_from_clinic_keyboard(items, page=0):
    keyboard = []
    for item in items:
        inv_short = item['inv_number'][:12] + '...' if len(item['inv_number']) > 12 else item['inv_number']
        btn_text = f"🏷️ {inv_short} | {item['cabinet']} | {item['tech'][:15]}"
        keyboard.append([InlineKeyboardButton(
            text=btn_text,
            callback_data=f"print_item_{item['id']}"
        )])
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text='⬅️ Страница', callback_data=f"print_clinic_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text='⬅️ В меню печати', callback_data='print_barcode'))
    if len(items) == 15:
        nav_row.append(InlineKeyboardButton(text='Вперёд ➡️', callback_data=f"print_clinic_page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_keyboard():
    """Административное меню (2 кнопки в ряд)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='📊 Статистика БД', callback_data='admin_stats'),
            InlineKeyboardButton(text='📋 Последние записи', callback_data='admin_view_last')
        ],
        [
            InlineKeyboardButton(text='🗑️ Удалить запись', callback_data='admin_delete'),
            InlineKeyboardButton(text='💾 Скачать БД', callback_data='admin_export_db')
        ],
        [
            InlineKeyboardButton(text='📊 Скачать Excel', callback_data='admin_export_excel'),
            InlineKeyboardButton(text='👥 Пользователи', callback_data='admin_users')
        ],
        [
            InlineKeyboardButton(text='⬅️ Назад', callback_data='back_to_menu')
        ]
    ])

def get_delete_method_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='🔍 По ID', callback_data='admin_delete_by_id'),
            InlineKeyboardButton(text='🏷️ По ИНВ номеру', callback_data='admin_delete_by_inv')
        ],
        [
            InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')
        ]
    ])

def get_confirm_edit_keyboard(data: dict):
    keyboard = []
    field_buttons = [
        ('🏢 Кабинет', 'cabinet'),
        ('🔧 Техника', 'tech'),
        ('🔢 Сер. номер', 'serial'),
        ('🏷️ ИНВ номер', 'inv'),
        ('🌐 IP', 'ip'),
        ('📡 MAC', 'mac'),
        ('🖥️ ОС', 'os'),
        ('🛡️ Dr.Web', 'drweb'),
        ('📄 Office', 'office'),
        ('💬 Примечание', 'note')
    ]
    
    for i in range(0, len(field_buttons), 2):
        row = []
        for j in range(2):
            if i + j < len(field_buttons):
                text, field = field_buttons[i + j]
                value = str(data.get(field, ''))
                if value and len(value) > 15:
                    btn_text = f"{text} ({value[:15]}...)"
                elif value:
                    btn_text = f"{text} ({value})"
                else:
                    btn_text = f"{text} (—)"
                row.append(InlineKeyboardButton(text=btn_text, callback_data=f"edit_field_{field}"))
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(text='✅ Подтвердить и сохранить', callback_data='confirm_save')
    ])
    keyboard.append([
        InlineKeyboardButton(text='❌ Отменить', callback_data='cancel_process')
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_after_save_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='📝 Ввести ещё', callback_data='new_inventory'),
            InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')
        ]
    ])

#============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
#============================================
async def delete_user_message(message: types.Message):
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение: {e}")

async def safe_edit_message(message_id: int, chat_id: int, text: str, reply_markup=None, parse_mode=None):
    try:
        if reply_markup:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode
            )
        return True
    except Exception as e:
        logger.debug(f"Не удалось отредактировать сообщение: {e}")
        return False

async def show_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    clinic_name = CLINICS.get(data.get('clinic', ''), data.get('clinic', 'Неизвестно'))
    tech_type_name = data.get('tech_type_name', 'Не указан')
    
    summary = (
        f"📋 **ПРОВЕРЬТЕ ДАННЫЕ ПЕРЕД СОХРАНЕНИЕМ**\n\n"
        f"🏥 **Поликлиника:** {clinic_name}\n"
        f"🔧 **Тип:** {tech_type_name}\n"
        f"🏢 **Кабинет:** {data.get('cabinet', '—')}\n"
        f"🔧 **Техника:** {data.get('tech', '—')}\n"
        f"🔢 **Серийный номер:** {data.get('serial', '—')}\n"
        f"🏷️ **ИНВ номер:** {data.get('inv', '—')}\n"
    )
    
    if data.get('ip'):
        summary += f"🌐 **IP-адрес:** {data.get('ip')}\n"
    if data.get('mac'):
        summary += f"📡 **MAC-адрес:** {data.get('mac')}\n"
    if data.get('os'):
        summary += f"🖥️ **ОС:** {data.get('os')}\n"
    if data.get('drweb'):
        summary += f"🛡️ **Dr.Web:** {data.get('drweb')}\n"
    if data.get('office'):
        summary += f"📄 **Office:** {data.get('office')}\n"
    if data.get('note'):
        summary += f"💬 **Примечание:** {data.get('note')}\n"
    
    summary += "\n⚠️ Если есть ошибки - нажмите на поле для редактирования"

    await message.answer(
        summary,
        parse_mode='Markdown',
        reply_markup=get_confirm_edit_keyboard(data)
    )

    await state.set_state(InventoryForm.confirming_save)

async def next_field(message, state: FSMContext,  data: dict, current_field: str):
    fields = data.get('tech_fields', INVENTORY_FIELDS)
    tech_type = data.get('tech_type', 'other')
    
    try:
        field_index = fields.index(current_field)
    except ValueError:
        field_index = -1
    
    if field_index >= 0 and field_index < len(fields) - 1:
        next_field_name = fields[field_index + 1]
        
        tech_examples = {
            'pc': 'Системный блок Dell',
            'monitor': 'Монитор Samsung',
            'printer': 'Принтер HP',
            'laptop': 'Ноутбук Lenovo',
            'other': 'Устройство'
        }
        tech_example = tech_examples.get(tech_type, 'Устройство')
        
        prompts = {
            'cabinet': '🏢 Введите номер кабинета (например, 101):',
            'tech': f'🔧 Введите наименование техники (например, {tech_example}):',
            'serial': '🔢 Введите серийный номер:',
            'inv': '🏷️ Введите инвентарный номер:',
            'ip': '🌐 Введите IP-адрес (или "Пропустить"):',
            'mac': '📡 Введите MAC-адрес (или "Пропустить"):',
            'os': '🖥️ Введите Операционную систему:',
            'drweb': '🛡️ Установлен Dr.Web? (да/нет):',
            'office': '📄 Установлен Office? (да/нет):',
            'note': '💬 Введите примечание (или нажмите Enter):'
        }
        
        state_map = {
            'cabinet': InventoryForm.entering_cabinet,
            'tech': InventoryForm.entering_tech,
            'serial': InventoryForm.entering_serial,
            'inv': InventoryForm.entering_inv,
            'ip': InventoryForm.entering_ip,
            'mac': InventoryForm.entering_mac,
            'os': InventoryForm.entering_os,
            'drweb': InventoryForm.entering_drweb,
            'office': InventoryForm.entering_office,
            'note': InventoryForm.entering_note
        }
        
        text = prompts.get(next_field_name, '')
        bot_msg_id = data.get('bot_question_msg_id')

        required_fields = ['cabinet', 'tech', 'serial', 'inv']
        can_skip = next_field_name not in required_fields
        
        if bot_msg_id:
            success = await safe_edit_message(
                message_id=bot_msg_id,
                chat_id=message.chat.id,
                text=text,
                reply_markup=get_nav_keyboard(can_back=True, can_skip=can_skip)
            )
            if not success:
                sent_msg = await message.answer(text, reply_markup=get_nav_keyboard(can_back=True, can_skip=can_skip))
                await state.update_data(bot_question_msg_id=sent_msg.message_id)
        else:
            sent_msg = await message.answer(text, reply_markup=get_nav_keyboard(can_back=True, can_skip=can_skip))
            await state.update_data(bot_question_msg_id=sent_msg.message_id)
        
        await state.set_state(state_map.get(next_field_name))
    else:
        await show_confirmation(message, state)

async def send_barcode_to_telegram(message, inv_number: str, tech: str, cabinet: str, serial: str, clinic: str):
    barcode_path = generate_barcode_image(inv_number)
    if not barcode_path or not os.path.exists(barcode_path):
        await message.answer("❌ Ошибка генерации штрих-кода")
        return
    
    label_text = (
        f"🏥 {clinic}\n📦 Устройство: {tech}\n"
        f"🏢 Кабинет: {cabinet}\n🔢 Сер. №: {serial}\n"
        f"🏷️ ИНВ №: {inv_number}"
    )
    await message.answer(label_text, parse_mode='HTML')

    with open(barcode_path, 'rb') as img_file:
        await message.answer_photo(
            types.BufferedInputFile(img_file.read(), filename="barcode.png"),
            caption=f"🏷️ ИНВ № {inv_number}"
        )

#============================================
# ОБРАБОТЧИКИ КОМАНД
#============================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    if not is_allowed(message.chat.id):
        await message.answer("❌ Доступ запрещён!")
        return
    
    db.clear_user_state(message.chat.id)
    await state.clear()
    welcome_text = f"👋 Привет, {message.from_user.first_name}!\n🏥 Бот инвентаризации\nВыберите действие:"

    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(message.chat.id),
        parse_mode='HTML'
    )

@dp.message(Command('cancel'))
async def cmd_cancel(message: types.Message, state: FSMContext):
    if not is_allowed(message.chat.id):
        return
    
    db.clear_user_state(message.chat.id)
    await state.clear()
    await message.answer("❌ Процесс отменён.", reply_markup=get_main_keyboard(message.chat.id))

@dp.message(Command('menu'))
async def cmd_menu(message: types.Message, state: FSMContext):
    if not is_allowed(message.chat.id):
        return
    
    db.clear_user_state(message.chat.id)
    await state.clear()
    await message.answer("📋 Главное меню:", reply_markup=get_main_keyboard(message.chat.id))

#============================================
# ОБРАБОТЧИКИ CALLBACK (КНОПКИ) - ОСНОВНЫЕ
#============================================
@dp.callback_query(F.data == 'start_inventory')
async def start_inventory(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    db.clear_user_state(callback.message.chat.id)
    await state.clear()
    await callback.message.edit_text("🏥 Выберите поликлинику:", reply_markup=get_clinic_keyboard())
    await state.set_state(InventoryForm.selecting_clinic)

@dp.callback_query(F.data.startswith('clinic_'), InventoryForm.selecting_clinic)
async def clinic_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    clinic_code = callback.data.split('_')[1]
    await state.update_data(clinic=clinic_code, clinic_name=CLINICS[clinic_code])
    
    await callback.message.edit_text(
        f"✅ Выбрана: {CLINICS[clinic_code]}\n🏢 Введите номер кабинета:",
        reply_markup=get_skip_cancel_keyboard()
    )
    await state.update_data(bot_question_msg_id=callback.message.message_id)
    await state.set_state(InventoryForm.entering_cabinet)

@dp.callback_query(F.data == 'print_barcode')
async def print_barcode_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "🏷️ Печать штрих-кода\nВыберите опцию:",
        reply_markup=get_print_menu_keyboard(),
        parse_mode='HTML'
    )

@dp.callback_query(F.data == 'back_to_menu')
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    db.clear_user_state(callback.message.chat.id)
    await callback.message.edit_text(
        "👋 Главное меню:",
        reply_markup=get_main_keyboard(callback.message.chat.id)
    )

@dp.callback_query(F.data == 'cancel_process')
async def cancel_process(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    db.clear_user_state(callback.message.chat.id)
    await callback.message.edit_text(
        "❌ Процесс отменён.",
        reply_markup=get_main_keyboard(callback.message.chat.id)
    )

@dp.callback_query(F.data == 'skip_current_field')
async def skip_field(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()
    
    required_fields = ['cabinet', 'tech', 'serial', 'inv']
    
    field_map = {
        'InventoryForm:entering_cabinet': 'cabinet',
        'InventoryForm:entering_tech': 'tech',
        'InventoryForm:entering_serial': 'serial',
        'InventoryForm:entering_inv': 'inv',
        'InventoryForm:entering_ip': 'ip',
        'InventoryForm:entering_mac': 'mac',
        'InventoryForm:entering_os': 'os',
        'InventoryForm:entering_drweb': 'drweb',
        'InventoryForm:entering_office': 'office',
        'InventoryForm:entering_note': 'note'
    }

    current_field = field_map.get(current_state)

    if current_field in required_fields:
        await callback.answer(
            f"⚠️ Поле \"{current_field}\" обязательно для заполнения!",
            show_alert=True
        )
        return

    if current_field:
        data[current_field] = ''
        await state.update_data(**data)
        await next_field(callback.message, state, data, current_field)
    else:
        await callback.answer("⚠️ Неизвестное поле", show_alert=True)

@dp.callback_query(F.data == 'back_prev_step')
async def back_prev_step(callback: types.CallbackQuery, state: FSMContext):
    """Возврат на предыдущий шаг ввода (инвентаризация)."""
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()

    # если мы не в процессе инвентаризации — просто в меню
    if not current_state:
        await back_to_menu(callback, state)
        return

    state_to_field = {
        'InventoryForm:entering_cabinet': 'cabinet',
        'InventoryForm:entering_tech': 'tech',
        'InventoryForm:entering_serial': 'serial',
        'InventoryForm:entering_inv': 'inv',
        'InventoryForm:entering_ip': 'ip',
        'InventoryForm:entering_mac': 'mac',
        'InventoryForm:entering_os': 'os',
        'InventoryForm:entering_drweb': 'drweb',
        'InventoryForm:entering_office': 'office',
        'InventoryForm:entering_note': 'note',
        'InventoryForm:selecting_tech_type': 'tech_type',
        'InventoryForm:selecting_clinic': 'clinic'
    }

    # 1) Назад из выбора типа техники -> назад к кабинету
    if current_state == 'InventoryForm:selecting_tech_type':
        bot_msg_id = data.get('bot_question_msg_id') or callback.message.message_id
        await safe_edit_message(
            bot_msg_id,
            callback.message.chat.id,
            "🏢 Введите номер кабинета:",
            get_nav_keyboard(can_back=True, can_skip=False)
        )
        await state.set_state(InventoryForm.entering_cabinet)
        await state.update_data(bot_question_msg_id=bot_msg_id)
        return

    # 2) Назад из кабинета -> выбор поликлиники
    if current_state == 'InventoryForm:entering_cabinet':
        await callback.message.edit_text("🏥 Выберите поликлинику:", reply_markup=get_clinic_keyboard())
        await state.set_state(InventoryForm.selecting_clinic)
        return

    # 3) Назад из любого поля -> предыдущее поле по tech_fields
    field = state_to_field.get(current_state)
    fields = data.get('tech_fields', INVENTORY_FIELDS)
    tech_type = data.get('tech_type', 'other')
    bot_msg_id = data.get('bot_question_msg_id') or callback.message.message_id

    if not field or field not in fields:
        await callback.answer("⚠️ Нельзя вернуться назад отсюда", show_alert=True)
        return

    idx = fields.index(field)
    if idx <= 0:
        await callback.answer("⚠️ Это первый шаг", show_alert=True)
        return

    prev_field = fields[idx - 1]

    tech_examples = {
        'pc': 'Системный блок Dell',
        'monitor': 'Монитор Samsung',
        'printer': 'Принтер HP',
        'laptop': 'Ноутбук Lenovo',
        'other': 'Устройство'
    }
    tech_example = tech_examples.get(tech_type, 'Устройство')

    prompts = {
        'cabinet': '🏢 Введите номер кабинета (например, 101):',
        'tech': f'🔧 Введите наименование техники (например, {tech_example}):',
        'serial': '🔢 Введите серийный номер:',
        'inv': '🏷️ Введите инвентарный номер:',
        'ip': '🌐 Введите IP-адрес (или "Пропустить"):',
        'mac': '📡 Введите MAC-адрес (или "Пропустить"):',
        'os': '🖥️ Введите Операционную систему:',
        'drweb': '🛡️ Установлен Dr.Web? (да/нет):',
        'office': '📄 Установлен Office? (да/нет):',
        'note': '💬 Введите примечание (или нажмите Enter):'
    }

    state_map = {
        'cabinet': InventoryForm.entering_cabinet,
        'tech': InventoryForm.entering_tech,
        'serial': InventoryForm.entering_serial,
        'inv': InventoryForm.entering_inv,
        'ip': InventoryForm.entering_ip,
        'mac': InventoryForm.entering_mac,
        'os': InventoryForm.entering_os,
        'drweb': InventoryForm.entering_drweb,
        'office': InventoryForm.entering_office,
        'note': InventoryForm.entering_note
    }

    required_fields = ['cabinet', 'tech', 'serial', 'inv']
    can_skip = prev_field not in required_fields

    ok = await safe_edit_message(
        bot_msg_id,
        callback.message.chat.id,
        prompts.get(prev_field, 'Введите значение:'),
        get_nav_keyboard(can_back=True, can_skip=can_skip)
    )
    if not ok:
        sent = await callback.message.answer(prompts.get(prev_field, 'Введите значение:'), reply_markup=get_nav_keyboard(can_back=True, can_skip=can_skip))
        bot_msg_id = sent.message_id

    await state.update_data(bot_question_msg_id=bot_msg_id, editing_field=None)
    await state.set_state(state_map.get(prev_field))

#============================================
# ВЫБОР ТИПА ТЕХНИКИ
#============================================
@dp.callback_query(F.data.startswith('tech_type_'), InventoryForm.selecting_tech_type)
async def tech_type_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    tech_key = callback.data.split('_')[2]
    tech_info = TECH_TYPES[tech_key]
    
    tech_examples = {
        'pc': 'Системный блок Dell OptiPlex',
        'monitor': 'Монитор Samsung 24"',
        'printer': 'Принтер HP LaserJet Pro',
        'laptop': 'Ноутбук Lenovo ThinkPad',
        'other': 'Устройство'
    }
    
    example = tech_examples.get(tech_key, 'Устройство')
    
    await state.update_data(
        tech_type=tech_key,
        tech_type_name=tech_info['name'],
        tech_fields=tech_info['fields']
    )
    
    data = await state.get_data()
    bot_msg_id = data.get('bot_question_msg_id')
    
    if bot_msg_id:
        await safe_edit_message(
            bot_msg_id,
            callback.message.chat.id,
            f"✅ {tech_info['name']}\n🔧 Введите наименование техники (например, {example}):",
            get_skip_cancel_keyboard()
        )
    else:
        new_msg = await callback.message.answer(
            f"✅ {tech_info['name']}\n🔧 Введите наименование техники (например, {example}):",
            reply_markup=get_skip_cancel_keyboard()
        )
        await state.update_data(bot_question_msg_id=new_msg.message_id)
    
    await state.set_state(InventoryForm.entering_tech)

#============================================
# РЕДАКТИРОВАНИЕ ПОЛЕЙ (ПОДТВЕРЖДЕНИЕ)
#============================================
@dp.callback_query(F.data.startswith('edit_field_'), InventoryForm.confirming_save)
async def edit_field_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    field_name = callback.data.split('_')[2]
    
    data = await state.get_data()
    tech_type = data.get('tech_type', 'other')
    
    tech_examples = {
        'pc': 'Системный блок Dell',
        'monitor': 'Монитор Samsung',
        'printer': 'Принтер HP',
        'laptop': 'Ноутбук Lenovo',
        'other': 'Устройство'
    }
    tech_example = tech_examples.get(tech_type, 'Устройство')
    
    field_to_state = {
        'cabinet': InventoryForm.entering_cabinet,
        'tech': InventoryForm.entering_tech,
        'serial': InventoryForm.entering_serial,
        'inv': InventoryForm.entering_inv,
        'ip': InventoryForm.entering_ip,
        'mac': InventoryForm.entering_mac,
        'os': InventoryForm.entering_os,
        'drweb': InventoryForm.entering_drweb,
        'office': InventoryForm.entering_office,
        'note': InventoryForm.entering_note
    }

    prompts = {
        'cabinet': '🏢 Введите НОВЫЙ номер кабинета:',
        'tech': f'🔧 Введите НОВОЕ наименование техники (например, {tech_example}):',
        'serial': '🔢 Введите НОВЫЙ серийный номер:',
        'inv': '🏷️ Введите НОВЫЙ инвентарный номер:',
        'ip': '🌐 Введите НОВЫЙ IP-адрес (или "Пропустить"):',
        'mac': '📡 Введите НОВЫЙ MAC-адрес (или "Пропустить"):',
        'os': '🖥️ Введите НОВУЮ операционную систему:',
        'drweb': '🛡️ Установлен Dr.Web? (да/нет):',
        'office': '📄 Установлен Office? (да/нет):',
        'note': '💬 Введите НОВОЕ примечание:'
    }

    await state.update_data(editing_field=field_name)

    await callback.message.edit_text(
        prompts.get(field_name, 'Введите новое значение:'),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад к проверке', callback_data='back_to_confirm')]
        ])
    )

    await state.set_state(field_to_state.get(field_name))

@dp.callback_query(F.data == 'back_to_confirm')
async def back_to_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(editing_field=None)
    await show_confirmation(callback.message, state)

@dp.callback_query(F.data == 'confirm_save', InventoryForm.confirming_save)
async def confirm_save(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    item_id = db.save_item(data['clinic'], data)
    await state.clear()

    await callback.message.edit_text(
        f"✅ **Сохранено!**\n\n"
        f"📝 **ID записи:** {item_id}\n\n"
        f"📋 **Что делаем дальше?**",
        parse_mode='Markdown',
        reply_markup=get_after_save_keyboard()
    )

@dp.callback_query(F.data == 'new_inventory')
async def new_inventory(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    db.clear_user_state(callback.message.chat.id)
    await state.clear()
    await callback.message.edit_text(
        "🏥 Выберите поликлинику:",
        reply_markup=get_clinic_keyboard()
    )
    await state.set_state(InventoryForm.selecting_clinic)

#============================================
# ОБРАБОТЧИКИ ПЕЧАТИ
#============================================
@dp.callback_query(F.data == 'print_last_label')
async def print_last_label(callback: types.CallbackQuery):
    await callback.answer()
    last_item = db.get_last_item()
    if not last_item:
        await callback.message.answer("❌ В базе нет данных", reply_markup=get_after_print_keyboard())
        return
    
    await send_barcode_to_telegram(
        callback.message,
        inv_number=last_item['inv_number'],
        tech=last_item['tech'],
        cabinet=last_item['cabinet'],
        serial=last_item['serial'],
        clinic=last_item['clinic']
    )
    await callback.message.answer("Выберите действие:", reply_markup=get_after_print_keyboard())

@dp.callback_query(F.data == 'print_recent_10')
async def print_recent_10(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    items = db.get_all_items(limit=10)
    if not items:
        await callback.message.answer("❌ В базе нет записей")
        return
    
    await state.update_data(print_page=0, print_source='recent')
    await callback.message.answer(
        "📂 Последние добавленные записи:\nВыберите для печати:",
        reply_markup=get_recent_items_keyboard(items)
    )

@dp.callback_query(F.data == 'print_by_clinic')
async def print_by_clinic_menu(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🏥 Выберите поликлинику для печати этикеток:",
        reply_markup=get_clinic_print_keyboard()
    )

@dp.callback_query(F.data.startswith('print_clinic_'))
async def print_clinic_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    clinic_code = callback.data.split('_')[2]
    items = db.get_all_items(clinic=clinic_code, limit=15)
    if not items:
        await callback.message.answer(f"❌ В {CLINICS[clinic_code]} нет записей")
        return
    
    await state.update_data(
        print_page=0,
        print_source='clinic',
        print_clinic=clinic_code
    )

    await callback.message.answer(
        f"🏥 {CLINICS[clinic_code]}\nВыберите устройство для печати:",
        reply_markup=get_items_from_clinic_keyboard(items)
    )

@dp.callback_query(F.data.startswith('print_item_'))
async def print_selected_item(callback: types.CallbackQuery):
    await callback.answer()
    item_id = int(callback.data.split('_')[2])
    item = db.get_item_by_id(item_id)
    if not item:
        await callback.message.answer("❌ Запись не найдена", reply_markup=get_after_print_keyboard())
        return
    
    await send_barcode_to_telegram(
        callback.message,
        item['inv_number'],
        item['tech'],
        item['cabinet'],
        item['serial'],
        item['clinic']
    )
    await callback.message.answer("Выберите действие:", reply_markup=get_after_print_keyboard())

@dp.callback_query(F.data == 'print_by_inv')
async def print_by_inv(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(print_mode='single')
    await callback.message.answer("🔍 Введите инвентарный номер:", reply_markup=get_print_input_keyboard(), parse_mode='HTML')
    await state.set_state(InventoryForm.waiting_for_inv_print)

@dp.callback_query(F.data == 'print_multiple_labels')
async def print_multiple_labels(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(print_mode='multiple')
    await callback.message.answer(
        "📑 Введите номера через запятую:\nПример: 034143020201024,034143020201025",
        reply_markup=get_print_input_keyboard(),
        parse_mode='HTML'
    )
    await state.set_state(InventoryForm.waiting_for_inv_print)

@dp.callback_query(F.data == 'start_edit')
async def start_edit(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("⚠️ Функция редактирования в разработке")

#============================================
# ОБРАБОТЧИКИ ВВОДА ДАННЫХ (С ОЧИСТКОЙ ЧАТА)
#============================================
@dp.message(InventoryForm.waiting_for_inv_print)
async def process_print_request(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    data = await state.get_data()
    print_mode = data.get('print_mode', 'single')
    text = message.text.strip()

    if print_mode == 'single':
        item = db.find_by_inv(text)
        if not item: 
            await message.answer(f"❌ ИНВ № {text} не найден.\nПопробуйте ещё раз или нажмите «Назад».", reply_markup=get_print_input_keyboard())
            return
        await send_barcode_to_telegram(
            message,
            item['inv_number'],
            item['tech'],
            item['cabinet'],
            item['serial'],
            item['clinic']
        )
        await message.answer("Выберите действие:", reply_markup=get_after_print_keyboard())
    else:
        inv_numbers = [x.strip() for x in text.split(',') if x.strip()]
        if not inv_numbers:
            await message.answer("❌ Не указаны номера.\nВведите номера через запятую или нажмите «Назад».", reply_markup=get_print_input_keyboard())
            return
        
        await message.answer("⏳ Генерирую PDF...")
        items = []
        for inv in inv_numbers:
            item = db.find_by_inv(inv)
            if item:
                items.append({
                    'clinic': CLINICS.get(item['clinic'], item['clinic']),
                    'cabinet': item['cabinet'],
                    'tech': item['tech'],
                    'serial': item['serial'],
                    'inv': item['inv_number']
                })
        if not items:
            await message.answer("❌ Ни одна запись не найдена.\nПроверьте номера или нажмите «Назад».", reply_markup=get_print_input_keyboard())
            return
        
        timestamp = int(time.time())
        pdf_path = os.path.join(config.LABELS_DIR, f"labels_{timestamp}.pdf")
        if create_label_pdf(items, pdf_path):
            with open(pdf_path, 'rb') as pdf_file:
                await message.answer_document(
                    types.BufferedInputFile(pdf_file.read(), filename=f"etiketki_{len(items)}.pdf"),
                    caption=f"📑 Этикетки ({len(items)} шт.)"
                )
            os.remove(pdf_path)
            await message.answer("✅ PDF отправлен!", reply_markup=get_after_print_keyboard())
        else:
            await message.answer("❌ Ошибка генерации PDF", reply_markup=get_after_print_keyboard())
            return

    await state.clear()

@dp.message(InventoryForm.entering_cabinet)
async def process_cabinet(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    
    # 1. Проверка на пустое значение
    if not text:
        data = await state.get_data()
        bot_msg_id = data.get('bot_question_msg_id')
        if bot_msg_id:
            await safe_edit_message(
                bot_msg_id, message.chat.id,
                '❌ Поле "Кабинет" не может быть пустым!\n🏢 Введите номер кабинета (101) или название (Регистратура):',
                get_skip_cancel_keyboard()
            )
        return

    # 2. Проверка на команду пропуска (если вдруг пользователь ввёл текстом)
    if text.lower() in ['пропустить', 'skip']:
        data = await state.get_data()
        bot_msg_id = data.get('bot_question_msg_id')
        if bot_msg_id:
            await safe_edit_message(
                bot_msg_id, message.chat.id,
                '❌ Поле "Кабинет" обязательно для заполнения!\n🏢 Введите номер или название:',
                get_skip_cancel_keyboard()
            )
        return

    # 3. Сохраняем значение (теперь принимаем и "101А", и "Регистратура")
    await state.update_data(cabinet=text)

    # ПОСЛЕ КАБИНЕТА - ПОКАЗЫВАЕМ ВЫБОР ТИПА ТЕХНИКИ
    data = await state.get_data()
    bot_msg_id = data.get('bot_question_msg_id')

    # ОТПРАВЛЯЕМ НОВОЕ СООБЩЕНИЕ С ВЫБОРОМ ТИПА ТЕХНИКИ
    tech_msg = await message.answer(
        "🔧 Выберите тип техники:",
        reply_markup=get_tech_type_keyboard()
    )

    # СОХРАНЯЕМ ID НОВОГО СООБЩЕНИЯ
    await state.update_data(bot_question_msg_id=tech_msg.message_id)
    await state.set_state(InventoryForm.selecting_tech_type)

@dp.message(InventoryForm.entering_tech)
async def process_tech(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(tech=message.text.strip())
    data = await state.get_data()
    
    if data.get('editing_field') == 'tech':
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, 'tech')

@dp.message(InventoryForm.entering_serial)
async def process_serial(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    
    if not text:
        data = await state.get_data()
        bot_msg_id = data.get('bot_question_msg_id')
        if bot_msg_id:
            await safe_edit_message(
                bot_msg_id, message.chat.id,
                '❌ Серийный номер не может быть пустым.\n🔢 Введите серийный номер:',
                get_skip_cancel_keyboard()
            )
        return

    await state.update_data(serial=text)
    data = await state.get_data()

    if data.get('editing_field') == 'serial':
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, 'serial')

@dp.message(InventoryForm.entering_inv)
async def process_inv(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    
    if not text:
        data = await state.get_data()
        bot_msg_id = data.get('bot_question_msg_id')
        if bot_msg_id:
            await safe_edit_message(
                bot_msg_id, message.chat.id,
                '❌ Инвентарный номер не может быть пустым.\n🏷️ Введите инвентарный номер:',
                get_skip_cancel_keyboard()
            )
        return

    await state.update_data(inv=text)
    data = await state.get_data()

    if data.get('editing_field') == 'inv':
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, 'inv')

@dp.message(InventoryForm.entering_ip)
async def process_ip(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    
    if text.lower() in ['пропустить', 'skip', '']:
        await state.update_data(ip='')
        data = await state.get_data()
        if data.get('editing_field') == 'ip':
            await show_confirmation(message, state)
        else:
            await next_field(message, state, data, 'ip')
        return

    if not re.match(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$', text):
        data = await state.get_data()
        bot_msg_id = data.get('bot_question_msg_id')
        if bot_msg_id:
            await safe_edit_message(
                bot_msg_id, message.chat.id,
                '❌ Неверный IP. Пример: 192.168.1.10\n🌐 Введите IP-адрес или "Пропустить":',
                get_skip_cancel_keyboard()
            )
        return

    await state.update_data(ip=text)
    data = await state.get_data()

    if data.get('editing_field') == 'ip':
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, 'ip')

@dp.message(InventoryForm.entering_mac)
async def process_mac(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    text = message.text.strip()
    
    if text.lower() in ['пропустить', 'skip', '']:
        await state.update_data(mac='')
        data = await state.get_data()
        if data.get('editing_field') == 'mac':
            await show_confirmation(message, state)
        else:
            await next_field(message, state, data, 'mac')
        return

    if not re.match(r'^([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2})$|^([0-9A-Fa-f]{2}[-]){5}([0-9A-Fa-f]{2})$', text):
        data = await state.get_data()
        bot_msg_id = data.get('bot_question_msg_id')
        if bot_msg_id:
            await safe_edit_message(
                bot_msg_id, message.chat.id,
                '❌ Неверный MAC. Пример: 00:1A:2B:3C:4D:5E\n📡 Введите MAC-адрес или "Пропустить":',
                get_skip_cancel_keyboard()
            )
        return

    await state.update_data(mac=text)
    data = await state.get_data()

    if data.get('editing_field') == 'mac':
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, 'mac')

@dp.message(InventoryForm.entering_os)
async def process_os(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(os=message.text.strip())
    data = await state.get_data()
    
    if data.get('editing_field') == 'os':
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, 'os')

@dp.message(InventoryForm.entering_drweb)
async def process_drweb(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(drweb=message.text.strip())
    data = await state.get_data()
    
    if data.get('editing_field') == 'drweb':
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, 'drweb')

@dp.message(InventoryForm.entering_office)
async def process_office(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(office=message.text.strip())
    data = await state.get_data()
    
    if data.get('editing_field') == 'office':
        await show_confirmation(message, state)
    else:
        await next_field(message, state, data, 'office')

@dp.message(InventoryForm.entering_note)
async def process_note(message: types.Message, state: FSMContext):
    await delete_user_message(message)
    await state.update_data(note=message.text.strip())
    data = await state.get_data()
    
    if data.get('editing_field') == 'note':
        await show_confirmation(message, state)
    else:
        await show_confirmation(message, state)

#============================================
# АДМИНСКИЕ ОБРАБОТЧИКИ
#============================================
@dp.callback_query(F.data == 'admin_menu')
async def admin_menu(callback: types.CallbackQuery):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚙️ **Администрирование**\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(),
        parse_mode='Markdown'
    )

@dp.callback_query(F.data == 'admin_stats')
async def admin_stats(callback: types.CallbackQuery):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    stats = db.get_db_stats()
    total = stats.get('total_items', 0)
    by_clinic = stats.get('by_clinic', {})

    stats_text = f"📊 **Статистика базы данных**\n\n"
    stats_text += f"📌 **Всего записей:** {total}\n\n"

    if by_clinic:
        stats_text += f"**По поликлиникам:**\n"
        for clinic, count in sorted(by_clinic.items()):
            clinic_name = CLINICS.get(clinic, clinic)
            stats_text += f"  • {clinic_name}: {count}\n"

    await callback.message.answer(
        stats_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')],
            [InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')]
        ])
    )

@dp.callback_query(F.data == 'admin_view_last')
async def admin_view_last(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    await state.set_state(InventoryForm.admin_view_count)
    await callback.message.answer(
        "📋 Введите количество записей для просмотра (1-100):\nПо умолчанию: 20",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')]
        ])
    )

@dp.message(InventoryForm.admin_view_count)
async def admin_show_records(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    
    try:
        count = int(message.text.strip())
        count = max(1, min(count, 100))
    except ValueError:
        count = 20

    items = db.get_all_items(limit=count)

    if not items:
        await message.answer("❌ В базе нет записей")
        await state.clear()
        return

    text = f"📋 **Последние {len(items)} записей:**\n\n"

    for i, item in enumerate(items, 1):
        text += f"{i}. **ID:** {item['id']} | **ИНВ:** {item['inv_number']}\n"
        text += f"   🏥 {item['clinic']} | 🏢 {item['cabinet']}\n"
        text += f"   🔧 {item['tech']}\n"
        text += f"   🔢 Сер.: {item['serial']}\n\n"

    await message.answer(text, parse_mode='Markdown')
    await state.clear()

@dp.callback_query(F.data == 'admin_delete')
async def admin_delete_menu(callback: types.CallbackQuery):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🗑️ **Удаление записи**\n\nВыберите способ:",
        reply_markup=get_delete_method_keyboard(),
        parse_mode='Markdown'
    )

@dp.callback_query(F.data == 'admin_delete_by_id')
async def admin_delete_by_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    await state.set_state(InventoryForm.admin_delete_id)
    await callback.message.answer(
        "🗑️ Введите ID записи для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_delete')]
        ])
    )

@dp.message(InventoryForm.admin_delete_id)
async def admin_confirm_delete_id(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    
    try:
        item_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите число.")
        return

    item = db.get_item_by_id(item_id)
    if not item:
        await message.answer(f"❌ Запись с ID {item_id} не найдена")
        await state.clear()
        return

    text = f"🗑️ **Удалить запись?**\n\n"
    text += f"**ID:** {item['id']}\n"
    text += f"**ИНВ №:** {item['inv_number']}\n"
    text += f"**Техника:** {item['tech']}\n"
    text += f"**Поликлиника:** {item['clinic']}\n"
    text += f"**Кабинет:** {item['cabinet']}\n\n"
    text += f"⚠️ Это действие нельзя отменить!"

    await state.update_data(delete_id=item_id)
    await message.answer(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='✅ Удалить', callback_data='admin_confirm_delete'),
                InlineKeyboardButton(text='❌ Отмена', callback_data='admin_delete')
            ]
        ])
    )

@dp.callback_query(F.data == 'admin_delete_by_inv')
async def admin_delete_by_inv(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    await state.set_state(InventoryForm.admin_delete_inv)
    await callback.message.answer(
        "🗑️ Введите инвентарный номер для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_delete')]
        ])
    )

@dp.message(InventoryForm.admin_delete_inv)
async def admin_confirm_delete_inv(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    
    inv_number = message.text.strip()

    item = db.find_by_inv(inv_number)
    if not item:
        await message.answer(f"❌ Запись с ИНВ № {inv_number} не найдена")
        await state.clear()
        return

    text = f"🗑️ **Удалить запись?**\n\n"
    text += f"**ID:** {item['id']}\n"
    text += f"**ИНВ №:** {item['inv_number']}\n"
    text += f"**Техника:** {item['tech']}\n"
    text += f"**Поликлиника:** {item['clinic']}\n"
    text += f"**Кабинет:** {item['cabinet']}\n\n"
    text += f"⚠️ Это действие нельзя отменить!"

    await state.update_data(delete_id=item['id'])
    await message.answer(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='✅ Удалить', callback_data='admin_confirm_delete'),
                InlineKeyboardButton(text='❌ Отмена', callback_data='admin_delete')
            ]
        ])
    )

@dp.callback_query(F.data == 'admin_confirm_delete')
async def admin_execute_delete(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    data = await state.get_data()
    item_id = data.get('delete_id')

    if not item_id:
        await callback.message.answer("❌ Ошибка: ID записи не найден")
        await state.clear()
        return

    if db.delete_item(item_id):
        await callback.message.answer(f"✅ Запись ID {item_id} успешно удалена!")
    else:
        await callback.message.answer(f"❌ Ошибка при удалении записи ID {item_id}")

    await state.clear()

@dp.callback_query(F.data == 'admin_export_db')
async def admin_export_db(callback: types.CallbackQuery):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    try:
        backup_path = f"inventory_backup_{int(time.time())}.db"
        shutil.copy2(config.DB_PATH, backup_path)
        
        with open(backup_path, 'rb') as db_file:
            await callback.message.answer_document(
                types.BufferedInputFile(db_file.read(), filename="inventory.db"),
                caption="💾 База данных инвентаризации"
            )
        
        os.remove(backup_path)
        
        await callback.message.answer(
            "⬅️ Вернуться в админ-меню:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')],
                [InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')]
            ])
        )
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка экспорта: {e}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')],
                [InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')]
            ])
        )

@dp.callback_query(F.data == 'admin_export_excel')
async def admin_export_excel(callback: types.CallbackQuery):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    try:
        timestamp = int(time.time())
        excel_path = f"data/inventory_export_{timestamp}.xlsx"
        
        os.makedirs("data", exist_ok=True)
        
        await callback.message.answer("⏳ Генерирую Excel файл...")
        
        from excel_export import export_to_excel
        result_path = export_to_excel(excel_path)
        
        if result_path and os.path.exists(result_path):
            with open(result_path, 'rb') as excel_file:
                await callback.message.answer_document(
                    types.BufferedInputFile(excel_file.read(), filename="inventory.xlsx"),
                    caption=f"📊 **Экспорт инвентаризации в Excel**\n\n"
                           f"📅 Дата экспорта: {time.strftime('%d.%m.%Y %H:%M')}"
                )
            
            os.remove(result_path)
            await callback.message.answer(
                "✅ Файл отправлен!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')],
                    [InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')]
                ])
            )
        else:
            await callback.message.answer(
                "❌ Ошибка генерации Excel файла",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')],
                    [InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')]
                ])
            )

    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка экспорта: {e}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')],
                [InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')]
            ])
        )
        logger.error(f"Ошибка экспорта Excel: {e}")

@dp.callback_query(F.data == 'admin_users')
async def admin_users(callback: types.CallbackQuery):
    await callback.answer()
    if not is_admin(callback.message.chat.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    
    users = config.ALLOWED_CHAT_IDS
    admins = config.ADMIN_CHAT_IDS

    text = "👥 **Пользователи с доступом:**\n\n"
    for i, user_id in enumerate(users, 1):
        role = "👑 Админ" if user_id in admins else "👤 Пользователь"
        text += f"{i}. ID: `{user_id}` - {role}\n"

    text += f"\n📌 **Всего пользователей:** {len(users)}\n"
    text += f"📌 **Администраторов:** {len(admins)}"

    await callback.message.answer(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')],
            [InlineKeyboardButton(text='📋 В меню', callback_data='back_to_menu')]
        ])
    )

#============================================
# ЗАПУСК БОТА
#============================================
async def main():
    db.init_db()
    logger.info("База данных инициализирована")
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")