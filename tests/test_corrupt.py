# -*- coding: utf-8 -*-
"""Устойчивость к повреждённым данным и недоступным путям.

На боевой машине config.json может оказаться обрезанным, runstate.json —
битым после сбоя питания, каталог записи — на отключённом диске или на шаре
только для чтения. Программа обязана деградировать, а не падать: иначе
эфирный файл не создастся вовсе.
"""
import json
import os
import tempfile

import pytest

import weather


# ---------------------------------------------------------------- конфиг
@pytest.mark.parametrize("content", [
    "",              # пустой файл — обрыв записи
    "{",             # обрезанный JSON
    "не json вовсе",  # мусор вместо JSON
    "[1, 2, 3]",      # список, а не объект
    "null",           # null вместо объекта
])
def test_broken_config_is_ignored(tmp_path, content):
    p = tmp_path / "config.json"
    p.write_text(content, encoding="utf-8")
    assert weather.load_config(str(p)) is None


def test_missing_config_is_none(tmp_path):
    assert weather.load_config(str(tmp_path / "нет-такого.json")) is None


def test_config_directory_instead_of_file(tmp_path):
    d = tmp_path / "config.json"
    d.mkdir()
    assert weather.load_config(str(d)) is None


def test_apply_config_none_is_noop():
    before = (weather.VOICE, list(weather.EDGE_VOICES), weather.PIPER_MODEL)
    assert weather.apply_config(None) == (None, None)
    assert weather.apply_config({}) == (None, None)
    assert (weather.VOICE, list(weather.EDGE_VOICES), weather.PIPER_MODEL) == before


def test_config_with_wrong_synth_type_is_still_loaded(tmp_path):
    """Объект с полем не того типа — не «битый файл»: load_config его отдаёт,
    а мусор внутри отбрасывает apply_config. Это разные уровни защиты."""
    p = tmp_path / "config.json"
    p.write_text('{"synth": "не список"}', encoding="utf-8")
    cfg = weather.load_config(str(p))
    assert cfg == {"synth": "не список"}
    assert weather.apply_config(cfg) == (None, None)   # молча по умолчанию


def test_config_with_garbage_synth_entries():
    cfg = {"synth": [None, 42, "Piper", {}, {"name": ""},
                     {"name": "Piper", "enabled": True}]}
    out, chain = weather.apply_config(cfg)
    assert out is None
    assert chain == ["Piper"]


# ---------------------------------------------------------------- runstate
@pytest.mark.parametrize("content", ["", "{", "[1,2]", "\x00\x01", "null"])
def test_broken_runstate_reads_as_empty(tmp_path, content):
    p = tmp_path / "runstate.json"
    p.write_bytes(content.encode("utf-8", "surrogateescape"))
    assert weather.read_runstate(str(p)) == {}


def test_missing_runstate_reads_as_empty(tmp_path):
    assert weather.read_runstate(str(tmp_path / "nope.json")) == {}


def test_write_runstate_to_missing_dir_does_not_raise(tmp_path):
    target = str(tmp_path / "нет" / "каталога" / "runstate.json")
    weather.write_runstate({"a": 1}, target)      # молча не пишет
    assert not os.path.exists(target)


def test_mark_slot_recovers_from_broken_state(tmp_path):
    p = tmp_path / "runstate.json"
    p.write_text("сломано", encoding="utf-8")
    weather.mark_slot("2026-10-24 09:00", runstate=str(p))
    assert weather.slot_fired("2026-10-24 09:00", runstate=str(p)) is True


# ---------------------------------------------------------------- каталоги
@pytest.mark.parametrize("bad", [None, "", "/нет/такого/каталога", "/etc/hostname"])
def test_dir_writable_rejects_bad_targets(bad):
    assert weather._dir_writable(bad) is False


def test_dir_writable_accepts_temp(tmp_path):
    assert weather._dir_writable(str(tmp_path)) is True
    assert not os.path.exists(str(tmp_path / ".wr_probe"))


def test_log_falls_back_to_temp_when_dir_broken(tmp_path, monkeypatch):
    """Журнал не должен теряться: при недоступном каталоге уходит в temp."""
    bad = str(tmp_path / "нет" / "weather.log")
    monkeypatch.setattr(weather, "LOG_FILE", bad)
    weather.log("проверка")
    assert weather.LOG_FILE != bad
    assert os.path.dirname(weather.LOG_FILE) == tempfile.gettempdir()
    with open(weather.LOG_FILE, encoding="utf-8") as fh:
        assert "проверка" in fh.read()


# ---------------------------------------------------------------- run()
@pytest.fixture
def run_stub(monkeypatch, tmp_path):
    """Всё тяжёлое заменено: сеть, синтез, ffmpeg. Остаётся логика путей."""
    data = {
        "current": {"temperature_2m": 5},
        "daily": {"time": ["2026-10-24", "2026-10-25"],
                  "temperature_2m_min": [1, 2],
                  "temperature_2m_max": [9, 10],
                  "weather_code": [1, 2]},
        "hourly": {},
    }
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"RIFF0000WAVE")

    monkeypatch.setattr(weather, "fetch_weather", lambda: data)
    monkeypatch.setattr(weather, "voice_budget", lambda: 20.0)
    monkeypatch.setattr(weather, "fit", lambda pri, target, chain=None: str(voice))
    monkeypatch.setattr(weather, "duration", lambda p: 1.0)
    monkeypatch.setattr(weather, "reset_cancel", lambda: None)
    monkeypatch.setattr(weather, "_check_cancel", lambda: None)

    def fake_mix(voice_wav, out_file=None):
        with open(out_file, "wb") as fh:
            fh.write(b"RIFF0000WAVE")

    monkeypatch.setattr(weather, "mix", fake_mix)
    return data


def test_run_falls_back_to_base_when_dir_missing(run_stub, monkeypatch):
    """Каталог «D:\\radio» не смонтирован — пишем рядом с программой."""
    monkeypatch.setattr(weather, "LOG_FILE", os.path.join(tempfile.gettempdir(),
                                                           "weather-test.log"))
    out = weather.run("/нет/такого/каталога/ПОГОДА.wav")
    assert out == os.path.join(weather.BASE, "ПОГОДА.wav")
    assert os.path.exists(out)
    os.remove(out)


def test_run_falls_back_to_write_dir_when_readonly(run_stub, monkeypatch, tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    target = ro / "ПОГОДА.wav"
    monkeypatch.setattr(weather, "LOG_FILE", os.path.join(str(tmp_path), "w.log"))
    # Каталог существует, но писать в него нельзя.
    monkeypatch.setattr(weather, "_dir_writable",
                        lambda d: os.path.abspath(str(d)) != os.path.abspath(str(ro)))
    monkeypatch.setattr(weather, "WRITE_DIR", str(tmp_path))
    out = weather.run(str(target))
    assert out == str(tmp_path / "ПОГОДА.wav")
    assert os.path.exists(out)


def test_run_relative_path_anchored_to_base(run_stub, monkeypatch, tmp_path):
    monkeypatch.setattr(weather, "LOG_FILE", os.path.join(str(tmp_path), "w.log"))
    out = weather.run("относительный.wav")
    assert out == os.path.join(weather.BASE, "относительный.wav")
    os.remove(out)
