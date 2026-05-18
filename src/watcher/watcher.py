"""
File-Watcher & Verarbeitungs-Pipeline
======================================
Überwacht den Eingangsordner auf neue PDF- und JSON-Dateien.
Jede erkannte Datei durchläuft die Pipeline:
  1. Rechnungsnummer extrahieren
  2. Rechnungsdaten laden (JSON-Positionen + DB-Ergänzung, oder nur DB)
  3. Verkäuferdaten-Fallback (DB → PDF-Extraktion → .env-Konfiguration)
  4. XRechnung-XML generieren
  5. XML validieren (XSD)
  6. Zusatzexporte (CSV, JSON-Daten, PDF-Archiv)
  7. XML per E-Mail an OZG-RE übertragen
  8. Quelldatei nach processed/ oder error/ verschieben
"""

import csv
import json
import logging
import re
import shutil
import time
from decimal import Decimal
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

logger = logging.getLogger("xrechnung.watcher")

_INV_RE = re.compile(r'(\d{8}-\d{3})')


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _cfg_bool(config: dict, key: str) -> bool:
    return str(config.get(key, "false")).lower() == "true"


def _move_to_processed(file_path: Path, config: dict) -> None:
    dest = Path(config["PROCESSED_FOLDER"]) / file_path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(file_path), str(dest))
    except Exception as e:
        logger.warning("Verschieben fehlgeschlagen: %s", e)
    logger.debug("→ processed/: %s", file_path.name)


def _move_to_error(file_path: Path, config: dict) -> None:
    dest = Path(config["ERROR_FOLDER"]) / file_path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(file_path), str(dest))
    except Exception as e:
        logger.warning("Verschieben (error) fehlgeschlagen: %s", e)
    logger.warning("→ error/: %s", file_path.name)


def _apply_seller_fallback(invoice_data: dict, file_path: Path, config: dict) -> None:
    """
    Ergänzt fehlende Verkäuferdaten in invoice_data.
    Fallback-Kette: DB-Daten vorhanden → PDF-Extraktion → SELLER_*-Werte aus .env
    """
    if invoice_data.get("seller_name"):
        return

    logger.info("Keine Verkäuferdaten aus DB — versuche Fallback-Quellen …")

    if file_path.suffix.lower() == ".pdf":
        try:
            from src.xrechnung.pdf_seller_reader import extract_seller_from_pdf
            pdf_seller = extract_seller_from_pdf(file_path)
            if pdf_seller.get("seller_name") or pdf_seller.get("seller_iban"):
                for key in [
                    "seller_name", "seller_street", "seller_zip", "seller_city",
                    "seller_vat_id", "seller_iban", "seller_bic",
                    "seller_email", "seller_phone",
                ]:
                    if not invoice_data.get(key):
                        val = pdf_seller.get(key)
                        if val:
                            invoice_data[key] = val
                logger.info("Verkäuferdaten aus PDF ergänzt")
                if invoice_data.get("seller_name"):
                    return
        except Exception as e:
            logger.debug("PDF-Seller-Extraktion fehlgeschlagen: %s", e)

    env_seller = {
        "seller_name":   config.get("SELLER_NAME", ""),
        "seller_street": config.get("SELLER_STREET", ""),
        "seller_zip":    config.get("SELLER_ZIP", ""),
        "seller_city":   config.get("SELLER_CITY", ""),
        "seller_vat_id": config.get("SELLER_VAT_ID", ""),
        "seller_iban":   config.get("SELLER_IBAN", ""),
        "seller_bic":    config.get("SELLER_BIC", ""),
        "seller_email":  config.get("SELLER_EMAIL", ""),
        "seller_phone":  config.get("SELLER_PHONE", ""),
    }
    if env_seller.get("seller_name") or env_seller.get("seller_iban"):
        for key, val in env_seller.items():
            if val and not invoice_data.get(key):
                invoice_data[key] = val
        logger.info("Verkäuferdaten aus .env übernommen")
    else:
        logger.warning(
            "Keine Verkäuferdaten verfügbar — XML wird ohne Absenderdaten erzeugt."
        )


def _export_csv(invoice_data: dict, output_dir: str) -> None:
    try:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        nr   = invoice_data.get("invoice_number", "rechnung")
        path = out / f"{nr}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Rechnungsnummer", nr])
            w.writerow(["Datum",            str(invoice_data.get("invoice_date", ""))])
            w.writerow(["Fälligkeitsdatum", str(invoice_data.get("due_date", ""))])
            w.writerow(["Käufer",           invoice_data.get("buyer_name", "")])
            w.writerow(["Verkäufer",        invoice_data.get("seller_name", "")])
            w.writerow([])
            w.writerow(["Pos.", "Artikel-Nr.", "Bezeichnung", "Menge",
                        "Einzelpreis (netto)", "MwSt. %", "Gesamt (netto)"])
            for item in invoice_data.get("items", []):
                w.writerow([
                    item.get("position_no", ""),
                    item.get("item_code", ""),
                    item.get("description", ""),
                    item.get("quantity", ""),
                    item.get("unit_price_net", ""),
                    item.get("tax_rate", ""),
                    item.get("line_total_net", ""),
                ])
        logger.info("CSV exportiert: %s", path.name)
    except Exception as e:
        logger.error("CSV-Export fehlgeschlagen: %s", e)


def _export_json_data(invoice_data: dict, output_dir: str) -> None:
    try:
        out  = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        nr   = invoice_data.get("invoice_number", "rechnung")
        path = out / f"{nr}_data.json"

        def _default(obj):
            import decimal, datetime
            if isinstance(obj, decimal.Decimal):
                return str(obj)
            if isinstance(obj, (datetime.date, datetime.datetime)):
                return obj.isoformat()
            return str(obj)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(invoice_data, f, ensure_ascii=False, indent=2, default=_default)
        logger.info("JSON-Daten exportiert: %s", path.name)
    except Exception as e:
        logger.error("JSON-Daten-Export fehlgeschlagen: %s", e)


# ---------------------------------------------------------------------------
# Haupt-Pipeline
# ---------------------------------------------------------------------------

def process_file(
    file_path: Path,
    config: dict,
    dry_run: bool = False,
    companion_json: Optional[Path] = None,
) -> bool:
    """
    Verarbeitungs-Pipeline für eine einzelne Rechnung (PDF oder JSON).
    Bei companion_json: PDF als Anker, JSON liefert Positionen, DB ergänzt fehlende Felder.
    """
    logger.info("Verarbeite: %s", file_path.name)

    # Schritt 1: Rechnungsnummer extrahieren
    invoice_data_from_json = None

    if file_path.suffix.lower() == ".json":
        try:
            from src.xrechnung.json_reader import extract_from_json
            invoice_number, invoice_data_from_json = extract_from_json(file_path)
        except Exception as e:
            logger.error("JSON-Lesefehler: %s", e)
            invoice_number = None
    else:
        try:
            from src.xrechnung.pdf_reader import extract_invoice_number
            invoice_number = extract_invoice_number(file_path)
        except Exception as e:
            logger.error("PDF-Lesefehler: %s", e)
            invoice_number = None

    if not invoice_number:
        logger.error("Rechnungsnummer nicht gefunden: %s", file_path.name)
        _move_to_error(file_path, config)
        return False

    logger.info("Rechnungsnummer: %s", invoice_number)

    # Schritt 2: Rechnungsdaten laden
    if invoice_data_from_json and invoice_data_from_json.get("items"):
        # Standalone JSON-Eingabe (kein PDF-Begleiter)
        invoice_data = invoice_data_from_json
        logger.info("Rechnungsdaten aus JSON-Datei übernommen")
    elif companion_json:
        # Gepaarter Modus: JSON liefert Positionen, DB ergänzt fehlende Felder
        json_companion_data = None
        try:
            from src.xrechnung.json_reader import extract_from_json
            _, json_companion_data = extract_from_json(companion_json)
        except Exception as e:
            logger.warning("Begleit-JSON nicht lesbar: %s", e)

        try:
            from src.database.db import get_invoice_full
            db_data = get_invoice_full(invoice_number)
        except Exception as e:
            logger.error("Datenbankfehler: %s", e)
            db_data = None

        if json_companion_data and json_companion_data.get("items"):
            invoice_data = json_companion_data
            if db_data:
                for key, val in db_data.items():
                    if val is not None and val != "" and not invoice_data.get(key):
                        invoice_data[key] = val
            logger.info(
                "Rechnungsdaten: JSON-Positionen + DB-Ergänzung (%s)",
                companion_json.name,
            )
        else:
            invoice_data = db_data
            logger.info("Begleit-JSON ohne Positionen — nur Datenbankdaten verwendet")
    else:
        try:
            from src.database.db import get_invoice_full
            invoice_data = get_invoice_full(invoice_number)
        except Exception as e:
            logger.error("Datenbankfehler: %s", e)
            invoice_data = None

    if not invoice_data:
        logger.error("Keine Rechnungsdaten für %s", invoice_number)
        _move_to_error(file_path, config)
        return False

    # Schritt 3: Verkäuferdaten-Fallback
    _apply_seller_fallback(invoice_data, file_path, config)

    # Schritt 4: XML generieren
    try:
        from src.xrechnung.generator import generate
        xml_path = generate(invoice_data, Path(config["OUTPUT_XML"]))
    except Exception as e:
        logger.error("XML-Generierung fehlgeschlagen: %s", e)
        xml_path = None

    if not xml_path:
        logger.error("XML-Generierung fehlgeschlagen: %s", invoice_number)
        _move_to_error(file_path, config)
        return False

    logger.info("XML erzeugt: %s", xml_path.name)

    # Schritt 5: XML validieren
    try:
        from src.xrechnung.validator import validate
        valid = validate(xml_path)
    except Exception as e:
        logger.warning("XSD-Validierung nicht möglich: %s", e)
        valid = True

    if not valid:
        logger.error("XML-Validierung fehlgeschlagen: %s", xml_path.name)
        _move_to_error(file_path, config)
        return False

    logger.info("XML-Validierung erfolgreich")

    # Schritt 6: Zusatzexporte
    if _cfg_bool(config, "EXPORT_CSV") and config.get("OUTPUT_CSV"):
        _export_csv(invoice_data, config["OUTPUT_CSV"])

    if _cfg_bool(config, "EXPORT_JSON_DATA") and config.get("OUTPUT_JSON_DATA"):
        _export_json_data(invoice_data, config["OUTPUT_JSON_DATA"])

    if _cfg_bool(config, "ARCHIVE_PDF") and file_path.suffix.lower() == ".pdf":
        try:
            arch = Path(config.get("OUTPUT_PDF", "output/pdf"))
            arch.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(file_path), str(arch / file_path.name))
            logger.info("PDF archiviert: %s", file_path.name)
        except Exception as e:
            logger.warning("PDF-Archivierung fehlgeschlagen: %s", e)

    # Schritt 7: Übertragen
    if dry_run:
        logger.info("[DRY-RUN] E-Mail-Versand übersprungen")
    else:
        try:
            from src.transmitter.transmitter import transmit
            if not transmit(xml_path, config):
                logger.error("Übertragung fehlgeschlagen: %s", xml_path.name)
                _move_to_error(file_path, config)
                return False
        except Exception as e:
            logger.error("Übertragung fehlgeschlagen: %s", e)
            _move_to_error(file_path, config)
            return False
        logger.info("Übertragung erfolgreich")

    # Schritt 8: Quelldatei verschieben
    _move_to_processed(file_path, config)
    logger.info("Abgeschlossen: %s", file_path.name)
    return True


# ---------------------------------------------------------------------------
# Dateisammlung mit Paar-Erkennung
# ---------------------------------------------------------------------------

def _collect_files(config: dict) -> tuple[list, dict]:
    """
    Sammelt Dateien aus dem Watch-Folder und bildet PDF+JSON-Paare.
    Gibt (files, companion_map) zurück.
    companion_map: {pdf_path: json_path}
    """
    watch_folder = Path(config["WATCH_FOLDER"])
    scan_json    = _cfg_bool(config, "SCAN_JSON")

    pdf_map : dict = {}
    json_map: dict = {}

    for p in watch_folder.glob("*.pdf"):
        m = _INV_RE.search(p.stem)
        pdf_map[(m.group(1) if m else p.stem).lower()] = p

    if scan_json:
        for p in watch_folder.glob("*.json"):
            m = _INV_RE.search(p.stem)
            json_map[(m.group(1) if m else p.stem).lower()] = p

    companion_map: dict = {}
    files        : list = []

    for key, pdf in pdf_map.items():
        files.append(pdf)
        if key in json_map:
            companion_map[pdf] = json_map[key]
            logger.info("Paar erkannt: %s + %s", pdf.name, json_map[key].name)

    for key, json_path in json_map.items():
        if key not in pdf_map:
            files.append(json_path)

    return files, companion_map


def _log_pair_discrepancies(companion_map: dict) -> None:
    """Protokolliert Abweichungen zwischen JSON und DB als WARNING (kein Dialog im Dienst-Modus)."""
    for _pdf_path, json_path in companion_map.items():
        try:
            from src.xrechnung.json_reader import extract_from_json
            invoice_number, json_data = extract_from_json(json_path)
            if not json_data or not invoice_number:
                continue

            from src.database.db import get_invoice_full
            db_data = get_invoice_full(invoice_number)
            if not db_data:
                continue

            diffs = []
            json_items = json_data.get("items", [])
            db_items   = db_data.get("items", [])
            if len(json_items) != len(db_items):
                diffs.append(
                    f"Positionen: JSON={len(json_items)}, DB={len(db_items)}"
                )

            def _sum_net(data):
                return sum(
                    Decimal(str(i.get("line_total_net") or 0))
                    for i in data.get("items", [])
                )

            json_net = _sum_net(json_data)
            db_net   = _sum_net(db_data)
            if abs(json_net - db_net) > Decimal("0.01"):
                diffs.append(
                    f"Nettosumme: JSON={json_net:.2f}€, DB={db_net:.2f}€"
                )

            if diffs:
                logger.warning(
                    "Abweichung JSON/DB für %s: %s — verwende JSON-Daten",
                    invoice_number,
                    "; ".join(diffs),
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Öffentliche Einstiegspunkte
# ---------------------------------------------------------------------------

def run_once(config: dict, dry_run: bool = False) -> tuple[int, int]:
    """
    Verarbeitet alle vorhandenen Dateien im Watch-Folder einmalig.
    Standard-Modus für den Windows Task Scheduler.

    Returns:
        (processed_count, failed_count)
    """
    watch_folder = Path(config["WATCH_FOLDER"])
    if not watch_folder.exists():
        logger.error("Watch-Folder nicht gefunden: %s", watch_folder)
        return 0, 0

    files, companion_map = _collect_files(config)
    if not files:
        logger.info("Keine Dateien im Watch-Folder gefunden.")
        return 0, 0

    logger.info(
        "%d Datei(en) gefunden (%d Paare PDF+JSON) — starte Verarbeitung …",
        len(files),
        len(companion_map),
    )

    if companion_map:
        _log_pair_discrepancies(companion_map)

    processed = failed = 0
    for file_path in files:
        companion = companion_map.get(file_path)
        if process_file(file_path, config, dry_run=dry_run, companion_json=companion):
            processed += 1
        else:
            failed += 1

    return processed, failed


class _FileHandler(FileSystemEventHandler):
    """Reagiert auf neu erstellte PDF- und JSON-Dateien im Watch-Folder."""

    def __init__(self, config: dict, dry_run: bool = False):
        self.config     = config
        self.dry_run    = dry_run
        self._scan_json = _cfg_bool(config, "SCAN_JSON")

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        ext  = path.suffix.lower()
        if ext == ".pdf" or (ext == ".json" and self._scan_json):
            logger.info("Neue Datei erkannt: %s", path.name)
            time.sleep(0.5)
            process_file(path, self.config, dry_run=self.dry_run)


def run_watch(config: dict, dry_run: bool = False) -> None:
    """
    Dauerhafter File-Watcher (blockierend).
    Nur für Entwicklung — im Produktivbetrieb run_once() via Task Scheduler.
    """
    watch_folder = Path(config["WATCH_FOLDER"])
    if not watch_folder.exists():
        logger.error("Watch-Folder nicht gefunden: %s", watch_folder)
        return

    logger.info("File-Watcher aktiv: %s", watch_folder)
    logger.info("Beenden mit Ctrl+C")

    run_once(config, dry_run=dry_run)

    event_handler = _FileHandler(config, dry_run=dry_run)
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
