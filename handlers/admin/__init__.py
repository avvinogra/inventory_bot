"""Админка — пакет, разложенный по экранам.

Раньше это был один файл handlers/admin.py на ~630 строк. Теперь:

    menu     — меню админки, статистика базы, последние записи
    delete   — удаление записи (по ID / по инвентарному номеру)
    exports  — экспорт базы (SQLite-файл) и выгрузка в Excel
    arms     — управление АРМ (список, просмотр, сборка нового АРМ)
    users    — пользователи с доступом и их роли

`router` ниже — агрегатор под-роутеров: handlers/__init__ импортирует
его как раньше (admin_router), bot.py не меняется. Фильтры хендлеров
разных экранов не пересекаются (разные callback-префиксы и состояния),
поэтому порядок include_router не влияет на поведение.
"""

from aiogram import Router

from . import arms, delete, exports, menu, users

router = Router()
router.include_router(menu.router)
router.include_router(delete.router)
router.include_router(exports.router)
router.include_router(arms.router)
router.include_router(users.router)
