"""
Экспорт данных из БД в Excel.

Структура листа приведена в соответствие со шаблоном "Инвентаризация.xlsx",
но заголовки колонок раскрыты без сокращений:
    № | Номер кабинета | Тип | Марка, модель | Инвентарный номер |
    Серийный номер | Операционная система | Dr.Web | IP-адрес |
    Имя компьютера | Физический MAC | Реальный MAC | Характеристики |
    Дополнительно
"""
import os
import sqlite3
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config


# Шапка листа — без сокращений.
HEADERS = [
    "№",                       # 1
    "Номер кабинета",          # 2
    "Тип",                     # 3
    "Марка, модель",           # 4
    "Инвентарный номер",       # 5
    "Серийный номер",          # 6
    "Операционная система",    # 7
    "Dr.Web",                  # 8
    "IP-адрес",                # 9
    "Имя компьютера",          # 10
    "Физический MAC",          # 11
    "Реальный MAC",            # 12
    "Характеристики",          # 13
    "Дополнительно",           # 14
]

# Маппинг: колонка XLSX → колонка БД
COLUMN_MAP = [
    "cabinet",
    "tech_type",
    "tech",
    "inv_number",
    "serial",
    "os",
    "drweb",
    "ip",
    "pc_name",
    "mac_phys",
    "mac_real",
    "specs",
    "note",
]

# Человекочитаемые имена типа техники
TECH_TYPE_LABELS = {
    "pc":      "Системный блок",
    "monitor": "Монитор",
    "printer": "Принтер / МФУ",
    "laptop":  "Ноутбук",
    "other":   "Другое",
}

# === ЦВЕТА ===
HEADER_FILL = PatternFill(start_color="2F543B", end_color="2F543B", fill_type="solid")
SERIAL_INV_FILL = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
IP_MAC_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")

HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
CELL_FONT = Font(size=10)

HEADER_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)
CELL_ALIGN = Alignment(horizontal='left', vertical='center')

THICK_BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin'),
)

COLUMN_WIDTHS = [6, 14, 20, 30, 22, 22, 22, 32, 18, 22, 22, 22, 32, 32]

# Совместимость со старыми короткими значениями Dr.Web —
# в Excel выводим нормальную подпись вместо «+»/«нет лиц»/«нет соед»/«нет».
DRWEB_DISPLAY_MAP = {
    "Установлен":                "Установлен",
    "Нет лицензии":              "Нет лицензии",
    "Нет соединения с сервером": "Нет соединения с сервером",
    "Не установлен":             "Не установлен",
    # Старые значения
    "+":         "Установлен",
    "да":        "Установлен",
    "yes":       "Установлен",
    "нет лиц":   "Нет лицензии",
    "нет соед":  "Нет соединения с сервером",
    "нет":       "Не установлен",
    "no":        "Не установлен",
}


def _human_tech_type(value: str) -> str:
    if not value:
        return ""
    return TECH_TYPE_LABELS.get(value, value)


def _human_drweb(value: str) -> str:
    if not value:
        return ""
    return DRWEB_DISPLAY_MAP.get(str(value).strip(), str(value))


def _cell_value(row: dict, db_field: str) -> str:
    """Безопасно достать поле из строки БД.
    Для mac_phys делаем fallback на legacy-поле mac, если mac_phys пустое.
    Для tech_type и drweb возвращаем человекочитаемое значение.
    """
    val = row.get(db_field) or ""
    if db_field == "mac_phys" and not val:
        val = row.get("mac") or ""
    if db_field == "tech_type":
        val = _human_tech_type(val)
    if db_field == "drweb":
        val = _human_drweb(val)
    return str(val)


def export_to_excel(output_path: str = None) -> str:
    """
    Экспорт всех данных из БД в Excel с группировкой по поликлиникам
    (один лист = одна поликлиника).
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"data/inventory_export_{timestamp}.xlsx"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        """
        SELECT * FROM inventory
        ORDER BY clinic, cabinet, id
        """
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        print("❌ База данных пуста!")
        return None

    wb = Workbook()
    wb.remove(wb.active)

    # Группируем по поликлиникам
    clinics = []
    seen = set()
    for r in rows:
        c = r.get("clinic") or "—"
        if c not in seen:
            seen.add(c)
            clinics.append(c)

    for clinic in clinics:
        clinic_rows = [r for r in rows if (r.get("clinic") or "—") == clinic]

        sheet_title = (clinic or "—")[:31]
        ws = wb.create_sheet(title=sheet_title)

        # === ШАПКА ===
        for col, header in enumerate(HEADERS, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = HEADER_ALIGN
            cell.border = THICK_BORDER

        # === ДАННЫЕ ===
        for row_idx, row in enumerate(clinic_rows, start=2):
            # № по порядку
            cell = ws.cell(row=row_idx, column=1, value=row_idx - 1)
            cell.alignment = CELL_ALIGN
            cell.border = THICK_BORDER
            cell.font = CELL_FONT

            for col_idx, db_field in enumerate(COLUMN_MAP, start=2):
                val = _cell_value(row, db_field)
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.alignment = CELL_ALIGN
                cell.border = THICK_BORDER
                cell.font = CELL_FONT

                # Подсветка:
                #   - Инвентарный и Серийный номер → жёлтый
                #   - IP, Физический MAC, Реальный MAC → светло-зелёный (если есть значение)
                if db_field in ("serial", "inv_number"):
                    cell.fill = SERIAL_INV_FILL
                elif db_field in ("ip", "mac_phys", "mac_real") and val:
                    cell.fill = IP_MAC_FILL

        # === АВТОШИРИНА ===
        for i, width in enumerate(COLUMN_WIDTHS, 1):
            col_letter = get_column_letter(i)
            ws.column_dimensions[col_letter].width = width

        ws.row_dimensions[1].height = 30
        ws.freeze_panes = 'A2'

    wb.save(output_path)
    print(f"✅ Экспорт завершён: {output_path}")
    print(f"📊 Создано листов: {len(clinics)} (по одному на каждую поликлинику)")
    return output_path


if __name__ == "__main__":
    export_to_excel()
    print("Готово!")
