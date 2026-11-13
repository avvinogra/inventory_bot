"""Слой доступа к данным (SQLite) — пакет database.

Фаза 2: раньше это был один файл database.py на ~880 строк (God-модуль).
Теперь разбит по зонам ответственности:

    connection — подключения (WAL, busy_timeout), get_db, ping
    schema     — CREATE TABLE / миграции / сидирование счётчиков
    items      — CRUD и поиск записей инвентаризации
    audit      — аудиторские фильтры проблемных записей
    arms       — АРМ (группы устройств), атомарная выдача arm_id

Этот __init__ — фасад: реэкспортирует весь публичный API, поэтому
`import database as db` и `from database import X` продолжают работать
без изменений во всех модулях бота и веб-панели (и в смоук-тестах).
"""

from database.arms import (
    add_to_arm,
    create_arm,
    delete_arm,
    get_all_arms,
    get_arm_items,
    get_items_without_arm,
    next_arm_id,
    remove_from_arm,
)
from database.audit import (
    count_problematic_items,
    find_problematic_items,
)
from database.connection import (
    BUSY_TIMEOUT_SECONDS,
    connect,
    get_db,
    ping,
)
from database.items import (
    delete_item,
    find_by_inv,
    find_by_pc_name,
    find_by_serial,
    find_duplicates_by_inv,
    find_duplicates_by_pc_name,
    find_duplicates_by_serial,
    get_all_items,
    get_db_stats,
    get_item_by_id,
    get_last_item,
    global_search,
    save_item,
    save_items,
    update_item,
)
from database.schema import (
    INVENTORY_FIELDS_DB,
    LEGACY_FIELDS_DB,
    init_db,
)

__all__ = [
    # connection
    "BUSY_TIMEOUT_SECONDS",
    # schema
    "INVENTORY_FIELDS_DB",
    "LEGACY_FIELDS_DB",
    # arms
    "add_to_arm",
    "connect",
    # audit
    "count_problematic_items",
    "create_arm",
    "delete_arm",
    # items
    "delete_item",
    "find_by_inv",
    "find_by_pc_name",
    "find_by_serial",
    "find_duplicates_by_inv",
    "find_duplicates_by_pc_name",
    "find_duplicates_by_serial",
    "find_problematic_items",
    "get_all_arms",
    "get_all_items",
    "get_arm_items",
    "get_db",
    "get_db_stats",
    "get_item_by_id",
    "get_items_without_arm",
    "get_last_item",
    "global_search",
    "init_db",
    "next_arm_id",
    "ping",
    "remove_from_arm",
    "save_item",
    "save_items",
    "update_item",
]
