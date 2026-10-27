from aiogram.fsm.state import State, StatesGroup


class InventoryForm(StatesGroup):
    # --- Создание новой записи ---
    selecting_clinic = State()
    selecting_tech_type = State()
    entering_cabinet = State()
    entering_tech = State()
    entering_serial = State()
    entering_inv = State()
    entering_os = State()
    entering_drweb = State()
    entering_ip = State()
    entering_pc_name = State()
    entering_mac_phys = State()
    entering_mac_real = State()
    entering_specs = State()
    entering_note = State()
    confirming_save = State()           # карточка "проверьте данные"

    # --- Подтверждение дубликатов (только при создании новой записи) ---
    confirming_inv_duplicate = State()        # нашли запись с таким же инв. номером
    confirming_serial_duplicate = State()    # нашли запись с таким же серийником
    confirming_pc_name_duplicate = State()    # нашли запись с таким же именем ПК
    confirming_mac_mismatch = State()         # физ. MAC ≠ реал. MAC
    confirming_exit = State()                  # подтверждение выхода во время ввода

    # --- Редактирование СУЩЕСТВУЮЩЕЙ записи ---
    edit_select_method = State()        # выбор: по ИНВ / по ID / по поликлинике / глобальный
    edit_enter_inv = State()            # ввод инв. номера (также глобальный поиск / поиск по имени ПК)
    edit_enter_id = State()             # ввод ID
    edit_select_clinic = State()        # выбор поликлиники (для списка)
    edit_select_item = State()          # выбор записи из списка
    edit_choose_field = State()         # карточка записи + кнопки полей
    edit_entering_field = State()       # ввод нового значения поля

    # --- Импорт из Excel (только админ) ---
    admin_import_waiting_file = State()

    # --- Аудиторский фильтр (только админ) ---
    audit_select_category = State()

    # --- Админка (без изменений) ---
    admin_view_count = State()
    admin_delete_id = State()
    admin_delete_inv = State()

    # --- Создание АРМ (выбор поликлиники) ---
    admin_arm_select_clinic = State()
