@echo off
title Arena Map Viewer
cd /d "%~dp0"

python -c "import pygame" 2>nul
if errorlevel 1 (
    echo.
    echo   Pygame fehlt. Installiere es jetzt...
    echo.
    python -m pip install pygame
    if errorlevel 1 (
        echo.
        echo   Installation fehlgeschlagen. Bitte manuell ausfuehren:
        echo       python -m pip install pygame
        echo.
        pause
        exit /b 1
    )
)

python main.py
if errorlevel 1 (
    echo.
    echo   Der Viewer wurde mit einem Fehler beendet.
    pause
)
