# -*- coding: utf-8 -*-
"""Свойства чистых функций (property-based).

hypothesis перебирает значения, которые руками писать лень: сотни температур,
углов, чисел и строк. Проверяем не «что получилось», а инварианты: число
словами без цифр, текст без двойных пробелов, падеж согласован с числом,
направление ветра — из фиксированного набора.

Главная ценность — краевые случаи. Именно здесь нашёлся num_gen(0) == ""
и диапазон «от  до пяти» — в эфире это звучит как «от до пяти градусов».
"""
import pytest

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")
from hypothesis import given, settings  # noqa: E402

import weather  # noqa: E402

settings.register_profile("ci", max_examples=300, deadline=None)
settings.load_profile("ci")

DIGITS = set("0123456789")


def no_digits(s):
    return not (set(s) & DIGITS)


def clean(s):
    """Ни двойных пробелов, ни пробела на концах — иначе TTS читает рвано."""
    return s == " ".join(s.split())


# ---------------------------------------------------------------- числа
@given(n=st.integers(min_value=0, max_value=999))
def test_num_word_below_thousand(n):
    s = weather.num_word(n)
    assert s and no_digits(s) and clean(s)
    if n == 0:
        assert s == "ноль"


@given(n=st.integers(min_value=1, max_value=2999))
def test_num_word_thousands(n):
    s = weather.num_word(n)
    assert s and no_digits(s) and clean(s)


@given(n=st.integers(min_value=1, max_value=99))
def test_num_gen_not_empty(n):
    s = weather.num_gen(n)
    assert s and no_digits(s) and clean(s)


def test_num_gen_zero_is_a_word():
    """Ноль в родительном падеже — «нуля», иначе диапазон теряет число."""
    assert weather.num_gen(0) == "нуля"


@given(n=st.integers(min_value=0, max_value=1000))
def test_plural_agrees_with_number(n):
    got = weather.plural(n, "год", "года", "лет")
    tail = abs(int(n)) % 100
    if 11 <= tail <= 19:
        assert got == "лет"
    else:
        u = tail % 10
        assert got == {1: "год"}.get(u, "года" if 2 <= u <= 4 else "лет")


@given(n=st.integers(min_value=1, max_value=31))
def test_day_ord_any_day_of_month(n):
    s = weather.day_ord(n)
    assert s and no_digits(s) and clean(s)


# ---------------------------------------------------------------- ветер и WMO
@given(deg=st.floats(min_value=-720, max_value=720, allow_nan=False))
def test_wind_dir_always_known(deg):
    assert weather.wind_dir(deg) in weather._WIND


def test_wind_dir_none_is_variable():
    assert weather.wind_dir(None) == "переменный"


@given(code=st.integers(min_value=-100, max_value=1000))
def test_wmo_always_pair(code):
    word, wet = weather.wmo(code)
    assert isinstance(word, str) and word
    assert isinstance(wet, bool)


def test_wmo_none_is_cloudy():
    assert weather.wmo(None) == ("облачно", False)


# ---------------------------------------------------------------- диапазоны
@given(lo=st.integers(-40, 40), hi=st.integers(-40, 40))
def test_temp_range_is_speakable(lo, hi):
    s = weather._temp_range(min(lo, hi), max(lo, hi))
    assert s and clean(s)
    assert no_digits(s)
    assert not s.endswith(("до", "минус", "от"))


def test_temp_range_from_zero():
    assert weather._temp_range(0, 5) == "от нуля до пяти"


def test_temp_range_to_zero():
    assert weather._temp_range(-5, 0) == "от минус пяти до нуля"


@given(lo=st.integers(-40, 40), hi=st.integers(-40, 40))
def test_deg_range_word(lo, hi):
    assert weather._deg_range(min(lo, hi), max(lo, hi)) in (
        "градус", "градуса", "градусов")


@given(a=st.floats(0, 30, allow_nan=False), b=st.floats(0, 30, allow_nan=False))
def test_wind_speed_is_speakable(a, b):
    s = weather._wind_speed(min(a, b), max(a, b))
    assert s and clean(s) and no_digits(s)
    assert not s.endswith(("до", "от"))


def test_wind_speed_from_zero():
    assert weather._wind_speed(0, 3) == "от нуля до трёх метров в секунду"


def test_wind_speed_none():
    assert weather._wind_speed(None, None) is None


# ---------------------------------------------------------------- слоты и обрезка
@given(h=st.integers(0, 23), m=st.integers(0, 59))
def test_valid_slot_accepts_real_times(h, m):
    assert weather.valid_slot("%02d:%02d" % (h, m)) is True
    assert weather.valid_slot(" %02d:%02d " % (h, m)) is True


@given(h=st.integers(-5, 30), m=st.integers(-5, 70))
def test_valid_slot_rejects_out_of_range(h, m):
    if 0 <= h <= 23 and 0 <= m <= 59:
        return
    assert weather.valid_slot("%d:%d" % (h, m)) is False


@given(text=st.text(max_size=20))
def test_valid_slot_never_raises(text):
    assert isinstance(weather.valid_slot(text), bool)


@given(budget=st.integers(0, 200))
def test_trim_keeps_order_and_subset(budget):
    pri = [(0, "ядро сейчас"), (1, "сегодня днём"), (2, "ветер"), (7, "давление")]
    got = weather.trim(pri, budget)
    full = [s for _, s in pri]
    assert got == [s for s in full if s in got]
    assert all(g in full for g in got)
    assert got                       # ядро не режется никогда


def test_trim_drops_low_priority_first():
    # Фразы по одному слову: бюджет 2 вмещает ядро и день, давление — нет.
    pri = [(0, "ядро"), (1, "день"), (7, "давление")]
    assert weather.trim(pri, 2) == ["ядро", "день"]


def test_trim_keeps_everything_when_budget_allows():
    pri = [(0, "ядро"), (1, "день")]
    assert weather.trim(pri, 100) == ["ядро", "день"]
