"""
PDF-Reader — Rechnungsnummer aus Dateiname extrahieren.
Format: Rechnung_20260105-001.pdf
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("xrechnung.pdf_reader")

# Dateiname-Format: Rechnung_YYYYMMDD-NNN.pdf
_FILENAME_PATTERN = re.compile(r"^Rechnung_(\d{8}-\d{3})\.pdf$")


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