#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeatherCast 73.76 — интерфейс (PySide6/Qt).

Автор: AVAIM0013 (псевдоним).

Возможности (по docs/PLAN.md):
  • кнопка создания файла с индикатором работы;
  • выбор постоянного места сохранения ПОГОДА.wav;
  • порядок синтезаторов, голос для каждого, вкл/выкл;
  • расписание: несколько времён, вкл/выкл слота, повтор каждый день.

Настройки хранятся рядом со скриптом в config.json. Портативно.

Единый дизайн (Fusion + style.py, без тёмной темы). Модель статусов — по исходу
последнего запуска: success / warning (пропущен синтезатор) / error / neutral.
Статус-строка сверху, строки расписания с маркерами, журнал сворачиваемый.
"""

import os
import sys
import json
import datetime

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QSize
from PySide6.QtGui import (QDesktopServices, QFont, QShortcut, QKeySequence,
                           QColor, QPixmap, QPainter)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QComboBox, QCheckBox, QProgressBar, QFileDialog, QSpinBox,
    QGroupBox, QMessageBox, QTextEdit, QStyle, QFrame, QSizePolicy,
)

# BASE — каталог для записи (config.json, ПОГОДА.wav): рядом с exe в сборке.
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import weather  # noqa: E402
import style    # noqa: E402

CONFIG = os.path.join(BASE, "config.json")
EDGE_VOICES = ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"]
SYNTH_NAMES = ("Edge TTS", "gTTS", "Piper")
MINUTE_STEPS = ("00", "05", "10", "15", "20", "30", "45")

# ---- единая сетка (кратно 4 px) ------------------------------------------
PAD = 8          # внутренний отступ
GAP = 8          # промежуток между группами и отступы внутри групп
H = 28           # высота полей ввода
H_BAR = 32       # высота прогресса и главной кнопки
GB_TOP = 18      # верхний отступ внутри QGroupBox (под заголовок)
BTN_MIN_W = 88   # минимальная ширина кнопки
BTN_SQ = 24      # квадратная кнопка (▲▼)
ROW_H = 30       # высота строки расписания

# исход запуска → иконка состояния (цвет — из style.py)
STATE_ICON = {
    "success": QStyle.SP_DialogApplyButton,
    "warning": QStyle.SP_MessageBoxWarning,
    "error": QStyle.SP_MessageBoxCritical,
    "neutral": QStyle.SP_MessageBoxInformation,
}
COLOR_KEY = {"success": "SUCCESS", "warning": "WARNING",
             "error": "ERROR", "neutral": "NEUTRAL"}


def repolish(w):
    """Перечитать QSS после смены свойства виджета (state и т.п.)."""
    w.style().unpolish(w)
    w.style().polish(w)


def dot_pixmap(color, size=8):
    """Цветная точка-маркер для строки расписания."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(0, 0, size - 1, size - 1)
    p.end()
    return pm


DEFAULTS = {
    "out_file": os.path.join(BASE, "ПОГОДА.wav"),
    "synth": [
        {"name": "Edge TTS", "enabled": True, "voice": EDGE_VOICES[0]},
        {"name": "gTTS", "enabled": True, "voice": ""},
        {"name": "Piper", "enabled": True, "voice": ""},
    ],
    "schedule": [],
}


# ================================================================ worker
class Worker(QThread):
    done = Signal(str)
    fail = Signal(str)
    logline = Signal(str)

    def __init__(self, out_file, chain):
        super().__init__()
        self.out_file = out_file
        self.chain = chain

    def run(self):
        try:
            path = weather.run(out_file=self.out_file, chain=self.chain)
            self.done.emit(path)
        except Exception as e:  # noqa
            self.fail.emit(str(e))


# ================================================================ строка синтезатора
class SynthRow:
    """Виджеты одной строки синтезатора (раскладываются в общий QGridLayout)."""

    def __init__(self, name, options, current, enabled, badge, badge_color, on_move):
        self.name = name

        self.check = QCheckBox()
        self.check.setChecked(bool(enabled))
        self.check.setFixedWidth(24)

        self.label = QLabel(name)
        self.label.setFixedWidth(110)

        self.combo = QComboBox()
        for lab, val in options:
            self.combo.addItem(lab, val)
        idx = self.combo.findData(current)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.setEnabled(len(options) > 1)   # выбор только если есть из чего
        self.combo.setMinimumWidth(190)
        self.combo.setFixedHeight(H)

        self.badge = QLabel(badge)
        self.badge.setFixedWidth(64)
        if badge_color:
            self.badge.setStyleSheet("color: %s;" % badge_color)

        # ▲▼ — иконками: метрики глифов ▲/▼ разные, кнопки «плыли» по ширине
        sty = QApplication.style()
        self.up = QPushButton()
        self.up.setObjectName("arr")
        self.up.setIcon(sty.standardIcon(QStyle.SP_ArrowUp))
        self.up.setFixedSize(BTN_SQ, BTN_SQ)
        self.up.setToolTip("Выше приоритетом")
        self.up.clicked.connect(lambda: on_move(self, -1))

        self.down = QPushButton()
        self.down.setObjectName("arr")
        self.down.setIcon(sty.standardIcon(QStyle.SP_ArrowDown))
        self.down.setFixedSize(BTN_SQ, BTN_SQ)
        self.down.setToolTip("Ниже приоритетом")
        self.down.clicked.connect(lambda: on_move(self, 1))

        # обе кнопки — как один контрол «порядок»
        self.order = QWidget()
        ob = QHBoxLayout(self.order)
        ob.setContentsMargins(0, 0, 0, 0)
        ob.setSpacing(2)
        ob.addWidget(self.up)
        ob.addWidget(self.down)

    def voice(self):
        """Выбранный голос/модель (значение, а не подпись)."""
        return self.combo.currentData()


# ================================================================ строка расписания
class SchedRow(QWidget):
    """Строка слота: [✓] ● 06:00  ✓ статус  [×].

    Маркер (точка цвета исхода) + иконка + текст статуса; × — удалить.
    """

    def __init__(self, time_str, enabled):
        super().__init__()
        self.time_str = time_str
        self.setFixedHeight(ROW_H)
        h = QHBoxLayout(self)
        h.setContentsMargins(PAD, 0, PAD, 0)
        h.setSpacing(PAD)

        self.check = QCheckBox()
        self.check.setChecked(bool(enabled))
        self.check.setFixedWidth(24)

        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.dot.setPixmap(dot_pixmap(style.color("NEUTRAL")))

        self.tlabel = QLabel(time_str)
        tf = self.tlabel.font()
        tf.setPointSize(9)
        tf.setBold(True)
        self.tlabel.setFont(tf)
        self.tlabel.setFixedWidth(48)

        self.status = QLabel("")
        sf = self.status.font()
        sf.setPointSize(8)
        self.status.setFont(sf)

        self.btn_del = QPushButton("×")
        self.btn_del.setObjectName("del")
        self.btn_del.setFixedSize(22, 22)
        self.btn_del.setToolTip("Удалить время")

        h.addWidget(self.check)
        h.addWidget(self.dot)
        h.addWidget(self.tlabel)
        h.addWidget(self.status, 1)
        h.addWidget(self.btn_del)

    def set_outcome(self, kind, text):
        """kind: success / warning / error / neutral → цвет точки и текст статуса."""
        col = style.color(COLOR_KEY.get(kind, "NEUTRAL"))
        self.dot.setPixmap(dot_pixmap(col))
        self.status.setText(text)
        self.status.setProperty("state", kind)
        repolish(self.status)

    def enabled(self):
        return self.check.isChecked()


# ================================================================ окно
class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")   # несёт фон окна (см. style.py)
        self.setWindowTitle("WeatherCast 73.76")
        self.cfg = self.load_cfg()
        self.worker = None
        self._fired_slot = None

        self._build()
        self._apply_cfg()
        self._refresh_status()
        self._update_schedule_status()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.save_cfg)
        self._wire_autosave()

        QShortcut(QKeySequence("F5"), self, self.run_now)
        QShortcut(QKeySequence("Ctrl+O"), self, self.pick_out)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_schedule)
        self.timer.start(20000)          # раз в 20 с проверяем расписание

    # -------------------------------------------------- конфиг
    def load_cfg(self):
        if os.path.exists(CONFIG):
            try:
                with open(CONFIG, encoding="utf-8") as fh:
                    data = json.load(fh)
                for k, v in DEFAULTS.items():
                    data.setdefault(k, v)
                return data
            except Exception:  # noqa
                pass
        return json.loads(json.dumps(DEFAULTS))

    def save_cfg(self):
        self.cfg["out_file"] = self.out_edit.text()
        self.cfg["synth"] = [
            {"name": r.name,
             "enabled": r.check.isChecked(),
             "voice": r.voice() or ""}
            for r in self.rows
        ]
        self.cfg["schedule"] = [
            {"time": self._sched_row(i).time_str,
             "enabled": self._sched_row(i).enabled()}
            for i in range(self.sched.count())
        ]
        try:
            with open(CONFIG, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception:  # noqa
            pass

    def _touch(self):
        if hasattr(self, "_save_timer"):
            self._save_timer.start(500)

    def _wire_autosave(self):
        self.out_edit.textChanged.connect(self._touch)
        for r in self.rows:
            r.check.toggled.connect(self._touch)
            r.combo.currentIndexChanged.connect(self._touch)

    # -------------------------------------------------- сборка UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(GAP, GAP, GAP, GAP)
        root.setSpacing(6)

        # шапка приложения: название слева, версия справа (как в макете)
        head = QWidget()
        hh = QHBoxLayout(head)
        hh.setContentsMargins(0, 0, 0, 0)
        hh.setSpacing(PAD)
        self.app_title = QLabel(getattr(weather, "APP_NAME", "WeatherCast 73.76"))
        tf = self.app_title.font()
        tf.setPointSize(12)
        tf.setBold(True)
        self.app_title.setFont(tf)
        self.ver_chip = QLabel("v%s · %s" % (weather.VERSION, weather.STATUS))
        vf = self.ver_chip.font()
        vf.setPointSize(8)
        self.ver_chip.setFont(vf)
        self.ver_chip.setProperty("state", "second")
        repolish(self.ver_chip)
        hh.addWidget(self.app_title)
        hh.addStretch(1)
        hh.addWidget(self.ver_chip)
        root.addWidget(head)

        # статус-баннер: карточка с цветной рамкой по исходу (как в макете)
        self.banner = QWidget()
        self.banner.setObjectName("banner")
        self.banner.setProperty("state", "neutral")
        hb = QHBoxLayout(self.banner)
        hb.setContentsMargins(PAD + 2, PAD, PAD + 2, PAD)
        hb.setSpacing(PAD)
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(20, 20)
        self.status_text = QLabel("")
        self.status_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.next_label = QLabel("")
        nf = self.next_label.font()
        nf.setPointSize(8)
        self.next_label.setFont(nf)
        self.next_label.setStyleSheet("color: %s;" % style.color("TEXT_SECOND"))
        self.btn_open = QPushButton("Открыть папку")
        self.btn_open.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        self.btn_open.setIconSize(QSize(16, 16))
        self.btn_open.setMinimumWidth(140)
        self.btn_open.setFixedHeight(H)
        self.btn_open.clicked.connect(self.open_folder)
        hb.addWidget(self.status_icon)
        hb.addWidget(self.status_text, 1)
        hb.addWidget(self.next_label)
        hb.addWidget(self.btn_open)
        root.addWidget(self.banner)

        # файл погоды
        gb_out = QGroupBox("Файл погоды")
        hl = QHBoxLayout(gb_out)
        hl.setContentsMargins(GAP, GB_TOP, GAP, GAP)
        hl.setSpacing(PAD)
        self.out_edit = QLineEdit(self.cfg["out_file"])
        self.out_edit.setFixedHeight(H)
        self.out_edit.setMinimumWidth(240)
        self.out_edit.setToolTip(self.cfg["out_file"])
        btn = QPushButton("Выбрать…")
        btn.setFixedHeight(H)
        btn.setMinimumWidth(BTN_MIN_W)
        btn.clicked.connect(self.pick_out)
        hl.addWidget(self.out_edit, 1)
        hl.addWidget(btn)
        root.addWidget(gb_out)

        # синтезаторы
        gb_syn = QGroupBox("Синтезаторы")
        vs = QVBoxLayout(gb_syn)
        vs.setContentsMargins(GAP, GB_TOP, GAP, GAP)
        vs.setSpacing(PAD)
        self.syn_grid = QGridLayout()
        self.syn_grid.setContentsMargins(0, 0, 0, 0)
        self.syn_grid.setHorizontalSpacing(PAD)
        self.syn_grid.setVerticalSpacing(PAD)
        self.syn_grid.setColumnStretch(2, 1)
        vs.addLayout(self.syn_grid)
        hint = QLabel("Галочка — включить; ▲▼ — порядок; серый список — один голос.")
        hint.setWordWrap(True)
        hf = hint.font()
        hf.setPointSize(8)
        hint.setFont(hf)
        hint.setStyleSheet("color: %s;" % style.color("TEXT_SECOND"))
        vs.addWidget(hint)
        root.addWidget(gb_syn)

        # расписание
        gb_sch = QGroupBox("Расписание (ежедневно)")
        vs2 = QVBoxLayout(gb_sch)
        vs2.setContentsMargins(GAP, GB_TOP, GAP, GAP)
        vs2.setSpacing(PAD)

        # ручной ввод: часы + минуты отдельно (в QTimeEdit минуты неочевидны)
        entry = QHBoxLayout()
        entry.setSpacing(PAD)
        self.hh = QSpinBox()
        self.hh.setRange(0, 23)
        self.hh.setWrapping(True)
        self.hh.setFixedSize(56, H)
        self.hh.setAlignment(Qt.AlignCenter)
        self.mm = QComboBox()
        self.mm.setEditable(True)
        self.mm.addItems(MINUTE_STEPS)
        self.mm.setFixedSize(64, H)
        lbl_h = QLabel("ч")
        lbl_m = QLabel("мин")
        for lbl in (lbl_h, lbl_m):
            lbf = lbl.font()
            lbf.setPointSize(8)
            lbl.setFont(lbf)
            lbl.setStyleSheet("color: %s;" % style.color("TEXT_SECOND"))
        b_add = QPushButton("Добавить")
        b_add.setFixedHeight(H)
        b_add.setMinimumWidth(BTN_MIN_W)
        b_add.clicked.connect(self.add_time)
        entry.addWidget(self.hh)
        entry.addWidget(lbl_h)
        entry.addWidget(self.mm)
        entry.addWidget(lbl_m)
        entry.addStretch(1)
        entry.addWidget(b_add)
        vs2.addLayout(entry)

        # список слотов: строки-виджеты, чередование фона
        self.sched = QListWidget()
        self.sched.setAlternatingRowColors(True)
        # Высоту задаёт _fit_sched_height: пустой список не должен держать
        # 160 px пустоты (жалоба: слишком много пустого места по вертикали).
        self.sched.setMinimumHeight(ROW_H + 6)
        self.sched.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.sched.setSelectionMode(QListWidget.NoSelection)
        vs2.addWidget(self.sched)
        root.addWidget(gb_sch)

        # журнал (сворачиваемый): кнопки компактно вверху, лог занимает высоту
        self.log_box = QGroupBox("Журнал")
        self.log_box.setCheckable(True)
        self.log_box.setChecked(False)
        outer = QVBoxLayout(self.log_box)
        outer.setContentsMargins(0, 22, 0, 0)
        outer.setSpacing(0)
        self.log_content = QWidget()
        vl = QVBoxLayout(self.log_content)
        vl.setContentsMargins(GAP, 0, GAP, GAP)
        vl.setSpacing(4)
        rowl = QHBoxLayout()
        rowl.addStretch(1)
        b_copy = QPushButton("Копировать")
        b_copy.setObjectName("del")
        b_copy.setFixedHeight(24)
        b_copy.setToolTip("Скопировать журнал в буфер")
        b_copy.clicked.connect(self.copy_log)
        b_clear = QPushButton("Очистить")
        b_clear.setObjectName("del")
        b_clear.setFixedHeight(24)
        b_clear.setToolTip("Очистить журнал")
        b_clear.clicked.connect(self.clear_log)
        rowl.addWidget(b_copy)
        rowl.addWidget(b_clear)
        vl.addLayout(rowl)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lf = QFont()
        lf.setFamilies(["Consolas", "Cascadia Mono", "monospace"])
        lf.setPointSizeF(8.5)
        self.log.setFont(lf)
        vl.addWidget(self.log, 1)
        outer.addWidget(self.log_content)
        self.log_box.toggled.connect(self.log_content.setVisible)
        self.log_content.setVisible(False)
        root.addWidget(self.log_box)

        # нижний action bar
        ab = QHBoxLayout()
        ab.setSpacing(PAD)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.bar.setAlignment(Qt.AlignCenter)
        self.bar.setFormat("Ожидание")
        self.bar.setFixedHeight(H_BAR)
        self.btn_run = QPushButton("Создать файл погоды")
        self.btn_run.setObjectName("primary")
        self.btn_run.setShortcut(QKeySequence("F5"))
        self.btn_run.setToolTip("Создать файл погоды (F5)")
        self.btn_run.setFixedSize(220, H_BAR)
        self.btn_run.clicked.connect(self.run_or_cancel)
        ab.addWidget(self.bar, 1)
        ab.addWidget(self.btn_run)
        root.addLayout(ab)

    def _apply_cfg(self):
        existing = {s["name"]: s for s in self.cfg["synth"]}
        order = [s["name"] for s in self.cfg["synth"]]
        order = [n for n in order if n in SYNTH_NAMES]
        for name in SYNTH_NAMES:
            if name not in order:
                order.append(name)
        self.rows = []
        for name in order:
            s = existing.get(name, {"enabled": True, "voice": ""})
            btext, bcolor = self.badge_for(name)
            row = SynthRow(name, self.voice_options(name),
                           s.get("voice", ""), s.get("enabled", True),
                           btext, bcolor, self.move_row)
            self.rows.append(row)
        self._relayout_synths()
        # расписание: новый формат {time,enabled} или старый ["HH:MM", ...]
        for item in self.cfg.get("schedule", []):
            if isinstance(item, dict):
                t, en = item.get("time", ""), item.get("enabled", True)
            else:
                t, en = str(item), True
            if self._valid_time(t):
                self.add_sched_row(t, bool(en), touch=False)
        self._fit_sched_height()

    def voice_options(self, name):
        if name == "Edge TTS":
            return [(v, v) for v in EDGE_VOICES]
        if name == "Piper":
            opts = [("авто (по умолчанию)", "")]
            for p in self.piper_models():
                opts.append((os.path.basename(p), p))
            return opts
        return [("русский", "")]        # gTTS — один голос

    def badge_for(self, name):
        """Бейдж строки: (текст, цвет). «1 голос» — ограничение, «офлайн» — режим."""
        if name == "gTTS":
            return "1 голос", style.color("TEXT_SECOND")
        if name == "Piper":
            return "офлайн", style.color("OFFLINE")
        return "", ""

    # -------------------------------------------------- раскладка синтезаторов
    def _relayout_synths(self):
        while self.syn_grid.count():
            self.syn_grid.takeAt(0)
        n = len(self.rows)
        for i, r in enumerate(self.rows):
            self.syn_grid.addWidget(r.check, i, 0)
            self.syn_grid.addWidget(r.label, i, 1)
            self.syn_grid.addWidget(r.combo, i, 2)
            self.syn_grid.addWidget(r.badge, i, 3)
            self.syn_grid.addWidget(r.order, i, 4)
            r.up.setEnabled(i > 0)
            r.down.setEnabled(i < n - 1)
            r.label.setToolTip("Приоритет: %d" % (i + 1))

    def move_row(self, row, d):
        i = self.rows.index(row)
        j = i + d
        if not (0 <= j < len(self.rows)):
            return
        self.rows[i], self.rows[j] = self.rows[j], self.rows[i]
        self._relayout_synths()
        self._touch()

    def piper_models(self):
        """Найти модели Piper (.onnx) в каталогах проекта, без дублей."""
        seen = set()
        out = []
        for d in (os.path.join(BASE, "voices"), os.path.join(weather.RES, "voices"), BASE, weather.RES):
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if not f.endswith(".onnx"):
                    continue
                p = os.path.join(d, f)
                real = os.path.realpath(p)
                if real in seen:
                    continue
                seen.add(real)
                out.append(p)
        return out

    # -------------------------------------------------- журнал
    def append_log(self, s):
        self.log.append(s)

    def copy_log(self):
        QApplication.clipboard().setText(self.log.toPlainText())

    def clear_log(self):
        if self.log.document().blockCount() > 100:
            if QMessageBox.question(self, "Журнал",
                                    "Очистить журнал? (много строк)") != QMessageBox.Yes:
                return
        self.log.clear()

    # -------------------------------------------------- статус (исход запуска)
    def _when_str(self, dt):
        today = datetime.date.today()
        if dt.date() == today:
            return "Сегодня, %s" % dt.strftime("%H:%M")
        if dt.date() == today - datetime.timedelta(days=1):
            return "Вчера, %s" % dt.strftime("%H:%M")
        return dt.strftime("%d.%m, %H:%M")

    def _outcome(self, lr):
        """Из last_run → (kind, текст статуса)."""
        if not lr:
            return "neutral", "Файл ещё не создан"
        when = lr.get("when", "")
        if not lr.get("ok"):
            return "error", "%s · файл не создан" % when
        size = lr.get("size", 0)
        sz = " · %.1f МБ" % (size / 1048576.0) if size else ""
        total = lr.get("total", 0)
        used = total - len(lr.get("skipped", []) or [])
        if lr.get("skipped"):
            return ("warning", "%s%s · %d/%d синт., пропущен %s"
                    % (when, sz, used, total, ", ".join(lr["skipped"])))
        return "success", "%s%s · %d/%d синт." % (when, sz, used, total or used)

    def _last_run(self):
        """Последний прогон — из общего runstate.json: его пишут и GUI,
        и CLI из планировщика, поэтому статус не зависит от того, кто запускал."""
        lr = weather.read_runstate().get("last_run") or {}
        if not lr:
            return None
        ts = lr.get("ts")
        if ts:
            try:
                lr = dict(lr)
                lr["when"] = self._when_str(datetime.datetime.fromisoformat(ts))
            except Exception:  # noqa
                pass
        return lr

    def _refresh_status(self):
        lr = self._last_run()
        kind, text = self._outcome(lr)
        ic = self.style().standardIcon(STATE_ICON.get(kind, QStyle.SP_MessageBoxInformation))
        self.status_icon.setPixmap(ic.pixmap(16, 16))
        self.status_text.setText(text)
        self.status_text.setProperty("state", kind)
        repolish(self.status_text)
        self.banner.setProperty("state", kind)
        repolish(self.banner)

    def _record_run(self, ok, path=None, err=None, slot=None):
        """Записать исход запуска в общий runstate.json (см. weather.record_run).
        Пишет туда же, куда и CLI из планировщика, — GUI лишь показывает."""
        weather.record_run(ok, path, err, slot)
        self._refresh_status()

    # -------------------------------------------------- действия
    def pick_out(self):
        p, _ = QFileDialog.getSaveFileName(self, "Куда сохранять ПОГОДА.wav",
                                           self.out_edit.text(), "WAV (*.wav)")
        if p:
            self.out_edit.setText(p)
            self.out_edit.setToolTip(p)

    def open_folder(self):
        d = os.path.dirname(self.out_edit.text()) or BASE
        if os.path.isdir(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # -------------------------------------------------- расписание
    @staticmethod
    def _valid_time(t):
        # Единый разбор с CLI (weather.valid_slot): одно правило на оба входа.
        return weather.valid_slot(t)

    def _sched_row(self, i):
        it = self.sched.item(i)
        return self.sched.itemWidget(it)

    def _fit_sched_height(self):
        # Без слотов список минимален (не держим 160 px пустоты); со слотами —
        # по числу строк, но не выше 160 px, чтобы окно влезало на 768 px.
        n = self.sched.count()
        h = min(ROW_H * n, 160) if n else ROW_H + 6
        self.sched.setFixedHeight(h)

    def add_sched_row(self, time_str, enabled=True, touch=True):
        it = QListWidgetItem()
        row = SchedRow(time_str, enabled)
        it.setSizeHint(QSize(0, ROW_H))
        self.sched.addItem(it)
        self.sched.setItemWidget(it, row)
        row.check.toggled.connect(self._update_schedule_status)
        row.check.toggled.connect(self._touch)
        row.btn_del.clicked.connect(lambda _=False, i=it: self.remove_sched_item(i))
        self._fit_sched_height()
        if touch:
            self._update_schedule_status()
            self._touch()

    def remove_sched_item(self, it):
        row = self.sched.itemWidget(it)
        if row is None:
            return
        if QMessageBox.question(self, "Расписание",
                                "Удалить слот %s из ежедневного расписания?"
                                % row.time_str) == QMessageBox.Yes:
            weather.forget_slot(row.time_str)
            self.sched.takeItem(self.sched.row(it))
            self._fit_sched_height()
            self._update_schedule_status()
            self._touch()

    def add_time_str(self, t):
        if not self._valid_time(t):
            QMessageBox.warning(self, "Расписание", "Некорректное время: %s" % t)
            return
        if t in [self._sched_row(i).time_str for i in range(self.sched.count())]:
            QMessageBox.information(self, "Расписание", "Время %s уже добавлено." % t)
            return
        self.add_sched_row(t, True, touch=True)

    def add_time(self):
        try:
            mm = int(str(self.mm.currentText()).strip())
        except Exception:  # noqa
            mm = -1
        if not (0 <= mm <= 59):
            QMessageBox.warning(self, "Расписание", "Минуты должны быть от 0 до 59.")
            return
        self.add_time_str("%02d:%02d" % (self.hh.value(), mm))

    @staticmethod
    def _left(delta):
        secs = int(delta.total_seconds())
        if secs < 60:
            return "сейчас"
        if secs < 3600:
            return "через %d мин" % (secs // 60)
        return "через %d ч %d мин" % (secs // 3600, (secs % 3600) // 60)

    def _slot_outcome_text(self, row, now, next_cand, passed):
        """Текст статуса слота: исход прошлого запуска важнее расписания."""
        res = (weather.read_runstate().get("slot_results") or {}).get(row.time_str)
        if not row.enabled():
            return "neutral", "отключён"
        if res:
            total = res.get("total", 0)
            used = total - len(res.get("skipped", []) or [])
            if not res.get("ok"):
                return "error", "пропущен · файл не создан"
            if res.get("skipped"):
                return "warning", "отработал · %d/%d, пропущен %s" \
                    % (used, total, ", ".join(res["skipped"]))
            return "success", "отработал · %d/%d" % (total or used, total or used)
        if passed:
            return "neutral", "прошёл · нет данных (приложение не работало)"
        return "neutral", "предстоит %s" % self._left(next_cand - now) if \
            (next_cand and not passed) else "предстоит"

    def _update_schedule_status(self):
        now = datetime.datetime.now()
        items = []
        for i in range(self.sched.count()):
            row = self._sched_row(i)
            if row is None:
                continue
            cand = None
            passed = False
            if self._valid_time(row.time_str):
                hh, mm = (int(x) for x in row.time_str.split(":"))
                today_at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                passed = today_at <= now
                cand = today_at + datetime.timedelta(days=1) if passed else today_at
            items.append((row, cand, passed))

        next_cand = None
        for row, cand, passed in items:
            if row.enabled() and cand is not None:
                if next_cand is None or cand < next_cand:
                    next_cand = cand

        for row, cand, passed in items:
            kind, text = self._slot_outcome_text(row, now, next_cand, passed)
            row.set_outcome(kind, text)

        if next_cand is None:
            self.next_label.setText("")
            return
        self.next_label.setText("Следующий: %s (%s)"
                                % (next_cand.strftime("%H:%M"), self._left(next_cand - now)))

    # -------------------------------------------------- запуск
    def active_chain(self):
        return [r.name for r in self.rows if r.check.isChecked()]

    def run_now(self, slot=None):
        if self.worker and self.worker.isRunning():
            return
        chain = self.active_chain()
        if not chain:
            QMessageBox.warning(self, "Синтезаторы", "Не включён ни один синтезатор.")
            return
        ev = next((r.voice() for r in self.rows if r.name == "Edge TTS"), "")
        if ev:
            weather.VOICE = ev
            weather.EDGE_VOICES = [ev] + [v for v in EDGE_VOICES if v != ev]
        pm = next((r.voice() for r in self.rows if r.name == "Piper"), "")
        weather.PIPER_MODEL = pm or None

        self._fired_slot = slot
        self.save_cfg()
        out = self.out_edit.text()
        self.log.clear()
        self._set_busy(True, chain)
        self.set_progress("work", None, "Синтез…")
        self.append_log("Запуск: %s" % ", ".join(chain))
        self.worker = Worker(out, chain)
        self.worker.done.connect(self.on_done)
        self.worker.fail.connect(self.on_fail)
        self.worker.logline.connect(self.append_log)
        weather.LOG_HOOK = self.worker.logline.emit
        self.worker.start()

    def run_or_cancel(self):
        """Главная кнопка: запуск, а во время работы — прерывание."""
        if self.worker and self.worker.isRunning():
            self.cancel_run()
        else:
            self.run_now()

    def cancel_run(self):
        if not (self.worker and self.worker.isRunning()):
            return
        if QMessageBox.question(self, "Прервать синтез",
                                "Прервать синтез? Файл не будет создан."
                                ) != QMessageBox.Yes:
            return
        self.worker.terminate()
        self.worker.wait(2000)
        self.append_log("Прервано оператором")
        self.set_progress("error", 0, "Прервано")
        self._record_run(False, None, "Прервано оператором", slot=self._fired_slot)
        self._set_busy(False)
        self._update_schedule_status()

    def set_progress(self, state, value, text):
        self.bar.setProperty("state", state if state in ("work", "success", "warning", "error") else "")
        repolish(self.bar)
        if value is None:
            self.bar.setRange(0, 0)          # бесконечный режим
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(value)
        self.bar.setFormat(text)

    def _set_busy(self, busy, chain=None):
        """Переключить главную кнопку и статус-строку в режим работы/покоя."""
        if busy:
            self.btn_run.setProperty("mode", "cancel")
            self.btn_run.setText("Отмена")
            self.btn_run.setToolTip("Прервать синтез")
            names = ", ".join(chain) if chain else ""
            ic = self.style().standardIcon(QStyle.SP_BrowserReload)
            self.status_icon.setPixmap(ic.pixmap(16, 16))
            self.status_text.setText("Идёт синтез · %s" % names if names else "Идёт синтез")
            self.status_text.setProperty("state", "neutral")
        else:
            self.btn_run.setProperty("mode", "")
            self.btn_run.setText("Создать файл погоды")
            self.btn_run.setToolTip("Создать файл погоды (F5)")
        repolish(self.btn_run)
        repolish(self.status_text)

    def on_done(self, path):
        self._set_busy(False)
        skipped = weather.LAST_RESULT.get("skipped") or []
        self.set_progress("warning" if skipped else "success", 100,
                          "Готово" if not skipped else "Готово (частично)")
        self.append_log("Готово: %s" % path)
        self._record_run(True, path, slot=self._fired_slot)
        self._update_schedule_status()

    def on_fail(self, err):
        self._set_busy(False)
        self.set_progress("error", 0, "Ошибка")
        self.append_log("Ошибка: %s" % err)
        self._record_run(False, None, err, slot=self._fired_slot)
        self.log_box.setChecked(True)
        self._update_schedule_status()

    # -------------------------------------------------- расписание (таймер)
    def check_schedule(self):
        self._update_schedule_status()
        now = datetime.datetime.now()
        key = now.strftime("%Y-%m-%d %H:%M")
        for i in range(self.sched.count()):
            row = self._sched_row(i)
            if row and row.enabled() and row.time_str == now.strftime("%H:%M") \
                    and not weather.slot_fired(key):
                weather.mark_slot(key)      # общий флаг с CLI: слот не сработает дважды
                self.append_log("Расписание: %s" % key)
                self.run_now(slot=row.time_str)
                break

    def closeEvent(self, e):
        try:
            self.save_cfg()
        except Exception:  # noqa
            pass
        super().closeEvent(e)


# Флаги, при которых тот же exe работает как консольный (см. weather.cli).
# Планировщику Windows GUI не нужен: без этой ветки `WeatherCast-73.76.exe
# --run --slot 07:30` открывал окно и НЕ создавал файл.
CLI_FLAGS = ("--run", "--selftest", "--show-config", "--slot")


def main():
    args = sys.argv[1:]
    if any(a == f or a.startswith(f + "=") for f in CLI_FLAGS for a in args):
        return weather.cli(args)          # без окна: синтез и выход

    app = QApplication(sys.argv)
    style.apply_style(app)          # Fusion + единый QSS
    w = Window()
    # 1366×768: окно с заголовком и панелью задач не должно вылезать за экран.
    # 700 + рамка/заголовок (~40) + панель задач (~40) укладываются в 768.
    w.resize(560, 700)
    w.setMinimumWidth(520)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
