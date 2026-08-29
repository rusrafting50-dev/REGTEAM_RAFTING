@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/4] Stop Flask (port 5001)...
rem Убиваем только процесс, слушающий именно этот порт, а не все python.exe
rem в системе - иначе запуск этого сайта попутно убивал бы COREZ/
rem RAFTING_CFO/SPORTS_REFEREE, если они уже работают (и наоборот).
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /r /c:":5001[^0-9]" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%p 1>nul 2>nul
)
timeout /t 2 /nobreak >nul

echo [2/4] Git pull...
git pull --ff-only origin main
if errorlevel 1 (
    echo.
    echo ============================================================
    echo   ВНИМАНИЕ: обновление НЕ применилось - запускается ПРЕЖНЯЯ
    echo   версия кода. Возможные причины: нет сети/прокси до GitHub,
    echo   либо есть локальные изменения, которые нельзя применить
    echo   автоматически ^(--ff-only не создаёт слияний и не трогает
    echo   файлы при конфликте - код остаётся как был^).
    echo ============================================================
    echo.
    pause
)

echo [3/4] pip install...
pip install -r requirements.txt --quiet

echo [4/4] Start Flask...
start http://localhost:5001
python app.py
pause
