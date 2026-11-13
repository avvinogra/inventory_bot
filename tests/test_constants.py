"""Согласованность единого источника констант (bot_core.constants).

Фаза 2 свела 4 копии Dr.Web-словарей и 5 копий меток типов к одному
файлу. Эти тесты — страховка от «тихого» расползания словарей обратно
и от рассинхронизации связанных представлений.
"""

from bot_core.constants import (
    DRWEB_CHOICES,
    DRWEB_DB_VALUES,
    DRWEB_DISPLAY_MAP,
    DRWEB_PROBLEM_VALUES,
    EDITABLE_FIELDS,
    FIELD_TO_DB_COLUMN,
    INVENTORY_FIELDS,
    OS_CHOICES,
    OS_UI_VALUES,
    TECH_TYPE_LABELS,
    TECH_TYPES,
    display_drweb,
    display_tech_type,
)
from database.schema import INVENTORY_FIELDS_DB


def test_tech_type_labels_match_tech_types():
    """Кнопки бота (с эмодзи) и метки для веба/Excel (без) — один набор ключей."""
    assert set(TECH_TYPE_LABELS) == set(TECH_TYPES)
    assert TECH_TYPE_LABELS["pc"] == "Системный блок"
    assert TECH_TYPES["pc"]["name"].endswith("Системный блок"), "у кнопки бота есть эмодзи-префикс"


def test_display_tech_type_unknown_passthrough():
    assert display_tech_type("pc") == "Системный блок"
    assert display_tech_type("custom-value") == "custom-value"


def test_drweb_db_values_match_choices():
    """Селекты веб-формы содержат ровно те 4 значения, что и кнопки бота.

    Порядок у представлений свой (кнопки бота / селект формы) — важен состав.
    """
    values = {value for _key, (_label, value) in DRWEB_CHOICES.items()}
    assert values == set(DRWEB_DB_VALUES)
    assert len(DRWEB_DB_VALUES) == 4
    assert values <= set(DRWEB_DISPLAY_MAP.values())


def test_drweb_problem_values_are_known_aliases():
    """Каждое «проблемное» значение обязано находиться в словаре отображения —
    иначе фильтр аудита и подпись в UI разойдутся."""
    assert set(DRWEB_PROBLEM_VALUES) <= set(DRWEB_DISPLAY_MAP)
    assert "нет лиц" in DRWEB_PROBLEM_VALUES, "legacy-значения тоже проблема"


def test_display_drweb_regression():
    """Регрессия фазы 2: веб-фильтр .lower() превращал «Установлен» в «установлен»."""
    assert display_drweb("Установлен") == "Установлен"
    assert display_drweb("нет лиц") == "Нет лицензии"
    assert display_drweb("+") == "Установлен"
    assert display_drweb("нет соед") == "Нет соединения с сервером"
    assert display_drweb("") == "—"
    assert display_drweb("свежее значение") == "свежее значение"


def test_os_ui_values_match_choices():
    assert tuple(OS_CHOICES.values()) == OS_UI_VALUES


def test_every_editable_field_has_db_column():
    """Все поля, доступные для редактирования в боте, мапятся на колонки БД."""
    for field, _label in EDITABLE_FIELDS:
        assert field in FIELD_TO_DB_COLUMN, f"поле {field!r} без маппинга в БД"


def test_schema_fields_match_bot_fields():
    """Страж слоёв: колонки БД и state-поля бота синхронны.

    Бот использует короткие ключи (inv), БД — полные колонки (inv_number);
    маппинг между ними описан в FIELD_TO_DB_COLUMN.
    """
    assert set(FIELD_TO_DB_COLUMN.values()) == set(INVENTORY_FIELDS_DB)
    assert len(FIELD_TO_DB_COLUMN) == len(set(FIELD_TO_DB_COLUMN.values())), (
        "два state-ключа не должны мапиться на одну колонку"
    )


def test_inventory_fields_subset_of_editable():
    """Порядок полей ввода соответствует редактируемым полям."""
    assert set(INVENTORY_FIELDS) <= {field for field, _label in EDITABLE_FIELDS}
