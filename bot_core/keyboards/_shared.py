"""Общие построители клавиатур — сетки и подписи.

Приватный модуль пакета bot_core.keyboards: наружу потребители получают
всё через фасад __init__, а эти хелперы нужны только внутри пакета.
Фаза 4: раньше двухколоночные циклы и подписи значений копировались
в каждом билдере заново.

Расположение кнопок — как в исходном дизайне (компактные 2-колоночные
сетки). Из визуального редизайна оставлено только исправление: в кнопке
«Тип» показывается человекочитаемое имя, а не сырой код «pc».
"""

from aiogram.types import InlineKeyboardButton

from bot_core.constants import EDITABLE_FIELDS, display_drweb, display_tech_type


def _two_column_rows(pairs: list[tuple[str, str]]) -> list[list[InlineKeyboardButton]]:
    """Кнопки в две колонки: [(текст, callback_data), ...] → ряды клавиатуры.

    Общий вид сеток «поликлиники», «типы техники», «выбор ОС».
    """
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(pairs), 2):
        row = [InlineKeyboardButton(text=pairs[i][0], callback_data=pairs[i][1])]
        if i + 1 < len(pairs):
            row.append(InlineKeyboardButton(text=pairs[i + 1][0], callback_data=pairs[i + 1][1]))
        rows.append(row)
    return rows


def _format_field_value_for_button(field_key: str, value) -> str:
    """Форматирует значение для показа в кнопке карточки/редактирования.
    Для Dr.Web применяет display_drweb, для типа техники — человекочитаемое
    имя (сырой код «pc» из state/БД в кнопке не показываем).
    """
    raw = str(value or "")
    if not raw:
        return "—"
    if field_key == "drweb":
        return display_drweb(raw)
    if field_key == "tech_type":
        return display_tech_type(raw)
    return raw


def _field_buttons_rows(source: dict, cb_prefix: str) -> list[list[InlineKeyboardButton]]:
    """Кнопки всех редактируемых полей со значениями из source (2 в ряд).

    Общее для карточки «проверьте данные» (review_field_*) и карточки
    существующей записи (edit_field_*) — различаются только префиксом
    callback и хвостовыми кнопками. Список полей — EDITABLE_FIELDS
    (constants.py, единый источник).
    """
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(EDITABLE_FIELDS), 2):
        row = []
        for j in range(2):
            if i + j < len(EDITABLE_FIELDS):
                field_key, label = EDITABLE_FIELDS[i + j]
                value = _format_field_value_for_button(field_key, source.get(field_key, ""))
                if value != "—" and len(value) > 20:
                    btn_text = f"{label} ({value[:20]}...)"
                elif value != "—":
                    btn_text = f"{label} ({value})"
                else:
                    btn_text = f"{label} (—)"
                row.append(
                    InlineKeyboardButton(text=btn_text, callback_data=f"{cb_prefix}{field_key}")
                )
        rows.append(row)
    return rows


def _item_short(item: dict) -> str:
    """Короткое описание записи для кнопок списка"""
    inv = item.get("inv_number") or "—"
    if len(inv) > 14:
        inv = inv[:14] + "…"
    cab = item.get("cabinet") or "—"
    tech = item.get("tech") or "—"
    if len(tech) > 18:
        tech = tech[:18] + "…"
    return f"#{item['id']} • {inv} • {cab} • {tech}"
