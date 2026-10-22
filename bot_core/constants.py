# Поля инвентаризации (порядок как в XLSX "Инвентаризация.xlsx"):
#   cabinet, tech (Марка,модель), serial, inv, os, drweb, ip,
#   pc_name, mac_phys, mac_real, specs, note
#
# ВАЖНО: tech_type сохраняется отдельно (выбор типа техники делается
# через меню pc/monitor/printer/laptop/other и записывается в БД как tech_type).
INVENTORY_FIELDS = [
    "cabinet", "tech", "serial", "inv", "os", "drweb",
    "ip", "pc_name", "mac_phys", "mac_real", "specs", "note",
]

# Соответствие "ключ в state" → "колонка в БД".
FIELD_TO_DB_COLUMN = {
    "cabinet":   "cabinet",
    "tech_type": "tech_type",
    "tech":      "tech",
    "serial":    "serial",
    "inv":       "inv_number",
    "os":        "os",
    "drweb":     "drweb",
    "ip":        "ip",
    "pc_name":   "pc_name",
    "mac_phys":  "mac_phys",
    "mac_real":  "mac_real",
    "specs":     "specs",
    "note":      "note",
}

# Обязательные поля (нельзя пропустить)
REQUIRED_FIELDS = ["cabinet", "tech", "serial", "inv"]

TECH_TYPES = {
    "pc": {
        "name": "💻 Системный блок",
        "fields": [
            "cabinet", "tech", "serial", "inv", "os", "drweb",
            "ip", "pc_name", "mac_phys", "mac_real", "specs", "note",
        ],
    },
    "monitor": {
        "name": "🖥️ Монитор",
        "fields": ["cabinet", "tech", "serial", "inv", "specs", "note"],
    },
    "printer": {
        "name": "🖨️ Принтер / МФУ",
        "fields": ["cabinet", "tech", "serial", "inv", "ip", "mac_phys", "mac_real", "note"],
    },
    "laptop": {
        "name": "💻 Ноутбук",
        "fields": [
            "cabinet", "tech", "serial", "inv", "os", "drweb",
            "ip", "pc_name", "mac_phys", "mac_real", "specs", "note",
        ],
    },
    "other": {
        "name": "📱 Другое",
        "fields": ["cabinet", "tech", "serial", "inv", "specs", "note"],
    },
}

# ============================================================
# ВАРИАНТЫ Dr.Web — без сокращений, без эмодзи
# ============================================================
# В БД хранится нормальная подпись (value), в кнопке видим тот же текст (label).
# Порядок: ключ callback → (метка на кнопке, значение в БД).
DRWEB_CHOICES = {
    "installed":  ("Установлен",                "Установлен"),
    "no_license": ("Нет лицензии",              "Нет лицензии"),
    "no_connect": ("Нет соединения с сервером", "Нет соединения с сервером"),
    "absent":     ("Не установлен",              "Не установлен"),
}

# Обратное отображение: значение в БД → подпись для UI.
# Покрывает и новые значения, и старые («+», «нет», «нет лиц», «нет соед»).
# Эмодзи убраны — везде выводим чистый текст.
DRWEB_DISPLAY_MAP = {
    # Новые значения
    "Установлен":                "Установлен",
    "Нет лицензии":              "Нет лицензии",
    "Нет соединения с сервером": "Нет соединения с сервером",
    "Не установлен":             "Не установлен",
    # Старые значения (для совместимости с уже существующими записями)
    "+":         "Установлен",
    "да":        "Установлен",
    "yes":       "Установлен",
    "нет лиц":   "Нет лицензии",
    "нет соед":  "Нет соединения с сервером",
    "нет":       "Не установлен",
    "no":        "Не установлен",
}


def display_drweb(value: str) -> str:
    """Преобразует значение Dr.Web (из БД или из state) в нормальную подпись.
    Если значение не из словаря — возвращает как есть.
    """
    if not value:
        return "—"
    return DRWEB_DISPLAY_MAP.get(str(value).strip(), str(value))


# ============================================================
# Поля, доступные для редактирования существующей записи.
# Метки — без сокращений (как в подсказках и карточке).
# ============================================================
EDITABLE_FIELDS = [
    ("cabinet",   "🏢 Номер кабинета"),
    ("tech_type", "📦 Тип"),
    ("tech",      "🏷️ Марка, модель"),
    ("inv",       "🔢 Инвентарный номер"),
    ("serial",    "🔢 Серийный номер"),
    ("os",        "🖥️ Операционная система"),
    ("drweb",     "🛡️ Dr.Web"),
    ("ip",        "🌐 IP-адрес"),
    ("pc_name",   "💻 Имя компьютера"),
    ("mac_phys",  "📡 Физический MAC"),
    ("mac_real",  "📡 Реальный MAC"),
    ("specs",     "⚙️ Характеристики"),
    ("note",      "💬 Дополнительно"),
]
