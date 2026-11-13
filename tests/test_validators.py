"""Валидаторы IP/MAC — единые для бота и веб-формы (появились в фазе 1).

Раньше regex жили только в боте, а веб-форма редактирования принимала
любой мусор в поля IP/MAC. Эти тесты фиксируют общий контракт.
"""

import pytest

import validators


@pytest.mark.parametrize(
    "value",
    [
        "192.168.1.10",
        "0.0.0.0",  # нижняя граница октета
        "255.255.255.255",  # верхняя граница октета
        "10.0.0.1",
        " 10.0.0.2 ",  # пробелы вокруг обрезаются
        "",  # пустое значение — валидно (поле необязательное)
    ],
)
def test_valid_ip(value):
    assert validators.is_valid_ip(value)


@pytest.mark.parametrize(
    "value",
    [
        "999.1.1.1",  # октет > 255
        "256.0.0.1",
        "abc",
        "10.0.0",  # три октета
        "10.0.0.1.5",  # пять октетов
        "10.0.0.1/24",  # маска — не IP-адрес
        "-1.0.0.0",
    ],
)
def test_invalid_ip(value):
    assert not validators.is_valid_ip(value)


@pytest.mark.parametrize(
    "value",
    [
        "00:1A:2B:3C:4D:5E",  # двоеточия
        "00-1A-2B-3C-4D-5E",  # дефисы
        "001A2B3C4D5E",  # слитно
        "ff:ff:ff:ff:ff:ff",  # нижний регистр
        " 00:1A:2B:3C:4D:5E ",  # пробелы вокруг
        "",
    ],
)
def test_valid_mac(value):
    assert validators.is_valid_mac(value)


@pytest.mark.parametrize(
    "value",
    [
        "00:1A:2B",  # не 6 пар
        "gg:1A:2B:3C:4D:5E",  # не hex
        "00:1A:2B:3C:4D",  # 5 пар
        "00:1a:2b:3c:4d:5e:6f",  # 7 пар
        "00 1A 2B 3C 4D 5E",  # пробелы-разделители не поддерживаются
    ],
)
def test_invalid_mac(value):
    assert not validators.is_valid_mac(value)
