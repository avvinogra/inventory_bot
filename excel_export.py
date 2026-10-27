"""
Экспорт данных из БД в Excel — с группировкой по кабинетам.

Два типа вывода:
  1. Если записи объединены в АРМ — они идут под общим заголовком АРМ
     с перечнем всех устройств.
  2. Если записи не в АРМ — идут под заголовком кабинета как обычно.

Колонки (без колонки АРМ):
  № | Кабинет | Тип | Марка, модель | Инв. № | Сер. № | ОС |
  Dr.Web | IP-адрес | Имя ПК | Физ. MAC | Реал. MAC |
  Характеристики | Дополнительно
"""
import os
import sqlite3
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config

# Колонки данных
HEADERS = [
    "№",                       # 1
    "Кабинет",                 # 2
    "Тип",                     # 3
    "Марка, модель",           # 4
    "Инв. №",                  # 5
    "Сер. №",                  # 6
    "ОС",                      # 7
    "Dr.Web",                  # 8
    "IP-адрес",                # 9
    "Имя ПК",                  # 10
    "Физ. MAC",                # 11
    "Реал. MAC",               # 12
    "Характеристики",          # 13
    "Дополнительно",           # 14
]

COLUMN_MAP = [
    None,      # № — генерируется
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

TECH_TYPE_LABELS = {
    "pc":      "Системный блок",
    "monitor": "Монитор",
    "printer": "Принтер / МФУ",
    "laptop":  "Ноутбук",
    "other":   "Другое",
}

# === ЦВЕТА ===
CAB_HEADER_FILL = PatternFill(start_color="2F543B", end_color="2F543B", fill_type="solid")
ARM_HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
COL_HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
SERIAL_INV_FILL = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
IP_MAC_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")

CAB_HEADER_FONT = Font(bold=True, size=12, color="FFFFFF")
ARM_HEADER_FONT = Font(bold=True, size=12, color="FFFFFF")
COL_HEADER_FONT = Font(bold=True, size=10, color="FFFFFF")
CELL_FONT = Font(size=10)

CELL_ALIGN = Alignment(horizontal='left', vertical='center', wrap_text=True)
HEADER_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)

BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin'),
)

COLUMN_WIDTHS = [5, 12, 18, 28, 20, 20, 20, 18, 16, 20, 20, 20, 28, 28]

DRWEB_DISPLAY_MAP = {
    "Установлен":                "Установлен",
    "Нет лицензии":              "Нет лицензии",
    "Нет соединения с сервером": "Нет соединения с сервером",
    "Не установлен":             "Не установлен",
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
    val = row.get(db_field) or ""
    if db_field == "mac_phys" and not val:
        val = row.get("mac") or ""
    if db_field == "tech_type":
        val = _human_tech_type(val)
    if db_field == "drweb":
        val = _human_drweb(val)
    return str(val)


def _write_header_row(ws, row_idx, headers, fill, font):
    """Записывает строку заголовков колонок."""
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=row_idx, column=col, value=header)
        cell.fill = fill
        cell.font = font
        cell.alignment = HEADER_ALIGN
        cell.border = BORDER


def _write_data_row(ws, row_idx, row_data, num_counter):
    """Записывает строку с данными устройства."""
    for col_idx, db_field in enumerate(COLUMN_MAP, 1):
        if db_field is None:
            # № по порядку
            val = num_counter
        else:
            val = _cell_value(row_data, db_field)

        cell = ws.cell(row=row_idx, column=col_idx, value=val)
        cell.alignment = CELL_ALIGN
        cell.border = BORDER
        cell.font = CELL_FONT

        # Подсветка
        if db_field in ("serial", "inv_number"):
            cell.fill = SERIAL_INV_FILL
        elif db_field in ("ip", "mac_phys", "mac_real") and val:
            cell.fill = IP_MAC_FILL


def export_to_excel(output_path: str = None) -> str:
    """Экспорт с группировкой: АРМ — отдельным блоком, без АРМ — по кабинетам."""
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"data/inventory_export_{timestamp}.xlsx"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM inventory ORDER BY clinic, cabinet, id"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        print("База данных пуста!")
        return None

    from config import CLINICS

    wb = Workbook()
    wb.remove(wb.active)
    num_cols = len(HEADERS)

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

        row_idx = 1
        counter = 1  # сквозная нумерация

        # === 1. ЗАПИСИ В АРМ ===
        # Группируем по arm_id
        arm_groups = {}
        for r in clinic_rows:
            arm = r.get("arm_id")
            if arm:
                if arm not in arm_groups:
                    arm_groups[arm] = []
                arm_groups[arm].append(r)

        # Записи с АРМ — выводим отдельными блоками
        for arm_id in sorted(arm_groups.keys()):
            arm_items = arm_groups[arm_id]

            # Заголовок АРМ
            ws.merge_cells(start_row=row_idx, start_column=1,
                           end_row=row_idx, end_column=num_cols)
            cab = arm_items[0].get("cabinet") or "—"
            cell = ws.cell(row=row_idx, column=1,
                          value=f"АРМ #{arm_id} — каб. {cab} — {len(arm_items)} шт.")
            cell.fill = ARM_HEADER_FILL
            cell.font = ARM_HEADER_FONT
            cell.alignment = Alignment(horizontal='left', vertical='center')
            for c in range(1, num_cols + 1):
                ws.cell(row=row_idx, column=c).border = BORDER
            row_idx += 1

            # Заголовки колонок
            _write_header_row(ws, row_idx, HEADERS, COL_HEADER_FILL, COL_HEADER_FONT)
            row_idx += 1

            # Данные
            for item in arm_items:
                _write_data_row(ws, row_idx, item, counter)
                counter += 1
                row_idx += 1

            # Пустая строка
            row_idx += 1

        # === 2. ЗАПИСИ БЕЗ АРМ — по кабинетам ===
        no_arm_rows = [r for r in clinic_rows if not r.get("arm_id")]

        # Группируем по кабинету
        cabinets = []
        cab_seen = set()
        for r in no_arm_rows:
            cab = r.get("cabinet") or "—"
            if cab not in cab_seen:
                cab_seen.add(cab)
                cabinets.append(cab)

        for cab in cabinets:
            cab_rows = [r for r in no_arm_rows if (r.get("cabinet") or "—") == cab]

            # Заголовок кабинета
            ws.merge_cells(start_row=row_idx, start_column=1,
                           end_row=row_idx, end_column=num_cols)
            cell = ws.cell(row=row_idx, column=1, value=f"Каб. {cab}")
            cell.fill = CAB_HEADER_FILL
            cell.font = CAB_HEADER_FONT
            cell.alignment = Alignment(horizontal='left', vertical='center')
            for c in range(1, num_cols + 1):
                ws.cell(row=row_idx, column=c).border = BORDER
            row_idx += 1

            # Заголовки колонок
            _write_header_row(ws, row_idx, HEADERS, COL_HEADER_FILL, COL_HEADER_FONT)
            row_idx += 1

            # Данные
            for item in cab_rows:
                _write_data_row(ws, row_idx, item, counter)
                counter += 1
                row_idx += 1

            # Пустая строка
            row_idx += 1

        # === Ширина колонок ===
        for i, width in enumerate(COLUMN_WIDTHS, 1):
            col_letter = get_column_letter(i)
            ws.column_dimensions[col_letter].width = width

        ws.freeze_panes = 'A2'

    wb.save(output_path)
    print(f"Экспорт завершён: {output_path}")
    print(f"Листов: {len(clinics)}")
    return output_path


if __name__ == "__main__":
    export_to_excel()
    print("Готово!")
