"""
PDF-Reader — Rechnungsnummer aus Rechnungs-PDF extrahieren.
Verwendet pdfplumber + Regex.
"""

import logging
import re
from pathlib import Path
from typing import Optional

import pdfplumber

logger = logging.getLogger("xrechnung.pdf_reader")

# Rechnungsnummern-Format: z. B. 20260105-001
INVOICE_NUMBER_PATTERN = re.compile(r"\b(\d{8}-\d{3})\b")


def extract_invoice_number(pdf_path: Path) -> Optional[str]:
    """
    Extrahiert die Rechnungsnummer aus einer Rechnungs-PDF.

    Args:
        pdf_path: Pfad zur PDF-Datei

    Returns:
        Rechnungsnummer als String, oder None wenn nicht gefunden.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                match = INVOICE_NUMBER_PATTERN.search(text)
                if match:
                    invoice_number = match.group(1)
                    logger.debug(f"Rechnungsnummer gefunden: {invoice_number}")
                    return invoice_number

        logger.warning(f"Keine Rechnungsnummer gefunden in: {pdf_path.name}")
        return None

    except Exception as e:
        logger.error(f"Fehler beim Lesen der PDF {pdf_path.name}: {e}")
        return None