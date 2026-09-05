@echo off
setlocal
title OpenFileRescue - Open Source File, Photo & Data Recovery

echo ==================================================
echo  Starting OpenFileRescue...
echo ==================================================

REM 1. Check for Astral UV (Instant execution, zero Python setup needed)
where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo  [OK] Using Astral UV (blazing-fast isolated environment)...
    uv run run.py %*
    goto :end
)

REM 2. Check for standard Python in system PATH
where python >nul 2>nul
if %errorlevel% equ 0 (
    echo  [OK] Using system Python...
    python run.py %*
    goto :end
)

REM 3. Check for Docker
where docker >nul 2>nul
if %errorlevel% equ 0 (
    echo  [INFO] Python not found. Launching via Docker Compose...
    docker compose up
    goto :end
)

REM 4. If neither UV, Python, nor Docker is installed, offer 1-line UV install
echo.
echo  [!] No Python, UV, or Docker environment detected.
echo      The easiest zero-admin way to run OpenFileRescue on Windows is Astral UV.
echo.
echo      To install UV instantly in PowerShell (no admin rights needed):
echo      powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
echo.
echo      Or download Python from: https://www.python.org/downloads/
echo ==================================================
pause

:end
