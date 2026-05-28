"""
XRechnung-Hintergrunddienst — Einstiegspunkt
=============================================
Wird regelmäßig über den Windows Task Scheduler ausgeführt.

Aufruf:
    python main.py               # Einmaliger Durchlauf (Task Scheduler)
    python main.py --watch       # Dauerhafter File-Watcher (Entwicklung)
    python main.py --dry-run     # Testlauf ohne E-Mail-Versand
"""

import sys
import argparse
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config
from src.utils.logger import setup_logger, setup_run_logger, close_run_logger
from src.database.db import test_connection
from src.watcher.watcher import run_once, run_watch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="XRechnung-Hintergrunddienst"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Dauerhafter File-Watcher-Modus (für Entwicklung)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Testlauf ohne E-Mail-Versand",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Log-Level überschreiben",
    )
    return parser.parse_args()


def main() -> int:
    args   = parse_args()
    config = load_config()

    log_file  = config.get("LOG_FILE", "logs/xrechnung_dienst.log")
    log_level = args.log_level or config.get("LOG_LEVEL", "INFO")

    # Haupt-Logger (dauerhaftes Gesamt-Log + Konsole)
    logger = setup_logger(log_file=log_file, level=log_level)

    # Lauf-spezifischer Handler (eigene Datei, immer DEBUG)
    run_handler = setup_run_logger(log_file=log_file)

    logger.info("XRechnung-Hintergrunddienst gestartet")
    logger.info(
        "Modus: %s%s",
        "Watch" if args.watch else "Einmaliger Durchlauf",
        " (Dry-Run)" if args.dry_run else "",
    )

    if not test_connection():
        logger.error("Datenbankverbindung fehlgeschlagen — Dienst wird beendet.")
        close_run_logger(run_handler)
        return 1

    try:
        if args.watch:
            run_watch(config, dry_run=args.dry_run)
        else:
            processed, failed = run_once(config, dry_run=args.dry_run)
            logger.info(
                "Durchlauf abgeschlossen: %d verarbeitet, %d fehlgeschlagen",
                processed, failed,
            )
    except KeyboardInterrupt:
        logger.info("Dienst durch Benutzer beendet (Ctrl+C)")
    except Exception as e:
        logger.exception("Unerwarteter Fehler: %s", e)
        close_run_logger(run_handler)
        return 1

    close_run_logger(run_handler)
    logger.info("XRechnung-Hintergrunddienst beendet")
    return 0


if __name__ == "__main__":
    sys.exit(main())