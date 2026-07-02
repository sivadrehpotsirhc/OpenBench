@echo off
cd /d "%~dp0"
title OpenBench Setup

echo ===================================================
echo               OpenBench Installer
echo ===================================================
echo.

:: Check if Python is installed
echo Checking for Python...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not added to PATH!
    echo Please install Python from https://www.python.org/downloads/ and ensure "Add Python to PATH" is checked during installation.
    pause
    exit /b 1
)

echo Python found. Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Installing required modules from requirements.txt...
python -m pip install -r requirements.txt

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] There was an issue installing the requirements.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   Setup completed successfully!
echo   You can now launch the software using start.bat
echo ===================================================
pause
