import json
import logging
import os
import traceback
from datetime import datetime, timezone

from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)
router = Router()

ERRORS_DIR = "logs"
ERRORS_FILE = os.path.join(ERRORS_DIR, "bot_errors.jsonl")


def _append_error_record(record: dict) -> None:
    os.makedirs(ERRORS_DIR, exist_ok=True)
    with open(ERRORS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


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

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type(exc).__name__,
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

    try:
        if callback:
            await callback.answer("❌ Произошла ошибка. Попробуйте ещё раз.", show_alert=True)
        elif message:
            await message.answer("❌ Произошла ошибка. Попробуйте ещё раз.")
    except Exception:
        # Ignore secondary errors while notifying user
        pass

    return True

