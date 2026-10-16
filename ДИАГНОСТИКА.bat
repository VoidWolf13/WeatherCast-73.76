@echo off
chcp 65001 >nul
title WeatherCast 73.76 - ДИАГНОСТИКА
setlocal
set SRC=D:\WeatherCast 73.76
if not exist "%SRC%\WeatherCast-73.76.exe" set SRC=%~dp0WeatherCast 73.76
set DST=%LOCALAPPDATA%\WeatherCast-73.76
cls
echo ============================================================
echo   ДИАГНОСТИКА WeatherCast 73.76
echo ============================================================
echo.
echo [1/6] Копирую сборку на локальный диск (обход virtiofs) ...
robocopy "%SRC%" "%DST%" /E /XO /NFL /NDL /NJH /NJS /NP /R:1 /W:1 >nul
if errorlevel 8 (echo        ОШИБКА копирования & pause & exit /b 1)
if not exist "%DST%\WeatherCast-73.76.exe" (echo        EXE НЕ НАЙДЕН: %DST% & pause & exit /b 1)
echo        готово: %DST%
echo.
echo [2/6] Проверяю интернет (api.open-meteo.com) ...
ping -n 2 api.open-meteo.com >nul 2>&1 && (echo        ping ЕСТЬ) || (echo        ping НЕ ПРОШЁЛ !!!)
echo.
echo [3/6] Чищу старые логи ...
del "%DST%\weather.log" >nul 2>&1
del "%TEMP%\weather.log" >nul 2>&1
echo        готово
echo.
echo [4/6] Запускаю. Нажмите "Создать файл погоды", дождитесь остановки индикатора и закройте окно.
start /wait "" "%DST%\WeatherCast-73.76.exe"
echo.
echo [5/6] Результаты ...
echo ---------- weather.log ----------
if exist "%DST%\weather.log" (type "%DST%\weather.log") else (echo    НЕТ)
echo ---------- weather.log в %%TEMP%% ----------
if exist "%TEMP%\weather.log" (type "%TEMP%\weather.log") else (echo    НЕТ)
echo ---------- ПОГОДА.wav ----------
if exist "%DST%\ПОГОДА.wav" (dir "%DST%\ПОГОДА.wav") else (echo    НЕ СОЗДАН)
echo.
echo [6/6] Возвращаю изменения и новые файлы в сборку ...
robocopy "%DST%" "%SRC%" /E /XO /NFL /NDL /NJH /NJS /NP /R:1 /W:1 >nul
if errorlevel 8 (echo        ВНИМАНИЕ: часть файлов не скопировалась обратно.) else (echo        готово: изменения в %SRC%)
echo ============================================================
pause
endlocal
