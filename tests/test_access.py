"""Контроль доступа бота: is_admin/is_allowed и декоратор admin_only.

admin_only (фаза 1) заменил 26 инлайн-проверок «if not is_admin(...)».
Проверяем поведение на РЕАЛЬНЫХ объектах aiogram, а не моках события.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from aiogram import types as aiogram_types

from bot_core.access import admin_only, is_admin, is_allowed

ADMIN_ID = 111  # задаётся в conftest: ADMIN_CHAT_IDS=111
REGULAR_ID = 222  # ALLOWED_CHAT_IDS=111,222
STRANGER_ID = 999  # ни админ, ни разрешённый


@admin_only
async def _guarded_handler(event, state=None):
    """Тестовый хендлер: возвращает маркер, если декоратор его пропустил."""
    return "RAN"


def test_is_admin_and_is_allowed():
    assert is_admin(ADMIN_ID)
    assert not is_admin(REGULAR_ID)
    assert is_allowed(REGULAR_ID)
    assert not is_allowed(STRANGER_ID)
    assert not is_admin(STRANGER_ID)


def test_admin_callback_is_executed(make_callback):
    result = asyncio.run(_guarded_handler(make_callback(ADMIN_ID)))
    assert result == "RAN"


def test_non_admin_callback_blocked_with_alert(make_callback):
    """Не-админ: хендлер не выполняется, пользователь видит алерт."""
    callback = make_callback(REGULAR_ID)
    with patch.object(aiogram_types.CallbackQuery, "answer", AsyncMock()) as answer_mock:
        result = asyncio.run(_guarded_handler(callback))

    assert result is None
    answer_mock.assert_called_once()
    alert_text = str(answer_mock.call_args.args[0] if answer_mock.call_args.args else "")
    assert "запрещ" in alert_text.lower(), f"в алерте должно быть «Доступ запрещён»: {alert_text!r}"


def test_non_admin_callback_without_message_uses_from_user(make_callback):
    """callback.message может быть None (старое сообщение) — chat_id из from_user."""
    callback = make_callback(REGULAR_ID, message=None)
    assert callback.message is None
    with patch.object(aiogram_types.CallbackQuery, "answer", AsyncMock()):
        result = asyncio.run(_guarded_handler(callback))
    assert result is None


def test_non_admin_message_silently_ignored(make_message):
    """Не-админ: message-хендлер тихо игнорируется (как в исходном коде)."""
    assert asyncio.run(_guarded_handler(make_message(REGULAR_ID))) is None


def test_admin_message_is_executed(make_message):
    assert asyncio.run(_guarded_handler(make_message(ADMIN_ID))) == "RAN"
