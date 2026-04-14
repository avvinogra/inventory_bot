"""
Локальная генерация штрих-кодов Code 128
"""
import barcode
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import config
import logging

logger = logging.getLogger(__name__)

# ============================================
# КРОССПЛАТФОРМЕННЫЕ ПУТИ К ШРИФТАМ
# ============================================
def get_font_paths():
    """Возвращает список путей к шрифтам для разных ОС"""
    import platform
    system = platform.system()
    
    if system == "Windows":
        return [
            r"C:\Windows\Fonts\Arial.ttf",
            r"C:\Windows\Fonts\times.ttf",
            r"C:\Windows\Fonts\DejaVuSans.ttf",
        ]
    elif system == "Darwin":  # macOS
        return [
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Arial.ttf",
            "/Library/Fonts/DejaVuSans.ttf",
        ]
    else:  # Linux
        return [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "./fonts/DejaVuSans.ttf",
        ]

# ============================================
# ГЕНЕРАЦИЯ ШТРИХ-КОДА
# ============================================
def generate_barcode_image(inventory_number: str) -> str:
    """
    Генерация штрих-кода и сохранение в файл
    Возвращает путь к файлу
    """
    try:
        # Создаём папку для штрих-кодов
        os.makedirs(config.LABELS_DIR, exist_ok=True)
        
        # Очищаем номер от лишних символов
        clean_number = str(inventory_number).strip()
        
        # Генерируем Code 128
        barcode_class = barcode.get_barcode_class('code128')
        bc = barcode_class(clean_number, writer=ImageWriter())
        
        # Сохраняем с write_text=False
        filename = os.path.join(config.LABELS_DIR, f"barcode_{clean_number}")
        filepath = bc.save(filename, options={
            'module_width': 0.4,
            'module_height': 15.0,
            'font_size': 6,
            'text_distance': 1,
            'margin': 2,
            'write_text': False  # ✅ ОТКЛЮЧАЕМ автоматический текст!
        })
        
        return filepath  # ✅ bc.save() уже возвращает путь с .png
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации штрих-кода: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================
# СОЗДАНИЕ PDF С ЭТИКЕТКАМИ (КОМПАКТНЫЙ ВАРИАНТ)
# ============================================
def create_label_pdf(inventory_items: list, output_path: str) -> bool:
    """
    Создание PDF с этикетками (компактный формат)
    """
    try:
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4
        
        # === РЕГИСТРАЦИЯ ШРИФТА С КИРИЛЛИЦЕЙ ===
        font_registered = False
        font_paths = get_font_paths()
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('CyrillicFont', font_path))
                    font_registered = True
                    logger.info(f"✅ Шрифт зарегистрирован: {font_path}")
                    break
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось зарегистрировать шрифт: {e}")
                    continue
        
        if not font_registered:
            logger.warning("⚠️ Кириллический шрифт не найден! Используем Helvetica (только латиница)")
        
        # === УМЕНЬШЕННЫЕ РАЗМЕРЫ ЭТИКЕТКИ ===
        label_width = 95 * mm
        label_height = 40 * mm  # ✅ УМЕНЬШИЛИ с 55mm до 40mm
        margin_x = 5 * mm
        margin_y = 10 * mm
        
        x_pos = margin_x
        y_pos = height - margin_y - label_height
        
        for i, item in enumerate(inventory_items):
            # Если этикетка не помещается - новая страница
            if y_pos < margin_y:
                c.showPage()
                y_pos = height - margin_y - label_height
                x_pos = margin_x
            
            # Рамка
            c.rect(x_pos, y_pos, label_width, label_height)
            
            # Выбираем шрифт
            if font_registered:
                c.setFont("CyrillicFont", 9)  # ✅ УМЕНЬШИЛИ шрифт
            else:
                c.setFont("Helvetica", 9)
            
            # === ПОЛИКЛИНИКА ===
            clinic_text = item.get('clinic', '')
            c.drawString(x_pos + 3*mm, y_pos + label_height - 6*mm, clinic_text)
            
            # === ЛИНИЯ ===
            c.line(x_pos + 3*mm, y_pos + label_height - 9*mm,
                  x_pos + label_width - 3*mm, y_pos + label_height - 9*mm)
            
            # === УСТРОЙСТВО ===
            if font_registered:
                c.setFont("CyrillicFont", 8)
            else:
                c.setFont("Helvetica", 8)
            
            y_text = y_pos + label_height - 14*mm
            c.drawString(x_pos + 3*mm, y_text, f"Устройство: {item.get('tech', '')}")
            
            # === ИНВ НОМЕР ===
            if font_registered:
                c.setFont("CyrillicFont", 9)
            else:
                c.setFont("Helvetica-Bold", 9)
            
            y_text -= 5*mm
            c.drawString(x_pos + 3*mm, y_text, f"ИНВ № {item.get('inv', '')}")
            
            # === ШТРИХ-КОД ===
            inv_number = item.get('inv', '')
            barcode_path = generate_barcode_image(inv_number)
            
            if barcode_path and os.path.exists(barcode_path):
                logger.info(f"✅ Штрих-код найден: {barcode_path}")
                bc_width = 55 * mm  # ✅ ЧУТЬ УМЕНЬШИЛИ
                bc_height = 12 * mm  # ✅ ЧУТЬ УМЕНЬШИЛИ
                bc_x = x_pos + (label_width - bc_width) / 2
                bc_y = y_pos + 3*mm  # ✅ ПОДНЯЛИ НИЖЕ
                
                try:
                    c.drawImage(barcode_path, bc_x, bc_y,
                               width=bc_width, height=bc_height,
                               preserveAspectRatio=True,
                               mask='auto')
                    logger.info("✅ Штрих-код вставлен")
                except Exception as img_error:
                    logger.error(f"❌ Ошибка вставки: {img_error}")
            else:
                logger.warning(f"⚠️ Штрих-код НЕ найден: {barcode_path}")
            
            # === ПОД ШТРИХ-КОДОМ: СЕРИЙНЫЙ НОМЕР ===
            if font_registered:
                c.setFont("CyrillicFont", 7)  # ✅ УМЕНЬШИЛИ шрифт
            else:
                c.setFont("Helvetica", 7)
            
            serial_number = item.get('serial', '')
            c.drawCentredString(x_pos + label_width/2, y_pos + 1*mm, serial_number)
            
            # Следующая позиция
            x_pos += label_width + 5*mm
            if x_pos + label_width > width - margin_x:
                x_pos = margin_x
                y_pos -= label_height + 5*mm
        
        c.save()
        logger.info(f"✅ PDF сохранён: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания PDF: {e}")
        import traceback
        traceback.print_exc()
        return False