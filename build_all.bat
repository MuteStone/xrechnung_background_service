@echo off
setlocal

echo ============================================================
echo  XRechnung Build-Skript
echo  Reihenfolge: Dienst -> Monitor -> Setup (mit Bundling)
echo ============================================================
echo.

REM Schritt 1: XRechnung-Dienst.exe
echo [1/3] Baue XRechnung-Dienst.exe ...
.venv\Scripts\pyinstaller.exe XRechnung-Dienst.spec --noconfirm
if errorlevel 1 (
    echo FEHLER beim Bauen von XRechnung-Dienst.exe
    exit /b 1
)
echo.

REM Schritt 2: XRechnung-Monitor.exe
echo [2/3] Baue XRechnung-Monitor.exe ...
.venv\Scripts\pyinstaller.exe XRechnung-Monitor.spec --noconfirm
if errorlevel 1 (
    echo FEHLER beim Bauen von XRechnung-Monitor.exe
    exit /b 1
)
echo.

REM Schritt 3: XRechnung-Setup.exe (bundelt Dienst + Monitor)
echo [3/3] Baue XRechnung-Setup.exe (enthält Dienst + Monitor) ...
.venv\Scripts\pyinstaller.exe XRechnung-Setup.spec --noconfirm
if errorlevel 1 (
    echo FEHLER beim Bauen von XRechnung-Setup.exe
    exit /b 1
)

echo.
echo ============================================================
echo  Fertig!
echo  Verteilungsdatei: dist\XRechnung-Setup.exe
echo  (enthält Dienst und Monitor eingebettet)
echo ============================================================
endlocal
