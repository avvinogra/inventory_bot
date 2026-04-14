import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

ALLOWED_CHAT_IDS = [
    int(x.strip()) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
]

ADMIN_CHAT_IDS = [
    int(x.strip()) for x in os.getenv("ADMIN_CHAT_IDS", "").split(",") if x.strip()
]

DB_PATH = os.getenv("DB_PATH", "data/inventory.db")
LABELS_DIR = os.getenv("LABELS_DIR", "labels/")

# Список поликлиник
CLINICS = {
    '10пл': '10 Поликлиника',
    'ДЦ': 'Диагностический центр',
    '1пл': '1 Поликлиника',
    '2пл': '2 Поликлиника',
    '3пл': '3 Поликлиника',
    '4пл': '4 Поликлиника',
    'ЦМР': 'Центр медицинской реабилитации',
    'Травмпункт': 'Травмпункт',
    'Дарвина': 'Дарвина'
}

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(LABELS_DIR, exist_ok=True)