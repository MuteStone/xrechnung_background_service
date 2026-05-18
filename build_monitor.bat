@echo off
REM ============================================================
REM  XRechnung-Monitor — Build-Skript
REM  Erstellt XRechnung-Monitor.exe im Ordner dist\
REM ============================================================

cd /d "%~dp0"

echo.
echo  XRechnung-Monitor Build
echo  =======================

SET VENV_PYTHON=.venv\Scripts\python.exe
SET VENV_PYINSTALLER=.venv\Scripts\pyinstaller.exe

REM Prüfen ob .venv vorhanden
if not exist "%VENV_PYTHON%" (
    echo.
    echo  [FEHLER] Virtuelle Umgebung nicht gefunden: %VENV_PYTHON%
    echo  Bitte zuerst installieren:
    echo    python -m venv .venv
    echo    .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM Alte Build-Artefakte entfernen
if exist "dist\XRechnung-Monitor.exe" (
    echo  Altes Build-Artefakt entfernen ...
    del /q "dist\XRechnung-Monitor.exe"
)

echo.
echo  Starte PyInstaller (virtuelle Umgebung: .venv) ...
echo.

"%VENV_PYINSTALLER%" XRechnung-Monitor.spec --noconfirm

if errorlevel 1 (
    echo.
    echo  [FEHLER] Build fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo  Build erfolgreich!
echo  EXE-Datei: dist\XRechnung-Monitor.exe
echo  ============================================================
echo.
echo  Hinweise:
echo    - Die .env-Datei muss im selben Ordner wie die EXE liegen.
echo    - Ohne .env: Einstellungen in der App konfigurieren und
echo      auf "Einstellungen speichern" klicken.
echo.
pause
