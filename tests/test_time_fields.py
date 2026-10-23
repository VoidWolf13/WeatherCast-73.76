# -*- coding: utf-8 -*-
"""Поля ввода времени: часы и минуты.

Часы — 0–23, минуты — 0–59 вручную и шаг 15 по кругу стрелками.
Невозможные значения зажимаются к границе, мусор не меняет прежнее значение.
"""
import pytest
from PySide6.QtWidgets import QApplication

import weather_gui


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def hours(app):
    return weather_gui.HourSpin()


@pytest.fixture
def minutes(app):
    return weather_gui.MinuteSpin()


def type_into(spin, text, start):
    """Набрать текст в поле и применить его как по Enter."""
    spin.setValue(start)
    spin.lineEdit().setText(text)
    spin.interpretText()
    return spin.value()


@pytest.mark.parametrize("text,expected", [
    ("25", 23), ("99", 23), ("-1", 0), ("7", 7), ("0", 0), ("23", 23),
])
def test_hours_clamped(hours, text, expected):
    assert type_into(hours, text, 10) == expected


@pytest.mark.parametrize("text", ["abc", ""])
def test_hours_garbage_keeps_value(hours, text):
    assert type_into(hours, text, 10) == 10


@pytest.mark.parametrize("text,expected", [
    ("7", 7), ("07", 7), ("31", 31), ("59", 59), ("75", 59), ("-3", 0),
])
def test_minutes_exact_input(minutes, text, expected):
    """Ручной ввод не округляется к шагу 15 — нужно точное значение."""
    assert type_into(minutes, text, 30) == expected


@pytest.mark.parametrize("text", ["abc", ""])
def test_minutes_garbage_keeps_value(minutes, text):
    assert type_into(minutes, text, 30) == 30


@pytest.mark.parametrize("start,direction,times,expected", [
    (0, 1, 5, [15, 30, 45, 0, 15]),
    (45, 1, 2, [0, 15]),
    (0, -1, 2, [45, 30]),
    (31, 1, 2, [45, 0]),
    (31, -1, 2, [30, 15]),
    (59, 1, 2, [0, 15]),
    (59, -1, 1, [45]),
])
def test_minutes_arrow_step_cycles(minutes, start, direction, times, expected):
    """Стрелки идут 00 → 15 → 30 → 45 → 00 независимо от ручного значения."""
    minutes.setValue(start)
    got = []
    for _ in range(times):
        minutes.stepBy(direction)
        got.append(minutes.value())
    assert got == expected
