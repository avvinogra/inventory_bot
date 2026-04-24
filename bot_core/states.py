from aiogram.fsm.state import State, StatesGroup


class InventoryForm(StatesGroup):
    selecting_clinic = State()
    selecting_tech_type = State()
    entering_cabinet = State()
    entering_tech = State()
    entering_serial = State()
    entering_inv = State()
    entering_ip = State()
    entering_mac = State()
    entering_os = State()
    entering_drweb = State()
    entering_office = State()
    entering_note = State()
    confirming_save = State()
    waiting_for_inv_print = State()
    admin_view_count = State()
    admin_delete_id = State()
    admin_delete_inv = State()

