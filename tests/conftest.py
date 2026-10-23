# -*- coding: utf-8 -*-
"""Общая настройка тестов WeatherCast 73.76.

Qt-тесты не должны открывать окно: выставляем offscreen ДО импорта PySide6.
Путь к проекту добавляем первым, чтобы `import weather` брал файлы рядом.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
