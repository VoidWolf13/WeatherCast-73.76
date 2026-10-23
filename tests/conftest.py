# -*- coding: utf-8 -*-
"""Общая настройка тестов WeatherCast 73.76.

Qt-тесты не должны открывать окно: выставляем offscreen ДО импорта PySide6.
Путь к проекту добавляем первым, чтобы `import weather` брал файлы рядом.
"""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(scope="session")
def qapp():
    """Один QApplication на весь прогон: второй экземпляр Qt не разрешает."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import style
    style.apply_style(app)
    return app
