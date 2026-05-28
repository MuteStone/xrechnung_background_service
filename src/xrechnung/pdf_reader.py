"""
PDF-Reader — Rechnungsnummer, Adressblock, Lizenznehmer-ID und
Leistungszeitraum aus PDF extrahieren.

Format Dateiname: Rechnung_YYYYMMDD-NNN.pdf

Extraktions-Logik Adressblock:
  Der Empfänger-Adressblock steht immer vor der Zeile "Rechnung YYYYMMDD-NNN".
  Er kann 2–5 Zeilen haben. PLZ+Ort (letzte Zeile) und Straße (vorletzte Zeile)
  werden per Regex erkannt — alle Zeilen davor sind Namenszeilen.

Extraktions-Logik Lizenznehmer:
  Nach der Zeile "Lizenznehmer:" folgt eine Zeile mit Kundennummer und Name.
  Die Kundennummer (5-stellig) wird extrahiert und für den DB-Lookup der
  Leitweg-ID verwendet.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("xrechnung.pdf_reader")

# Dateiname-Format: Rechnung_YYYYMMDD-NNN.pdf (Groß-/Kleinschreibung egal)
_FILENAME_PATTERN = re.compile(r"^[Rr]echnung_(\d{8}-\d{3})\.pdf$", re.IGNORECASE)

# Rechnungsnummer im PDF-Text
_CONTENT_PATTERN = re.compile(r"\b(\d{8}-\d{3})\b")

# Abrechnungszeitraum: 01.05.2026 bis 30.04.2027
_PERIOD_PATTERN = re.compile(
    r"Abrechnungszeitraum\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})\s+bis\s+\d{1,2}\.\d{1,2}\.\d{4}",
    re.IGNORECASE,
)

# PLZ + Ort: "18055 Rostock" oder "18055 Rostock-Altstadt"
_PLZ_ORT_PATTERN = re.compile(r"^(\d{5})\s+(.+)$")

# Straße: Wort(e) gefolgt von Hausnummer (optional Buchstabe)
# Erkennt: "Neuer Markt 1", "Geschwister-Scholl-Str. 31", "Zum Amtsbrink 1a"
_STRASSE_PATTERN = re.compile(
    r"^.{3,}\s+\d+[a-zA-Z]?\s*$|^.{3,}\s+\d+[-/]\d+\s*$",
    re.UNICODE,
)

# Lizenznehmer-Kundennummer: erste Zahl am Anfang der Zeile nach "Lizenznehmer:"
_LIZENZNEHMER_ID_PATTERN = re.compile(r"^(\d+)\b")

# Trennzeile zwischen Adressblock und Rechnungskopf
_RECHNUNG_HEADER_PATTERN = re.compile(r"^Rechnung\s+\d{8}-\d{3}", re.IGNORECASE)


def _parse_date(date_str: str) -> Optional[str]:
    """Wandelt DD.MM.YYYY in YYYYMMDD um. Gibt None bei ungültigem Datum zurück."""
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y").strftime("%Y%m%d")
    except ValueError:
        return None


def _read_text(pdf_path: Path) -> str:
    """Liest den Rohtext der ersten Seite via pdfplumber."""
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return pdf.pages[0].extract_text() or ""


# ---------------------------------------------------------------------------
# Rechnungsnummer
# ---------------------------------------------------------------------------

def extract_invoice_number(pdf_path: Path) -> Optional[str]:
    """
    Extrahiert die Rechnungsnummer aus dem Dateinamen.
    Fallback auf PDF-Inhalt wenn Dateiname nicht passt.
    """
    match = _FILENAME_PATTERN.match(pdf_path.name)
    if match:
        invoice_number = match.group(1)
        logger.debug("Rechnungsnummer aus Dateiname: %s", invoice_number)
        return invoice_number

    logger.warning(
        "Dateiname entspricht nicht dem erwarteten Format: %s — "
        "versuche Extraktion aus PDF-Inhalt", pdf_path.name
    )
    try:
        text = _read_text(pdf_path)
        match = _CONTENT_PATTERN.search(text)
        if match:
            logger.debug("Rechnungsnummer aus PDF-Inhalt: %s", match.group(1))
            return match.group(1)
        logger.error("Keine Rechnungsnummer gefunden in: %s", pdf_path.name)
        return None
    except Exception as e:
        logger.error("Fehler beim Lesen der PDF %s: %s", pdf_path.name, e)
        return None


# ---------------------------------------------------------------------------
# Empfänger-Adressblock
# ---------------------------------------------------------------------------

def extract_buyer_address(pdf_path: Path) -> dict:
    """
    Extrahiert den Empfänger-Adressblock aus der PDF.

    Der Block steht vor der Zeile "Rechnung YYYYMMDD-NNN" und enthält
    2–5 Zeilen. Erkennt PLZ+Ort und Straße per Regex, alle Zeilen davor
    sind Namenszeilen.

    Returns:
        {
            "buyer_name":   str,   # Zeile 1 (immer vorhanden)
            "buyer_name2":  str,   # Zeile 2 (falls vorhanden)
            "buyer_name3":  str,   # Zeile 3 (falls vorhanden)
            "buyer_street": str,
            "buyer_zip":    str,
            "buyer_city":   str,
        }
        Leeres Dict bei Fehler oder wenn kein Block gefunden.
    """
    try:
        text = _read_text(pdf_path)
        lines = [ln.strip() for ln in text.splitlines()]
        return _parse_address_block(lines)
    except Exception as e:
        logger.warning("Adressblock-Extraktion fehlgeschlagen (%s): %s", pdf_path.name, e)
        return {}


def _parse_address_block(lines: list[str]) -> dict:
    """
    Schneidet den Adressblock vor der 'Rechnung'-Zeile heraus
    und parst ihn in Namens-, Straßen- und PLZ/Ort-Felder.
    """
    # Adressblock = alle nicht-leeren Zeilen vor "Rechnung YYYYMMDD-NNN"
    block = []
    for line in lines:
        if not line:
            continue
        if _RECHNUNG_HEADER_PATTERN.match(line):
            break
        block.append(line)

    if not block:
        logger.debug("Kein Adressblock vor 'Rechnung'-Zeile gefunden")
        return {}

    # Letzte Zeile: PLZ + Ort
    plz_ort_match = _PLZ_ORT_PATTERN.match(block[-1])
    if not plz_ort_match:
        logger.debug("Letzte Zeile des Adressblocks ist kein PLZ+Ort: %r", block[-1])
        return {}

    buyer_zip  = plz_ort_match.group(1)
    buyer_city = plz_ort_match.group(2).strip()
    remaining  = block[:-1]

    # Vorletzte Zeile: Straße (falls Muster passt)
    buyer_street = ""
    if remaining and _STRASSE_PATTERN.match(remaining[-1]):
        buyer_street = remaining[-1]
        remaining = remaining[:-1]
    else:
        # Kein eindeutiges Straßenmuster — trotzdem letzte verbleibende Zeile
        # als Straße nehmen wenn mindestens eine Namenszeile übrig bleibt
        if len(remaining) >= 2:
            buyer_street = remaining[-1]
            remaining = remaining[:-1]

    # Alle verbleibenden Zeilen: Namenszeilen (max. 3)
    names = remaining[-3:] if len(remaining) > 3 else remaining
    buyer_name  = names[0] if len(names) > 0 else ""
    buyer_name2 = names[1] if len(names) > 1 else ""
    buyer_name3 = names[2] if len(names) > 2 else ""

    result = {
        "buyer_name":   buyer_name,
        "buyer_name2":  buyer_name2,
        "buyer_name3":  buyer_name3,
        "buyer_street": buyer_street,
        "buyer_zip":    buyer_zip,
        "buyer_city":   buyer_city,
    }
    logger.debug("Adressblock extrahiert: %s", result)
    return result


# ---------------------------------------------------------------------------
# Lizenznehmer-Kundennummer
# ---------------------------------------------------------------------------

def extract_lizenznehmer_id(pdf_path: Path) -> Optional[str]:
    """
    Extrahiert die Kundennummer des Lizenznehmers aus der PDF.

    Sucht nach dem Muster:
        Lizenznehmer:
        104346 "Türmchenschule" Grundschule Reutershagen Rostock

    Gibt die Kundennummer als String zurück (z. B. '104346'), oder None.
    """
    try:
        text = _read_text(pdf_path)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip().lower() == "lizenznehmer:":
                # Nächste nicht-leere Zeile
                for j in range(i + 1, min(i + 4, len(lines))):
                    next_line = lines[j].strip()
                    if next_line:
                        match = _LIZENZNEHMER_ID_PATTERN.match(next_line)
                        if match:
                            kundennr = match.group(1)
                            logger.debug(
                                "Lizenznehmer-Kundennummer aus PDF: %s", kundennr
                            )
                            return kundennr
                        break
        logger.debug("Keine Lizenznehmer-Zeile gefunden in: %s", pdf_path.name)
        return None
    except Exception as e:
        logger.warning(
            "Lizenznehmer-Extraktion fehlgeschlagen (%s): %s", pdf_path.name, e
        )
        return None


# ---------------------------------------------------------------------------
# Leistungsdatum
# ---------------------------------------------------------------------------

def extract_service_start_date(pdf_path: Path) -> Optional[str]:
    """
    Extrahiert das erste Datum des Abrechnungszeitraums aus dem PDF-Inhalt.
    Gibt das Startdatum als YYYYMMDD zurück, oder None.
    """
    try:
        text = _read_text(pdf_path)
        match = _PERIOD_PATTERN.search(text)
        if match:
            start_date = _parse_date(match.group(1))
            if start_date:
                logger.debug("Leistungsbeginn aus PDF: %s (%s)", start_date, pdf_path.name)
                return start_date
        logger.debug("Kein Abrechnungszeitraum gefunden in: %s", pdf_path.name)
        return None
    except Exception as e:
        logger.warning(
            "Fehler beim Lesen des Abrechnungszeitraums (%s): %s", pdf_path.name, e
        )
        return None