@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ========================================
echo   MeetScribe — one-time setup (Windows)
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 where py >nul 2>&1
if errorlevel 1 (
    echo Python not found.
    echo Install from https://python.org — check "Add python.exe to PATH"
    echo Or: winget install Python.Python.3.12
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv
        pause
        exit /b 1
    )
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
echo Installing Python packages ...
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
)

echo.
echo Optional tools (recommended):
echo   winget install Gyan.FFmpeg
echo   winget install VideoLAN.VLC
echo.

choice /C YN /M "Install FFmpeg and VLC now via winget"
if not errorlevel 2 (
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    winget install --id VideoLAN.VLC -e --accept-source-agreements --accept-package-agreements
)

call "%~dp0create-shortcut.bat"

echo.
echo Setup complete.
echo   - Double-click run.bat
echo   - Or use the MeetScribe shortcut on your Desktop
echo.
pause
