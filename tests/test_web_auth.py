"""Веб-панель под паролем: логин, rate limit, CSRF, закрытые страницы."""

import re

import bcrypt
import pytest
from fastapi.testclient import TestClient

import config
import database as db

PASSWORD = "secret123"
# rounds=4 — чтобы bcrypt не тормозил тесты; продакшен-хэши используют 12
PASSWORD_HASH = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def protected_client(db_path, monkeypatch, clean_rate_limit):
    """TestClient панели, закрытой bcrypt-паролем."""
    import web_app

    monkeypatch.setattr(config, "WEB_PANEL_PASSWORD", PASSWORD_HASH)
    with TestClient(web_app.app, raise_server_exceptions=False) as c:
        yield c


def _login(client, password: str):
    return client.post("/login", data={"password": password}, follow_redirects=False)


def _csrf_token(client) -> str:
    """CSRF-токен из meta-тега авторизованной страницы."""
    html = client.get("/").text
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    assert match, "авторизованная страница обязана содержать CSRF-токен"
    return match.group(1)


# ============================================================
# ЗАКРЫТЫЕ СТРАНИЦЫ
# ============================================================
def test_pages_redirect_to_login_when_protected(protected_client):
    response = protected_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")


def test_login_form_renders(protected_client):
    response = protected_client.get("/login")
    assert response.status_code == 200
    assert "пароль" in response.text.lower()


def test_api_docs_requires_auth(protected_client):
    response = protected_client.get("/api/docs", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")


# ============================================================
# ЛОГИН
# ============================================================
def test_login_wrong_password(protected_client):
    response = _login(protected_client, "wrong")
    assert response.status_code == 401
    assert "Неверный пароль" in response.text


def test_login_success_opens_panel(protected_client):
    assert _login(protected_client, PASSWORD).status_code == 303
    assert protected_client.get("/").status_code == 200


def test_login_rate_limit(protected_client):
    """5 неудач → блок на 5 минут, дальше 429 даже с верным паролем."""
    for _ in range(5):
        assert _login(protected_client, "wrong").status_code == 401

    blocked = _login(protected_client, "wrong")
    assert blocked.status_code == 429
    assert "Слишком много попыток" in blocked.text

    # Rate limit проверяется ДО пароля — верный пароль тоже блокируется
    assert _login(protected_client, PASSWORD).status_code == 429


def test_login_success_resets_rate_limit(protected_client):
    for _ in range(4):
        _login(protected_client, "wrong")
    assert _login(protected_client, PASSWORD).status_code == 303
    # после успешного входа счётчик сброшен
    for _ in range(4):
        assert _login(protected_client, "wrong").status_code == 401


# ============================================================
# CSRF
# ============================================================
def test_post_requires_csrf_when_protected(protected_client):
    """После входа POST без/с неверным CSRF-токеном → 403."""
    item_id = db.save_item("1пл", {"cabinet": "1", "tech": "PC", "inv": "CSRF-1"})
    assert _login(protected_client, PASSWORD).status_code == 303

    response = protected_client.delete(f"/delete/{item_id}")
    assert response.status_code == 403
    assert db.get_item_by_id(item_id) is not None

    response = protected_client.delete(f"/delete/{item_id}", headers={"X-CSRF-Token": "forged"})
    assert response.status_code == 403
    assert db.get_item_by_id(item_id) is not None


def test_post_with_valid_csrf_succeeds(protected_client):
    item_id = db.save_item("1пл", {"cabinet": "1", "tech": "PC", "inv": "CSRF-2"})
    assert _login(protected_client, PASSWORD).status_code == 303

    token = _csrf_token(protected_client)
    response = protected_client.delete(f"/delete/{item_id}", headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    assert db.get_item_by_id(item_id) is None


def test_htmx_request_gets_401_not_redirect(protected_client):
    """HTMX-запросы получают 401 для JS-обработки, а не 303-редирект."""
    response = protected_client.get("/", headers={"Hx-Request": "true"})
    assert response.status_code == 401
