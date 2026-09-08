@echo off
rem Launcher for the pipeline control panel.
rem
rem Double-click opens the panel in a browser. Can be pinned to the taskbar.
rem
rem Finds the project venv on its own: a human should not have to remember that
rem dependencies live in .venv, while the system python dies on "import yaml"
rem with a traceback that never mentions the interpreter.
rem
rem ASCII only on purpose: Windows reads .cmd in the OEM codepage, and Cyrillic
rem stored as UTF-8 turns into garbage that breaks command parsing.

cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo.
    echo Project environment not found: %PY%
    echo.
    echo Create it once:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo Starting the panel; the browser will open by itself.
echo Keep this window open - it IS the server. Ctrl+C stops it.
echo.
"%PY%" scripts\serve.py %*

rem Pause only on failure: a normal Ctrl+C should just close the window, while a
rem crashed start is something the human must have time to read.
if errorlevel 1 pause
