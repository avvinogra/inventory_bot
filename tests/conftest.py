"""Общие фикстуры pytest для inventory_bot.

Окружение фиксируется ДО импорта модулей проекта: config.py читает
переменные один раз при импорте, а load_dotenv() не переопределяет
уже установленные переменные — поэтому тесты не зависят от локального
.env разработчика и от того, из какого каталога запущен pytest.

Запуск:
    python -m pytest          # из корня проекта
    pytest                    # тоже работает: pythonpath задан в pyproject.toml
"""

import atexit
import datetime
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# 1. Детерминированное окружение (до import config)
# ============================================================
# Значение DB_PATH на момент импорта нигде не используется для записи:
# каждый тест получает свою БД через фикстуру db_path (monkeypatch
# config.DB_PATH — database.connect() читает его при каждом вызове).
_import_scratch = tempfile.mkdtemp(prefix="inv_pytest_import_")
atexit.register(shutil.rmtree, _import_scratch, ignore_errors=True)

os.environ["DB_PATH"] = os.path.join(_import_scratch, "import_time.db")
os.environ["ADMIN_CHAT_IDS"] = "111"
os.environ["ALLOWED_CHAT_IDS"] = "111,222"
os.environ["BOT_TOKEN"] = ""  # сам bot.py в тестах не импортируем (fail-fast)
os.environ["WEB_PANEL_PASSWORD"] = ""  # панель открыта; пароль — отдельные тесты
os.environ["WEB_SESSION_SECRET"] = "pytest-session-secret"
os.environ.pop("TRUSTED_PROXIES", None)  # дефолт loopback — его поведение и проверяем
os.environ.pop("REDIS_URL", None)
os.environ.pop("PROXY_URL", None)
os.environ.pop("SOCKS5_PROXY", None)

import config  # noqa: E402 — env должен быть настроен ДО этого импорта
import database as db  # noqa: E402


# ============================================================
# 2. БД и веб-панель
# ============================================================
@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Свежая изолированная БД для теста.

    database.connect() читает config.DB_PATH при каждом вызове, поэтому
    подмена атрибута даёт полную изоляцию без перезагрузки модулей.
    """
    path = tmp_path / "inventory.db"
    monkeypatch.setattr(config, "DB_PATH", str(path))
    db.init_db()
    return path


@pytest.fixture
def client(db_path, monkeypatch):
    """TestClient веб-панели: панель ОТКРЫТА (пароль не задан)."""
    from fastapi.testclient import TestClient

    import web_app

    monkeypatch.setattr(config, "WEB_PANEL_PASSWORD", "")
    with TestClient(web_app.app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def clean_rate_limit(monkeypatch):
    """Изолированное хранилище rate limit (dict на уровне модуля web.security)."""
    from web import security

    monkeypatch.setattr(security, "_login_attempts", defaultdict(list))


# ============================================================
# 3. Фабрики aiogram-объектов (для декоратора admin_only)
# ============================================================
@pytest.fixture
def make_message():
    """Фабрика aiogram Message."""
    from aiogram import types

    def _make(
        chat_id: int, *, user_id: int | None = None, text: str | None = None, message_id: int = 1
    ):
        return types.Message(
            message_id=message_id,
            date=datetime.datetime.now(datetime.UTC),
            chat=types.Chat(id=chat_id, type="private"),
            from_user=types.User(id=user_id or chat_id, is_bot=False, first_name="Test"),
            text=text,
        )

    return _make


@pytest.fixture
def make_callback(make_message):
    """Фабрика aiogram CallbackQuery.

    message=None — реальный кейс старых/недоступных сообщений:
    декоратор обязан брать chat_id из from_user. По умолчанию (message="auto")
    создаётся обычное сообщение от того же пользователя.
    """
    from aiogram import types

    def _make(user_id: int, *, message="auto", data: str = "admin_menu", text: str | None = None):
        msg = make_message(user_id, text=text) if message == "auto" else message
        return types.CallbackQuery(
            id=str(user_id),
            from_user=types.User(id=user_id, is_bot=False, first_name="Test"),
            chat_instance="pytest",
            data=data,
            message=msg,
        )

    return _make


# ============================================================
# 4. Мок-полигон aiogram: записываем всё, что бот отправляет
# ============================================================
class BotPolygon:
    """Рекордер исходящих сообщений бота.

    У вручную созданных aiogram-объектов .bot is None, поэтому
    safe_edit_message() тихо возвращается к message.answer() — весь
    UI-вывод хендлеров стекается в .messages. Алерты колбэков и
    документы пишутся отдельно.
    """

    def __init__(self):
        self.messages: list[tuple[str, object]] = []  # (text, reply_markup)
        self.alerts: list[str] = []  # тексты callback.answer()
        self.documents: list[str] = []  # имена отправленных файлов
        self.deleted_user_messages: list[int] = []
        self._next_id = 1000

    @property
    def texts(self) -> list[str]:
        return [t for t, _ in self.messages]

    @property
    def last_text(self) -> str:
        return self.texts[-1] if self.texts else ""

    def last_markup_callbacks(self) -> list[str]:
        """callback_data кнопок последнего отправленного сообщения."""
        if not self.messages:
            return []
        markup = self.messages[-1][1]
        if markup is None:
            return []
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    def text_with(self, fragment: str) -> bool:
        return any(fragment in t for t in self.texts)


@pytest.fixture
def ui():
    """Активирует полигон на время теста: Message.answer/delete и
    CallbackQuery.answer подменяются рекордером."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from aiogram import types as aiogram_types

    polygon = BotPolygon()

    async def _answer(self, text, reply_markup=None, parse_mode=None, **kwargs):
        polygon.messages.append((text, reply_markup))
        sent = SimpleNamespace(message_id=polygon._next_id)
        polygon._next_id += 1
        return sent

    async def _answer_document(self, document, caption=None, **kwargs):
        name = getattr(document, "filename", None) or str(document)
        polygon.documents.append(name)
        return SimpleNamespace(message_id=polygon._next_id)

    async def _delete(self, **kwargs):
        polygon.deleted_user_messages.append(self.message_id)
        return True

    async def _cb_answer(self, text=None, show_alert=False, **kwargs):
        if text:
            polygon.alerts.append(text)
        return True

    with (
        patch.object(aiogram_types.Message, "answer", _answer),
        patch.object(aiogram_types.Message, "answer_document", _answer_document),
        patch.object(aiogram_types.Message, "delete", _delete),
        patch.object(aiogram_types.CallbackQuery, "answer", _cb_answer),
    ):
        yield polygon


@pytest.fixture
def fsm_state():
    """Настоящий FSMContext поверх MemoryStorage — без бота и Telegram."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=42, user_id=42)
    return FSMContext(storage=storage, key=key)
