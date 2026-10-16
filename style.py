#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeatherCast 73.76 — единый стиль (Fusion + QSS), тёмная тема.

Палитра снята с референса (magick, PNG 848x1264): фон окна — тёплый
почти-чёрный #1E1E1C, карточки #282826, поля #2C2C2B, текст светлый
#E9E9E5/#9B9B95. Два акцента как в референсе: фиолетово-синий #5F5CC3
(основной) и зелёный #6CBA45 (успех); красный #C0564A — ошибка.
Глубина — фоном и отступами, рамки почти невидимы. Сетка 4/8 px.

Все цвета только здесь. Корневой виджет помечен objectName="root" и несёт
фон окна; остальные контейнеры прозрачны — иначе внутри карточек появляется
двухцветие.
"""

from string import Template

COLORS = {
    "BG_WINDOW":    "#1E1E1C",
    "BG_PANEL":     "#282826",
    "BG_FIELD":     "#2C2C2B",
    "BG_ALT":       "#232321",
    "BG_HOVER":     "#33332F",
    "BG_PRESSED":   "#3C3C38",
    "TEXT_PRIMARY": "#E9E9E5",
    "TEXT_SECOND":  "#9B9B95",
    "TEXT_DISABLED":"#5F5F5A",
    "BORDER":       "#35352F",
    "BORDER_HOVER": "#45453E",
    "ACCENT":       "#5F5CC3",
    "ACCENT_HOVER": "#7270D6",
    "ACCENT_TEXT":  "#FFFFFF",
    "SUCCESS":      "#6CBA45",
    "SUCCESS_BG":   "#233018",
    "WARNING":      "#C9A227",
    "WARNING_BG":   "#332C13",
    "ERROR":        "#C0564A",
    "ERROR_BG":     "#331D1A",
    "NEUTRAL":      "#9B9B95",
    "NEUTRAL_BG":   "#2A2A28",
    "OFFLINE":      "#8FB08F",
}

_QSS = Template("""
/* фон окна несёт только корень; прочие контейнеры прозрачны */
#root { background: $BG_WINDOW; }
QWidget { color: $TEXT_PRIMARY; font-family: "Segoe UI"; font-size: 9pt; background: transparent; }

/* секция: плоская, отделена тонкой линией сверху (как в макете — без «карточек») */
QGroupBox {
    background: transparent;
    border: none;
    border-top: 1px solid $BORDER;
    border-radius: 0;
    margin-top: 22px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 0;
    top: 6px;
    padding: 0 0 6px 0;
    color: $TEXT_SECOND;
    font-weight: 600;
    font-size: 8pt;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* поля */
QLineEdit, QComboBox, QSpinBox {
    background: $BG_FIELD;
    border: 1px solid $BORDER;
    border-radius: 8px;
    padding: 0 10px;
    min-height: 30px;
    selection-background-color: $ACCENT;
    selection-color: $ACCENT_TEXT;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: $BORDER_HOVER; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: $ACCENT; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    color: $TEXT_DISABLED; background: $BG_ALT;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: $BG_PANEL;
    border: 1px solid $BORDER;
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: $BG_HOVER;
}

/* кнопки */
QPushButton {
    background: $BG_FIELD;
    border: 1px solid $BORDER;
    border-radius: 8px;
    padding: 0 14px;
    min-height: 30px;
    color: $TEXT_PRIMARY;
}
QPushButton:hover   { background: $BG_HOVER; border-color: $BORDER_HOVER; }
QPushButton:pressed { background: $BG_PRESSED; }
QPushButton:disabled { color: $TEXT_DISABLED; background: $BG_ALT; }

QPushButton#primary {
    background: $ACCENT;
    color: $ACCENT_TEXT;
    border: none;
    border-radius: 18px;
    font-weight: 700;
    min-height: 36px;
    padding: 0 22px;
}
QPushButton#primary:hover    { background: $ACCENT_HOVER; }
QPushButton#primary:disabled { background: $NEUTRAL_BG; color: $TEXT_DISABLED; }

QPushButton#del { border: none; background: transparent; color: $TEXT_SECOND; min-height: 22px; padding: 0 6px; }
QPushButton#del:hover { color: $ERROR; }

QPushButton#arr { border: none; background: transparent; padding: 0; min-height: 20px; }
QPushButton#arr:hover { background: $BG_HOVER; border-radius: 6px; }
QPushButton#arr:disabled { background: transparent; }

QPushButton[mode="cancel"] {
    background: $ERROR_BG; color: $ERROR; border: 1px solid $ERROR;
    border-radius: 8px; font-weight: 700; min-height: 34px;
}
QPushButton[mode="cancel"]:hover { background: #42241F; }

/* прогресс */
QProgressBar {
    background: $NEUTRAL_BG;
    border: none;
    border-radius: 8px;
    text-align: center;
    min-height: 34px;
    color: $TEXT_PRIMARY;
    font-weight: 600;
}
QProgressBar::chunk { background: $ACCENT; border-radius: 8px; }
QProgressBar[state="success"]::chunk { background: $SUCCESS; }
QProgressBar[state="warning"]::chunk { background: $WARNING; }
QProgressBar[state="error"]::chunk   { background: $ERROR; }
QProgressBar[state="work"]    { color: $ACCENT_TEXT; }
QProgressBar[state="success"] { color: #12210A; }
QProgressBar[state="warning"] { color: #221B08; }
QProgressBar[state="error"]   { color: #2A0F0C; }

/* журнал */
QTextEdit {
    background: $BG_FIELD;
    border: 1px solid $BORDER;
    border-radius: 8px;
    font-family: "Consolas";
    font-size: 8.5pt;
    padding: 8px;
    color: $TEXT_SECOND;
}

/* список слотов */
QListWidget {
    background: $BG_FIELD;
    border: 1px solid $BORDER;
    border-radius: 8px;
    outline: none;
    padding: 2px;
}
QListWidget::item:alternate { background: $BG_ALT; }

/* чекбокс со своим индикатором */
QCheckBox { background: transparent; spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid $BORDER_HOVER; background: $BG_FIELD; }
QCheckBox::indicator:hover { border-color: $ACCENT; }
QCheckBox::indicator:checked { background: $ACCENT; border-color: $ACCENT; image: none; }
QCheckBox::indicator:disabled { background: $BG_ALT; border-color: $BORDER; }

/* прокрутка */
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: $BG_PRESSED; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4A4A44; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QToolTip { background: $BG_PANEL; color: $TEXT_PRIMARY; border: 1px solid $BORDER; border-radius: 6px; padding: 6px 8px; }

/* статус-баннер: карточка с цветной рамкой по исходу (как в макете) */
#banner { background: $BG_PANEL; border: 1px solid $BORDER; border-radius: 10px; }
#banner[state="success"] { border-color: $SUCCESS; }
#banner[state="warning"] { border-color: $WARNING; }
#banner[state="error"]   { border-color: $ERROR; }
#banner[state="neutral"] { border-color: $BORDER; }

/* статусы */
QLabel { background: transparent; }
QLabel[state="success"] { color: $SUCCESS; }
QLabel[state="warning"] { color: $WARNING; }
QLabel[state="error"]   { color: $ERROR; }
QLabel[state="neutral"] { color: $NEUTRAL; }
QLabel[state="second"]  { color: $TEXT_SECOND; }
""").substitute(COLORS)


def apply_style(app):
    app.setStyle("Fusion")
    app.setStyleSheet(_QSS)


def color(name):
    return COLORS.get(name, "#000000")
