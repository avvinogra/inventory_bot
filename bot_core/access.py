import functools

from aiogram import types
from aiogram.exceptions import TelegramBadRequest

import config


def is_admin(chat_id: int) -> bool:
    return chat_id in config.ADMIN_CHAT_IDS


def is_allowed(chat_id: int) -> bool:
    return chat_id in config.ALLOWED_CHAT_IDS


def admin_only(handler):
    """Декоратор для aiogram-хендлеров: пропускает только админов.

    Заменяет 26 копий инлайн-проверки
    ``if not is_admin(...): await callback.answer(...); return``.

    Поведение для не-админа:
      * CallbackQuery — алерт «Доступ запрещён» (не оставляем спиннер
        в Telegram-клиенте);
      * Message — тихий игнор (как было в исходных message-хендлерах).

    Декоратор ставится ПОД декоратор роутера::

        @router.callback_query(F.data == "admin_menu")
        @admin_only
        async def admin_menu(callback, state): ...
    """

    @functools.wraps(handler)
    async def wrapper(event, *args, **kwargs):
        if isinstance(event, types.CallbackQuery):
            # callback.message может быть None (старое/недоступное сообщение)
            chat_id = event.message.chat.id if event.message else event.from_user.id
            if not is_admin(chat_id):
                try:
                    await event.answer("❌ Доступ запрещён!", show_alert=True)
                except TelegramBadRequest:
                    pass  # запрос уже отвечен/устарел — ничего не поделать
                return
        elif isinstance(event, types.Message):
            if not is_admin(event.chat.id):
                return
        return await handler(event, *args, **kwargs)

    return wrapper
