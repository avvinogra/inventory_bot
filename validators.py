"""Общие валидаторы пользовательского ввода.

Единое место проверки IP/MAC для бота (handlers/inventory/fields.py)
и веб-панели (web/). Раньше regex жили только в боте,
а веб-форма редактирования принимала любой мусор в полях IP/MAC.
"""

import re

# IPv4: четыре октета 0-255 через точку.
IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
)

# MAC: AA:BB:CC:DD:EE:FF | AA-BB-CC-DD-EE-FF | AABBCCDDEEFF
MAC_RE = re.compile(
    r"^([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2})$"
    r"|^([0-9A-Fa-f]{2}[-]){5}([0-9A-Fa-f]{2})$"
    r"|^[0-9A-Fa-f]{12}$"
)


def is_valid_ip(text: str) -> bool:
    """True, если текст — корректный IPv4-адрес (или пустая строка)."""
    if not text:
        return True
    return bool(IP_RE.match(text.strip()))


def is_valid_mac(text: str) -> bool:
    """True, если текст — корректный MAC (или пустая строка)."""
    if not text:
        return True
    return bool(MAC_RE.match(text.strip()))
