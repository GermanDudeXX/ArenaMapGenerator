@echo off
REM Baut die .exe neu. Ergebnis: dist\ArenaMapTool.exe
title Arena Map Tool bauen
cd /d "%~dp0"

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller fehlt, wird installiert...
    python -m pip install pyinstaller || goto :fehler
)

python -m PyInstaller --noconfirm --log-level WARN ArenaTool.spec || goto :fehler

echo.
echo Selbsttest der frisch gebauten .exe...
dist\ArenaMapTool.exe --selbsttest "%TEMP%\ArenaMapTool_Selbsttest"
if errorlevel 1 (
    echo.
    echo   SELBSTTEST FEHLGESCHLAGEN - siehe
    echo   %TEMP%\ArenaMapTool_Selbsttest\selbsttest.txt
    pause
    exit /b 1
)

REM Anleitung mit ins Ausgabeverzeichnis - "rm -rf dist" beim Neubau
REM hat sie sonst jedes Mal mitgenommen.
copy /Y LIESMICH.txt dist\LIESMICH.txt >nul

echo.
echo   Fertig: dist\ArenaMapTool.exe
pause
exit /b 0

:fehler
echo.
echo   Bauen fehlgeschlagen.
pause
exit /b 1
