"""
File-Watcher & Verarbeitungs-Pipeline
======================================
Überwacht den Export-Ordner der Kundenverwaltung auf neue PDF-Dateien.
Jede erkannte PDF durchläuft die Pipeline:
  1. Rechnungsnummer aus PDF extrahieren
  2. Rechnungsdaten aus DB laden
  3. XRechnung-XML generieren
  4. XML validieren (XSD)
  5. XML per E-Mail an OZG-RE übertragen
  6. PDF nach processed/ oder error/ verschieben
"""

import logging
import shutil
import time
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

logger = logging.getLogger("xrechnung.watcher")


def process_pdf(pdf_path: Path, config: dict, dry_run: bool = False) -> bool:
    """
    Verarbeitet eine einzelne Rechnungs-PDF durch die komplette Pipeline.

    Args:
        pdf_path: Pfad zur PDF-Datei
        config:   Konfigurationsdictionary
        dry_run:  Bei True kein E-Mail-Versand

    Returns:
        True bei Erfolg, False bei Fehler.
    """
    logger.info(f"Verarbeite: {pdf_path.name}")

    # Schritt 1: Rechnungsnummer extrahieren
    from src.xrechnung.pdf_reader import extract_invoice_number
    invoice_number = extract_invoice_number(pdf_path)
    if not invoice_number:
        logger.error(f"Rechnungsnummer nicht gefunden: {pdf_path.name}")
        _move_to_error(pdf_path, config)
        return False
    logger.info(f"Rechnungsnummer: {invoice_number}")

    # Schritt 2: Rechnungsdaten aus DB laden
    from src.database.db import get_invoice_full
    invoice_data = get_invoice_full(invoice_number)
    if not invoice_data:
        logger.error(f"Keine DB-Daten für Rechnung {invoice_number}")
        _move_to_error(pdf_path, config)
        return False

    # Schritt 3: XRechnung-XML generieren
    from src.xrechnung.generator import generate
    output_dir = Path(config["OUTPUT_XML"])
    xml_path = generate(invoice_data, output_dir)
    if not xml_path:
        logger.error(f"XML-Generierung fehlgeschlagen: {invoice_number}")
        _move_to_error(pdf_path, config)
        return False
    logger.info(f"XML erzeugt: {xml_path.name}")

    # Schritt 4: XML validieren
    from src.xrechnung.validator import validate
    if not validate(xml_path):
        logger.error(f"XML-Validierung fehlgeschlagen: {xml_path.name}")
        _move_to_error(pdf_path, config)
        return False
    logger.info("XML-Validierung erfolgreich")

    # Schritt 5: Übertragen
    if dry_run:
        logger.info("[DRY-RUN] E-Mail-Versand übersprungen")
    else:
        from src.transmitter.transmitter import transmit
        if not transmit(xml_path, config):
            logger.error(f"Übertragung fehlgeschlagen: {xml_path.name}")
            _move_to_error(pdf_path, config)
            return False
        logger.info("Übertragung erfolgreich")

    # Schritt 6: PDF verschieben
    _move_to_processed(pdf_path, config)
    logger.info(f"Abgeschlossen: {pdf_path.name}")
    return True


def _move_to_processed(pdf_path: Path, config: dict) -> None:
    dest = Path(config["PROCESSED_FOLDER"]) / pdf_path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdf_path), str(dest))
    logger.debug(f"→ processed/: {pdf_path.name}")


def _move_to_error(pdf_path: Path, config: dict) -> None:
    dest = Path(config["ERROR_FOLDER"]) / pdf_path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdf_path), str(dest))
    logger.warning(f"→ error/: {pdf_path.name}")


def run_once(config: dict, dry_run: bool = False) -> tuple[int, int]:
    """
    Verarbeitet alle vorhandenen PDFs im Watch-Folder einmalig.
    Standard-Modus für den Windows Task Scheduler.

    Returns:
        (processed_count, failed_count)
    """
    watch_folder = Path(config["WATCH_FOLDER"])
    if not watch_folder.exists():
        logger.error(f"Watch-Folder nicht gefunden: {watch_folder}")
        return 0, 0

    pdf_files = list(watch_folder.glob("*.pdf"))
    if not pdf_files:
        logger.info("Keine PDF-Dateien im Watch-Folder gefunden.")
        return 0, 0

    logger.info(f"{len(pdf_files)} PDF(s) gefunden — starte Verarbeitung …")

    processed, failed = 0, 0
    for pdf_path in pdf_files:
        if process_pdf(pdf_path, config, dry_run=dry_run):
            processed += 1
        else:
            failed += 1

    return processed, failed


class _PDFHandler(FileSystemEventHandler):
    """Reagiert auf neu erstellte PDF-Dateien im Watch-Folder."""

    def __init__(self, config: dict, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".pdf":
            return
        logger.info(f"Neue PDF erkannt: {path.name}")
        time.sleep(0.5)  # Warten bis Schreibvorgang abgeschlossen
        process_pdf(path, self.config, dry_run=self.dry_run)


def run_watch(config: dict, dry_run: bool = False) -> None:
    """
    Dauerhafter File-Watcher (blockierend).
    Nur für Entwicklung — im Produktivbetrieb run_once() via Task Scheduler.
    """
    watch_folder = Path(config["WATCH_FOLDER"])
    if not watch_folder.exists():
        logger.error(f"Watch-Folder nicht gefunden: {watch_folder}")
        return

    logger.info(f"File-Watcher aktiv: {watch_folder}")
    logger.info("Beenden mit Ctrl+C")

    # Bereits vorhandene PDFs beim Start verarbeiten
    run_once(config, dry_run=dry_run)

    event_handler = _PDFHandler(config, dry_run=dry_run)
    observer = Observer()
    observer.schedule(event_handler, str(watch_folder), recursive=False)
    observer.start()

    try:
        while observer.is_alive():
            observer.join(timeout=1)
    finally:
        observer.stop()
        observer.join()
        logger.info("File-Watcher beendet")