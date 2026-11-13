"""Клавиатуры бота — пакет, разложенный по экранам (фаза 4).

Раньше это был один файл keyboards.py на ~590 строк. Теперь:

    menu     — главное меню, «после сохранения», подтверждение выхода
    entry    — сценарий ввода новой записи (клиника, АРМ, навигация по
               полям, выбор Dr.Web/ОС, карточка «проверьте данные»,
               предупреждения о дубликатах и MAC)
    editing  — поиск и правка существующей записи
    audit    — аудиторский фильтр (категории + результаты)
    admin    — админка и управление АРМ
    _shared  — общие построители (двухколоночные сетки, кнопки полей)

Этот __init__ — фасад: реэкспортирует весь публичный API, поэтому
`from bot_core.keyboards import X` продолжает работать без изменений
во всех хендлерах, bot_core.flow и bot_core.cards. Внутренние модули
пакета потребители импортировать не должны (страж в tests/test_structure.py).
"""

from bot_core.keyboards.admin import (
    get_admin_back_keyboard,
    get_admin_keyboard,
    get_arm_list_keyboard,
    get_arm_menu_keyboard,
    get_arm_select_items_keyboard,
    get_arm_view_keyboard,
    get_delete_method_keyboard,
)
from bot_core.keyboards.audit import (
    AUDIT_CATEGORIES,
    get_audit_keyboard,
    get_audit_results_keyboard,
)
from bot_core.keyboards.editing import (
    get_edit_after_action_keyboard,
    get_edit_back_keyboard,
    get_edit_clinic_keyboard,
    get_edit_delete_confirm_keyboard,
    get_edit_field_input_keyboard,
    get_edit_items_keyboard,
    get_edit_method_keyboard,
    get_edit_record_keyboard,
)
from bot_core.keyboards.entry import (
    get_arm_after_save_keyboard,
    get_arm_mode_keyboard,
    get_clinic_keyboard,
    get_confirm_edit_keyboard,
    get_drweb_choice_keyboard,
    get_duplicate_inv_keyboard,
    get_duplicate_serial_keyboard,
    get_mac_mismatch_keyboard,
    get_nav_keyboard,
    get_os_choice_keyboard,
    get_skip_cancel_keyboard,
    get_tech_type_keyboard,
)
from bot_core.keyboards.menu import (
    get_after_save_keyboard,
    get_exit_confirm_keyboard,
    get_main_keyboard,
)

__all__ = [
    "AUDIT_CATEGORIES",
    "get_admin_back_keyboard",
    "get_admin_keyboard",
    "get_after_save_keyboard",
    "get_arm_after_save_keyboard",
    "get_arm_list_keyboard",
    "get_arm_menu_keyboard",
    "get_arm_mode_keyboard",
    "get_arm_select_items_keyboard",
    "get_arm_view_keyboard",
    "get_audit_keyboard",
    "get_audit_results_keyboard",
    "get_clinic_keyboard",
    "get_confirm_edit_keyboard",
    "get_delete_method_keyboard",
    "get_drweb_choice_keyboard",
    "get_duplicate_inv_keyboard",
    "get_duplicate_serial_keyboard",
    "get_edit_after_action_keyboard",
    "get_edit_back_keyboard",
    "get_edit_clinic_keyboard",
    "get_edit_delete_confirm_keyboard",
    "get_edit_field_input_keyboard",
    "get_edit_items_keyboard",
    "get_edit_method_keyboard",
    "get_edit_record_keyboard",
    "get_exit_confirm_keyboard",
    "get_mac_mismatch_keyboard",
    "get_main_keyboard",
    "get_nav_keyboard",
    "get_os_choice_keyboard",
    "get_skip_cancel_keyboard",
    "get_tech_type_keyboard",
]
