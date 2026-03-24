"""
Logging-Konfiguration: Rotating File Handler + Konsole.
"""

import logging
import logging.handlers
from pathlib import Path


def setup_logger(
    log_file: str = "logs/xrechnung_dienst.log",
    level: str = "INFO",
    max_bytes: int = 5_242_880,
    backup_count: int = 3,
) -> logging.Logger:
    """
    Richtet den Logger ein:
    - Rotating File Handler
    - Konsolen-Handler (farbig wenn colorlog verfügbar)
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger("xrechnung")
    logger.setLevel(numeric_level)

    if logger.handlers:
        return logger  # Bereits initialisiert

    fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # File Handler (Rotating)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
    file_handler.setLevel(numeric_level)
    logger.addHandler(file_handler)

    # Konsolen-Handler
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


def get_logger(name: str = "xrechnung") -> logging.Logger:
    """Gibt den Logger für ein Untermodul zurück."""
    return logging.getLogger(name)