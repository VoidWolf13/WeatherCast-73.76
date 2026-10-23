#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeatherCast 73.76 — единый стиль (Fusion + QSS), тёмная тема.

Палитра снята с референса 23.10.2026 (magick, 564x942):
фон #232324, панели/карточки темнее и чуть светлее, акценты — индиго
#817DD1/#6864BE, зелёный #7BB946, оранжевый #F7980E, жёлтый #FBD40D,
	красный #F5503A. Принцип референса: тёмное полотно, карточки-панели с
мягким скруглением, крупные цифры-метрики, цвет — только как сигнал
(полоса карточки, подпись, прогресс), а не как украшение.

Все цвета только здесь. Корневой виджет помечен objectName="root" и несёт
фон окна; остальные контейнеры прозрачны.
"""

import os
import sys
from string import Template


def _icon(name):
    """Абсолютный путь к PNG-иконке: рядом со скриптом или в _MEIPASS сборки."""
    for base in (os.path.dirname(os.path.abspath(__file__)),
                 getattr(sys, "_MEIPASS", "")):
        if not base:
            continue
        p = os.path.join(base, "assets", "icons", name)
        if os.path.exists(p):
            return p.replace("\\", "/")
    return ""

COLORS = {
    "BG_WINDOW":    "#1B1B1D",
    "BG_PANEL":     "#232326",
    "BG_FIELD":     "#2B2B2F",
    "BG_ALT":       "#202023",
    "BG_HOVER":     "#34343A",
    "BG_PRESSED":   "#3C3C43",
    "TEXT_PRIMARY": "#EDEDF2",
    "TEXT_SECOND":  "#9A9AA3",
    "TEXT_DISABLED":"#5E5E66",
    "BORDER":       "#303035",
    "BORDER_HOVER": "#414148",
    "ACCENT":       "#817DD1",
    "ACCENT_HOVER": "#928EE0",
    "ACCENT_TEXT":  "#FFFFFF",
    "SUCCESS":      "#7BB946",
    "SUCCESS_BG":   "#233018",
    "WARNING":      "#F7980E",
    "WARNING_BG":   "#33280F",
    "ERROR":        "#F5503A",
    "ERROR_BG":     "#331B17",
    "NEUTRAL":      "#9A9AA3",
    "NEUTRAL_BG":   "#2B2B2F",
    "OFFLINE":      "#A3C051",
}

_QSS = Template("""
/* фон окна несёт только корень */
#root { background: $BG_WINDOW; border: 1px solid $WARNING; }
QWidget { color: $TEXT_PRIMARY; font-family: "Segoe UI"; font-size: 9pt; background: transparent; }

/* ---- KPI-карточки (главный уровень иерархии, как в референсе) ---- */
#card { background: $BG_PANEL; border: 1px solid $BORDER; border-left: 3px solid $BORDER; border-radius: 10px; }
#card[state="success"] { border-left-color: $SUCCESS; }
#card[state="warning"] { border-left-color: $WARNING; }
#card[state="error"]   { border-left-color: $ERROR; }
#card[state="info"]    { border-left-color: $ACCENT; }
QLabel#cardTitle { color: $TEXT_SECOND; font-size: 7.5pt; font-weight: 700; }
QLabel#cardValue { color: $TEXT_PRIMARY; font-size: 19pt; font-weight: 700; }
QLabel#cardSub   { color: $TEXT_SECOND; font-size: 8pt; }

/* ---- секции-панели ---- */
QGroupBox {
    background: $BG_PANEL;
    border: 1px solid $BORDER;
    border-radius: 10px;
    margin-top: 0;
}
QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 12px;
    top: 8px;
    padding: 0;
    color: $TEXT_SECOND;
    font-weight: 700;
    font-size: 7.5pt;
}

/* ---- поля ---- */
QLineEdit, QComboBox, QSpinBox {
    background: $BG_FIELD;
    border: 1px solid $BORDER;
    border-radius: 8px;
    padding: 0 10px;
    min-height: 28px;
    selection-background-color: $ACCENT;
    selection-color: $ACCENT_TEXT;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: $BORDER_HOVER; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: $ACCENT; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: $TEXT_DISABLED; background: $BG_ALT; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url("$ICON_DOWN"); width: 12px; height: 8px; }

/* QSpinBox: свои кнопки — иначе Fusion рисует невнятные прямоугольники */
QSpinBox { padding-right: 26px; }
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: 24px;
    background: transparent;
    border: none;
}
QSpinBox::up-button   { subcontrol-position: top right; }
QSpinBox::down-button { subcontrol-position: bottom right; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: $BG_HOVER; }
QSpinBox::up-arrow   { image: url("$ICON_UP"); width: 12px; height: 8px; }
QSpinBox::down-arrow { image: url("$ICON_DOWN"); width: 12px; height: 8px; }
QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled { image: none; }
QComboBox QAbstractItemView {
    background: $BG_PANEL; border: 1px solid $BORDER; border-radius: 8px;
    padding: 4px; outline: none; selection-background-color: $BG_HOVER;
}

/* ---- кнопки ---- */
QPushButton {
    background: $BG_FIELD;
    border: 1px solid $BORDER;
    border-radius: 8px;
    padding: 0 12px;
    min-height: 28px;
    color: $TEXT_PRIMARY;
}
QPushButton:hover   { background: $BG_HOVER; border-color: $BORDER_HOVER; }
QPushButton:pressed { background: $BG_PRESSED; }
QPushButton:disabled { color: $TEXT_DISABLED; background: $BG_ALT; }

QPushButton#primary {
    background: $ACCENT; color: $ACCENT_TEXT; border: none; border-radius: 9px;
    font-weight: 700; font-size: 10.5pt; padding: 0 20px;
}
QPushButton#primary:hover    { background: $ACCENT_HOVER; }
QPushButton#primary:disabled { background: $NEUTRAL_BG; color: $TEXT_DISABLED; }

QPushButton#del { border: none; background: transparent; color: $TEXT_SECOND; min-height: 22px; padding: 0 6px; }
QPushButton#del:hover { color: $ERROR; }

QPushButton#arr { border: none; background: transparent; padding: 0; min-height: 20px; }
QPushButton#arr:hover { background: $BG_HOVER; border-radius: 6px; }
QPushButton#arr:disabled { background: transparent; }

/* #primary специфичнее [mode], поэтому отмена перекрывается отдельно */
QPushButton[mode="cancel"],
QPushButton#primary[mode="cancel"] {
    background: $ERROR_BG; color: $ERROR; border: 1px solid $ERROR;
    border-radius: 9px; font-weight: 700; font-size: 10.5pt;
}
QPushButton[mode="cancel"]:hover,
QPushButton#primary[mode="cancel"]:hover { background: #42241F; }

/* ---- прогресс ---- */
QProgressBar {
    background: $BG_ALT; border: 1px solid $BORDER; border-radius: 9px;
    text-align: center; color: $TEXT_SECOND; font-weight: 600;
}
QProgressBar::chunk { background: $ACCENT; border-radius: 8px; }
QProgressBar[state="success"]::chunk { background: $SUCCESS; }
QProgressBar[state="warning"]::chunk { background: $WARNING; }
QProgressBar[state="error"]::chunk   { background: $ERROR; }
QProgressBar[state="work"]    { color: $TEXT_PRIMARY; }
QProgressBar[state="success"] { color: #12210A; }
QProgressBar[state="warning"] { color: #221B08; }
QProgressBar[state="error"]   { color: #2A0F0C; }

/* ---- журнал ---- */
QTextEdit {
    background: $BG_ALT; border: 1px solid $BORDER; border-radius: 8px;
    font-family: "Consolas"; font-size: 8.5pt; padding: 8px; color: $TEXT_SECOND;
}

/* ---- список слотов ---- */
QListWidget {
    background: $BG_ALT; border: 1px solid $BORDER; border-radius: 8px;
    outline: none; padding: 2px;
}
QListWidget::item:alternate { background: $BG_HOVER; }

/* ---- чекбокс ---- */
QCheckBox { background: transparent; spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid $BORDER_HOVER; background: $BG_FIELD; }
QCheckBox::indicator:hover { border-color: $ACCENT; }
QCheckBox::indicator:checked { background: $ACCENT; border-color: $ACCENT; image: none; }
QCheckBox::indicator:disabled { background: $BG_ALT; border-color: $BORDER; }

/* ---- прокрутка ---- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: $BG_PRESSED; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4A4A52; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QToolTip { background: $BG_PANEL; color: $TEXT_PRIMARY; border: 1px solid $BORDER; border-radius: 6px; padding: 6px 8px; }

/* ---- статусы текста ---- */
QLabel { background: transparent; }
QLabel[state="success"] { color: $SUCCESS; }
QLabel[state="warning"] { color: $WARNING; }
QLabel[state="error"]   { color: $ERROR; }
QLabel[state="neutral"] { color: $NEUTRAL; }
QLabel[state="second"]  { color: $TEXT_SECOND; }
""").substitute({**COLORS,
    "ICON_UP": _icon("chevron-up.png"),
    "ICON_DOWN": _icon("chevron-down.png"),
})


def apply_style(app):
    app.setStyle("Fusion")
    app.setStyleSheet(_QSS)


def color(name):
    return COLORS.get(name, "#000000")
