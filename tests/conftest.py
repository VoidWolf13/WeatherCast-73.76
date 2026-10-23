# -*- coding: utf-8 -*-
"""Общая настройка тестов WeatherCast 73.76.

Qt-тесты не должны открывать окно: выставляем offscreen ДО импорта PySide6.
Путь к проекту добавляем первым, чтобы `import weather` брал файлы рядом.
"""
import os
import sys
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ранний журнал пишется при импорте weather (до любых фикстур), поэтому
# каталог задаём здесь же — иначе каждая сессия pytest оставляет строку
# «=== старт ===» в боевом weather.log проекта.
_state_dir = os.path.join(tempfile.gettempdir(), "wtts-test-state")
os.makedirs(_state_dir, exist_ok=True)
os.environ["WEATHER_LOG_DIR"] = _state_dir

@pytest.fixture(autouse=True)
def isolated_state(tmp_path_factory, monkeypatch):
    """Ни один тест не должен писать в боевой weather.log и runstate.json.

    Раньше тесты падений/путей журналировали прямо в каталог проекта —
    после прогона в боевом журнале появлялись строки вида
    `[runstate] не удалось записать /tmp/pytest-of-void/...`, и настоящая
    история эфира тонула в мусоре. Теперь состояние по умолчанию уводится
    во временный каталог; тест может переопределить путь, если проверяет
    именно его.
    """
    import weather

    d = tmp_path_factory.mktemp("state")
    monkeypatch.setattr(weather, "RUNSTATE", str(d / "runstate.json"))
    monkeypatch.setattr(weather, "LOG_FILE", str(d / "weather.log"))


@pytest.fixture(scope="session")
def qapp():
    """Один QApplication на весь прогон: второй экземпляр Qt не разрешает."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import style
    style.apply_style(app)
    return app
