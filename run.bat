@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

call :ResolvePython
if not defined PYTHON_EXE (
    echo.
    echo [MeetScribe] Python not found.
    echo Run install.bat once, or install Python 3.10+ from https://python.org
    echo.
    pause
    exit /b 1
)

call :EnsureDependencies
if errorlevel 1 (
    echo.
    echo [MeetScribe] Failed to install dependencies.
    echo Try running install.bat manually.
    echo.
    pause
    exit /b 1
)

set "PYTHONW_EXE=%PYTHON_EXE:python.exe=pythonw.exe%"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%PYTHON_EXE%"
start "" "%PYTHONW_EXE%" main.py
exit /b 0

:ResolvePython
set "PYTHON_EXE="
if defined MEETSCRIBE_VENV if exist "%MEETSCRIBE_VENV%\Scripts\python.exe" (
    set "PYTHON_EXE=%MEETSCRIBE_VENV%\Scripts\python.exe"
    goto :eof
)
if defined TRANSCRIPTOR_VENV if exist "%TRANSCRIPTOR_VENV%\Scripts\python.exe" (
    set "PYTHON_EXE=%TRANSCRIPTOR_VENV%\Scripts\python.exe"
    goto :eof
)
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
    goto :eof
)
if exist "%USERPROFILE%\.venvs\meet-scribe\Scripts\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\.venvs\meet-scribe\Scripts\python.exe"
    goto :eof
)
if exist "%USERPROFILE%\.venvs\my-transcriptor\Scripts\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\.venvs\my-transcriptor\Scripts\python.exe"
    goto :eof
)
where py >nul 2>&1 && (
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
)
if defined PYTHON_EXE goto :eof
where python >nul 2>&1 && (
    for /f "delims=" %%P in ('where python ^| findstr /i "WindowsApps" >nul && echo. || where python') do (
        set "PYTHON_EXE=%%P"
        goto :eof
    )
)
for /f "delims=" %%P in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%P"
    goto :eof
)
goto :eof

:EnsureDependencies
"%PYTHON_EXE%" -c "import customtkinter" >nul 2>&1
if not errorlevel 1 exit /b 0

echo [MeetScribe] Installing dependencies (first run may take a few minutes)...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
exit /b 0
