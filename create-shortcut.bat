@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create-shortcut.ps1"
if errorlevel 1 (
    echo Could not create desktop shortcut.
    exit /b 1
)
echo Desktop shortcut created: MeetScribe
exit /b 0
