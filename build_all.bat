@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  XRechnung Build-Skript
echo  Baut in der richtigen Reihenfolge: Dienst -^> Monitor -^> Setup
echo  (Setup.exe buendelt die zuvor gebauten Dienst- und Monitor-EXEs
echo   sowie die KoSIT-Werkzeuge aus kosit\)
echo ============================================================
echo.

set VENV_PYINSTALLER=.venv\Scripts\pyinstaller.exe

REM --- Voraussetzungen pruefen ---
if not exist "%VENV_PYINSTALLER%" (
    echo [FEHLER] Virtuelle Umgebung nicht gefunden: %VENV_PYINSTALLER%
    echo Bitte zuerst einrichten:
    echo    python -m venv .venv
    echo    .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)

REM --- Warnung, falls die KoSIT-Werkzeuge fehlen ---
if not exist "kosit\scenario\scenarios.xml" (
    echo [WARNUNG] Ordner kosit\ fehlt oder ist unvollstaendig.
    echo           Die Setup.exe wird dann OHNE KoSIT-Validierung ausgeliefert.
    echo           Zum Beschaffen zuerst ausfuehren:  python tools\fetch_kosit.py
    echo.
)

REM --- [1/3] Hintergrunddienst ---
echo [1/3] Baue XRechnung-Dienst.exe ...
"%VENV_PYINSTALLER%" XRechnung-Dienst.spec --noconfirm
if errorlevel 1 (
    echo [FEHLER] Build von XRechnung-Dienst.exe fehlgeschlagen.
    exit /b 1
)
echo.

REM --- [2/3] Monitor ---
echo [2/3] Baue XRechnung-Monitor.exe ...
"%VENV_PYINSTALLER%" XRechnung-Monitor.spec --noconfirm
if errorlevel 1 (
    echo [FEHLER] Build von XRechnung-Monitor.exe fehlgeschlagen.
    exit /b 1
)
echo.

REM --- [3/3] Setup (buendelt Dienst + Monitor + kosit\) ---
echo [3/3] Baue XRechnung-Setup.exe (enthaelt Dienst + Monitor + KoSIT) ...
"%VENV_PYINSTALLER%" XRechnung-Setup.spec --noconfirm
if errorlevel 1 (
    echo [FEHLER] Build von XRechnung-Setup.exe fehlgeschlagen.
    exit /b 1
)

echo.
echo ============================================================
echo  Fertig!
echo  Verteilungsdatei: dist\XRechnung-Setup.exe
echo  (enthaelt Dienst, Monitor und KoSIT-Werkzeuge eingebettet)
echo ============================================================
endlocal
