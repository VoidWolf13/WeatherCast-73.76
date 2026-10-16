@echo off
chcp 65001 >nul
title WeatherCast 73.76 - запуск с локального диска
setlocal

rem ==== ПУТИ ====
rem Сборка (канон) — в общей папке LinWinData; в ВМ это диск D:.
set SRC=D:\WeatherCast 73.76
if not exist "%SRC%\WeatherCast-73.76.exe" set SRC=%~dp0WeatherCast 73.76
rem Рабочая копия на ЛОКАЛЬНОМ диске гостя. Frozen-сборку нельзя запускать
rem прямо с virtiofs: загрузчик PyInstaller падает с
rem "Module object for pyimod02_importers is NULL!".
set DST=%LOCALAPPDATA%\WeatherCast-73.76

if not exist "%SRC%\WeatherCast-73.76.exe" (
  echo.
  echo  НЕ НАЙДЕНА сборка: "%SRC%\WeatherCast-73.76.exe"
  echo  Проверьте, что диск D: ^(LinWinData^) подключён.
  echo.
  pause
  exit /b 1
)

echo.
echo  === WeatherCast 73.76 ===
echo  Сборка  : %SRC%
echo  Рабочая : %DST%
echo.

echo  [1/3] Обновляю рабочую копию из сборки ...
robocopy "%SRC%" "%DST%" /E /XO /NFL /NDL /NJH /NJS /NP /R:1 /W:1 >nul
if errorlevel 8 (
  echo        ОШИБКА копирования. Проверьте доступ к диску.
  pause
  exit /b 1
)

echo  [2/3] Запускаю программу. Когда закончите — закройте окно ...
start /wait "" "%DST%\WeatherCast-73.76.exe"

echo  [3/3] Переношу изменения и новые файлы обратно в сборку ...
robocopy "%DST%" "%SRC%" /E /XO /NFL /NDL /NJH /NJS /NP /R:1 /W:1 >nul
if errorlevel 8 (
  echo        ВНИМАНИЕ: часть файлов не скопировалась обратно.
) else (
  echo        готово: config.json / ПОГОДА.wav / weather.log — в сборке.
)

echo.
pause
endlocal
