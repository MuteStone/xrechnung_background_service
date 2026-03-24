"""
XRechnung-Hintergrunddienst — Einstiegspunkt
=============================================
Wird täglich über den Windows Task Scheduler ausgeführt.

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
from src.utils.logger import setup_logger
from src.database.db import test_connection
from src.watcher.watcher import run_once, run_watch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="XRechnung-Hintergrunddienst — FuxMedia GmbH & Co. KG"
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
    args = parse_args()
    config = load_config()

    log_level = args.log_level or config.get("LOG_LEVEL", "INFO")
    logger = setup_logger(
        log_file=config.get("LOG_FILE", "logs/xrechnung_dienst.log"),
        level=log_level,
    )

    logger.info("=" * 60)
    logger.info("XRechnung-Hintergrunddienst gestartet")
    logger.info(
        f"Modus: {'Watch' if args.watch else 'Einmaliger Durchlauf'}"
        f"{' (Dry-Run)' if args.dry_run else ''}"
    )
    logger.info("=" * 60)

    if not test_connection():
        logger.error("Datenbankverbindung fehlgeschlagen — Dienst wird beendet.")
        return 1

    try:
        if args.watch:
            run_watch(config, dry_run=args.dry_run)
        else:
            processed, failed = run_once(config, dry_run=args.dry_run)
            logger.info(
                f"Durchlauf abgeschlossen: {processed} verarbeitet, "
                f"{failed} fehlgeschlagen"
            )
    except KeyboardInterrupt:
        logger.info("Dienst durch Benutzer beendet (Ctrl+C)")
    except Exception as e:
        logger.exception(f"Unerwarteter Fehler: {e}")
        return 1

    logger.info("XRechnung-Hintergrunddienst beendet")
    return 0


if __name__ == "__main__":
    sys.exit(main())