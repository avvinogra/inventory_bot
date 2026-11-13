"""Конфигурация: парсинг переменных окружения при импорте.

config.py читает env один раз при импорте, поэтому проверки краевых
случаев запускаются в ПОДПРОЦЕССЕ с собственным набором переменных.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

import config  # noqa: E402 — импорт после настройки env в conftest


def _run_config_snippet(env_overrides: dict, code: str, cwd: Path) -> subprocess.CompletedProcess:
    """Запускает `python -c code` с подменёнными переменными окружения."""
    env = {
        "DB_PATH": "",  # нейтрализуем возможный локальный .env
        "ADMIN_CHAT_IDS": "",
        "ALLOWED_CHAT_IDS": "",
        "BOT_TOKEN": "",
        "WEB_PANEL_PASSWORD": "",
        "PYTHONPATH": str(PROJECT_ROOT),
        **env_overrides,
    }
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_db_path_without_directory_does_not_crash(tmp_path):
    """Регрессия фазы 0: DB_PATH=inventory.db ронял os.makedirs("")."""
    result = _run_config_snippet(
        {"DB_PATH": "inventory.db"},
        "import config; assert config.DB_PATH == 'inventory.db'; print('OK')",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr


def test_trusted_proxies_default_is_loopback():
    """По умолчанию доверяем только loopback — спуфинг XFF снаружи закрыт."""
    assert any(str(net) == "127.0.0.0/8" for net in config.TRUSTED_PROXIES)


def test_trusted_proxies_invalid_entries_ignored(tmp_path):
    """Некорректные записи пропускаются с предупреждением, валидные работают."""
    result = _run_config_snippet(
        {"TRUSTED_PROXIES": "10.0.0.0/8, не-адрес-вовсе, 192.168.1.5"},
        "import config\n"
        "nets = sorted(str(n) for n in config.TRUSTED_PROXIES)\n"
        "assert nets == ['10.0.0.0/8', '192.168.1.5/32'], nets\n"
        "print('OK')",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "некорректное значение" in result.stdout.lower()


def test_admin_ids_parsed_from_env(tmp_path):
    result = _run_config_snippet(
        {"ADMIN_CHAT_IDS": "111, 222,333", "ALLOWED_CHAT_IDS": "444"},
        "import config\n"
        "assert config.ADMIN_CHAT_IDS == [111, 222, 333]\n"
        "assert config.ALLOWED_CHAT_IDS == [444]\n"
        "print('OK')",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr


def test_clinics_are_configured():
    """CLINICS — основа маппинга листов Excel и кнопок бота: не пуст и уникален."""
    assert len(config.CLINICS) > 0
    codes = [c.lower() for c in config.CLINICS]
    assert len(codes) == len(set(codes)), "коды поликлиник должны быть уникальны"
