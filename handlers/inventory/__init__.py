"""Ввод новой записи — пакет, разложенный по сценариям (фаза 4).

Раньше это был один файл inventory.py на ~830 строк. Теперь:

    entry          — выбор поликлиники, режим АРМ, тип техники
    fields         — ввод текстовых полей + общая трёхрежимная логика
                     (_after_field_input — единая точка для всех полей)
    choices        — выбор Dr.Web и ОС из inline-кнопок
    confirmations  — подтверждение предупреждений (дубликаты, MAC)
    review         — карточка «проверьте данные» и сохранение
    arm            — цикл АРМ: добавить ещё устройство / завершить

`router` ниже — агрегатор под-роутеров: handlers/__init__ импортирует
его как раньше (inventory_router), bot.py не меняется. Фильтры
хендлеров разных сценариев не пересекаются (разные состояния и
callback-префиксы), поэтому порядок include_router не влияет на
поведение.
"""

from aiogram import Router

from . import arm, choices, confirmations, entry, fields, review

router = Router()
router.include_router(entry.router)
router.include_router(fields.router)
router.include_router(choices.router)
router.include_router(confirmations.router)
router.include_router(review.router)
router.include_router(arm.router)
