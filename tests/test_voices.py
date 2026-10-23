# -*- coding: utf-8 -*-
"""Выбор голосов: человеческие подписи и портативная модель Piper.

config.json должен переживать перенос папки на другую машину: там хранится
имя файла модели, а не абсолютный путь. Старые конфиги с Windows-путём
(`C:\\Users\\...\\ru_RU-ruslan-medium.onnx`) тоже должны читаться.
"""
import os

import pytest

import weather


VOICES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voices")


@pytest.mark.parametrize("value,expected", [
    ("ru_RU-denis-medium.onnx", "ru_RU-denis-medium.onnx"),
    ("ru_RU-irina-medium.onnx", "ru_RU-irina-medium.onnx"),
    (r"C:\Users\void\AppData\Local\WeatherCast-73.76\_internal\voices\ru_RU-ruslan-medium.onnx",
     "ru_RU-ruslan-medium.onnx"),
    ("/some/where/voices/ru_RU-dmitri-medium.onnx", "ru_RU-dmitri-medium.onnx"),
])
def test_resolve_piper_model_by_name(value, expected):
    got = weather.resolve_piper_model(value)
    assert got is not None
    assert os.path.basename(got) == expected


@pytest.mark.parametrize("value", ["", None, "нет-такого.onnx"])
def test_resolve_piper_model_missing(value):
    assert weather.resolve_piper_model(value) is None


def test_apply_config_accepts_portable_name():
    weather.PIPER_MODEL = None
    weather.apply_config({"synth": [{"name": "Piper", "enabled": True,
                                     "voice": "ru_RU-irina-medium.onnx"}]})
    try:
        assert weather.PIPER_MODEL is not None
        assert os.path.basename(weather.PIPER_MODEL) == "ru_RU-irina-medium.onnx"
        assert os.path.isabs(weather.PIPER_MODEL)
    finally:
        weather.PIPER_MODEL = None
