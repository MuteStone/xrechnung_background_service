"""
JSON-Reader — Rechnungsnummer und -daten aus JSON-Dateien extrahieren.

Unterstützte Formate:
  {"invoice_number": "20260105-001", ...}
  {"rechnungsnummer": "20260105-001", ...}
  {"rechnung": {"nummer": "20260105-001"}}
  Vollständige Rechnungsdaten (gleiche Struktur wie get_invoice_full())
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
    Rechnungsdaten ist None wenn nur die Nummer gefunden wurde (DB-Lookup nötig).
    """
    try:
        with open(json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("JSON-Lesefehler %s: %s", json_path.name, e)
        return None, None

    invoice_number = _find_invoice_number(data)

    if not invoice_number:
        logger.error("Keine Rechnungsnummer in %s gefunden", json_path.name)
        return None, None

    logger.debug("Rechnungsnummer aus JSON: %s", invoice_number)

    # Prüfen ob vollständige Positionsdaten vorhanden
    invoice_data = None
    if data.get("items") or data.get("positionen"):
        invoice_data = _normalize_json_data(data, invoice_number)
        logger.info("Vollständige Rechnungsdaten aus JSON geladen")

    return invoice_number, invoice_data


def _find_invoice_number(data: dict) -> Optional[str]:
    if not isinstance(data, dict):
        return None

    # Direkte Schlüssel (case-insensitive)
    for key in list(data.keys()):
        if key.lower() in _NUMBER_KEYS:
            val = data[key]
            if val and _PATTERN.match(str(val)):
                return str(val)

    # Verschachtelte Suche
    for parent_key in _PARENT_KEYS:
        sub = data.get(parent_key, {})
        if isinstance(sub, dict):
            for key in list(sub.keys()):
                if key.lower() in _NUMBER_KEYS:
                    val = sub[key]
                    if val and _PATTERN.match(str(val)):
                        return str(val)

    # Regex-Fallback im gesamten JSON-String
    match = _PATTERN.search(json.dumps(data))
    if match:
        return match.group(1)

    return None


def _normalize_json_data(data: dict, invoice_number: str) -> dict:
    """Normalisiert JSON-Daten auf das interne invoice_data-Format."""
    result = dict(data)
    result["invoice_number"] = invoice_number

    # Positionen normalisieren (alternativ: "positionen" → "items")
    if "positionen" in result and "items" not in result:
        result["items"] = result.pop("positionen")

    items = result.get("items", [])
    normalized_items = []
    for i, item in enumerate(items):
        norm = {
            "position_no":    item.get("position_no") or item.get("pos") or item.get("position") or str(i + 1),
            "item_code":      item.get("item_code") or item.get("artikelcode") or item.get("code") or "",
            "description":    item.get("description") or item.get("bezeichnung") or item.get("name") or "",
            "quantity":       item.get("quantity") or item.get("anzahl") or item.get("menge") or "1",
            "unit_price_net": item.get("unit_price_net") or item.get("einzelpreis") or item.get("preis") or "0",
            "tax_rate":       item.get("tax_rate") or item.get("mwstsatz") or item.get("mwst") or "19",
            "line_total_net": item.get("line_total_net") or item.get("gesamt") or item.get("total") or "0",
            "unit_code":      item.get("unit_code") or "C62",
            "tax_category_code": item.get("tax_category_code") or "S",
        }
        normalized_items.append(norm)

    result["items"] = normalized_items
    return result
