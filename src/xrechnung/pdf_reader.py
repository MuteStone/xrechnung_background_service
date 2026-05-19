"""
PDF-Reader — Rechnungsnummer und Leistungszeitraum aus PDF extrahieren.
Format Dateiname: Rechnung_YYYYMMDD-NNN.pdf
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("xrechnung.pdf_reader")

# Dateiname-Format: Rechnung_YYYYMMDD-NNN.pdf (Groß-/Kleinschreibung egal)
_FILENAME_PATTERN = re.compile(r"^[Rr]echnung_(\d{8}-\d{3})\.pdf$", re.IGNORECASE)

# Abrechnungszeitraum: 01.05.2026 bis 30.04.2027
# Erfasst das erste Datum (Leistungsbeginn) aus dem Zeitraum.
_PERIOD_PATTERN = re.compile(
    r"Abrechnungszeitraum\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})\s+bis\s+\d{1,2}\.\d{1,2}\.\d{4}",
    re.IGNORECASE,
)


def _parse_date(date_str: str) -> Optional[str]:
    """Wandelt DD.MM.YYYY in YYYYMMDD um. Gibt None bei ungültigem Datum zurück."""
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y").strftime("%Y%m%d")
    except ValueError:
        return None


def extract_invoice_number(pdf_path: Path) -> Optional[str]:
    """
    Extrahiert die Rechnungsnummer aus dem Dateinamen.

    Erwartet: Rechnung_20260105-001.pdf
    Gibt zurück: '20260105-001'

    Fallback auf PDF-Inhalt wenn Dateiname nicht passt.

    Args:
        pdf_path: Pfad zur PDF-Datei

    Returns:
        Rechnungsnummer als String, oder None wenn nicht gefunden.
    """
    # Primär: aus Dateiname
    match = _FILENAME_PATTERN.match(pdf_path.name)
    if match:
        invoice_number = match.group(1)
        logger.debug(f"Rechnungsnummer aus Dateiname: {invoice_number}")
        return invoice_number

    # Fallback: aus PDF-Inhalt (pdfplumber)
    logger.warning(
        f"Dateiname entspricht nicht dem erwarteten Format: {pdf_path.name} — "
        "versuche Extraktion aus PDF-Inhalt"
    )
    return _extract_from_content(pdf_path)


def extract_service_start_date(pdf_path: Path) -> Optional[str]:
    """
    Extrahiert das erste Datum des Abrechnungszeitraums aus dem PDF-Inhalt.

    Sucht nach dem Muster: "Abrechnungszeitraum: DD.MM.YYYY bis DD.MM.YYYY"
    Gibt das Startdatum als YYYYMMDD zurück, oder None wenn kein Zeitraum gefunden.

    Args:
        pdf_path: Pfad zur PDF-Datei

    Returns:
        Startdatum als YYYYMMDD-String, oder None wenn kein Zeitraum gefunden.
    """
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                match = _PERIOD_PATTERN.search(text)
                if match:
                    start_date = _parse_date(match.group(1))
                    if start_date:
                        logger.debug(
                            f"Leistungsbeginn aus PDF extrahiert: {start_date} "                            f"({pdf_path.name})"
                        )
                        return start_date

        logger.debug(f"Kein Abrechnungszeitraum gefunden in: {pdf_path.name}")
        return None

    except Exception as e:
        logger.warning(f"Fehler beim Lesen des Abrechnungszeitraums ({pdf_path.name}): {e}")
        return None


def _extract_from_content(pdf_path: Path) -> Optional[str]:
    """
    Fallback: Liest den PDF-Inhalt und sucht per Regex nach der Rechnungsnummer.
    """
    try:
        import pdfplumber

        _content_pattern = re.compile(r"\b(\d{8}-\d{3})\b")

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                match = _content_pattern.search(text)
                if match:
                    invoice_number = match.group(1)
                    logger.debug(
                        f"Rechnungsnummer aus PDF-Inhalt: {invoice_number}"
                    )
                    return invoice_number

        logger.error(f"Keine Rechnungsnummer gefunden in: {pdf_path.name}")
        return None

    except Exception as e:
        logger.error(f"Fehler beim Lesen der PDF {pdf_path.name}: {e}")
        return None