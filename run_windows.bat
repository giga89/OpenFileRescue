@echo off
title OpenFileRescue - Open Source File, Photo & Data Recovery
echo Starting OpenFileRescue...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in system PATH.
    echo Please download and install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

python run.py
pause
