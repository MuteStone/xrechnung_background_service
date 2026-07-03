"""
Logger-Konfiguration für den XRechnung-Hintergrunddienst.

Zwei Handler-Ebenen:
  1. Haupt-Log (RotatingFileHandler) — dauerhaftes Gesamt-Log, Level aus Konfiguration
  2. Lauf-Log (FileHandler)          — pro Durchlauf eine eigene Datei, immer DEBUG
"""

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path, PureWindowsPath


def _resolve_log_path(log_file: str) -> Path:
    r"""
    Löst einen Log-Pfad auf das korrekte Basisverzeichnis auf.
    Relative Pfade werden relativ zum EXE-Verzeichnis (frozen)
    bzw. zum Projektstamm (Entwicklung) aufgelöst.

    Erkennt Windows-Pfade (C:/... und C:\...) korrekt als absolut,
    auch wenn der Code auf einem anderen System läuft.
    """
    p = Path(log_file)
    # PureWindowsPath erkennt C:/... und C:\... korrekt als absolut
    # Path.is_absolute() versagt bei C:/... auf Windows selbst
    if p.is_absolute() or PureWindowsPath(log_file).is_absolute():
        result = Path(log_file)
    else:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            # Projektstamm: 2 Ebenen über src/utils/logger.py
            try:
                base = Path(__file__).resolve().parents[2]
            except IndexError:
                base = Path(__file__).resolve().parent
        result = base / p

    # Robustheit: Zeigt LOG_FILE (fehlkonfiguriert) auf ein bestehendes
    # Verzeichnis, hängen wir einen Standard-Dateinamen an. Andernfalls würde
    # der FileHandler beim Öffnen mit PermissionError abstürzen und der Dienst
    # bräche noch vor der Verarbeitung ab.
    if result.exists() and result.is_dir():
        result = result / "xrechnung_dienst.log"
    return result


def setup_logger(
    log_file: str = "logs/xrechnung_dienst.log",
    level: str = "INFO",
    max_bytes: int = 5_242_880,
    backup_count: int = 3,
) -> logging.Logger:
    """
    Richtet den Haupt-Logger ein:
    - RotatingFileHandler für das dauerhafte Gesamt-Log
    - Konsolen-Handler (farbig wenn colorlog verfügbar)
    """
    log_path = _resolve_log_path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger("xrechnung")
    logger.setLevel(logging.DEBUG)  # Logger selbst immer auf DEBUG — Handler filtern

    if logger.handlers:
        return logger  # Bereits initialisiert

    fmt      = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # ── Haupt-Log (Rotating) ──────────────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
    file_handler.setLevel(numeric_level)
    logger.addHandler(file_handler)

    # ── Konsolen-Handler ──────────────────────────────────────────────────
    try:
        import colorlog
        console_formatter = colorlog.ColoredFormatter(
            "%(log_color)s" + fmt,
            datefmt=date_fmt,
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "green",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "bold_red",
            },
        )
    except ImportError:
        console_formatter = logging.Formatter(fmt, datefmt=date_fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(numeric_level)
    logger.addHandler(console_handler)

    return logger


def setup_run_logger(log_file: str = "logs/xrechnung_dienst.log") -> logging.FileHandler:
    """
    Legt für den aktuellen Durchlauf eine eigene Log-Datei an.

    Dateiname: logs/runs/xrechnung_YYYYMMDD_HHMMSS.log
    Level:     immer DEBUG — vollständiges Protokoll des Laufs

    Gibt den FileHandler zurück damit main.py ihn nach dem Lauf
    sauber schließen und entfernen kann.

    Aufbau der Log-Datei:
      - Header-Block mit Zeitstempel und Trennlinie
      - Alle DEBUG/INFO/WARNING/ERROR-Einträge des Laufs
      - Wird nie rotiert — ein Lauf = eine Datei
    """
    base_log = _resolve_log_path(log_file)
    run_log_dir = base_log.parent / "runs"
    run_log_dir.mkdir(parents=True, exist_ok=True)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log_path = run_log_dir / f"xrechnung_{timestamp}.log"

    fmt      = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    run_handler = logging.FileHandler(run_log_path, encoding="utf-8")
    run_handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
    run_handler.setLevel(logging.DEBUG)  # Immer vollständig

    logger = logging.getLogger("xrechnung")
    logger.addHandler(run_handler)

    # Header in die Lauf-Log-Datei schreiben
    logger.info("=" * 60)
    logger.info("XRechnung-Hintergrunddienst — Laufprotokoll")
    logger.info("Gestartet: %s", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    logger.info("Log-Datei: %s", run_log_path)
    logger.info("=" * 60)

    return run_handler


def close_run_logger(run_handler: logging.FileHandler) -> None:
    """
    Schreibt einen Abschluss-Block in die Lauf-Log-Datei
    und entfernt den Handler vom Logger.
    """
    logger = logging.getLogger("xrechnung")
    logger.info("=" * 60)
    logger.info("Laufprotokoll abgeschlossen: %s", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    logger.info("=" * 60)
    run_handler.close()
    logger.removeHandler(run_handler)


def get_logger(name: str = "xrechnung") -> logging.Logger:
    """Gibt den Logger für ein Untermodul zurück."""
    return logging.getLogger(name)