"""
JSON-Reader — Rechnungsnummer und -daten aus JSON-Dateien extrahieren.

Unterstützte Formate:
  1. ePost-Format (Priorität):
       {"custom1": "20260105-001", "custom3": "13071156-K000-34",
        "custom4": "100076418", "addressLine1": "Hansestadt Rostock", ...}

  2. Internes Format:
       {"invoice_number": "20260105-001", "items": [...], ...}

  3. Sonstige bekannte Schlüssel:
       {"rechnungsnummer": "...", "nummer": "...", ...}
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("xrechnung.json_reader")

_NUMBER_KEYS = [
    "invoice_number", "invoicenumber", "invoice_no",
    "rechnungsnummer", "rechnungs_nr", "rechnungsnr",
    "nummer", "belegnummer", "dokumentnummer",
]

_PARENT_KEYS = ["invoice", "rechnung", "document", "dokument", "header"]

_PATTERN = re.compile(r"\b(\d{8}-\d{3})\b")


def extract_from_json(json_path: Path) -> tuple[Optional[str], Optional[dict]]:
    """
    Liest eine JSON-Datei und gibt (Rechnungsnummer, Rechnungsdaten) zurück.

    Erkennt automatisch ePost-Format (custom1/custom3/addressLine*) und
    internes Format (invoice_number/items).

    Returns:
        (invoice_number, invoice_data)
        invoice_data ist None wenn nur die Nummer gefunden wurde.
        Bei ePost-Format enthält invoice_data buyer_* und leitweg_id,
        aber keine items (Positionen kommen aus der DB via dokumenteid).
    """
    try:
        with open(json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("JSON-Lesefehler %s: %s", json_path.name, e)
        return None, None

    # ePost-Format erkennen: custom1 oder addressLine1 vorhanden
    if _is_epost_format(data):
        return _extract_epost(data, json_path)

    # Internes / generisches Format
    return _extract_generic(data, json_path)


# ---------------------------------------------------------------------------
# ePost-Format
# ---------------------------------------------------------------------------

def _is_epost_format(data: dict) -> bool:
    """Erkennt das ePost-JSON-Format anhand typischer Schlüssel."""
    return isinstance(data, dict) and (
        "custom1" in data or "addressLine1" in data or "fileName" in data
    )


def _extract_epost(data: dict, json_path: Path) -> tuple[Optional[str], Optional[dict]]:
    """
    Parst das ePost-JSON-Format.

    Mapping:
      custom1  → Rechnungsnummer
      custom2  → buyer_customer_number (Lizenznehmer-Kundennummer)
      custom3  → leitweg_id
      custom4  → dokumenteid (für DB-Positions-Lookup)
      addressLine1–5 → buyer_name, buyer_name2, buyer_name3, buyer_street, buyer_street2
      zipCode  → buyer_zip
      city     → buyer_city
      country  → buyer_country
    """
    # Rechnungsnummer aus custom1
    invoice_number = str(data.get("custom1") or "").strip()
    if not invoice_number or not _PATTERN.match(invoice_number):
        # Fallback: Regex über gesamtes JSON
        match = _PATTERN.search(json.dumps(data))
        invoice_number = match.group(1) if match else None

    if not invoice_number:
        logger.error("ePost-JSON: Keine Rechnungsnummer gefunden in %s", json_path.name)
        return None, None

    logger.debug("ePost-Format erkannt, Rechnungsnummer: %s", invoice_number)

    # Adresszeilen parsen (addressLine1–5)
    addr_lines = [
        str(data.get(f"addressLine{i}") or "").strip()
        for i in range(1, 6)
    ]
    addr_lines = [ln for ln in addr_lines if ln]  # Leerzeilen entfernen

    # Letzte Zeile: PLZ+Ort aus zipCode/city (nicht aus addressLine)
    # Die addressLines enthalten Name und Straße — PLZ/Ort stehen separat
    buyer_zip  = str(data.get("zipCode") or "").strip()
    buyer_city = str(data.get("city") or "").strip()

    # addressLine-Zuweisung: letzte Zeile = Straße, alles davor = Namenszeilen
    buyer_street = ""
    name_lines   = addr_lines

    if addr_lines:
        # Letzte addressLine ist die Straße (Konvention laut ePost-Format)
        buyer_street = addr_lines[-1]
        name_lines   = addr_lines[:-1]

    buyer_name  = name_lines[0] if len(name_lines) > 0 else ""
    buyer_name2 = name_lines[1] if len(name_lines) > 1 else ""
    buyer_name3 = name_lines[2] if len(name_lines) > 2 else ""

    # Leitweg-ID und IDs
    leitweg_id          = str(data.get("custom3") or "").strip()
    buyer_customer_nr   = str(data.get("custom2") or "").strip()
    dokumenteid_str     = str(data.get("custom4") or "").strip()
    dokumenteid         = int(dokumenteid_str) if dokumenteid_str.isdigit() else None

    # Land
    country_raw  = str(data.get("country") or "").strip()
    buyer_country = country_raw if country_raw else "DE"

    invoice_data = {
        "invoice_number":        invoice_number,
        "buyer_name":            buyer_name,
        "buyer_name2":           buyer_name2,
        "buyer_name3":           buyer_name3,
        "buyer_street":          buyer_street,
        "buyer_zip":             buyer_zip,
        "buyer_city":            buyer_city,
        "buyer_country":         buyer_country,
        "buyer_customer_number": buyer_customer_nr,
        "leitweg_id":            leitweg_id,
        # dokumenteid wird in watcher.py für den DB-Lookup verwendet
        "_dokumenteid":          dokumenteid,
        # Keine items — kommen aus der DB via dokumenteid
    }

    logger.info(
        "ePost-JSON geladen: %s — Empfänger: %s, Leitweg-ID: %s",
        invoice_number, buyer_name, leitweg_id or "(leer)"
    )
    return invoice_number, invoice_data


# ---------------------------------------------------------------------------
# Internes / generisches Format
# ---------------------------------------------------------------------------

def _extract_generic(data: dict, json_path: Path) -> tuple[Optional[str], Optional[dict]]:
    """Parst internes oder generisches JSON-Format."""
    invoice_number = _find_invoice_number(data)

    if not invoice_number:
        logger.error("Keine Rechnungsnummer in %s gefunden", json_path.name)
        return None, None

    logger.debug("Rechnungsnummer aus JSON: %s", invoice_number)

    invoice_data = None
    if data.get("items") or data.get("positionen"):
        invoice_data = _normalize_json_data(data, invoice_number)
        logger.info("Vollständige Rechnungsdaten aus JSON geladen")

    return invoice_number, invoice_data


def _find_invoice_number(data: dict) -> Optional[str]:
    if not isinstance(data, dict):
        return None

    for key in list(data.keys()):
        if key.lower() in _NUMBER_KEYS:
            val = data[key]
            if val and _PATTERN.match(str(val)):
                return str(val)

    for parent_key in _PARENT_KEYS:
        sub = data.get(parent_key, {})
        if isinstance(sub, dict):
            for key in list(sub.keys()):
                if key.lower() in _NUMBER_KEYS:
                    val = sub[key]
                    if val and _PATTERN.match(str(val)):
                        return str(val)

    match = _PATTERN.search(json.dumps(data))
    if match:
        return match.group(1)

    return None


def _normalize_json_data(data: dict, invoice_number: str) -> dict:
    """Normalisiert JSON-Daten auf das interne invoice_data-Format."""
    result = dict(data)
    result["invoice_number"] = invoice_number

    if "positionen" in result and "items" not in result:
        result["items"] = result.pop("positionen")

    items = result.get("items", [])
    normalized_items = []
    for i, item in enumerate(items):
        norm = {
            "position_no":       item.get("position_no") or item.get("pos") or item.get("position") or str(i + 1),
            "item_code":         item.get("item_code") or item.get("artikelcode") or item.get("code") or "",
            "description":       item.get("description") or item.get("bezeichnung") or item.get("name") or "",
            "quantity":          item.get("quantity") or item.get("anzahl") or item.get("menge") or "1",
            "unit_price_net":    item.get("unit_price_net") or item.get("einzelpreis") or item.get("preis") or "0",
            "tax_rate":          item.get("tax_rate") or item.get("mwstsatz") or item.get("mwst") or "19",
            "line_total_net":    item.get("line_total_net") or item.get("gesamt") or item.get("total") or "0",
            "unit_code":         item.get("unit_code") or "C62",
            "tax_category_code": item.get("tax_category_code") or "S",
        }
        normalized_items.append(norm)

    result["items"] = normalized_items
    return result