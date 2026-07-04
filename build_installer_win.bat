@echo off
title OMR Test Manager - Windows Installer Builder
echo ===================================================
echo   OMR Test Manager - Windows Installer Builder
echo ===================================================
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in your PATH.
    echo Please install Python 3.7+ from python.org and try again.
    pause
    exit /b %errorlevel%
)

echo === Step 1: Installing Required Dependencies ===
pip install Pillow pymupdf google-cloud-firestore opencv-python deepmerge dotmap jsonschema matplotlib numpy pandas rich screeninfo PyInstaller
if %errorlevel% neq 0 (
    echo Error: Failed to install Python dependencies.
    pause
    exit /b %errorlevel%
)

echo.
echo === Step 2: Compiling Executable ===
python build_installer.py
if %errorlevel% neq 0 (
    echo Error: Build failed!
    pause
    exit /b %errorlevel%
)

echo.
echo ===================================================
echo Success! Standalone EXE is generated in the "dist" folder.
echo You can send "dist/OMRTestManager.exe" to the school.
echo ===================================================
pause
