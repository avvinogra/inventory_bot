"""Безопасность веб-панели: bcrypt, rate limit, CSRF, сессии, IP клиента."""

import ipaddress
import secrets
import time
import warnings
from collections import defaultdict

import bcrypt
from fastapi import HTTPException, Request, status

import config


# ============================================================
# ПАРОЛЬ (BCRYPT)
# ============================================================
def verify_password(plain: str, stored: str) -> bool:
    """Сравнивает введённый пароль с хранимым значением.

    Поддерживает:
    - bcrypt-хэш (начинается с $2a$, $2b$, $2y$) — рекомендуется
    - plain text (для совместимости — выводит warning при запуске)
    """
    if not plain or not stored:
        return False
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
        except (ValueError, TypeError):
            # битый/некорректный хэш — вход запрещён (fail-closed)
            return False
    # Plain text — для совместимости (используем constant-time comparison)
    return secrets.compare_digest(plain, stored)


def _warn_plain_password():
    """Выводит предупреждение, если WEB_PANEL_PASSWORD — plain text."""
    if not config.WEB_PANEL_PASSWORD:
        return
    if not config.WEB_PANEL_PASSWORD.startswith(("$2a$", "$2b$", "$2y$")):
        warnings.warn(
            "⚠️ WEB_PANEL_PASSWORD хранится в открытом виде (plain text). "
            "Сгенерируйте bcrypt-хэш: python web_app.py --hash-password — "
            "и пропишите его в .env. Это защитит пароль при утечке .env.",
            stacklevel=2,
        )


_warn_plain_password()


# ============================================================
# RATE LIMITING НА /login
# ============================================================
# Хранилище в памяти: {ip: [timestamp, timestamp, ...]}
# При перезапуске процесса сбрасывается — для production лучше Redis,
# но для внутреннего использования этого достаточно.
_login_attempts: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 60  # секунд: 5 попыток за 60 сек
RATE_LIMIT_BLOCK = 300  # 5 минут блокировки после превышения


def _get_client_ip(request: Request) -> str:
    """IP клиента для rate limiting — с защитой от подделки X-Forwarded-For.

    Раньше заголовку X-Forwarded-For верили безусловно: любой клиент
    с прямым доступом к панели мог прислать X-Forwarded-For: 1.2.3.4
    и получать «свежий» IP на каждую попытку входа — rate limit
    на 5 попыток не работал.

    Теперь заголовки прокси учитываются ТОЛЬКО если запрос пришёл
    от доверенного прокси (config.TRUSTED_PROXIES). При этом берём
    крайний правый НЕ-доверенный адрес из цепочки — его дописал наш
    прокси, подделать его клиент не мог.
    """
    direct = request.client.host if request.client else "unknown"

    def _is_trusted(addr: str) -> bool:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        return any(ip in net for net in config.TRUSTED_PROXIES)

    if _is_trusted(direct):
        xff = request.headers.get("X-Forwarded-For", "")
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        for hop in reversed(hops):
            if not _is_trusted(hop):
                return hop
        if hops:
            return hops[0]  # вся цепочка — наши прокси
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip
    return direct


def _check_rate_limit(ip: str) -> int | None:
    """Проверяет, можно ли ещё пытаться войти.
    Возвращает None, если можно. Иначе — сколько секунд до разблокировки.
    """
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    # Чистим старые записи (старше RATE_LIMIT_BLOCK)
    _login_attempts[ip] = [t for t in attempts if now - t < RATE_LIMIT_BLOCK]
    attempts = _login_attempts[ip]

    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        oldest = attempts[0]
        wait = int(RATE_LIMIT_BLOCK - (now - oldest))
        return max(wait, 1)
    return None


def _record_failed_login(ip: str):
    _login_attempts[ip].append(time.time())


def _clear_attempts(ip: str):
    _login_attempts.pop(ip, None)


# ============================================================
# CSRF-ТОКЕНЫ
# ============================================================
def _get_csrf_token(request: Request) -> str:
    """Получает CSRF-токен из сессии. Если нет — генерирует новый."""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        request.session["csrf_token"] = token
    return token


async def csrf_protect(request: Request):
    """Зависимость для POST/DELETE/PATCH эндпоинтов.
    Проверяет CSRF-токен в заголовке X-CSRF-Token (HTMX) или в форме (csrf_token).
    """
    if not config.WEB_PANEL_PASSWORD:
        return  # авторизация не нужна — CSRF не нужен

    expected = request.session.get("csrf_token")
    if not expected:
        raise HTTPException(status_code=403, detail="CSRF-токен не найден в сессии")

    token = request.headers.get("X-CSRF-Token")
    if not token:
        # Пытаемся достать из form data (для обычных POST-форм)
        try:
            form = await request.form()
            token = form.get("csrf_token")
        except Exception:  # noqa: BLE001 — чтение form data не критично
            token = None  # для CSRF-проверки: нет токена = отказ

    if not token or not secrets.compare_digest(str(token), str(expected)):
        raise HTTPException(status_code=403, detail="Неверный CSRF-токен")


# ============================================================
# АВТОРИЗАЦИЯ
# ============================================================
def is_authenticated(request: Request) -> bool:
    """Проверяет, авторизован ли пользователь в текущей сессии."""
    if not config.WEB_PANEL_PASSWORD:
        return True  # пароль не задан — панель открыта
    return bool(request.session.get("authed"))


def require_auth(request: Request):
    """Если не авторизован — выбрасывает 401 / редирект на /login."""
    if not is_authenticated(request):
        # Для HTMX-запросов (Hx-Request: true) — отдаём 401, чтобы JS показал логин
        if request.headers.get("Hx-Request") == "true":
            raise HTTPException(status_code=401, detail="Требуется авторизация")
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
