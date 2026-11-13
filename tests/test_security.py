"""Безопасность веб-панели: пароли, X-Forwarded-For, rate limit (юнит-уровень)."""

from unittest.mock import MagicMock

import bcrypt

import config
from web.security import (
    _check_rate_limit,
    _clear_attempts,
    _get_client_ip,
    _record_failed_login,
    verify_password,
)


# ============================================================
# ПАРОЛЬ
# ============================================================
def test_verify_password_bcrypt():
    stored = bcrypt.hashpw(b"secret123", bcrypt.gensalt(rounds=4)).decode()
    assert verify_password("secret123", stored) is True
    assert verify_password("wrong", stored) is False


def test_verify_password_plaintext_compat():
    """Plain text — для совместимости, сравнение constant-time."""
    assert verify_password("secret123", "secret123") is True
    assert verify_password("wrong", "secret123") is False


def test_verify_password_corrupted_hash_fails_closed():
    """Битый хэш — отказ, а не исключение на весь /login (fail-closed)."""
    assert verify_password("secret123", "$2b$12$garbagegarbagegarbage") is False


def test_verify_password_empty_inputs():
    assert verify_password("", "x") is False
    assert verify_password("x", "") is False


# ============================================================
# IP КЛИЕНТА (защита от спуфинга X-Forwarded-For)
# ============================================================
def _request(host: str, headers: dict) -> MagicMock:
    req = MagicMock()
    req.client.host = host
    req.headers = headers
    return req


def test_direct_client_cannot_spoof_xff():
    """Прямой (недоверенный) клиент с XFF получает свой IP — rate limit честен."""
    req = _request("203.0.113.7", {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert _get_client_ip(req) == "203.0.113.7"


def test_trusted_proxy_yields_rightmost_untrusted_hop():
    req = _request("127.0.0.1", {"X-Forwarded-For": "1.2.3.4, 203.0.113.9"})
    assert _get_client_ip(req) == "203.0.113.9"


def test_all_trusted_chain_takes_first_hop():
    req = _request("127.0.0.1", {"X-Forwarded-For": "127.0.0.2, 127.0.0.3"})
    assert _get_client_ip(req) == "127.0.0.2"


def test_trusted_proxy_x_real_ip():
    req = _request("127.0.0.1", {"X-Real-IP": "198.51.100.5"})
    assert _get_client_ip(req) == "198.51.100.5"


def test_no_headers_returns_direct_host():
    req = _request("10.1.2.3", {})
    assert _get_client_ip(req) == "10.1.2.3"


def test_default_trusted_proxies_is_loopback():
    assert any(str(net) == "127.0.0.0/8" for net in config.TRUSTED_PROXIES)


# ============================================================
# RATE LIMIT
# ============================================================
def test_rate_limit_blocks_after_five_failures(clean_rate_limit):
    ip = "203.0.113.99"
    for _ in range(5):
        assert _check_rate_limit(ip) is None
        _record_failed_login(ip)
    wait = _check_rate_limit(ip)
    assert isinstance(wait, int) and wait >= 1, "после 5 попыток — блок"


def test_rate_limit_cleared_after_success(clean_rate_limit):
    ip = "203.0.113.100"
    for _ in range(5):
        _record_failed_login(ip)
    _clear_attempts(ip)  # успешный вход сбрасывает счётчик
    assert _check_rate_limit(ip) is None
