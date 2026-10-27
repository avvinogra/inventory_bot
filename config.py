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

# ✅ Печать штрих-кодов вырезана. LABELS_DIR оставлен только на случай,
# если он используется внешними скриптами. Можно удалить, если не нужно.
LABELS_DIR = os.getenv("LABELS_DIR", "labels/")

# ============================================================
# FSM STORAGE — Redis (опционально)
# ============================================================
# Если REDIS_URL задан — бот использует Redis для хранения FSM-состояний.
# Это позволяет переживать перезапуски бота без потери текущего ввода
# пользователя. Если REDIS_URL не задан — используется MemoryStorage
# (состояния хранятся в оперативной памяти, при перезапуске бота — теряются).
#
# Пример для локального Redis на той же машине:
#   REDIS_URL=redis://localhost:6379/0
# Пример с паролем:
#   REDIS_URL=redis://:password@localhost:6379/0
# ============================================================
REDIS_URL = os.getenv("REDIS_URL", "").strip() or None

# ============================================================
# ВЕБ-ПАНЕЛЬ (web_app.py) — опционально
# ============================================================
# Если WEB_PANEL_PASSWORD задан — все страницы веб-панели защищены
# формой входа с cookie-сессией (8 часов, с httponly/samesite=strict).
# Поддерживаются два формата пароля:
#
#   1) bcrypt-хэш — рекомендуется. Начинается с $2a$, $2b$ или $2y$.
#      Сгенерировать хэш:  python web_app.py --hash-password
#      Пример: WEB_PANEL_PASSWORD=$2b$12$G7HbZ4QF...
#
#   2) plain text — для совместимости со старыми установками.
#      Пример: WEB_PANEL_PASSWORD=my_secret
#      ⚠️ Выводит предупреждение в лог при запуске. Используйте bcrypt.
#
# Если WEB_PANEL_PASSWORD не задан — панель открыта. Не используйте
# открытую панель на публичном сервере!
#
# WEB_PANEL_FORCE_HTTPS = True → cookie с флагом Secure + заголовок HSTS.
# Включайте, если панель доступна через HTTPS (напрямую или за reverse proxy).
# По умолчанию False (для localhost разработки).
# ============================================================
WEB_PANEL_PASSWORD = os.getenv("WEB_PANEL_PASSWORD", "").strip() or None
WEB_PANEL_HOST = os.getenv("WEB_PANEL_HOST", "127.0.0.1")
WEB_PANEL_PORT = int(os.getenv("WEB_PANEL_PORT", "5000"))
WEB_PANEL_FORCE_HTTPS = os.getenv("WEB_PANEL_FORCE_HTTPS", "").strip().lower() in ("1", "true", "yes", "on")

# ============================================================
# ПРОКСИ (если api.telegram.org заблокирован)
# ============================================================
# Поддерживаются 2 формата:
#   1) HTTP/HTTPS-прокси:       PROXY_URL=http://user:pass@proxy.local:8080
#   2) SOCKS5-прокси:           SOCKS5_PROXY=socks5://user:pass@1.2.3.4:1080
#                              (для SOCKS5 нужно установить aiohttp-socks)
# Если ни одна переменная не задана — бот идёт напрямую.
# ============================================================
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None
SOCKS5_PROXY = os.getenv("SOCKS5_PROXY", "").strip() or None

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
