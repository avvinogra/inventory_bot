import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from handlers import (
    admin_router,
    audit_router,
    common_router,
    editing_router,
    errors_router,
    import_router,
    inventory_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_storage():
    """Создаёт storage для FSM. Если задан REDIS_URL — использует Redis,
    иначе — MemoryStorage (данные в RAM, теряются при перезапуске).
    """
    if not config.REDIS_URL:
        return MemoryStorage()

    try:
        from aiogram.fsm.storage.redis import RedisStorage
        logger.info(f"📦 FSM storage: Redis ({config.REDIS_URL})")
        return RedisStorage.from_url(config.REDIS_URL)
    except ImportError:
        logger.warning(
            "⚠️ Библиотека redis не установлена. Поставьте: pip install redis. "
            "Используем MemoryStorage (состояния потеряются при перезапуске)."
        )
        return MemoryStorage()
    except Exception as e:
        logger.warning(
            f"⚠️ Не удалось подключиться к Redis: {e}. "
            "Используем MemoryStorage."
        )
        return MemoryStorage()


def _build_bot() -> Bot:
    """Создаёт Bot, при необходимости с прокси для обхода блокировки Telegram."""
    session = None

    # 1) HTTP/HTTPS-прокси (простой случай, не требует доп. пакетов)
    if config.PROXY_URL:
        logger.info(f"🌐 Использую HTTP-прокси: {config.PROXY_URL}")
        session = AiohttpSession(proxy=config.PROXY_URL)

    # 2) SOCKS5-прокси (требует установленный aiohttp-socks)
    elif config.SOCKS5_PROXY:
        try:
            from aiohttp_socks import ProxyConnector
        except ImportError:
            logger.error(
                "❌ Установите aiohttp-socks для SOCKS5-прокси:\n"
                "    pip install aiohttp-socks"
            )
            sys.exit(1)
        logger.info(f"🧦 Использую SOCKS5-прокси: {config.SOCKS5_PROXY}")
        connector = ProxyConnector.from_url(config.SOCKS5_PROXY)
        session = AiohttpSession(connector=connector)

    kwargs = {
        "token": config.BOT_TOKEN,
        "default": DefaultBotProperties(parse_mode="HTML"),
    }
    if session is not None:
        kwargs["session"] = session
    return Bot(**kwargs)


bot = _build_bot()
dp = Dispatcher(storage=_build_storage())
# Порядок важен: общие обработчики -> создание записи -> правка существующих -> импорт -> админка -> ошибки
dp.include_router(common_router)
dp.include_router(inventory_router)
dp.include_router(editing_router)
dp.include_router(import_router)
dp.include_router(audit_router)
dp.include_router(admin_router)
dp.include_router(errors_router)


async def main():
    db.init_db()
    logger.info("База данных инициализирована")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except TelegramNetworkError as e:
        logger.error(
            "\n"
            "========================================\n"
            "❌ НЕ УДАЛОСЬ ПОДКЛЮЧИТЬСЯ К api.telegram.org\n"
            "========================================\n"
            f"Ошибка: {e}\n\n"
            "Что делать:\n"
            "  1) Проверьте, что есть интернет (curl https://api.telegram.org)\n"
            "  2) Если Telegram заблокирован вашим провайдером —\n"
            "     настройте прокси и задайте в .env одну из переменных:\n\n"
            "       PROXY_URL=http://user:pass@proxy.host:8080\n"
            "         (HTTP/HTTPS-прокси — simplest, работает из коробки)\n\n"
            "       SOCKS5_PROXY=socks5://user:pass@1.2.3.4:1080\n"
            "         (SOCKS5 — нужно: pip install aiohttp-socks)\n\n"
            "  3) Либо запустите бота с включённым VPN/Tor на машине.\n"
            "========================================"
        )
        return

    logger.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
