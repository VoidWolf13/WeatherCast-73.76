#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeatherCast 73.76 — прогноз погоды для радиоэфира (Ростов-на-Дону, «Радио 7»).
Автор: AVAIM0013 (псевдоним).

Портативный: все пути считаются от каталога самого файла. Где запустил —
там и работает, никаких абсолютных путей и внешних конфигов.

Правила проекта (см. docs/RULES.md):
  • только локальный синтез речи, порядок выбора генератора:
      1. Edge TTS (Microsoft)
      2. gTTS (Google Translate)
      3. Piper
    Если предыдущий недоступен — берётся следующий.
  • надёжность: любой сбой одного движка не должен валить эфир;
  • после изменений пересобирать exe под Windows.

Аудио (см. docs/RULES.md):
  фон WEATHER_2023_IIII.wav + голос с задержкой 4 с, голос чуть громче фона,
  результат — ПОГОДА.wav рядом со скриптом.
"""

import os
import sys
import json
import argparse
import asyncio
import subprocess
import tempfile
import shutil
import urllib.request
import urllib.parse
import datetime

# Консольные подпроцессы (ffmpeg/ffprobe/piper) в GUI-сборке под Windows
# создают мелькающие окна cmd — CREATE_NO_WINDOW их прячет. На Linux флаг = 0.
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Хук для трансляции журнала в интерфейс (weather_gui.py подписывается сюда).
LOG_HOOK = None

# Результат последнего синтеза: какой движок сработал и какие были пропущены.
# Заполняет synthesize(); читает интерфейс (weather_gui.py) для статуса «N/N».
LAST_RESULT = {}


# ---- кооперативная отмена ----
# terminate() потока оставляет висящие ffmpeg/piper и temp-файлы, поэтому
# GUI просит остановиться флагом, а синтез проверяет его между этапами.
class Cancelled(Exception):
    """Синтез прерван оператором."""


CANCEL = {"flag": False}


def request_cancel():
    CANCEL["flag"] = True


def reset_cancel():
    CANCEL["flag"] = False


def _check_cancel():
    if CANCEL["flag"]:
        raise Cancelled("Прервано оператором")


# Консоль Windows по умолчанию cp1251: русский текст и «→» в print() валят UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ================================================================ пути (портативность)
# BASE — каталог для ЗАПИСИ (рядом с exe в сборке, иначе рядом со скриптом).
# RES  — каталог вложенных РЕСУРСОВ (в onefile-сборке это распакованный _MEIPASS).
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
    RES = getattr(sys, "_MEIPASS", BASE)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
    RES = BASE

def _early_log(msg):
    """ПРАВКА11 — след с первой секунды. Основной log() определён ниже
    и зависит от WRITE_DIR; если падение случится при импорте или в GUI
    до run(), обычный журнал не появится вовсе. Эта запись идёт сразу
    после вычисления путей, поэтому переживает любой более поздний сбой."""
    line = "%s %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    for d in (BASE, tempfile.gettempdir()):
        try:
            with open(os.path.join(d, "weather.log"), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            return
        except Exception:  # noqa
            continue

_early_log("=== старт: BASE=%s RES=%s frozen=%s ==="
           % (BASE, RES, bool(getattr(sys, "frozen", False))))

def _find(*rel):
    """Первый существующий путь из списка (сначала вложенные ресурсы, потом рядом)."""
    for r in rel:
        for root in (RES, BASE):
            p = os.path.join(root, r)
            if os.path.exists(p):
                return p
    return os.path.join(BASE, rel[0])

def _tool(name):
    """Путь к внешнему бинарнику: сначала рядом с программой (портативно),
    потом в PATH. Нужно потому, что на чистой Windows ffmpeg/ffprobe/piper
    в PATH не лежат, а в сборке лежат рядом с exe."""
    exe = name + (".exe" if os.name == "nt" else "")
    for root in (RES, BASE):
        p = os.path.join(root, exe)
        if os.path.exists(p):
            return p
    return shutil.which(name)

FFMPEG  = _tool("ffmpeg") or "ffmpeg"
FFPROBE = _tool("ffprobe") or "ffprobe"

BG_FILE  = _find("assets/WEATHER_2023_IIII.wav",
                 "Нужные файлы/WEATHER_2023_IIII.wav",
                 "WEATHER_2023_IIII.wav")
OUT_FILE = os.path.join(BASE, "ПОГОДА.wav")

# ПРАВКА3 — журнал: в сборке --windowed глушит print, поэтому события пишем
# в weather.log рядом с exe (иначе сбой синтеза неотличим от «не сработало»).
# print() обёрнут в try: при --windowed sys.stdout/stderr бывают None.
def _dir_writable(d):
    """Можно ли писать в каталог — проверяем пробным файлом.
    Нужно потому, что папка бывает доступна только на чтение (сетевая шара,
    смонтированный ISO, чужой диск), и тогда ни журнал, ни ПОГОДА.wav не создать."""
    try:
        if not d or not os.path.isdir(d):
            return False
        probe = os.path.join(d, ".wr_probe")
        with open(probe, "w") as fh:
            fh.write("1")
        os.remove(probe)
        return True
    except Exception:  # noqa
        return False

# ПРАВКА10 — каталог для ЗАПИСИ: сначала рядом с программой (портативность),
# а если туда нельзя — временный каталог. Иначе на шаре «только для чтения»
# молча пропадали и журнал, и готовый файл.
WRITE_DIR = BASE if _dir_writable(BASE) else tempfile.gettempdir()
LOG_FILE = os.path.join(WRITE_DIR, "weather.log")

def log(msg):
    global LOG_FILE
    line = "%s %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa
        # Каталог рядом с программой оказался недоступен — уводим журнал
        # во временный каталог, чтобы сбой не остался без следов.
        try:
            LOG_FILE = os.path.join(tempfile.gettempdir(), "weather.log")
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa
            pass
    try:
        print(line, file=sys.stderr)
    except Exception:  # noqa
        pass
    # Трансляция в окно интерфейса (если интерфейс подписан).
    if LOG_HOOK is not None:
        try:
            LOG_HOOK(line)
        except Exception:  # noqa
            pass

# ================================================================ параметры
# Версия и статус сборки — показываются в --show-config, /status и в журнале.
# Схема: патч (+0.0.1) — мелкие правки, минор (+0.1.0) — новый блок/функция,
# мажор (+1.0.0) — смена формата эфира. 0.x — бета, 1.0 — боевой релиз.
# Версия и статус — ЕДИНЫЙ ИСТОЧНИК: файл VERSION рядом с программой
# (см. ~/.claude/STANDARDS.md). Если файла нет — резервные значения ниже.
_FALLBACK_VERSION = "0.11.0"
_FALLBACK_STATUS  = "бета"


def _read_version_file():
    cands = []
    try:
        cands.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass
    mp = getattr(sys, "_MEIPASS", "")
    if mp:
        cands.append(mp)
    try:
        cands.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    for base in cands:
        try:
            with open(os.path.join(base, "VERSION"), encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            if len(lines) >= 2:
                return lines[0], lines[1]
        except Exception:
            continue
    return _FALLBACK_VERSION, _FALLBACK_STATUS


VERSION, STATUS = _read_version_file()
AUTHOR   = "AVAIM0013"          # псевдоним автора
APP_NAME = "WeatherCast 73.76"    # имя программы
STATION  = "Радио 7"              # радиостанция
STATION_URL = "https://radio7.ru" # сайт станции

LAT, LON = 47.2357, 39.7015          # Ростов-на-Дону
CITY     = "В Ростове"                # предложный падеж для эфира
VOICE    = "ru-RU-DmitryNeural"       # запасной: ru-RU-SvetlanaNeural

BG_DELAY_MS  = 4000                   # голос начинается через 4 с после фона
BG_VOLUME    = 0.35                   # фон тише
VOICE_VOLUME = 1.2                    # голос громче фона (сравнен со вступлением: было 1.0)
GTTS_ATEMPO  = 1.28                   # gTTS от природы медленный — ускоряем

# Open-Meteo: хост по умолчанию в этой сети отваливается по таймауту,
# historical-forecast-api работает. Порядок = порядок попыток.
API_HOSTS = [
    "https://historical-forecast-api.open-meteo.com/v1/forecast",
    "https://api.open-meteo.com/v1/forecast",
    "https://ensemble-api.open-meteo.com/v1/forecast",
]

# ================================================================ числа → слова
_UNITS = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь",
          "девять", "десять", "одиннадцать", "двенадцать", "тринадцать",
          "четырнадцать", "пятнадцать", "шестнадцать", "семнадцать",
          "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
         "семьдесят", "восемьдесят", "девяносто"]
_HUNDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот",
          "семьсот", "восемьсот", "девятьсот"]


def num_word(n):
    """Число прописью, мужской род (0..9999)."""
    n = int(round(abs(n)))
    if n == 0:
        return "ноль"
    out = []
    if n >= 1000:
        th = n // 1000
        if th == 1:
            out.append("одна тысяча")
        elif th == 2:
            out.append("две тысячи")
        else:
            out.append(num_word(th) + " тысяч")
        n %= 1000
    if n >= 100:
        out.append(_HUNDS[n // 100]); n %= 100
    if n >= 20:
        out.append(_TENS[n // 10]); n %= 10
    if n > 0:
        out.append(_UNITS[n])
    return " ".join(out)


_GEN = ["", "одного", "двух", "трёх", "четырёх", "пяти", "шести", "семи", "восьми",
        "девяти", "десяти", "одиннадцати", "двенадцати", "тринадцати", "четырнадцати",
        "пятнадцати", "шестнадцати", "семнадцати", "восемнадцати", "девятнадцати"]
_GEN_TENS = ["", "", "двадцати", "тридцати", "сорока", "пятидесяти", "шестидесяти",
             "семидесяти", "восьмидесяти", "девяноста"]


def num_gen(n):
    """Родительный падеж (для «до …», «от … до …»), 0..99."""
    n = int(round(abs(n)))
    if n < 20:
        return _GEN[n]
    if n < 100:
        t, u = n // 10, n % 10
        return _GEN_TENS[t] + (" " + _GEN[u] if u else "")
    return num_word(n)


def plural(n, one, few, many):
    n = abs(int(round(n))) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


_ORD = ["", "первое", "второе", "третье", "четвёртое", "пятое", "шестое",
        "седьмое", "восьмое", "девятое", "десятое", "одиннадцатое",
        "двенадцатое", "тринадцатое", "четырнадцатое", "пятнадцатое",
        "шестнадцатое", "семнадцатое", "восемнадцатое", "девятнадцатое",
        "двадцатое"]


def day_ord(n):
    """Порядковое числительное среднего рода для даты: «первое», «двадцать
    первое», «тридцатое»."""
    n = int(n)
    if n <= 20:
        return _ORD[n]
    if n < 30:
        return "двадцать " + _ORD[n - 20]
    if n == 30:
        return "тридцатое"
    return "тридцать " + _ORD[n - 30]


# ================================================================ ветер
_WIND = ["северный", "северо-восточный", "восточный", "юго-восточный",
         "южный", "юго-западный", "западный", "северо-западный"]


def wind_dir(deg):
    if deg is None:
        return "переменный"
    return _WIND[int((float(deg) % 360) / 45.0 + 0.5) % 8]


# ================================================================ WMO
# Коды WMO → одно общее слово (требование эфира: без уточнений вроде
# «преимущественно», «с прояснениями», «сильный», «ледяной» и т.п.).
WMO = {
    0: ("ясно", False), 1: ("ясно", False),
    2: ("облачно", False), 3: ("пасмурно", False),
    45: ("туман", False), 48: ("туман", False),
    51: ("морось", True), 53: ("морось", True), 55: ("морось", True),
    56: ("морось", True), 57: ("морось", True),
    61: ("дождь", True), 63: ("дождь", True), 65: ("дождь", True),
    66: ("дождь", True), 67: ("дождь", True),
    71: ("снег", True), 73: ("снег", True), 75: ("снег", True),
    77: ("снег", True),
    80: ("дождь", True), 81: ("дождь", True), 82: ("дождь", True),
    85: ("снег", True), 86: ("снег", True),
    95: ("гроза", True), 96: ("гроза", True), 99: ("гроза", True),
}


def wmo(code):
    """(описание, есть_осадки); неизвестный код → «облачно» (в словаре
    WMO теперь только одно общее слово на код, поэтому и запасное — оттуда)."""
    if code is None:
        return "облачно", False
    return WMO.get(int(code), ("облачно", False))


def _precip_type(codes):
    """Тип осадков по списку кодов WMO: «гроза» > «снег» > «дождь».
    None — осадков нет. Нужно для отдельного предложения про осадки завтра:
    доминирующий код дня может не назвать кратковременный дождь или снег."""
    kinds = set()
    for c in codes:
        if c is None:
            continue
        t, wet = wmo(c)
        if not wet:
            continue
        if t == "гроза":
            kinds.add("гроза")
        elif t == "снег":
            kinds.add("снег")
        else:
            kinds.add("дождь")
    for k in ("гроза", "снег", "дождь"):
        if k in kinds:
            return k
    return None


# ================================================================ сеть
def _urlopen_ipv4(req, timeout):
    """urlopen с принудительным IPv4. Python предпочитает AAAA-запись, и на
    сетях с «висящим» IPv6-маршрутом SSL-handshake не успевает за таймаут —
    ровно этот сбой случился на чужом ПК (handshake operation timed out)."""
    import socket
    orig = socket.getaddrinfo

    def v4(host, port, family=0, type=0, proto=0, flags=0):
        return orig(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = v4
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    finally:
        socket.getaddrinfo = orig


def _open(req, timeout, force_v4):
    """urlopen; force_v4=True — только IPv4, иначе системное поведение."""
    if force_v4:
        return _urlopen_ipv4(req, timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def _fetch_openmeteo():
    params = {
        "latitude": LAT, "longitude": LON,
        "current": "temperature_2m,weather_code,wind_speed_10m,wind_direction_10m,"
                   "pressure_msl,relative_humidity_2m",
        "hourly": "temperature_2m,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m,pressure_msl,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,wind_direction_10m_dominant",
        "wind_speed_unit": "ms",          # иначе Open-Meteo отдаёт км/ч (×3.6)
        "timezone": "Europe/Moscow",
        "forecast_days": 2,
    }
    qs = urllib.parse.urlencode(params)
    last = None
    # Сначала IPv4 (обходит «висящий» IPv6), затем системный порядок —
    # чтобы работать и в IPv6-only сети.
    for host in API_HOSTS:
        for force_v4 in (True, False):
            try:
                req = urllib.request.Request(host + "?" + qs,
                                             headers={"User-Agent": "WeatherCast-73.76/1.0"})
                with _open(req, timeout=20, force_v4=force_v4) as r:
                    if r.status == 200:
                        return json.loads(r.read().decode("utf-8"))
                    last = "HTTP %s" % r.status
            except Exception as e:  # noqa
                last = "%s: %s" % (host, e)
    raise RuntimeError("Open-Meteo недоступен: %s" % last)


# ---------------------------------------------------------------- met.no (резерв)
# На чужой сети провайдер может резать/сбрасывать все хосты Open-Meteo
# (WinError 10054 «удалённый хост разорвал подключение»). met.no — независимый
# источник; его ответ приводим к структуре Open-Meteo, чтобы build_text не менялся.
_METNO_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
_MSK = datetime.timezone(datetime.timedelta(hours=3))   # Europe/Moscow, без DST


def _metno_code(sym):
    """symbol_code met.no → код WMO (крупно)."""
    s = (sym or "").lower()
    if "thunder" in s:
        return 95
    if "snow" in s:
        return 75 if "heavy" in s else 71
    if "sleet" in s:
        return 66
    if "rain" in s:
        return 65 if "heavy" in s else 61
    if "fog" in s:
        return 45
    if "cloudy" in s:
        return 3 if s.startswith("cloudy") else 2
    if "clearsky" in s:
        return 0
    if "fair" in s:
        return 1
    return 3


def _metno_sev(code):
    """«Тяжесть» кода WMO — чтобы выбрать код дня (осадки важнее облачности)."""
    if code is None:
        return 0
    if code >= 95:
        return 5
    if code in (71, 73, 75, 85, 86):
        return 4
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return 3
    if code in (51, 53, 55, 56, 57):
        return 2
    if code == 45:
        return 1
    return 0


def _metno_dt(ts):
    """ISO-время met.no (UTC, с Z) → наивное локальное Europe/Moscow."""
    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(_MSK).replace(tzinfo=None)


def _fetch_metno():
    qs = urllib.parse.urlencode({"lat": LAT, "lon": LON})
    last = None
    raw = None
    for force_v4 in (True, False):
        try:
            req = urllib.request.Request(
                _METNO_URL + "?" + qs,
                headers={"User-Agent": "WeatherCast-73.76 https://radio7.ru"})
            with _open(req, timeout=25, force_v4=force_v4) as r:
                if r.status != 200:
                    last = "HTTP %s" % r.status
                    continue
                raw = json.loads(r.read().decode("utf-8"))
                break
        except Exception as e:  # noqa
            last = str(e)
    if raw is None:
        raise RuntimeError("met.no: %s" % last)

    ts = raw.get("properties", {}).get("timeseries", [])
    if not ts:
        raise RuntimeError("met.no: пустой timeseries")

    hourly = {"time": [], "temperature_2m": [], "weather_code": [],
              "wind_speed_10m": [], "wind_direction_10m": [],
              "wind_gusts_10m": [], "pressure_msl": [], "relative_humidity_2m": []}
    for point in ts:
        d = point.get("data", {})
        inst = d.get("instant", {}).get("details", {})
        sym = None
        for key in ("next_1_hours", "next_6_hours", "next_12_hours"):
            s = d.get(key, {}).get("summary", {}).get("symbol_code")
            if s:
                sym = s
                break
        hourly["time"].append(_metno_dt(point["time"]).strftime("%Y-%m-%dT%H:%M:%S"))
        hourly["temperature_2m"].append(inst.get("air_temperature"))
        hourly["weather_code"].append(_metno_code(sym))
        hourly["wind_speed_10m"].append(inst.get("wind_speed"))
        hourly["wind_direction_10m"].append(inst.get("wind_from_direction"))
        hourly["wind_gusts_10m"].append(None)
        hourly["pressure_msl"].append(inst.get("air_pressure_at_sea_level"))
        hourly["relative_humidity_2m"].append(inst.get("relative_humidity"))

    # Сутки по датам в порядке появления: [0] сегодня, [1] завтра, ...
    day_idx = {}
    for i, t in enumerate(hourly["time"]):
        day_idx.setdefault(t[:10], []).append(i)

    daily = {"time": [], "temperature_2m_max": [], "temperature_2m_min": [],
             "weather_code": [], "wind_direction_10m_dominant": []}
    for d in sorted(day_idx):
        idxs = day_idx[d]
        temps = [hourly["temperature_2m"][i] for i in idxs
                 if hourly["temperature_2m"][i] is not None]
        codes = [hourly["weather_code"][i] for i in idxs]
        daily["time"].append(d)
        daily["temperature_2m_max"].append(max(temps) if temps else None)
        daily["temperature_2m_min"].append(min(temps) if temps else None)
        daily["weather_code"].append(max(codes, key=_metno_sev) if codes else None)
        daily["wind_direction_10m_dominant"].append(None)

    cur = {
        "temperature_2m": hourly["temperature_2m"][0],
        "weather_code": hourly["weather_code"][0],
        "wind_speed_10m": hourly["wind_speed_10m"][0],
        "wind_direction_10m": hourly["wind_direction_10m"][0],
        "pressure_msl": hourly["pressure_msl"][0],
        "relative_humidity_2m": hourly["relative_humidity_2m"][0],
    }
    return {"current": cur, "hourly": hourly, "daily": daily}


def fetch_weather():
    """Прогноз для Ростова. Сначала Open-Meteo, при полном отказе — met.no."""
    try:
        return _fetch_openmeteo()
    except Exception as e:  # noqa
        om_err = str(e)
    try:
        return _fetch_metno()
    except Exception as e:  # noqa
        raise RuntimeError("Погодные API недоступны — %s | %s" % (om_err, e))


# ================================================================ текст прогноза
def _temp(t):
    """Температура отдельным числом: «пять», «минус пять». «Плюс» не проговариваем."""
    return ("минус " if t < 0 else "") + num_word(abs(t))


def _temp_range(lo, hi, gen=False):
    """Температура словами. Диапазон — «от … до …», а не тире: тире TTS
    читает как обрыв. Положительные — без «плюс».
    gen оставлен ради совместимости вызовов и на результат не влияет."""
    lo, hi = int(round(lo)), int(round(hi))
    if lo == hi:
        return ("минус " if lo < 0 else "") + num_word(abs(lo))
    if lo >= 0:
        return "от %s до %s" % (num_gen(lo), num_gen(hi))
    if hi < 0:
        return "от минус %s до минус %s" % (num_gen(-lo), num_gen(-hi))
    return "от минус %s до %s" % (num_gen(-lo), num_gen(hi))


def _deg(hi, ranged):
    """Слово «градус» после температуры: в диапазоне («до двадцати одного
    градуса») — родительный, отдельно стоящее — именительный («двадцать
    градусов»)."""
    return (plural(hi, "градуса", "градусов", "градусов") if ranged
            else plural(hi, "градус", "градуса", "градусов"))


def _deg_range(lo, hi):
    """Слово «градус» после диапазона «от X до Y». Здесь всегда родительный
    множественного — «от тринадцати до двадцати четырёх градусов»; для
    одиночного значения (lo == hi) — по числу."""
    if int(round(lo)) == int(round(hi)):
        return plural(hi, "градус", "градуса", "градусов")
    return "градусов"


def _wind_speed(wmin, wmax):
    """Скорость ветра словами: одно значение — «два метра в секунду»,
    диапазон — «от двух до трёх метров в секунду»."""
    if wmin is None and wmax is None:
        return None
    if wmin is None:
        wmin = wmax
    if wmax is None:
        wmax = wmin
    a, b = int(round(wmin)), int(round(wmax))
    if a == b:
        return "%s %s в секунду" % (num_word(b), plural(b, "метр", "метра", "метров"))
    return "от %s до %s %s в секунду" % (
        num_gen(a), num_gen(b), plural(b, "метра", "метров", "метров"))


def _hours(hourly, day_off, h0, h1):
    """Индексы часов за сутки (day_off дней от сегодня) в интервале [h0; h1)."""
    base = datetime.date.today() + datetime.timedelta(days=day_off)
    times = hourly.get("time", [])
    return [i for i, ts in enumerate(times)
            if datetime.datetime.fromisoformat(ts).date() == base
            and h0 <= datetime.datetime.fromisoformat(ts).hour < h1]


def _pick(hourly, key, idx, fn=min):
    vals = [hourly[key][i] for i in idx if hourly.get(key) and hourly[key][i] is not None]
    return fn(vals) if vals else None


def _pick_mid(hourly, key, idx):
    """Среднее значение параметра за набор часов (давление/влажность)."""
    vals = [hourly[key][i] for i in idx if hourly.get(key) and hourly[key][i] is not None]
    return (sum(vals) / len(vals)) if vals else None


def build_text(data):
    """Список (приоритет, предложение). Меньший приоритет — важнее, его оставляем
    при нехватке времени (см. docs/TEXT-RULES.md).
    Порядок в эфире: Сейчас -> Сегодня -> Ночью -> Завтра.
    Ветер, давление и влажность — детали дня, низкий приоритет (режутся первыми).
       0 — сейчас (ядро, не режется)           3 — влажность
       1 — температура+погода дня/ночи/завтра  4 — давление
       2 — ветер (только скорость, без порывов) 5 — осадки завтра (низший)
    Направление ветра не называем — только скорость."""
    cur, daily, hourly = data.get("current", {}), data.get("daily", {}), data.get("hourly", {})
    out = []

    # 1. Сейчас — только температура (ядро, не режется). Погоду в блоке
    #    «сейчас» не называем — по требованию эфира.
    t = cur.get("temperature_2m")
    if t is not None:
        out.append((0, "%s сейчас %s %s." % (
            CITY, _temp(t),
            plural(t, "градус", "градуса", "градусов"))))

    # 2. Сегодня днём (9:00–19:00): температура+погода, ветер, давление, влажность
    di = _hours(hourly, 0, 9, 19)
    if di:
        lo = _pick(hourly, "temperature_2m", di, min)
        hi = _pick(hourly, "temperature_2m", di, max)
        w, wet = wmo(_pick(hourly, "weather_code", di, max))
        if lo is not None and hi is not None:
            out.append((1, "Сегодня днём %s %s, %s." % (
                _temp_range(lo, hi), _deg_range(lo, hi),
                w)))
            wmin = _pick(hourly, "wind_speed_10m", di, min)
            wmax = _pick(hourly, "wind_speed_10m", di, max)
            wtxt = _wind_speed(wmin, wmax)
            if wtxt:
                out.append((2, "Ветер %s." % wtxt))
            h = _pick_mid(hourly, "relative_humidity_2m", di)
            if h is not None:
                h = int(round(h))
                out.append((3, "Относительная влажность %s %s." % (
                    num_word(h), plural(h, "процент", "процента", "процентов"))))
            p = _pick_mid(hourly, "pressure_msl", di)
            if p is not None:
                p = int(round(p * 0.750062))
                out.append((4, "Атмосферное давление %s %s ртутного столба." % (
                    num_word(p), plural(p, "миллиметр", "миллиметра", "миллиметров"))))

    # 3. Ночью (21:00–07:00): температура и погода, затем (низший приоритет)
    #    влажность и давление — заполняют эфир при запасе времени.
    ni = _hours(hourly, 0, 21, 24) + _hours(hourly, 1, 0, 7)
    if ni:
        lo = _pick(hourly, "temperature_2m", ni, min)
        hi = _pick(hourly, "temperature_2m", ni, max)
        w, wet = wmo(_pick(hourly, "weather_code", ni, max))
        if lo is not None and hi is not None:
            out.append((1, "Ночью %s %s, %s." % (
                _temp_range(lo, hi),
                plural(hi, "градуса", "градусов", "градусов"),
                w)))
            h = _pick_mid(hourly, "relative_humidity_2m", ni)
            if h is not None:
                h = int(round(h))
                out.append((6, "Относительная влажность %s %s." % (
                    num_word(h), plural(h, "процент", "процента", "процентов"))))
            p = _pick_mid(hourly, "pressure_msl", ni)
            if p is not None:
                p = int(round(p * 0.750062))
                out.append((7, "Атмосферное давление %s %s ртутного столба." % (
                    num_word(p), plural(p, "миллиметр", "миллиметра", "миллиметров"))))

    # 4. Завтра: температура и погода. Дату не называем, ветер/давление/
    #    влажность не даём. В КОНЕЦ блока — отдельное предложение про осадки
    #    самым низким приоритетом (5): при нехватке времени уходит первым,
    #    при запасе — добирает эфир.
    dates = daily.get("time", [])
    if len(dates) >= 2:
        lo, hi = daily["temperature_2m_min"][1], daily["temperature_2m_max"][1]
        w, wet = wmo(daily.get("weather_code", [None, None])[1])
        out.append((1, "Завтра %s %s, %s." % (
            _temp_range(lo, hi),
            _deg_range(lo, hi),
            w)))
        # Осадки за ДЕНЬ завтра (9:00–19:00, как блок «Сегодня днём») — по
        # часовым кодам: доминирующий код дня может не назвать кратковременный
        # дождь/снег. Ночные часы завтра в расчёт не берём. Не дублируем уже
        # сказанное в основной фразе.
        d1_all = _hours(hourly, 1, 9, 19)
        codes = [hourly["weather_code"][i] for i in d1_all
                 if hourly.get("weather_code") and hourly["weather_code"][i] is not None]
        ptype = _precip_type(codes) if codes else None
        if ptype and ptype not in w:
            out.append((5, "%s %s." % ("Возможна" if ptype == "гроза" else "Возможен", ptype)))
        elif not ptype and not wet:
            out.append((5, "Без осадков."))
        # Детали завтра (низший приоритет): влажность и давление — заполняют
        # эфир при запасе времени, при нехватке уходят первыми.
        h = _pick_mid(hourly, "relative_humidity_2m", d1_all)
        if h is not None:
            h = int(round(h))
            out.append((6, "Относительная влажность %s %s." % (
                num_word(h), plural(h, "процент", "процента", "процентов"))))
        p = _pick_mid(hourly, "pressure_msl", d1_all)
        if p is not None:
            p = int(round(p * 0.750062))
            out.append((7, "Атмосферное давление %s %s ртутного столба." % (
                num_word(p), plural(p, "миллиметр", "миллиметра", "миллиметров"))))

    return out


def trim(pri_sents, budget_words):
    """Оставляет важнейшие фразы в пределах бюджета слов, сохраняя порядок."""
    order = sorted(range(len(pri_sents)), key=lambda i: pri_sents[i][0])
    keep, used = [False] * len(pri_sents), 0
    for i in order:
        w = len(pri_sents[i][1].split())
        if used + w <= budget_words or not any(keep):
            keep[i] = True; used += w
    return [pri_sents[i][1] for i in range(len(pri_sents)) if keep[i]]


# ================================================================ медиа
def duration(path):
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path],
                           capture_output=True, text=True, check=True,
                           creationflags=NOWIN)
        return float(r.stdout.strip())
    except Exception:  # noqa
        return None


def to_wav(src, dst):
    try:
        subprocess.run([FFMPEG, "-y", "-i", src, "-ar", "44100", "-ac", "2", dst],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=NOWIN)
    except Exception as e:  # noqa
        log("[конверт] сбой ffmpeg: %s (dst=%s)" % (e, dst))
        raise


PAUSE_MAX_S  = 0.40   # тишина длиннее — считаем большой паузой
PAUSE_KEEP_S = 0.12   # и оставляем от неё столько


def shorten_pauses(src):
    """Подрезает длинные паузы в речи: блоки идут плотнее (жалоба эфира на
    большие паузы). Режет только тишину длиннее PAUSE_MAX_S, оставляя
    PAUSE_KEEP_S. Работает поверх любого движка."""
    out = os.path.join(os.path.dirname(src), "voice_short.wav")
    af = ("silenceremove=stop_periods=-1:stop_duration=%.2f:"
          "stop_threshold=-40dB:stop_silence=%.2f" % (PAUSE_MAX_S, PAUSE_KEEP_S))
    try:
        subprocess.run([FFMPEG, "-y", "-i", src, "-filter:a", af,
                        "-ar", "44100", "-ac", "2", out],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=NOWIN)
        return out
    except Exception as e:  # noqa
        log("[паузы] сбой ffmpeg: %s" % e)
        return src


def _atempo(src, factor):
    """Ускоряет дорожку без изменения тона (для медленного gTTS)."""
    out = os.path.join(os.path.dirname(src), "voice_tempo.wav")
    try:
        subprocess.run([FFMPEG, "-y", "-i", src, "-filter:a", "atempo=%.4f" % factor,
                        "-ar", "44100", "-ac", "2", out],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=NOWIN)
        return out
    except Exception as e:  # noqa
        log("[темп] сбой ffmpeg: %s" % e)
        return src


# ПРАВКА4
# ================================================================ синтез речи
# 1) Edge TTS — основной. Пустой ответ (NoAudioReceived) случается непостоянно,
#    поэтому на каждую фразу несколько попыток и перебор голосов.
EDGE_TRIES = 6
EDGE_VOICES = [VOICE, "ru-RU-SvetlanaNeural"]

# Порядок и включённость синтезаторов задаёт интерфейс (weather_gui.py) или
# конфиг. Пустой список = «все по умолчанию». Piper берёт модель отсюда,
# если она задана; иначе ищет .onnx в voices/ и рядом со скриптом.
SYNTH_CHAIN = ["Edge TTS", "gTTS", "Piper"]
PIPER_MODEL = None


def synth_edge(sentences, mp3):
    """Edge TTS: отправляем ВЕСЬ текст одной фразой — один запрос вместо N.
    Паузы между предложениями расставляет сам Edge (естественные, короткие),
    поэтому ручная склейка и подрезка тишины больше не нужны.
    NoAudioReceived у Edge непостоянен — поэтому несколько попыток."""
    try:
        import edge_tts
    except ImportError:
        return False

    text = " ".join(sentences)

    async def run():
        for v in dict.fromkeys(EDGE_VOICES):
            for k in range(EDGE_TRIES):
                try:
                    await edge_tts.Communicate(text, v).save(mp3)
                    if os.path.getsize(mp3) > 0:
                        log("[edge-tts] ок: голос %s, попытка %d, %.1f кБ"
                            % (v, k + 1, os.path.getsize(mp3) / 1024.0))
                        return True
                except Exception as e:  # noqa
                    log("[edge-tts] %s: %s" % (type(e).__name__, str(e)[:100]))
                await asyncio.sleep(1.5 * (k + 1))
        return False

    try:
        return asyncio.run(run())
    except Exception as e:  # noqa
        log("[edge-tts] сбой: %s" % e)
        return False


# 2) gTTS — сетевой, но без ключей.
def synth_gtts(sentences, mp3):
    try:
        from gtts import gTTS
    except ImportError:
        return False
    try:
        gTTS(text=" ".join(sentences), lang="ru", slow=False).save(mp3)
        return os.path.getsize(mp3) > 0
    except Exception as e:  # noqa
        log("[gTTS] %s" % e)
        return False


# 3) Piper — полностью локальный, резерв. Модель .onnx ищется в voices/ и рядом.
def synth_piper(sentences, wav):
    # Бинарник ищем как ffmpeg/ffprobe: сначала рядом с программой (в сборке
    # piper.exe лежит в _internal), потом в PATH. shutil.which на чистой
    # Windows PATH пуст — без _tool() резервный синтезатор не находился.
    exe = _tool("piper") or shutil.which("piper")
    if not exe:
        log("[piper] бинарник не найден рядом с программой и в PATH")
        return False
    model = PIPER_MODEL
    if model and not os.path.exists(model):
        log("[piper] модель из настроек не найдена: %s" % model)
        model = None
    if not model:
        for d in (os.path.join(BASE, "voices"), os.path.join(RES, "voices"), BASE, RES):
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if fn.endswith(".onnx"):
                        model = os.path.join(d, fn); break
            if model:
                break
    if not model:
        return False
    try:
        p = subprocess.run([exe, "--model", model, "--output_file", wav],
                           input=" ".join(sentences).encode("utf-8"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=NOWIN)
        return p.returncode == 0 and os.path.getsize(wav) > 0
    except Exception as e:  # noqa
        log("[piper] %s" % e)
        return False


def synthesize(sentences, chain=None):
    """Пробует генераторы в заданном порядке; возвращает путь к WAV с голосом.
    chain — список имён в порядке приоритета (None → SYNTH_CHAIN)."""
    tmp = tempfile.mkdtemp(prefix="wtts_out_")
    wav = os.path.join(tmp, "voice.wav")
    mp3 = os.path.join(tmp, "voice.mp3")

    registry = {
        "Edge TTS": lambda: synth_edge(sentences, mp3),
        "gTTS": lambda: synth_gtts(sentences, mp3),
        "Piper": lambda: synth_piper(sentences, wav),
    }
    if chain is None:
        chain = SYNTH_CHAIN or list(registry)
    skipped = []
    for name in chain:
        _check_cancel()
        fn = registry.get(name)
        if not fn:
            continue
        if fn():
            if name != "Piper":
                to_wav(mp3, wav)
            if name == "gTTS" and GTTS_ATEMPO > 1.001:
                wav = _atempo(wav, GTTS_ATEMPO)
            wav = shorten_pauses(wav)
            log("[синтез] %s, фраз: %d" % (name, len(sentences)))
            LAST_RESULT.clear()
            LAST_RESULT.update({"used": name, "skipped": list(skipped),
                                "total": len(chain)})
            return wav
        skipped.append(name)
    LAST_RESULT.clear()
    LAST_RESULT.update({"used": None, "skipped": list(skipped), "total": len(chain)})
    raise RuntimeError("Ни один синтезатор не сработал (%s)" % ", ".join(chain))


# ================================================================ подгонка и микс
def voice_budget():
    """Сколько секунд отведено голосу: фон минус вступление минус запас."""
    bg = duration(BG_FILE) if BG_FILE else None
    return max(5.0, bg - BG_DELAY_MS / 1000.0 - 0.5) if bg else 30.0


def fit(pri_sents, target, chain=None):
    """Сначала режем текст по приоритету, затем при необходимости слегка ускоряем.
    Скорость речи измеряется по факту — работает для любого движка."""
    _check_cancel()
    full = [s for _, s in pri_sents]
    wav = synthesize(full, chain)
    dur = duration(wav)
    if dur and dur > target:
        words = sum(len(s.split()) for s in full)
        sel = trim(pri_sents, target * (words / dur))
        if len(sel) < len(full):
            log("[подгонка] фраз %d → %d (было %.1f с)" % (len(full), len(sel), dur))
            wav, dur = synthesize(sel, chain), None
            dur = duration(wav)
    if dur and dur > target:
        atempo = min(dur / target, 1.15)          # не быстрее +15%
        if atempo > 1.001:
            out = os.path.join(os.path.dirname(wav), "voice_fit.wav")
            subprocess.run([FFMPEG, "-y", "-i", wav, "-filter:a", "atempo=%.4f" % atempo,
                            "-ar", "44100", "-ac", "2", out],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wav, dur = out, duration(out)
    if dur:
        log("[подгонка] голос %.1f с (цель %.1f с)" % (dur, target))
    return wav


def mix(voice_wav, out_file=None):
    """Фон + голос с задержкой; голос чуть громче фона → ПОГОДА.wav.
    Диагностика: ffmpeg запускается с захватом stderr — иначе сбой микса
    неотличим от «не сработало» (журнал молчит). При сбое — аварийный
    даунмикс: пишем только голос, лишь бы файл для эфира был."""
    _check_cancel()
    out_file = out_file or OUT_FILE
    log("[микс] фон=%s голос=%s → %s" % (BG_FILE, voice_wav, out_file))
    if not BG_FILE or not os.path.exists(BG_FILE):
        log("[микс] фон не найден — пишу только голос")
        to_wav(voice_wav, out_file)
        return
    fc = ("[0:a]volume=%.2f[bg];"
          "[1:a]volume=%.2f,adelay=%d|%d[vo];"
          "[bg][vo]amix=inputs=2:duration=first:dropout_transition=0[out]"
          % (BG_VOLUME, VOICE_VOLUME, BG_DELAY_MS, BG_DELAY_MS))
    try:
        p = subprocess.run([FFMPEG, "-y", "-i", BG_FILE, "-i", voice_wav,
                            "-filter_complex", fc, "-map", "[out]",
                            "-ar", "44100", "-ac", "2", out_file],
                           capture_output=True, text=True, creationflags=NOWIN)
    except Exception as e:  # noqa
        log("[микс] сбой вызова ffmpeg: %s" % e)
        to_wav(voice_wav, out_file)
        return
    if p.returncode != 0:
        log("[микс] ffmpeg rc=%d: %s" % (p.returncode, (p.stderr or "").strip()[-600:]))
        log("[микс] аварийно: пишу только голос без фона")
        to_wav(voice_wav, out_file)
        return
    log("[микс] готово: %s (%.0f кБ)" % (out_file, os.path.getsize(out_file) / 1024.0))


# ================================================================ main
def run(out_file=None, chain=None):
    out_file = out_file or OUT_FILE
    # Относительный путь (как в config.json: "ПОГОДА.wav") привязываем к каталогу
    # программы, а не к текущему каталогу процесса: GUI мог быть запущен ярлыком
    # или планировщиком с другим CWD, и тогда ffmpeg не мог записать файл.
    if not os.path.isabs(out_file):
        out_file = os.path.join(BASE, out_file)
    # Если заданный каталог недоступен (другая буква диска, папка не смонтирована)
    # — пишем рядом с программой: портативность важнее конкретного пути.
    d = os.path.dirname(out_file)
    if d and not os.path.isdir(d):
        out_file = os.path.join(BASE, os.path.basename(out_file))
        log("[путь] каталог недоступен, пишу рядом с программой: %s" % out_file)
    d = os.path.dirname(out_file)
    if d and not _dir_writable(d):
        alt = os.path.join(WRITE_DIR, os.path.basename(out_file))
        log("[путь] в %s писать нельзя, пишу в %s" % (d, alt))
        out_file = alt
    LAST_RESULT.clear()
    reset_cancel()
    log("%s v%s (%s), автор %s, для %s (%s)" % (APP_NAME, VERSION, STATUS, AUTHOR, STATION, STATION_URL))
    log("[1/3] Open-Meteo…")
    data = fetch_weather()
    _check_cancel()
    log("[2/3] Текст…")
    pri = build_text(data)
    _check_cancel()
    target = voice_budget()
    log("--- ТЕКСТ ПРОГНОЗА ---")
    for _, s in pri:
        log(s)
    log("--- %d сл., лимит голоса %.1f с ---"
        % (sum(len(s.split()) for _, s in pri), target))
    log("[3/3] Синтез и микс…")
    voice = fit(pri, target, chain)
    # Сколько секунд занял голос из отведённого окна — файл фиксирован по
    # длительности фона, а вот заполнение окна меняется от текста к тексту.
    vd = duration(voice)
    LAST_RESULT.update({"voice_dur": round(vd, 1) if vd else None,
                        "budget": round(target, 1)})
    mix(voice, out_file)
    log("Готово: %s" % out_file)
    return out_file


# ================================================================ управление извне
# Программой можно управлять без окна: из командной строки (планировщик
# Windows, скрипты) и по HTTP (см. weather_gui.py --serve). Разделение простое:
# здесь — разбор настроек и генерация, там — сеть.


def load_config(path=None):
    """config.json рядом с программой (или свой путь). Битого файла не боимся:
    None равнозначен «настроек нет, работаем по умолчанию»."""
    path = path or os.path.join(BASE, "config.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa
        return None


def apply_config(cfg):
    """Настройки из config.json → глобальные параметры модуля.
    Возвращает (out_file, chain); пустые поля игнорируются."""
    global VOICE, EDGE_VOICES, PIPER_MODEL
    if not cfg:
        return None, None
    out = cfg.get("out_file")
    chain, voices = None, {}
    synth = cfg.get("synth")
    if isinstance(synth, list):
        names = []
        for s in synth:
            if not isinstance(s, dict) or not s.get("name"):
                continue
            voices[s["name"]] = s.get("voice") or ""
            if s.get("enabled"):
                names.append(s["name"])
        if names:
            chain = names
    if voices.get("Edge TTS"):
        VOICE = voices["Edge TTS"]
        EDGE_VOICES = [VOICE] + [v for v in EDGE_VOICES if v != VOICE]
    if voices.get("Piper"):
        PIPER_MODEL = voices["Piper"]
    return out, chain


def config_view():
    """Текущее состояние настроек — для машинного вывода (--show-config, /status)."""
    return {
        "app": APP_NAME,
        "version": VERSION,
        "status": STATUS,
        "author": AUTHOR,
        "out_file": OUT_FILE,
        "synth_chain": SYNTH_CHAIN,
        "edge_voice": VOICE,
        "edge_voices": EDGE_VOICES,
        "piper_model": PIPER_MODEL,
        "base": BASE,
        "background": BG_FILE,
        "ffmpeg": FFMPEG,
        "ffprobe": FFPROBE,
    }


# ================================================================ журнал прогонов
# Общий для CLI и GUI: исход каждого запуска (какой движок сработал, что
# пропущено) и защита от двойного срабатывания слота. Лежит ОТДЕЛЬНО от
# config.json: config.json — пользовательские настройки (правит только GUI),
# а это — служебное состояние, которое пишут и GUI, и CLI из планировщика.

RUNSTATE = os.path.join(BASE, "runstate.json")


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa
        return {}


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        return True
    except Exception as e:  # noqa
        log("[runstate] не удалось записать %s: %s" % (path, e))
        return False


def read_runstate(path=None):
    """Служебное состояние прогонов: last_run, slot_results, fired."""
    return _load_json(path or RUNSTATE)


def write_runstate(data, path=None):
    return _save_json(path or RUNSTATE, data)


def valid_slot(s):
    """Проверка формата HH:MM (00-23, 00-59) для --slot: без неё мусорный
    аргумент попадал и в ключ fired, и в slot_results."""
    try:
        hh, mm = (int(x) for x in str(s).strip().split(":"))
    except Exception:  # noqa
        return False
    return 0 <= hh <= 23 and 0 <= mm <= 59


def record_run(ok, path=None, err=None, slot=None, *, when=None, runstate=None):
    """Записать исход прогона — единая точка для CLI и GUI.
    slot — 'HH:MM' слота, если запуск был по расписанию."""
    st = read_runstate(runstate)
    now = when or datetime.datetime.now()
    lr = {
        "ts": now.isoformat(timespec="seconds"),
        "when": now.strftime("%d.%m, %H:%M"),
        "ok": bool(ok),
        "path": os.path.basename(path) if path else "ПОГОДА.wav",
        "size": os.path.getsize(path) if (path and os.path.exists(path)) else 0,
        "err": (err or "")[:200],
        "used": LAST_RESULT.get("used"),
        "skipped": list(LAST_RESULT.get("skipped") or []),
        "total": LAST_RESULT.get("total") or 0,
        "voice_dur": LAST_RESULT.get("voice_dur"),
        "budget": LAST_RESULT.get("budget"),
    }
    st["last_run"] = lr
    if slot:
        st.setdefault("slot_results", {})[slot] = {
            "ts": lr["ts"], "ok": lr["ok"], "used": lr["used"],
            "skipped": lr["skipped"], "total": lr["total"],
        }
    write_runstate(st, runstate)
    return lr


def forget_slot(slot, runstate=None):
    """Забыть всё про слот: и исход, и отметку «уже сработал».

    Без чистки fired удалённый и заново добавленный слот на то же время
    сегодня уже не сработал бы — снаружи это выглядело как поломка.
    """
    st = read_runstate(runstate)
    changed = st.get("slot_results", {}).pop(slot, None) is not None
    fired = st.get("fired") or {}
    stale = [k for k in fired if k.endswith(" " + slot)]
    for k in stale:
        fired.pop(k, None)
    if stale:
        changed = True
    if changed:
        write_runstate(st, runstate)


def slot_fired(key, runstate=None):
    """True, если слот уже срабатывал (key = 'YYYY-MM-DD HH:MM')."""
    return bool(read_runstate(runstate).get("fired", {}).get(key))


def mark_slot(key, runstate=None):
    """Отметить слот сработавшим — общий флаг для GUI и CLI."""
    st = read_runstate(runstate)
    fired = st.setdefault("fired", {})
    fired[key] = datetime.datetime.now().isoformat(timespec="seconds")
    if len(fired) > 400:                    # держим только свежие
        for k in sorted(fired)[:len(fired) - 400]:
            fired.pop(k, None)
    write_runstate(st, runstate)


def selftest():
    """Проверка окружения без записи эфирного файла: ffmpeg/ffprobe, сеть, синтез.
    Возвращает dict для машинного вывода (--selftest --json)."""
    checks = {}
    for name, tool in (("ffmpeg", FFMPEG), ("ffprobe", FFPROBE)):
        try:
            r = subprocess.run([tool, "-version"], capture_output=True, text=True, timeout=15)
            checks[name] = (r.returncode == 0)
        except Exception as e:  # noqa
            checks[name] = False
            checks["%s_err" % name] = str(e)[:120]
    try:
        data = fetch_weather()
        checks["network"] = True
        checks["sentences"] = len(build_text(data))
    except Exception as e:  # noqa
        checks["network"] = False
        checks["network_err"] = str(e)[:160]
    try:
        wav = synthesize(["Проверка синтеза речи."])
        checks["synth"] = bool(wav and os.path.getsize(wav) > 0)
    except Exception as e:  # noqa
        checks["synth"] = False
        checks["synth_err"] = str(e)[:160]
    checks["ok"] = all(checks.get(k) for k in ("ffmpeg", "ffprobe", "network", "synth"))
    return checks


def generate(out_file=None, chain=None, cfg=None):
    """Единая точка входа для CLI и HTTP: применить настройки и сгенерировать файл."""
    out_cfg, chain_cfg = apply_config(cfg if cfg is not None else load_config())
    path = run(out_file or out_cfg, chain if chain is not None else chain_cfg)
    return {
        "ok": True,
        "path": path,
        "size": os.path.getsize(path) if path and os.path.exists(path) else 0,
        "duration": duration(path) if path else None,
    }


def cli(argv=None):
    """Командная строка. Примеры:
        weather.py --run
        weather.py --run --out D:\\radio\\ПОГОДА.wav --json
        weather.py --run --chain "Edge TTS,gTTS" --voice ru-RU-SvetlanaNeural
        weather.py --show-config
    Без аргументов — прежнее поведение: сгенерировать файл по config.json."""
    global SYNTH_CHAIN, VOICE, EDGE_VOICES, PIPER_MODEL
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        return run()

    ap = argparse.ArgumentParser(
        prog="weather.py",
        description="WeatherCast 73.76: прогноз погоды для Радио 7 (Ростов-на-Дону) → ПОГОДА.wav")
    ap.add_argument("--run", action="store_true", help="сгенерировать файл и выйти")
    ap.add_argument("--out", metavar="PATH",
                    help="куда писать WAV (по умолчанию — из config.json)")
    ap.add_argument("--chain", metavar="A,B,C",
                    help="порядок синтезаторов через запятую: \"Edge TTS,gTTS,Piper\"")
    ap.add_argument("--voice", metavar="NAME", help="голос Edge TTS")
    ap.add_argument("--piper-model", metavar="PATH", help="модель Piper (.onnx)")
    ap.add_argument("--config", metavar="PATH", help="свой config.json вместо встроенного")
    ap.add_argument("--json", action="store_true", help="машинный вывод в stdout")
    ap.add_argument("--show-config", action="store_true",
                    help="напечатать действующие настройки и выйти")
    ap.add_argument("--selftest", action="store_true",
                    help="проверить ffmpeg, сеть и синтез без записи эфирного файла")
    ap.add_argument("--slot", metavar="HH:MM",
                    help="отметить слот расписания: исход ляжет в slot_results "
                         "и повтор того же слота будет заблокирован")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.chain:
        SYNTH_CHAIN = [s.strip() for s in args.chain.split(",") if s.strip()]
    if args.voice:
        VOICE = args.voice
        EDGE_VOICES = [VOICE] + [v for v in EDGE_VOICES if v != VOICE]
    if args.piper_model:
        PIPER_MODEL = args.piper_model
    out_cfg, chain_cfg = apply_config(cfg)
    if args.out:
        out_cfg = args.out

    if args.show_config:
        print(json.dumps(config_view(), ensure_ascii=False, indent=2))
        return 0
    if args.selftest:
        res = selftest()
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            for k, v in res.items():
                print("%s: %s" % (k, v))
        return 0 if res.get("ok") else 1
    if not args.run:
        ap.print_help()
        return 2

    # --slot: запуск по расписанию. Отмечаем слот ДО старта, чтобы повторный
    # запуск в ту же минуту (второй планировщик, ручной пуск) не дублировал эфир.
    slot_key = None
    if args.slot:
        if not valid_slot(args.slot):
            msg = "Некорректное время слота: %r (ожидается HH:MM)" % args.slot
            print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False)
                  if args.json else msg, file=sys.stderr)
            return 2
        slot_key = "%s %s" % (datetime.datetime.now().strftime("%Y-%m-%d"), args.slot)
        if slot_fired(slot_key):
            msg = "Слот %s уже отработал — пропускаю" % args.slot
            print(json.dumps({"ok": False, "skipped_slot": args.slot},
                             ensure_ascii=False) if args.json else msg)
            return 0
        mark_slot(slot_key)

    try:
        res = generate(out_cfg, SYNTH_CHAIN if args.chain else chain_cfg, cfg=None)
    except Exception as e:  # noqa
        record_run(False, None, str(e), args.slot)
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        else:
            print("Ошибка: %s" % e, file=sys.stderr)
        return 1
    record_run(True, res.get("path"), None, args.slot)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print("Готово: %s" % res["path"])
    return 0


if __name__ == "__main__":
    sys.exit(cli())
