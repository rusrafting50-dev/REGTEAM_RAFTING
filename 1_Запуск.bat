@echo off
chcp 65001 >nul
cd /d "%~dp0"

if "%~1"=="continue" goto :after_pull

echo [1/4] Stop Flask on port 5001...
rem Убиваем только процесс на этом порту, а не все python.exe в системе -
rem иначе запуск этого сайта попутно убивал бы COREZ, RAFTING_CFO и
rem SPORTS_REFEREE, если они уже работают, и наоборот.
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /r /c:":5001[^0-9]" ^| findstr "LISTENING"') do taskkill /f /pid %%p 1>nul 2>nul
timeout /t 2 /nobreak >nul

echo [2/4] Git pull...
git pull --ff-only origin main
set PULL_ERR=%errorlevel%

rem git pull выше мог изменить сам этот файл на диске, пока он ещё
rem выполняется - cmd.exe читает .bat по ходу исполнения, а не
rem загружает целиком в память заранее, поэтому продолжать в этом же
rem процессе небезопасно: последующие строки могут исполниться по
rem смещённым/перепутанным байтам уже изменившегося файла - так один раз
rem пропала часть шагов запуска, а другой раз ложно сработало
rem предупреждение об ошибке обновления. Вместо этого запускаем себя же
rem заново отдельным процессом - он гарантированно читает уже полностью
rem обновлённый файл с нуля, с самого начала.
cmd /c "%~f0" continue
exit /b

:after_pull
if not "%PULL_ERR%"=="0" (
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
