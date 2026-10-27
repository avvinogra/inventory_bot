import json
import logging
import os
import traceback
from datetime import datetime, timezone

from aiogram import Router
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramConflictError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)
router = Router()

ERRORS_DIR = "logs"
ERRORS_FILE = os.path.join(ERRORS_DIR, "bot_errors.jsonl")

# Размер файла лога, после которого делаем ротацию (10 МБ)
_MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024
# Сколько старых файлов логов хранить (последние N)
_MAX_ROTATED_FILES = 10


def _rotate_log_if_needed():
    """Если файл лога стал слишком большим — переименовываем его
    с суффиксом даты-времени и начинаем новый. Старые ротации
    (сверх _MAX_ROTATED_FILES) удаляем.
    """
    try:
        if not os.path.exists(ERRORS_FILE):
            return
        if os.path.getsize(ERRORS_FILE) < _MAX_LOG_SIZE_BYTES:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated_path = os.path.join(
            ERRORS_DIR, f"bot_errors_{ts}.jsonl"
        )
        os.rename(ERRORS_FILE, rotated_path)
        logger.info(f"Лог ошибок ротирован: {rotated_path}")

        # Удаляем самые старые ротации, если их больше лимита
        existing = sorted(
            [f for f in os.listdir(ERRORS_DIR)
             if f.startswith("bot_errors_") and f.endswith(".jsonl")],
        )
        if len(existing) > _MAX_ROTATED_FILES:
            for old_file in existing[: len(existing) - _MAX_ROTATED_FILES]:
                try:
                    os.remove(os.path.join(ERRORS_DIR, old_file))
                except OSError:
                    pass
    except Exception as e:
        logger.warning(f"Не удалось сделать ротацию лога ошибок: {e}")


def _append_error_record(record: dict) -> None:
    """Дописывает запись об ошибке в jsonl-лог, с ротацией при необходимости."""
    os.makedirs(ERRORS_DIR, exist_ok=True)
    _rotate_log_if_needed()
    try:
        with open(ERRORS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Не удалось записать ошибку в файл: %s", e)


def _user_friendly_message(exc) -> str:
    """Возвращает понятное сообщение для пользователя в зависимости
    от типа исключения. Без технических деталей, на русском.
    """
    # Сетевые проблемы (нет интернета / прокси упал / Telegram недоступен)
    if isinstance(exc, TelegramNetworkError):
        return (
            "⚠️ Проблема с сетью. Проверьте подключение к интернету "
            "и настройки прокси (если используются). Попробуйте позже."
        )
    # Слишком много запросов — Telegram просит подождать
    if isinstance(exc, TelegramRetryAfter):
        retry = getattr(exc, "retry_after", None)
        if retry:
            return f"⏳ Слишком много запросов. Попробуйте через {int(retry)} секунд."
        return "⏳ Слишком много запросов. Попробуйте через минуту."
    # Серверная ошибка Telegram
    if isinstance(exc, TelegramServerError):
        return "⚠️ Сервер Telegram недоступен. Попробуйте позже."
    # Бот заблокирован пользователем или нет прав
    if isinstance(exc, TelegramForbiddenError):
        return "⚠️ Нет доступа. Возможно, бот заблокирован или у вас нет прав."
    # Неверный запрос (например, сообщение слишком длинное)
    if isinstance(exc, TelegramBadRequest):
        return "⚠️ Неверный запрос. Проверьте введённые данные и попробуйте ещё раз."
    # Не авторизован — неверный токен
    if isinstance(exc, TelegramUnauthorizedError):
        return "⚠️ Неверный токен бота. Обратитесь к администратору."
    # Конфликт — два бота с одним токеном
    if isinstance(exc, TelegramConflictError):
        return "⚠️ Запущена вторая копия бота с тем же токеном."
    # Таймаут / общая ошибка — запасной вариант
    return "⚠️ Произошла ошибка. Попробуйте ещё раз или обратитесь к администратору."


@router.error()
async def global_error_handler(event: ErrorEvent):
    update = event.update
    exc = event.exception

    message = getattr(update, "message", None)
    callback = getattr(update, "callback_query", None)

    chat_id = None
    user_id = None
    update_type = "unknown"
    update_text = None

    if message:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        update_type = "message"
        update_text = message.text
    elif callback:
        chat_id = callback.message.chat.id if callback.message else None
        user_id = callback.from_user.id if callback.from_user else None
        update_type = "callback_query"
        update_text = callback.data

    # Единый формат записи в лог
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type(exc).__name__,
        "module": type(exc).__module__,
        "error": str(exc),
        "chat_id": chat_id,
        "user_id": user_id,
        "update_type": update_type,
        "update_text": update_text,
        "traceback": traceback.format_exc(),
    }

    try:
        _append_error_record(record)
    except Exception as file_exc:
        logger.error("Не удалось записать ошибку в файл: %s", file_exc)

    logger.exception("Unhandled bot error: %s", exc)

    # Понятное сообщение пользователю по типу ошибки
    user_msg = _user_friendly_message(exc)

    try:
        if callback:
            await callback.answer(user_msg, show_alert=True)
        elif message:
            await message.answer(user_msg)
    except Exception:
        # Игнорируем вторичные ошибки при уведомлении пользователя
        pass

    return True
