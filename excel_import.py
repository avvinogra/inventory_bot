"""
Импорт данных из Excel в БД.

Считывает .xlsx, для каждого листа (имя = название поликлиники)
парсит строки и создаёт записи в БД через database.save_item.

Поддерживаемые форматы:
    - Имя листа → код поликлиники из config.CLINICS
      (распознаём «1 пол», «1 поликлиника», «ДЦ», «Диагностический центр» и т. д.)
    - Заголовки колонок → короткие ключи state (cabinet, tech, serial, ...)
      (распознаём «№ кабинета» / «Номер кабинета», «Инв №» / «Инвентарный номер», и т. д.)
    - Значения поля «Тип» → код TECH_TYPES (pc/monitor/printer/laptop/other)
    - Значения Dr.Web → нормализуем в «Установлен» / «Не установлен» / «Нет лицензии» /
      «Нет соединения с сервером» (совместимость со старыми «+», «нет лиц» и т. д.)
"""
import re
from typing import Optional

from openpyxl import load_workbook

import database as db


def _normalize(text: str) -> str:
    """Приводим к нижнему регистру и схлопываем пробелы."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip().lower()


# ============================================================
# МАППИНГ ИМЕНИ ЛИСТА → КОД ПОЛИКЛИНИКИ
# ============================================================
_CLINIC_ALIASES_RAW = {
    "1 пол":                   "1пл",
    "1 поликлиника":           "1пл",
    "1-я поликлиника":         "1пл",
    "1 поликлиника":           "1пл",
    "2 пол":                   "2пл",
    "2 поликлиника":           "2пл",
    "3 пол":                   "3пл",
    "3 поликлиника":           "3пл",
    "4 пол":                   "4пл",
    "4 поликлиника":           "4пл",
    "10 пол":                  "10пл",
    "10 поликлиника":          "10пл",
    "дц":                      "ДЦ",
    "диагностический центр":   "ДЦ",
    "цмр":                     "ЦМР",
    "центр медицинской реабилитации": "ЦМР",
    "травмпункт":              "Травмпункт",
    "давина":                  "Дарвина",  # иногда опечатка
    "дарвина":                 "Дарвина",
}
CLINIC_SHEET_ALIASES = {_normalize(k): v for k, v in _CLINIC_ALIASES_RAW.items()}

# Имя листа, которое игнорируем (это пояснения, не данные)
_EXCLUDED_SHEETS = {_normalize("Пояснения"), _normalize("Пояснение")}


# ============================================================
# МАППИНГ ЗНАЧЕНИЙ ПОЛЯ «Тип» → КОД TECH_TYPES
# ============================================================
_TECH_TYPE_ALIASES_RAW = {
    "сист блок":       "pc",
    "системный блок":  "pc",
    "сб":              "pc",
    "пк":              "pc",
    "компьютер":       "pc",
    "монитор":         "monitor",
    "принтер":         "printer",
    "мфу":             "printer",
    "принтер/мфу":     "printer",
    "принтер / мфу":   "printer",
    "ноутбук":         "laptop",
    "нб":              "laptop",
}
TECH_TYPE_ALIASES = {_normalize(k): v for k, v in _TECH_TYPE_ALIASES_RAW.items()}


# ============================================================
# МАППИНГ ЗНАЧЕНИЙ Dr.Web → НОРМАЛИЗОВАННОЕ ЗНАЧЕНИЕ
# ============================================================
_DRWEB_ALIASES_RAW = {
    "Установлен":                "Установлен",
    "Не установлен":             "Не установлен",
    "Нет лицензии":              "Нет лицензии",
    "Нет соединения с сервером": "Нет соединения с сервером",
    "+":                         "Установлен",
    "да":                        "Установлен",
    "yes":                       "Установлен",
    "установлен":                "Установлен",
    "не установлен":             "Не установлен",
    "нет":                       "Не установлен",
    "no":                        "Не установлен",
    "нет лиц":                   "Нет лицензии",
    "нет лицензии":              "Нет лицензии",
    "нет соед":                  "Нет соединения с сервером",
    "нет соединения":            "Нет соединения с сервером",
    "нет соединения с сервером": "Нет соединения с сервером",
}
DRWEB_ALIASES = {_normalize(k): v for k, v in _DRWEB_ALIASES_RAW.items()}


# ============================================================
# МАППИНГ ЗНАЧЕНИЙ ПОЛЯ «ОС» → НОРМАЛИЗОВАННОЕ ЗНАЧЕНИЕ
# ============================================================
# При импорте из Excel значения ОС могут быть разными:
# «Win10», «Windows 10», «Win 10 Pro», «РЕД ОС 7.3», «RedOS 7.3» и т.д.
# Нормализуем в один из стандартных вариантов из OS_CHOICES.
_OS_ALIASES_RAW = {
    # Windows 10
    "windows 10 x64":            "Windows 10 x64",
    "windows 10 64":             "Windows 10 x64",
    "win10 x64":                 "Windows 10 x64",
    "win 10 x64":                "Windows 10 x64",
    "win10 64":                  "Windows 10 x64",
    "windows 10 pro x64":        "Windows 10 x64",
    "windows 10 x86":           "Windows 10 x86 (32)",
    "windows 10 32":             "Windows 10 x86 (32)",
    "windows 10 x86 (32)":      "Windows 10 x86 (32)",
    "win10 x86":                 "Windows 10 x86 (32)",
    "win 10 x86":                "Windows 10 x86 (32)",
    "win10 32":                  "Windows 10 x86 (32)",
    "windows 10 pro x86":       "Windows 10 x86 (32)",
    "windows 10":                "Windows 10 x64",  # по умолчанию x64
    "win10":                     "Windows 10 x64",
    "win 10":                    "Windows 10 x64",
    "windows 10 pro":           "Windows 10 x64",
    # Windows 11
    "windows 11 x64":           "Windows 11 x64",
    "windows 11 64":             "Windows 11 x64",
    "win11 x64":                 "Windows 11 x64",
    "win 11 x64":                "Windows 11 x64",
    "win11 64":                  "Windows 11 x64",
    "windows 11 pro x64":       "Windows 11 x64",
    "windows 11 x86":           "Windows 11 x86 (32)",
    "windows 11 32":             "Windows 11 x86 (32)",
    "windows 11 x86 (32)":      "Windows 11 x86 (32)",
    "win11 x86":                 "Windows 11 x86 (32)",
    "win 11 x86":                "Windows 11 x86 (32)",
    "win11 32":                  "Windows 11 x86 (32)",
    "windows 11 pro x86":       "Windows 11 x86 (32)",
    "windows 11":                "Windows 11 x64",
    "win11":                     "Windows 11 x64",
    "win 11":                    "Windows 11 x64",
    "windows 11 pro":           "Windows 11 x64",
    # Windows 7
    "windows 7 x64":            "Windows 7 x64",
    "windows 7 64":             "Windows 7 x64",
    "win7 x64":                  "Windows 7 x64",
    "win 7 x64":                 "Windows 7 x64",
    "win7 64":                   "Windows 7 x64",
    "windows 7 x86":            "Windows 7 x86 (32)",
    "windows 7 32":             "Windows 7 x86 (32)",
    "windows 7 x86 (32)":       "Windows 7 x86 (32)",
    "win7 x86":                  "Windows 7 x86 (32)",
    "win 7 x86":                 "Windows 7 x86 (32)",
    "win7 32":                   "Windows 7 x86 (32)",
    "windows 7":                 "Windows 7 x64",
    "win7":                      "Windows 7 x64",
    "win 7":                     "Windows 7 x64",
    # РЕД ОС
    "ред ос 7.3":               "РЕД ОС 7.3",
    "redos 7.3":                 "РЕД ОС 7.3",
    "red os 7.3":                "РЕД ОС 7.3",
    "ред ос 8":                 "РЕД ОС 8",
    "redos 8":                   "РЕД ОС 8",
    "red os 8":                  "РЕД ОС 8",
}
OS_ALIASES = {_normalize(k): v for k, v in _OS_ALIASES_RAW.items()}


# ============================================================
# МАППИНГ ЗАГОЛОВКОВ КОЛОНОК → КОРОТКИЕ КЛЮЧИ STATE
# ============================================================
_HEADER_ALIASES_RAW = {
    "№ кабинета":              "cabinet",
    "номер кабинета":          "cabinet",
    "кабинет":                 "cabinet",
    "тип":                     "tech_type",
    "марка, модель":           "tech",
    "марка / модель":          "tech",
    "марка модель":            "tech",
    "марка":                   "tech",
    "модель":                  "tech",
    "наименование":            "tech",
    "техника":                 "tech",
    "инв №":                   "inv",
    "инвентарный номер":       "inv",
    "инв. номер":              "inv",
    "инвентарник":             "inv",
    "сер №":                   "serial",
    "сер. №":                  "serial",
    "серийный номер":          "serial",
    "серийник":                "serial",
    "сер.номер":               "serial",
    "ос":                      "os",
    "операционная система":    "os",
    "операционка":             "os",
    "dr web":                  "drweb",
    "dr.web":                 "drweb",
    "drweb":                  "drweb",
    "dr. web":                "drweb",
    "ip-адрес":                "ip",
    "ip адрес":                "ip",
    "ip":                     "ip",
    "ip-адрес ":               "ip",
    "имя пк":                 "pc_name",
    "имя компьютера":          "pc_name",
    "имя":                    "pc_name",
    "имя компьютера ":         "pc_name",
    "физический mac":          "mac_phys",
    "физ. mac":               "mac_phys",
    "физ mac":                "mac_phys",
    "физический":             "mac_phys",
    "реальный mac":           "mac_real",
    "реал. mac":              "mac_real",
    "реал mac":               "mac_real",
    "реальный":               "mac_real",
    "характеристики":         "specs",
    "дополнительно":          "note",
    "примечание":             "note",
    "примечания":             "note",
    "комментарий":            "note",
    "комментарии":            "note",
    "№ п/п":                  "_skip",   # нумерация строк — игнорируем
    "№":                      "_skip",
    "номер":                  "_skip",
    "№ по порядку":           "_skip",
    "*":                      "_skip",
}
HEADER_ALIASES = {_normalize(k): v for k, v in _HEADER_ALIASES_RAW.items()}


# Имена типов для отображения (берём из bot_core.constants)
_TECH_TYPE_LABELS = {
    "pc":      "💻 Системный блок",
    "monitor": "🖥️ Монитор",
    "printer": "🖨️ Принтер / МФУ",
    "laptop":  "💻 Ноутбук",
    "other":   "📱 Другое",
}


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def _resolve_clinic(sheet_name: str) -> Optional[str]:
    """По имени листа возвращает код поликлиники или None."""
    norm = _normalize(sheet_name)
    return CLINIC_SHEET_ALIASES.get(norm)


def _resolve_tech_type(value: str) -> str:
    """Возвращает код типа техники или 'other'."""
    if not value:
        return ""
    return TECH_TYPE_ALIASES.get(_normalize(value), "other")


def _resolve_drweb(value: str) -> str:
    """Нормализует значение Dr.Web в одно из 4 стандартных.
    Если не распознаётся — возвращает как есть.
    """
    if not value:
        return ""
    return DRWEB_ALIASES.get(_normalize(value), str(value).strip())


def _resolve_os(value: str) -> str:
    """Нормализует значение ОС в один из стандартных вариантов.
    Если не распознаётся — возвращает как есть (например, «Windows 10 Enterprise»).
    """
    if not value:
        return ""
    return OS_ALIASES.get(_normalize(value), str(value).strip())


def _resolve_header(col_header: str) -> Optional[str]:
    """Возвращает ключ state по заголовку колонки или None."""
    if not col_header:
        return None
    return HEADER_ALIASES.get(_normalize(col_header))


def _clean_cell(value) -> str:
    """Преобразует ячейку в строку, убирает лишние пробелы."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ ИМПОРТА
# ============================================================
def import_from_excel(file_path: str) -> dict:
    """Импортирует все листы из Excel в БД.

    Возвращает dict:
        {
            "imported": int,                 # сколько записей добавлено
            "skipped": int,                  # сколько строк пропущено (пустые или с ошибкой)
            "errors": list[str],            # список ошибок (первые 50)
            "by_clinic": {clinic_code: int}, # распределение по поликлиникам
            "unrecognized_clinics": list[str], # листы с нераспознанным именем поликлиники
        }
    """
    result = {
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "by_clinic": {},
        "unrecognized_clinics": [],
    }

    try:
        wb = load_workbook(file_path, data_only=True)
    except Exception as e:
        result["errors"].append(f"Не удалось открыть файл: {e}")
        return result

    for sheet_name in wb.sheetnames:
        # Игнорируем листы с пояснениями
        if _normalize(sheet_name) in _EXCLUDED_SHEETS:
            continue

        clinic_code = _resolve_clinic(sheet_name)
        if not clinic_code:
            result["unrecognized_clinics"].append(sheet_name)
            continue

        ws = wb[sheet_name]

        # === ИЩЁМ СТРОКУ С ЗАГОЛОВКАМИ ===
        # Проходим первые 10 строк и ищем ту, где распознаётся ≥3 заголовков
        header_row_idx = None
        header_map = {}  # col_idx → field_key

        for row_idx in range(1, min(10, ws.max_row + 1)):
            local_map = {}
            for col_idx in range(1, ws.max_column + 1):
                value = ws.cell(row=row_idx, column=col_idx).value
                if value:
                    field = _resolve_header(value)
                    if field and field != "_skip":
                        local_map[col_idx] = field
            if len(local_map) >= 3:
                header_row_idx = row_idx
                header_map = local_map
                break

        if not header_map:
            result["errors"].append(
                f"Лист «{sheet_name}»: не найдена строка заголовков — лист пропущен"
            )
            continue

        # === ПАРСИМ ДАННЫЕ ===
        for row_idx in range(header_row_idx + 1, ws.max_row + 1):
            row_has_data = False
            data = {}

            for col_idx, field_key in header_map.items():
                cell_value = _clean_cell(ws.cell(row=row_idx, column=col_idx).value)
                data[field_key] = cell_value
                if cell_value:
                    row_has_data = True

            # Пропускаем полностью пустые строки
            if not row_has_data:
                continue

            # Пропускаем, если нет ни инв. ни серийного номера (пустая запись)
            if not data.get("inv") and not data.get("serial"):
                continue

            # Нормализуем tech_type (если пусто — оставляем пусто, не 'other',
            # чтобы не было 'other' у записей где колонки «Тип» вообще нет)
            if "tech_type" in data and data["tech_type"]:
                data["tech_type"] = _resolve_tech_type(data["tech_type"])
            else:
                data["tech_type"] = ""

            # Заполняем tech_type_name для совместимости с show_confirmation
            if data.get("tech_type"):
                data["tech_type_name"] = _TECH_TYPE_LABELS.get(
                    data["tech_type"], "📱 Другое"
                )
            else:
                data["tech_type_name"] = "📱 Другое"

            # Нормализуем Dr.Web
            if "drweb" in data and data["drweb"]:
                data["drweb"] = _resolve_drweb(data["drweb"])

            # Нормализуем ОС
            if "os" in data and data["os"]:
                data["os"] = _resolve_os(data["os"])

            try:
                item_id = db.save_item(clinic_code, data)
                if item_id > 0:
                    result["imported"] += 1
                    result["by_clinic"][clinic_code] = (
                        result["by_clinic"].get(clinic_code, 0) + 1
                    )
                else:
                    result["skipped"] += 1
            except Exception as e:
                result["skipped"] += 1
                if len(result["errors"]) < 50:
                    result["errors"].append(
                        f"Лист «{sheet_name}», строка {row_idx}: {e}"
                    )

    return result
