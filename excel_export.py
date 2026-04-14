"""
Экспорт данных из БД в Excel (с группировкой по поликлиникам)
"""
import sqlite3
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
import config
import os
from datetime import datetime

def export_to_excel(output_path: str = None) -> str:
    """
    Экспорт всех данных из БД в Excel с группировкой по поликлиникам
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"data/inventory_export_{timestamp}.xlsx"
    
    # Создаём папку, если нет
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Подключаемся к БД
    conn = sqlite3.connect(config.DB_PATH)
    
    # Получаем все данные
    query = """
    SELECT 
        clinic,
        cabinet,
        tech,
        serial,
        inv_number,
        ip,
        mac,
        os,
        office,
        drweb,
        note
    FROM inventory
    ORDER BY clinic, cabinet
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("❌ База данных пуста!")
        return None
    
    # Создаём workbook
    wb = Workbook()
    
    # Удаляем стандартный лист
    wb.remove(wb.active)
    
    # Группируем по поликлиникам
    clinics = df['clinic'].unique()
    
    for clinic in clinics:
        clinic_df = df[df['clinic'] == clinic].copy()
        
        # Создаём новый лист
        sheet_title = clinic[:31]  # Excel ограничивает имя листа 31 символом
        ws = wb.create_sheet(title=sheet_title)
        
        # === ЦВЕТА ===
        header_fill = PatternFill(start_color="2F543B", end_color="2F543B", fill_type="solid")  # Тёмно-зелёный
        serial_inv_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")  # Жёлтый
        ip_mac_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")  # Светло-зелёный
        
        # Шрифты
        header_font = Font(bold=True, size=11, color="FFFFFF")  # Белый текст
        cell_font = Font(size=10)
        
        # Выравнивание
        header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell_alignment = Alignment(horizontal='left', vertical='center')
        
        # Границы
        thick_border = Border(
            left=Side(style='thick'),
            right=Side(style='thick'),
            top=Side(style='thick'),
            bottom=Side(style='thick')
        )
        
        # === ШАПКА ТАБЛИЦЫ (Строка 1) ===
        headers = [
            '№ п/п', '№ кабинета', 'Техника', 'Серийный номер',
            'Инвентарный номер', 'IP-Адрес', 'MAC-Адрес',
            'ОС', 'Office', 'Dr.Web', 'Примечание'
        ]
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thick_border
        
        # === ДАННЫЕ (Строки 2+) ===
        for row_idx, (_, row) in enumerate(clinic_df.iterrows(), start=2):
            # № п/п
            cell = ws.cell(row=row_idx, column=1, value=row_idx - 1)
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            
            # № кабинета
            cell = ws.cell(row=row_idx, column=2, value=row['cabinet'])
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            
            # Техника
            cell = ws.cell(row=row_idx, column=3, value=row['tech'])
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            
            # Серийный номер (ЖЁЛТЫЙ)
            cell = ws.cell(row=row_idx, column=4, value=row['serial'])
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            cell.fill = serial_inv_fill
            
            # Инвентарный номер (ЖЁЛТЫЙ)
            cell = ws.cell(row=row_idx, column=5, value=row['inv_number'])
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            cell.fill = serial_inv_fill
            
            # IP-Адрес (СВЕТЛО-ЗЕЛЁНЫЙ)
            cell = ws.cell(row=row_idx, column=6, value=row['ip'] or '')
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            if row['ip']:  # Только если есть IP
                cell.fill = ip_mac_fill
            
            # MAC-Адрес (СВЕТЛО-ЗЕЛЁНЫЙ)
            cell = ws.cell(row=row_idx, column=7, value=row['mac'] or '')
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            if row['mac']:  # Только если есть MAC
                cell.fill = ip_mac_fill
            
            # ОС
            cell = ws.cell(row=row_idx, column=8, value=row['os'] or '')
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            
            # Office
            cell = ws.cell(row=row_idx, column=9, value=row['office'] or '')
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            
            # Dr.Web
            cell = ws.cell(row=row_idx, column=10, value=row['drweb'] or '')
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
            
            # Примечание
            cell = ws.cell(row=row_idx, column=11, value=row['note'] or '')
            cell.alignment = cell_alignment
            cell.border = thick_border
            cell.font = cell_font
        
        # === АВТОШИРИНА КОЛОНОК ===
        column_widths = [6, 12, 25, 20, 22, 18, 22, 15, 8, 8, 20]
        for i, width in enumerate(column_widths, 1):
            col_letter = get_column_letter(i)
            ws.column_dimensions[col_letter].width = width
        
        # Высота шапки
        ws.row_dimensions[1].height = 30
        
        # Заморозить шапку
        ws.freeze_panes = 'A2'
    
    # Сохраняем файл
    wb.save(output_path)
    print(f"✅ Экспорт завершён: {output_path}")
    print(f"📊 Создано листов: {len(clinics)} (по одному на каждую поликлинику)")
    return output_path


if __name__ == "__main__":
    export_to_excel()
    print("Готово!")