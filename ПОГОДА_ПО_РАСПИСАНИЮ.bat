@echo off
chcp 65001 >nul
title WeatherCast 73.76 - выпуск по расписанию
setlocal

rem ======================================================================
rem  Выпуск ПОГОДА.wav по расписанию (планировщик Windows).
rem
rem  Запуск вручную:   ПОГОДА_ПО_РАСПИСАНИЮ.bat 09:00
rem  Без аргумента берётся текущее время (удобно для проверки).
rem
rem  Что делает:
rem    1. обновляет рабочую копию на ЛОКАЛЬНОМ диске гостя (обход virtiofs:
rem       frozen-сборку нельзя запускать прямо с диска D: — падает загрузчик);
rem    2. вызывает WeatherCast-73.76.exe --run --slot HH:MM — тот же exe, что
rem       и в окне: в консольном режиме окна не открывает;
rem    3. возвращает config.json / runstate.json / ПОГОДА.wav / weather.log
rem       обратно в сборку.
rem
rem  Повторный запуск того же слота в ту же минуту безопасен: слот отмечается
rem  в runstate.json ДО старта, поэтому второй вызов ничего не делает
rem  (возвращает {"ok": false, "skipped_slot": "HH:MM"}).
rem
rem  Регистрация в планировщике — см. docs/RULES.md, п. 8.
rem ======================================================================

rem ==== ПУТИ ====
set SRC=D:\WeatherCast 73.76
if not exist "%SRC%\WeatherCast-73.76.exe" set SRC=%~dp0WeatherCast 73.76
set DST=%LOCALAPPDATA%\WeatherCast-73.76

rem ==== ВРЕМЯ СЛОТА ====
set SLOT=%~1
if "%SLOT%"=="" (
  rem %TIME% в русской локали: " 7:30:15,23" — пробел в часе меняем на ноль.
  set T=%TIME: =0%
  set SLOT=%T:~0,2%:%T:~3,2%
)

if not exist "%SRC%\WeatherCast-73.76.exe" (
  echo  НЕ НАЙДЕНА сборка: "%SRC%\WeatherCast-73.76.exe"
  echo  Проверьте, что диск D: ^(LinWinData^) подключён.
  exit /b 1
)

echo.
echo  === WeatherCast 73.76: выпуск по расписанию ===
echo  Слот    : %SLOT%
echo  Сборка  : %SRC%
echo  Рабочая : %DST%
echo.

rem [1/3] Обновляю рабочую копию. /XO — не трогаем то, что в рабочей копии
rem новее: свежие config.json и runstate.json остаются на месте.
robocopy "%SRC%" "%DST%" /E /XO /NFL /NDL /NJH /NJS /NP /R:1 /W:1 >nul
if errorlevel 8 (
  echo  [1/3] ОШИБКА копирования. Проверьте доступ к диску D:.
  exit /b 1
)
echo  [1/3] рабочая копия обновлена

rem [2/3] Выпуск. start /wait нужен, чтобы дождаться конца синтеза и вернуть
rem код: 0 — файл создан или слот уже отработал, 1 — ошибка синтеза, 2 — плохой аргумент.
start /wait "" "%DST%\WeatherCast-73.76.exe" --run --slot %SLOT%
set RC=%ERRORLEVEL%
echo  [2/3] выпуск завершён, код %RC%

rem [3/3] Возвращаю изменения и новые файлы в сборку.
robocopy "%DST%" "%SRC%" /E /XO /NFL /NDL /NJH /NJS /NP /R:1 /W:1 >nul
if errorlevel 8 (
  echo  [3/3] ВНИМАНИЕ: часть файлов не скопировалась обратно.
) else (
  echo  [3/3] готово: runstate.json / ПОГОДА.wav / weather.log — в сборке.
)

if exist "%DST%\ПОГОДА.wav" (
  for %%F in ("%DST%\ПОГОДА.wav") do echo  Файл: %%~zF байт, %%~tF
) else (
  echo  ВНИМАНИЕ: ПОГОДА.wav не создан — смотрите weather.log.
)

echo  ====================================================
exit /b %RC%
