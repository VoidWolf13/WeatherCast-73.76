# -*- coding: utf-8 -*-
"""Журнал прогонов (runstate.json): исход, слоты, отметка «сработал».

Это общий контракт GUI и CLI: если он сломан, слот либо теряется, либо
срабатывает дважды.
"""
import datetime

import weather


def use_result(used="Edge TTS", skipped=(), total=3, voice_dur=54.3, budget=58.0):
    weather.LAST_RESULT.clear()
    weather.LAST_RESULT.update({"used": used, "skipped": list(skipped),
                                "total": total, "voice_dur": voice_dur,
                                "budget": budget})


def test_record_run_writes_last_run(tmp_path):
    p = tmp_path / "runstate.json"
    use_result()
    lr = weather.record_run(True, None, slot=None, runstate=str(p))
    data = weather.read_runstate(str(p))
    assert data["last_run"]["ok"] is True
    assert data["last_run"]["total"] == 3
    assert data["last_run"]["voice_dur"] == 54.3
    assert data["last_run"]["budget"] == 58.0
    assert lr["skipped"] == []


def test_record_run_skipped_is_warning_payload(tmp_path):
    p = tmp_path / "runstate.json"
    use_result(used="gTTS", skipped=("Piper",))
    weather.record_run(True, None, slot="09:00", runstate=str(p))
    st = weather.read_runstate(str(p))
    assert st["slot_results"]["09:00"]["skipped"] == ["Piper"]


def test_mark_slot_blocks_second_run(tmp_path):
    p = tmp_path / "runstate.json"
    key = "2026-10-24 09:00"
    assert weather.slot_fired(key, runstate=str(p)) is False
    weather.mark_slot(key, runstate=str(p))
    assert weather.slot_fired(key, runstate=str(p)) is True


def test_forget_slot_clears_result_and_fired(tmp_path):
    """Удалил слот и добавил заново — он должен сработать снова."""
    p = tmp_path / "runstate.json"
    key = "2026-10-24 09:00"
    use_result()
    weather.record_run(True, None, slot="09:00", runstate=str(p))
    weather.mark_slot(key, runstate=str(p))

    weather.forget_slot("09:00", runstate=str(p))

    st = weather.read_runstate(str(p))
    assert "09:00" not in (st.get("slot_results") or {})
    assert not (st.get("fired") or {}).get(key)


def test_forget_slot_keeps_other_slots(tmp_path):
    p = tmp_path / "runstate.json"
    use_result()
    weather.record_run(True, None, slot="09:00", runstate=str(p))
    weather.mark_slot("2026-10-24 09:00", runstate=str(p))
    weather.mark_slot("2026-10-24 12:00", runstate=str(p))

    weather.forget_slot("09:00", runstate=str(p))

    st = weather.read_runstate(str(p))
    assert "2026-10-24 12:00" in (st.get("fired") or {})


def test_cancel_flag_raises_cancelled(tmp_path):
    weather.reset_cancel()
    weather.request_cancel()
    try:
        with __import__("pytest").raises(weather.Cancelled):
            weather._check_cancel()
    finally:
        weather.reset_cancel()
    weather._check_cancel()   # после сброса не бросает
