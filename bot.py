import asyncio
import logging

from aiogram import Bot, Dispatcher

import config
import database as db
from handlers import admin_router, common_router, errors_router, inventory_router, printing_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(common_router)
dp.include_router(inventory_router)
dp.include_router(printing_router)
dp.include_router(admin_router)
dp.include_router(errors_router)


async def main():
    db.init_db()
    logger.info("База данных инициализирована")
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")