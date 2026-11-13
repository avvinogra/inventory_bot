"""Экраны сценария ввода новой записи.

Поликлиника → режим АРМ → тип техники → поля (навигация, выбор
Dr.Web и ОС из кнопок) → карточка «проверьте данные» → предупреждения
о дубликатах и несовпадении MAC.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_core.constants import DRWEB_CHOICES, OS_CHOICES, TECH_TYPES
from bot_core.keyboards._shared import _field_buttons_rows, _two_column_rows
from config import CLINICS


def get_clinic_keyboard():
    rows = _two_column_rows(
        [(f"{code} — {name}", f"clinic_{code}") for code, name in CLINICS.items()]
    )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_process")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_tech_type_keyboard():
    rows = _two_column_rows(
        [(info["name"], f"tech_type_{key}") for key, info in TECH_TYPES.items()]
    )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_process")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_skip_cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process"),
            ]
        ]
    )


def get_arm_mode_keyboard():
    """Клавиатура: Создать АРМ? Да/Нет"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, создать АРМ", callback_data="arm_mode_yes"),
                InlineKeyboardButton(text="Нет, обычный ввод", callback_data="arm_mode_no"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_process")],
        ]
    )


def get_arm_after_save_keyboard():
    """После сохранения записи в режиме АРМ: добавить ещё / завершить"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить устройство", callback_data="arm_add_another"
                ),
                InlineKeyboardButton(text="✅ Завершить АРМ", callback_data="arm_finish"),
            ],
            [InlineKeyboardButton(text="📋 В меню", callback_data="back_to_menu")],
        ]
    )


def get_nav_keyboard(*, can_back: bool, can_skip: bool, can_absent: bool = False):
    """Навигация во время ввода поля.

    can_absent — показывать кнопку «Отсутствует» (для инв. и серийного
    номера).

    Ряды: [⬅️ Назад][⏭️ Пропустить] — навигация парой; «Отсутствует» —
    своей строкой на всю ширину; «Отменить» — всегда последней строкой
    на всю ширину. В одном ряду из 3–4 кнопок Telegram делит ширину
    поровну, и подписи обрезались: «Отсутств…», «Пропус…», «Отмени…».
    """
    rows = []
    nav_row = []
    if can_back:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_prev_step"))
    if can_skip:
        nav_row.append(
            InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field")
        )
    if nav_row:
        rows.append(nav_row)
    if can_absent:
        rows.append([InlineKeyboardButton(text="❓ Отсутствует", callback_data="field_absent")])
    rows.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_drweb_choice_keyboard():
    """Inline-меню выбора статуса Dr.Web. Без сокращений, без «+».
    Кнопки: Установлен / Нет лицензии / Нет соединения с сервером / Не установлен +
    Пропустить + Назад.
    """
    rows = []
    # По 1 кнопке в ряд — длинные подписи
    for key, (label, _value) in DRWEB_CHOICES.items():
        rows.append([InlineKeyboardButton(text=label, callback_data=f"drweb_choice_{key}")])

    rows.append(
        [
            InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_prev_step"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_os_choice_keyboard():
    """Inline-меню выбора ОС. 8 вариантов в 2 колонки + «Другая ОС»."""
    rows = []
    keys = list(OS_CHOICES.keys())
    # Все кнопки, кроме "other" — по 2 в ряд
    main_keys = [k for k in keys if k != "other"]
    rows.extend(_two_column_rows([(OS_CHOICES[k], f"os_choice_{k}") for k in main_keys]))

    # «Другая ОС» — в отдельном ряду
    rows.append(
        [
            InlineKeyboardButton(
                text="🔧 Другая ОС",
                callback_data="os_choice_other",
            )
        ]
    )
    # Пропустить + Назад
    rows.append(
        [
            InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_current_field"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_prev_step"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_confirm_edit_keyboard(data: dict):
    """Карточка "проверьте данные" → кнопки для правки каждого поля.

    Список полей берём из EDITABLE_FIELDS (constants.py).
    Для Dr.Web показываем нормальную подпись вместо «+»/«нет».
    """
    keyboard = _field_buttons_rows(data, "review_field_")
    keyboard.append(
        [InlineKeyboardButton(text="✅ Подтвердить и сохранить", callback_data="confirm_save")]
    )
    keyboard.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_duplicate_inv_keyboard():
    """Инвентарный номер уже есть в БД — это может быть АРМ (нормально)
    или дубликат (ошибка). Не блокируем, просто уточняем.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Продолжить (это АРМ)", callback_data="confirm_inv_continue"
                ),
                InlineKeyboardButton(text="❌ Ввести заново", callback_data="confirm_inv_cancel"),
            ],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")],
        ]
    )


def get_duplicate_serial_keyboard():
    """Серийный номер уже есть в БД — почти всегда ошибка (серийник уникален)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Продолжить всё равно", callback_data="confirm_serial_continue"
                ),
                InlineKeyboardButton(
                    text="❌ Ввести заново", callback_data="confirm_serial_cancel"
                ),
            ],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")],
        ]
    )


def get_mac_mismatch_keyboard():
    """Физический MAC ≠ реальному MAC — должно совпадать по нормативу."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Продолжить", callback_data="mac_mismatch_continue")],
            [
                InlineKeyboardButton(
                    text="✏️ Ввести реальный MAC заново", callback_data="mac_mismatch_reenter"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏭️ Пропустить реальный MAC", callback_data="mac_mismatch_skip"
                )
            ],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_process")],
        ]
    )
