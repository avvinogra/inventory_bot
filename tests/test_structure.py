"""Архитектурные стражи: структура пакетов, дедупликация, отсутствие
мусора, который принесли и закрыли фазы 0–4.

Эти тесты читают ИСХОДНИКИ (AST/строки), а не поведение: они ловят
регрессии формы — возврат инлайн-проверок, копий словарей, ленивых
импортов — которые поведенческими тестами не видны.
"""

import ast
import importlib
import re
import subprocess
import sys
from pathlib import Path

import database as db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _src(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


# ============================================================
# ДЕДУПЛИКАЦИЯ (фаза 2)
# ============================================================
def test_drweb_dicts_have_single_source():
    """Копии словаря Dr.Web не расползаются обратно по модулям."""
    assert '"Нет лицензии":' not in _src("excel_export.py")
    assert "TECH_TYPE_LABELS = {" not in _src("excel_export.py")
    assert "DRWEB_DISPLAY_MAP.items()" in _src("excel_import.py")
    assert '"Нет лицензии"' not in _src("web_app.py")


def test_keyboards_does_not_redefine_is_admin():
    """is_admin определён один раз — в bot_core.access.

    Фаза 4: keyboards — пакет; is_admin нужен только модулю menu.
    """
    keyboards_dir = PROJECT_ROOT / "bot_core" / "keyboards"
    files = sorted(keyboards_dir.glob("*.py"))
    assert files, "пакет bot_core/keyboards исчез"
    for path in files:
        assert "def is_admin" not in path.read_text(encoding="utf-8"), path.name
    assert "from bot_core.access import is_admin" in _src("bot_core/keyboards/menu.py")


def test_handlers_use_admin_only_decorator():
    admin_pkg = PROJECT_ROOT / "handlers" / "admin"
    admin_files = sorted(p for p in admin_pkg.glob("*.py") if p.name != "__init__.py")
    assert admin_files, "пакет handlers/admin исчез"
    for path in admin_files:
        src = path.read_text(encoding="utf-8")
        assert "if not is_admin(" not in src, f"{path.name}: вернулась инлайн-проверка"
        assert "@admin_only" in src, f"{path.name}: хендлеры должны быть под @admin_only"
    for handler_file in ("handlers/audit.py", "handlers/import_xlsx.py"):
        src = _src(handler_file)
        assert "if not is_admin(" not in src, f"{handler_file}: вернулась инлайн-проверка"
        assert "@admin_only" in src, f"{handler_file}: хендлеры должны быть под @admin_only"


def test_cards_module_breaks_handler_to_handler_dependency():
    """show_record_card живёт в bot_core.cards, а не в хендлере.

    Фаза 4: inventory — пакет; карточку показывает fields.py
    (_after_field_input, режим редактирования существующей записи).
    """
    assert "from bot_core.cards import show_record_card" in _src("handlers/editing.py")
    assert "from bot_core.cards import show_record_card" in _src("handlers/inventory/fields.py")
    assert "from bot_core.cards import show_record_card" in _src("handlers/common.py")


# ============================================================
# МЁРТВЫЙ КОД (фаза 2)
# ============================================================
def test_user_states_dead_code_stays_removed():
    assert not hasattr(db, "set_user_state")
    assert not hasattr(db, "clear_user_state")
    assert "clear_user_state" not in _src("handlers/common.py")
    assert "clear_user_state" not in _src("handlers/editing.py")


def test_labels_dir_removed():
    import config

    assert not hasattr(config, "LABELS_DIR")


# ============================================================
# ЛЕНИВЫЕ ИМПОРТЫ (фаза 2)
# ============================================================
# Опциональные зависимости — оправданные исключения (фолбэк при отсутствии)
_JUSTIFIED_LAZY = ("getpass", "redis", "aiohttp_socks", "RedisStorage", "ProxyConnector")


def _lazy_imports(path: Path) -> list[str]:
    """Находит import/from внутри тел функций (отступ > 0)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, (ast.Import, ast.ImportFrom)):
                continue
            module = getattr(sub, "module", "") or ""
            names = " ".join(alias.name for alias in sub.names)
            joined = f"{module} {names}"
            if any(needle in joined for needle in _JUSTIFIED_LAZY):
                continue
            found.append(f"{path.name}:{sub.lineno}")
    return found


def test_no_imports_inside_function_bodies():
    scanned = [
        *(PROJECT_ROOT / "handlers").rglob("*.py"),
        *(PROJECT_ROOT / "bot_core").rglob("*.py"),
        *(PROJECT_ROOT / "web").glob("*.py"),
        *(PROJECT_ROOT / "database").glob("*.py"),
        PROJECT_ROOT / "web_app.py",
        PROJECT_ROOT / "excel_import.py",
        PROJECT_ROOT / "excel_export.py",
    ]
    offenders = [loc for path in scanned for loc in _lazy_imports(path)]
    assert not offenders, f"импорты вернулись в тела функций: {offenders}"


# ============================================================
# ФАСАД database И ЦЕЛОСТНОСТЬ ПАКЕТОВ
# ============================================================
def test_database_facade_exports_full_api():
    """`import database as db` продолжает работать для всего вызывающего кода."""
    expected = {
        "connect",
        "get_db",
        "ping",
        "init_db",
        "get_db_stats",
        "save_item",
        "save_items",
        "get_all_items",
        "get_item_by_id",
        "find_by_serial",
        "find_by_inv",
        "find_by_pc_name",
        "get_last_item",
        "find_duplicates_by_inv",
        "find_duplicates_by_serial",
        "find_duplicates_by_pc_name",
        "global_search",
        "find_problematic_items",
        "count_problematic_items",
        "update_item",
        "delete_item",
        "next_arm_id",
        "create_arm",
        "get_arm_items",
        "get_all_arms",
        "add_to_arm",
        "remove_from_arm",
        "delete_arm",
        "get_items_without_arm",
        "INVENTORY_FIELDS_DB",
        "LEGACY_FIELDS_DB",
    }
    missing = expected - set(dir(db))
    assert not missing, f"фасад database потерял: {sorted(missing)}"


def test_all_modules_importable():
    """Импорт-дым: ловит потерянные файлы/имена (баг validators.py из фазы 2).

    bot.py НЕ импортируется: у него fail-fast на пустой BOT_TOKEN.
    """
    modules = [
        "config",
        "validators",
        "database",
        "database.connection",
        "database.schema",
        "database.items",
        "database.audit",
        "database.arms",
        "excel_export",
        "excel_import",
        "web_app",
        "web.context",
        "web.security",
        "web.views",
        "web.api",
        "web.export",
        "bot_core.constants",
        "bot_core.keyboards",
        "bot_core.cards",
        "bot_core.flow",
        "bot_core.states",
        "bot_core.access",
        "bot_core.keyboards._shared",
        "bot_core.keyboards.menu",
        "bot_core.keyboards.entry",
        "bot_core.keyboards.editing",
        "bot_core.keyboards.audit",
        "bot_core.keyboards.admin",
        "handlers",
        "handlers.admin",
        "handlers.admin.menu",
        "handlers.admin.delete",
        "handlers.admin.exports",
        "handlers.admin.arms",
        "handlers.admin.users",
        "handlers.audit",
        "handlers.common",
        "handlers.editing",
        "handlers.errors",
        "handlers.import_xlsx",
        "handlers.inventory",
        "handlers.inventory.entry",
        "handlers.inventory.fields",
        "handlers.inventory.choices",
        "handlers.inventory.confirmations",
        "handlers.inventory.review",
        "handlers.inventory.arm",
    ]
    for name in modules:
        importlib.import_module(name)  # не должно бросить


def test_web_app_remains_executable_module():
    """`python web_app.py` — команда docker-compose: точка входа на месте."""
    assert '__name__ == "__main__"' in _src("web_app.py")


def test_bot_fails_fast_without_token(tmp_path):
    """Без BOT_TOKEN бот падает сразу с понятным сообщением (фаза 0)."""
    env = {
        "DB_PATH": str(tmp_path / "unused.db"),
        "PYTHONPATH": str(PROJECT_ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", "import bot"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    assert "BOT_TOKEN не задан" in (result.stdout + result.stderr)


# ============================================================
# РАЗБИЕНИЕ ПО ЭКРАНАМ / СЦЕНАРИЯМ (фаза 4)
# ============================================================
def test_keyboards_consumed_only_via_facade():
    """Клавиатуры импортируются только через фасад bot_core.keyboards.

    Внутренние модули пакета (menu/entry/editing/...) не должны
    расползаться по импортам потребителей — иначе фасад теряет смысл.
    """
    offenders = []
    for path in [
        *(PROJECT_ROOT / "handlers").rglob("*.py"),
        *(PROJECT_ROOT / "bot_core").glob("*.py"),
        PROJECT_ROOT / "bot.py",
    ]:
        src = path.read_text(encoding="utf-8")
        for match in re.finditer(r"from bot_core\.keyboards\.\w+ import", src):
            offenders.append(f"{path.name}: {match.group(0)}")
    assert not offenders, f"импорт в обход фасада: {offenders}"


def test_keyboards_facade_exports_all_builders():
    """Фасад re-exportит всех публичных билдеров пакета keyboards."""
    import bot_core.keyboards as keyboards_pkg

    public_builders = set()
    for path in (PROJECT_ROOT / "bot_core" / "keyboards").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and not node.name.startswith("_"):
                public_builders.add(node.name)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    # приватные константы (ведущее «_») — как и приватные
                    # функции, реэкспорта через фасад не требуют
                    if (
                        isinstance(target, ast.Name)
                        and target.id.isupper()
                        and not target.id.startswith("_")
                    ):
                        public_builders.add(target.id)
    missing = public_builders - set(keyboards_pkg.__all__)
    assert not missing, f"фасад keyboards потерял: {sorted(missing)}"


def test_inventory_router_aggregates_scenario_routers():
    """handlers/inventory — пакет: единый router собирается из под-роутеров."""
    src = _src("handlers/inventory/__init__.py")
    for module in ("entry", "fields", "choices", "confirmations", "review", "arm"):
        assert f"{module}.router" in src, f"под-роутер {module} не подключён к агрегатору"
        assert (PROJECT_ROOT / "handlers" / "inventory" / f"{module}.py").exists()

    # Контракт с handlers/__init__.py не изменился
    assert "from .inventory import router as inventory_router" in _src("handlers/__init__.py")
    # bot.py не ссылается на внутренности пакета
    assert "handlers.inventory." not in _src("bot.py")


def test_admin_router_aggregates_scenario_routers():
    """handlers/admin — пакет: единый router собирается из под-роутеров."""
    src = _src("handlers/admin/__init__.py")
    for module in ("menu", "delete", "exports", "arms", "users"):
        assert f"{module}.router" in src, f"под-роутер {module} не подключён к агрегатору"
        assert (PROJECT_ROOT / "handlers" / "admin" / f"{module}.py").exists()

    # Контракт с handlers/__init__.py не изменился, старый монолит удалён
    assert "from .admin import router as admin_router" in _src("handlers/__init__.py")
    assert not (PROJECT_ROOT / "handlers" / "admin.py").exists()
    # bot.py не ссылается на внутренности пакета
    assert "handlers.admin." not in _src("bot.py")


def test_no_stale_monoliths_next_to_packages():
    """Монолитные .py-файлы не возвращаются рядом с одноимёнными пакетами.

    Модуль-монолит рядом с пакетом (keyboards.py vs keyboards/) — мёртвый
    код: импорт разрешается в пакет, а файл продолжает существовать,
    путать читателя и портить покрытие.
    """
    for module in ("bot_core/keyboards", "handlers/inventory", "handlers/admin"):
        assert (PROJECT_ROOT / module).is_dir(), f"пакет {module} исчез"
        assert not (PROJECT_ROOT / f"{module}.py").exists(), (
            f"мёртвый монолит {module}.py лежит рядом с пакетом"
        )


def test_after_field_input_single_source():
    """Трёхрежимная логика после ввода поля существует в одном месте.

    Раньше (до фазы 4) ветки mode == "existing" / "new_record" были
    скопированы в drweb_choice_selected и os_choice_selected.
    """
    assert 'mode == "existing"' in _src("handlers/inventory/fields.py")
    assert 'mode == "new_record"' in _src("handlers/inventory/fields.py")
    # Ни в одном другом сценарном модуле — ни ветвления, ни прямого UPDATE:
    # правка поля existing-записи идёт только через общую точку.
    for name in ("entry", "choices", "confirmations", "review", "arm"):
        src = _src(f"handlers/inventory/{name}.py")
        assert 'mode == "existing"' not in src, name
        assert "db.update_item" not in src, name
    # choices переиспользует общую логику, а не свою копию
    assert "from handlers.inventory.fields import _after_field_input" in _src(
        "handlers/inventory/choices.py"
    )


def test_no_dead_page_size_in_inventory():
    """PAGE_SIZE в inventory был мёртвым кодом (используется только
    в editing.py и audit.py) — не должен возвращаться."""
    for path in (PROJECT_ROOT / "handlers" / "inventory").glob("*.py"):
        assert "PAGE_SIZE" not in path.read_text(encoding="utf-8"), path.name


# ============================================================
# ЛИНТЕР
# ============================================================
def test_ruff_check_clean():
    """`ruff check .` → 0 замечаний; конфиг закреплён в pyproject.toml."""
    result = subprocess.run(
        ["ruff", "check", "."],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout[-2000:]
