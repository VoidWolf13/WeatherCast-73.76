# -*- coding: utf-8 -*-
"""Случайные действия с интерфейсом (stateful fuzz).

hypothesis составляет случайные последовательности действий с окном и после
каждого шага проверяет инварианты. Найденное падение он сам сокращает до
минимальной воспроизводимой последовательности — этим stateful-фаззинг
отличается от «monkey», который просто кликает и падает без повторяемого
сценария.

Побочные эффекты изолированы:
  • config.json / runstate.json / weather.log — во временный каталог;
  • weather.run заменён мгновенной заглушкой (никакой сети и ffmpeg);
  • модальные диалоги отвечают автоматически (иначе поток встанет);
  • открытие файлов и папок не происходит.

Запуск:  python3 -m pytest tests -m fuzz -q
Обычный прогон (`pytest tests`) этот файл пропускает — см. pytest.ini.
"""
import json
import os
import time

import pytest

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")
from hypothesis import HealthCheck, settings  # noqa: E402
from hypothesis.stateful import (RuleBasedStateMachine, invariant, rule,
                                 run_state_machine_as_test)  # noqa: E402

pytestmark = pytest.mark.fuzz

SETTINGS = settings(
    max_examples=25,
    stateful_step_count=20,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

HOUR_TEXTS = ("", "0", "7", "07", "23", "24", "-1", "99", "abc", " 5 ", "0012")
MINUTE_TEXTS = ("", "0", "7", "07", "15", "31", "59", "60", "-3", "abc", " 45 ")
PATH_TEXTS = ("", "ПОГОДА.wav", "sub/out.wav", "/tmp/x.wav",
              "C:\\radio\\ПОГОДА.wav", "юникод.wav", "a" * 300)


def test_random_ui_actions(qapp, tmp_path):
    from PySide6.QtWidgets import QApplication, QMessageBox

    import weather
    import weather_gui

    cfg_path = str(tmp_path / "config.json")
    rst_path = str(tmp_path / "runstate.json")
    log_path = str(tmp_path / "weather.log")
    wav_path = str(tmp_path / "ПОГОДА.wav")

    saved = {
        "run": weather.run,
        "runstate": weather.RUNSTATE,
        "log_file": weather.LOG_FILE,
        "config": weather_gui.CONFIG,
        "messagebox": weather_gui.QMessageBox,
        "desktop": weather_gui.QDesktopServices,
        "edge_voices": list(weather.EDGE_VOICES),
        "piper_model": weather.PIPER_MODEL,
    }

    # Все файлы состояния — во временный каталог, проект не трогаем.
    weather.RUNSTATE = rst_path
    weather.LOG_FILE = log_path
    weather_gui.CONFIG = cfg_path

    def fake_run(out_file=None, chain=None):
        """Мгновенная замена боевого синтеза: без сети, ffmpeg и задержек."""
        chain = list(chain or [])
        weather.LAST_RESULT.clear()
        weather.LAST_RESULT.update({
            "used": chain[0] if chain else None,
            "skipped": chain[1:],
            "total": len(chain),
            "voice_dur": 42.0,
            "budget": 58.0,
        })
        with open(wav_path, "wb") as fh:
            fh.write(b"RIFF0000WAVE")
        return wav_path

    class FakeMessageBox:
        """Автоответы: иначе QMessageBox заблокирует поток теста."""
        Yes = QMessageBox.Yes
        Ok = QMessageBox.Ok

        @staticmethod
        def question(*_a, **_k):
            return QMessageBox.Yes

        @staticmethod
        def warning(*_a, **_k):
            return QMessageBox.Ok

        @staticmethod
        def information(*_a, **_k):
            return QMessageBox.Ok

    class FakeDesktop:
        @staticmethod
        def openUrl(*_a, **_k):
            return True

    weather.run = fake_run
    weather_gui.QMessageBox = FakeMessageBox
    weather_gui.QDesktopServices = FakeDesktop

    class Machine(RuleBasedStateMachine):
        def __init__(self):
            super().__init__()
            self.w = weather_gui.Window()
            self.w.show()
            QApplication.processEvents()

        # ------------------------------------------------ служебное
        @staticmethod
        def _pump():
            QApplication.processEvents()

        def _settle(self, ms=3000):
            """Дождаться окончания фонового синтеза и доставить сигналы."""
            deadline = time.time() + ms / 1000.0
            while time.time() < deadline:
                QApplication.processEvents()
                if not (self.w.worker and self.w.worker.isRunning()):
                    break
                time.sleep(0.005)
            for _ in range(5):
                QApplication.processEvents()
                time.sleep(0.002)

        # ------------------------------------------------ синтезаторы
        @rule(idx=st.integers(min_value=0, max_value=6))
        def toggle_synth(self, idx):
            row = self.w.rows[idx % len(self.w.rows)]
            row.check.setChecked(not row.check.isChecked())
            self._pump()

        @rule(idx=st.integers(min_value=0, max_value=6),
              pos=st.integers(min_value=0, max_value=6))
        def pick_voice(self, idx, pos):
            row = self.w.rows[idx % len(self.w.rows)]
            n = row.combo.count()
            if n:
                row.combo.setCurrentIndex(pos % n)
            self._pump()

        @rule(idx=st.integers(min_value=0, max_value=6),
              direction=st.sampled_from([-1, 1]))
        def move_synth(self, idx, direction):
            self.w.move_row(self.w.rows[idx % len(self.w.rows)], direction)
            self._pump()

        # ------------------------------------------------ поля времени
        @rule(text=st.sampled_from(HOUR_TEXTS))
        def type_hours(self, text):
            self.w.hh.lineEdit().setText(text)
            self.w.hh.interpretText()
            self._pump()

        @rule(text=st.sampled_from(MINUTE_TEXTS))
        def type_minutes(self, text):
            self.w.mm.lineEdit().setText(text)
            self.w.mm.interpretText()
            self._pump()

        @rule(steps=st.integers(min_value=-5, max_value=5))
        def step_hours(self, steps):
            if steps:
                self.w.hh.stepBy(steps)
            self._pump()

        @rule(steps=st.integers(min_value=-5, max_value=5))
        def step_minutes(self, steps):
            if steps:
                self.w.mm.stepBy(steps)
            self._pump()

        # ------------------------------------------------ расписание
        @rule()
        def add_slot(self):
            self.w.add_time()
            self._pump()

        @rule(idx=st.integers(min_value=0, max_value=8))
        def toggle_slot(self, idx):
            if self.w.sched.count():
                row = self.w._sched_row(idx % self.w.sched.count())
                row.check.setChecked(not row.check.isChecked())
            self._pump()

        @rule(idx=st.integers(min_value=0, max_value=8))
        def delete_slot(self, idx):
            if self.w.sched.count():
                it = self.w.sched.item(idx % self.w.sched.count())
                self.w.remove_sched_item(it)
            self._pump()

        @rule()
        def tick_schedule(self):
            self.w.check_schedule()
            self._settle()

        # ------------------------------------------------ файл, журнал, запуск
        @rule(text=st.sampled_from(PATH_TEXTS))
        def edit_out_path(self, text):
            self.w.out_edit.setText(text)
            self._pump()

        @rule()
        def play_file(self):
            self.w.play_file()
            self._pump()

        @rule()
        def open_folder(self):
            self.w.open_folder()
            self._pump()

        @rule()
        def toggle_log(self):
            self.w.log_box.setChecked(not self.w.log_box.isChecked())
            self._pump()

        @rule()
        def copy_log(self):
            self.w.copy_log()

        @rule()
        def clear_log(self):
            self.w.clear_log()
            self._pump()

        @rule()
        def press_run(self):
            self.w.btn_run.click()
            self._settle()

        @rule()
        def start_stop(self):
            if not (self.w.worker and self.w.worker.isRunning()):
                self.w.run_now()
            if self.w.worker and self.w.worker.isRunning():
                self.w.cancel_run()
            self._settle()

        @rule()
        def save_config(self):
            self.w.save_cfg()

        @rule()
        def reload_from_config(self):
            """Сохранить и поднять окно заново: состояние обязано совпасть."""
            self.w.save_cfg()
            before = {
                "times": [self.w._sched_row(i).time_str
                          for i in range(self.w.sched.count())],
                "chain": self.w.active_chain(),
                "voices": [(r.name, r.voice()) for r in self.w.rows],
                "out": self.w.out_edit.text(),
            }
            second = weather_gui.Window()
            try:
                after = {
                    "times": [second._sched_row(i).time_str
                              for i in range(second.sched.count())],
                    "chain": second.active_chain(),
                    "voices": [(r.name, r.voice()) for r in second.rows],
                    "out": second.out_edit.text(),
                }
                assert after["times"] == before["times"], "слоты не пережили сохранение"
                assert after["chain"] == before["chain"], "галочки не пережили сохранение"
                assert after["voices"] == before["voices"], "голоса не пережили сохранение"
                assert after["out"] == before["out"], "путь не пережил сохранение"
            finally:
                second.deleteLater()
                QApplication.processEvents()

        # ------------------------------------------------ инварианты
        @invariant()
        def slots_valid_and_unique(self):
            times = [self.w._sched_row(i).time_str
                     for i in range(self.w.sched.count())]
            assert len(times) == len(set(times)), "дубли слотов: %r" % (times,)
            for t in times:
                assert weather.valid_slot(t), "некорректное время: %r" % (t,)

        @invariant()
        def chain_matches_checkboxes(self):
            checked = [r.name for r in self.w.rows if r.check.isChecked()]
            assert self.w.active_chain() == checked

        @invariant()
        def synth_rows_complete(self):
            assert {r.name for r in self.w.rows} == set(weather_gui.SYNTH_NAMES)

        @invariant()
        def config_is_valid_json(self):
            if os.path.exists(cfg_path):
                with open(cfg_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                assert isinstance(data, dict)
                assert isinstance(data.get("synth", []), list)
                assert isinstance(data.get("schedule", []), list)

        @invariant()
        def runstate_is_valid_json(self):
            if os.path.exists(rst_path):
                with open(rst_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                assert isinstance(data, dict)

        @invariant()
        def cards_have_values(self):
            for card in (self.w.card_last, self.w.card_next, self.w.card_syn):
                assert card["value"].text() != ""

        # ------------------------------------------------ завершение
        def teardown(self):
            w = self.w
            try:
                if w.worker and w.worker.isRunning():
                    weather.request_cancel()
                    w.worker.wait(3000)
                w.close()
            except Exception:  # noqa
                pass
            finally:
                w.deleteLater()
                QApplication.processEvents()
                weather.reset_cancel()

    try:
        run_state_machine_as_test(Machine, settings=SETTINGS)
    finally:
        weather.run = saved["run"]
        weather.RUNSTATE = saved["runstate"]
        weather.LOG_FILE = saved["log_file"]
        weather_gui.CONFIG = saved["config"]
        weather_gui.QMessageBox = saved["messagebox"]
        weather_gui.QDesktopServices = saved["desktop"]
        weather.EDGE_VOICES = list(saved["edge_voices"])
        weather.PIPER_MODEL = saved["piper_model"]
        weather.reset_cancel()
