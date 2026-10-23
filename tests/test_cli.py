# -*- coding: utf-8 -*-
"""Командная строка: контракт для планировщика Windows.

Это боевой путь: `weather.py --run --slot 09:00` вызывает планировщик.
docs/RULES.md обещает коды возврата:
    0 — файл создан ИЛИ слот уже отработал (повтор не нужен)
    1 — ошибка синтеза
    2 — некорректный --slot либо нечего делать (нет --run)

Ни одна из этих ветвей раньше не проверялась. Здесь сеть, ffmpeg и синтез
заменены заглушками — проверяется именно логика CLI.
"""
import json

import pytest

import weather


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """Изоляция: свой runstate, свой журнал, свой «синтез». Возвращает список вызовов run()."""
    calls = []
    out = tmp_path / "ПОГОДА.wav"

    def fake_run(out_file=None, chain=None):
        calls.append({"out": out_file, "chain": list(chain or [])})
        out.write_bytes(b"RIFF0000WAVE")
        weather.LAST_RESULT.clear()
        weather.LAST_RESULT.update({
            "used": (chain or ["Edge TTS"])[0],
            "skipped": list((chain or [])[1:]),
            "total": len(chain or ["Edge TTS"]),
        })
        return str(out)

    # Боевой config.json проекта не должен влиять: без --config настроек нет.
    orig_load = weather.load_config

    def guarded_load(path=None):
        return orig_load(path) if path else None

    monkeypatch.setattr(weather, "load_config", guarded_load)
    monkeypatch.setattr(weather, "run", fake_run)
    monkeypatch.setattr(weather, "duration", lambda p: 1.5)
    monkeypatch.setattr(weather, "RUNSTATE", str(tmp_path / "runstate.json"))
    monkeypatch.setattr(weather, "LOG_FILE", str(tmp_path / "weather.log"))
    monkeypatch.setattr(weather, "SYNTH_CHAIN", ["Edge TTS", "gTTS", "Piper"])
    monkeypatch.setattr(weather, "VOICE", "ru-RU-DmitryNeural")
    monkeypatch.setattr(weather, "EDGE_VOICES", ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"])
    monkeypatch.setattr(weather, "PIPER_MODEL", None)
    return calls


def test_show_config_is_json(cli_env, capsys):
    rc = weather.cli(["--show-config"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["app"] == weather.APP_NAME
    assert data["version"] == weather.VERSION
    assert data["synth_chain"] == ["Edge TTS", "gTTS", "Piper"]
    for key in ("out_file", "edge_voice", "ffmpeg", "ffprobe"):
        assert key in data


def test_without_run_prints_help_and_returns_2(cli_env, capsys):
    rc = weather.cli(["--out", "x.wav"])
    assert rc == 2
    assert cli_env == []          # синтез не запускался
    assert "--slot" in capsys.readouterr().out


def test_invalid_slot_returns_2_and_marks_nothing(cli_env, capsys):
    rc = weather.cli(["--run", "--slot", "25:00"])
    assert rc == 2
    assert cli_env == []
    assert "Некорректное время слота" in capsys.readouterr().err
    assert weather.read_runstate() == {}


@pytest.mark.parametrize("slot", ["7:5", "aa:bb", "", ":", "12:60"])
def test_garbage_slots_rejected(cli_env, slot):
    assert weather.cli(["--run", "--slot", slot]) == 2
    assert cli_env == []


def test_slot_runs_once_then_skips(cli_env, capsys):
    assert weather.cli(["--run", "--slot", "09:00", "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["ok"] is True
    assert len(cli_env) == 1

    st = weather.read_runstate()
    assert st["slot_results"]["09:00"]["ok"] is True

    # Второй запуск в ту же минуту — файл не создаём, но и ошибки нет.
    assert weather.cli(["--run", "--slot", "09:00", "--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second == {"ok": False, "skipped_slot": "09:00"}
    assert len(cli_env) == 1, "повторный слот не должен снова синтезировать"


def test_failed_run_returns_1_and_records_error(cli_env, capsys, monkeypatch):
    def boom(out_file=None, chain=None):
        raise RuntimeError("нет сети")

    monkeypatch.setattr(weather, "run", boom)
    rc = weather.cli(["--run", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "нет сети" in payload["error"]

    lr = weather.read_runstate()["last_run"]
    assert lr["ok"] is False
    assert "нет сети" in lr["err"]


def test_chain_override_reaches_run(cli_env):
    assert weather.cli(["--run", "--chain", "gTTS, Piper"]) == 0
    assert cli_env[-1]["chain"] == ["gTTS", "Piper"]
    assert weather.SYNTH_CHAIN == ["gTTS", "Piper"]


def test_voice_override_moves_to_front(cli_env):
    assert weather.cli(["--run", "--voice", "ru-RU-SvetlanaNeural"]) == 0
    assert weather.VOICE == "ru-RU-SvetlanaNeural"
    assert weather.EDGE_VOICES[0] == "ru-RU-SvetlanaNeural"
    assert weather.EDGE_VOICES.count("ru-RU-SvetlanaNeural") == 1


def test_out_override_reaches_run(cli_env, tmp_path):
    target = str(tmp_path / "эфир.wav")
    assert weather.cli(["--run", "--out", target]) == 0
    assert cli_env[-1]["out"] == target


def test_selftest_exit_code_follows_ok(cli_env, capsys, monkeypatch):
    monkeypatch.setattr(weather, "selftest", lambda: {"ok": True, "ffmpeg": True})
    assert weather.cli(["--selftest", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

    monkeypatch.setattr(weather, "selftest", lambda: {"ok": False, "network": False})
    assert weather.cli(["--selftest"]) == 1
    assert "network: False" in capsys.readouterr().out


def test_config_file_is_honoured(cli_env, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "out_file": "свой.wav",
        "synth": [{"name": "Piper", "enabled": True, "voice": ""}],
    }, ensure_ascii=False), encoding="utf-8")
    assert weather.cli(["--run", "--config", str(cfg)]) == 0
    assert cli_env[-1]["chain"] == ["Piper"]
    assert cli_env[-1]["out"] == "свой.wav"
