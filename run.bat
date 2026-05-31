@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE="

if defined MEETSCRIBE_VENV (
    if exist "%MEETSCRIBE_VENV%\Scripts\python.exe" (
        set "PYTHON_EXE=%MEETSCRIBE_VENV%\Scripts\python.exe"
    )
)

if not defined PYTHON_EXE if defined TRANSCRIPTOR_VENV (
    if exist "%TRANSCRIPTOR_VENV%\Scripts\python.exe" (
        set "PYTHON_EXE=%TRANSCRIPTOR_VENV%\Scripts\python.exe"
    )
)

if not defined PYTHON_EXE if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)

if defined PYTHON_EXE (
    "%PYTHON_EXE%" main.py
) else (
    python main.py
)

if errorlevel 1 (
    echo.
    echo Startup failed. Check that Python and dependencies are installed.
    echo See README.md — Installation section.
    pause
)
