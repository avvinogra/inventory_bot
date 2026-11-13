"""Веб-панель: HTML-страницы, JSON API, экспорт, единый UPDATE (панель открыта)."""

import os
import time

import config
import database as db

VALID_FORM = {
    "clinic": "2пл",
    "cabinet": "56",
    "tech_type": "printer",
    "tech": "New Tech",
    "inv_number": "UPD-1",
    "serial": "S1",
    "os": "",
    "drweb": "",
    "ip": "10.0.0.10",
    "pc_name": "PC1",
    "mac_phys": "00:11:22:33:44:55",
    "mac_real": "00:11:22:33:44:55",
    "specs": "спецификации",
    "note": "",
}


def _add_item(**extra) -> int:
    data = {"cabinet": "55", "tech": "Old", "inv": "UPD-1", "ip": "10.0.0.9"}
    data.update(extra)
    return db.save_item("1пл", data)


# ============================================================
# СТРАНИЦЫ
# ============================================================
def test_dashboard_renders(client):
    _add_item()
    response = client.get("/")
    assert response.status_code == 200
    assert "Инвентаризация" in response.text or "Дашборд" in response.text


def test_inventory_page_renders(client):
    _add_item()
    response = client.get("/inventory")
    assert response.status_code == 200
    assert "UPD-1" in response.text


def test_audit_page_renders(client):
    _add_item()
    response = client.get("/audit")
    assert response.status_code == 200


def test_item_detail_renders_with_context_selects(client):
    """Селекты Dr.Web/ОС приходят из bot_core.constants, а не из шаблона."""
    _add_item(tech_type="pc", drweb="Установлен", os="РЕД ОС 7.3")
    response = client.get("/item/1")
    assert response.status_code == 200
    assert 'value="Установлен"' in response.text
    assert "РЕД ОС 7.3" in response.text


def test_item_detail_missing_returns_404(client):
    assert client.get("/item/99999").status_code == 404


def test_security_headers_present(client):
    response = client.get("/health")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in response.headers
    # HSTS не включается без FORCE_HTTPS (default False — localhost-разработка)
    assert "Strict-Transport-Security" not in response.headers


# ============================================================
# HEALTHCHECK
# ============================================================
def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_health_degraded_when_db_unavailable(client, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", "/nonexistent_dir_xyz/inventory.db")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


# ============================================================
# JSON API
# ============================================================
def test_api_stats(client):
    _add_item()
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.json()["total_items"] >= 1


def test_api_items_search_filter(client):
    _add_item(tech="Dell OptiPlex")
    _add_item(tech="HP LaserJet", inv="UPD-2")
    response = client.get("/api/items", params={"search": "OptiPlex"})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["tech"] == "Dell OptiPlex"


def test_api_item_by_id_and_404(client):
    item_id = _add_item()
    assert client.get(f"/api/items/{item_id}").status_code == 200
    assert client.get("/api/items/99999").status_code == 404


def test_api_audit_category(client):
    _add_item(tech_type="pc", ip="")
    response = client.get("/api/audit/no_ip")
    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "no_ip"
    assert body["count"] == 1
    assert len(body["items"]) == 1


def test_api_audit_unknown_category_400(client):
    assert client.get("/api/audit/no_such").status_code == 400


# ============================================================
# ЭКСПОРТ
# ============================================================
def test_export_returns_xlsx_and_cleans_temp_file(client, monkeypatch):
    """Файл отдаётся клиенту и удаляется после отдачи (фаза 0)."""
    import tempfile as tempfile_module

    _add_item()
    captured = {}
    real_mkstemp = tempfile_module.mkstemp

    def spying_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        captured["path"] = path
        return fd, path

    monkeypatch.setattr(tempfile_module, "mkstemp", spying_mkstemp)

    response = client.get("/export")

    assert response.status_code == 200
    assert response.content[:2] == b"PK", "это zip/xlsx-магия"
    assert "spreadsheetml" in response.headers["content-type"]
    # BackgroundTask удаляет файл после отдачи; даём короткий запас на надёжность
    for _ in range(20):
        if captured["path"] and not os.path.exists(captured["path"]):
            break
        time.sleep(0.05)
    assert not os.path.exists(captured["path"]), "временный файл должен быть удалён"


# ============================================================
# АРМ ЧЕРЕЗ ВЕБ
# ============================================================
def test_arm_create_via_web(client):
    ids = [_add_item(tech=f"PC-{i}") for i in range(2)]
    response = client.post("/arm/create", data={"item_ids": [str(i) for i in ids]})
    assert response.status_code in (200, 303, 307)
    arms = db.get_all_arms()
    assert len(arms) == 1 and arms[0]["count"] == 2


# ============================================================
# ЕДИНЫЙ UPDATE (фаза 1)
# ============================================================
def test_update_item_single_query_changes_all_fields(client):
    item_id = _add_item()
    response = client.post(f"/update/{item_id}", data=VALID_FORM, follow_redirects=False)
    assert response.status_code == 303

    updated = db.get_item_by_id(item_id)
    assert updated["clinic"] == "2пл"
    assert updated["cabinet"] == "56"
    assert updated["tech_type"] == "printer"
    assert updated["tech"] == "New Tech"
    assert updated["ip"] == "10.0.0.10"
    assert updated["specs"] == "спецификации"


def test_update_item_invalid_ip_mac_rejected_without_db_change(client):
    """400 + баннер ошибок + введённые данные сохранены, БД не тронута."""
    item_id = _add_item()
    form = dict(VALID_FORM, ip="не-ip", mac_phys="gg:00")
    response = client.post(f"/update/{item_id}", data=form, follow_redirects=False)

    assert response.status_code == 400
    assert "Исправьте ошибки" in response.text
    assert "Неверный формат IP" in response.text
    # Данные не тронуты: валидное значение из БД осталось прежним
    assert db.get_item_by_id(item_id)["ip"] == "10.0.0.9"


def test_delete_item_via_web(client):
    item_id = _add_item()
    response = client.delete(f"/delete/{item_id}")
    assert response.status_code == 200
    assert db.get_item_by_id(item_id) is None
