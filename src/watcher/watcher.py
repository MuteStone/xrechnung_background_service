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
from datetime import datetime
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


def _move_to_processed(
    file_path: Path,
    config: dict,
    companion_json: Optional[Path] = None,
    xml_path: Optional[Path] = None,
) -> None:
    """
    Verschiebt alle zu einer erfolgreich verarbeiteten Rechnung gehörenden
    Dateien in einen eigenen Unterordner unter PROCESSED_FOLDER.

    Ordnerstruktur:
        processed/
          <invoice_number_or_stem>/
            <dateiname>.pdf   (oder .json bei Standalone-JSON)
            <dateiname>.json  (falls companion_json vorhanden)
            <dateiname>.xml   (bereits direkt hier erzeugt, kein Kopieren nötig)
    """
    folder_name  = file_path.stem
    processed_dir = Path(config["PROCESSED_FOLDER"]) / folder_name
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Quelldatei(en) verschieben
    for src in [file_path, companion_json]:
        if src and src.exists():
            try:
                shutil.move(str(src), str(processed_dir / src.name))
            except Exception as e:
                logger.warning("Verschieben (processed) fehlgeschlagen (%s): %s", src.name, e)

    # XML wurde bereits direkt in processed/<stem>/ erzeugt — kein Kopieren nötig

    logger.debug("→ processed/%s/: %s", folder_name, file_path.name)


def _move_to_error(
    file_path: Path,
    config: dict,
    reason: str = "",
    companion_json: Optional[Path] = None,
) -> None:
    """
    Verschiebt eine fehlgeschlagene Rechnung in einen eigenen Unterordner
    unter ERROR_FOLDER und erstellt eine Fehler-Log-Datei.

    Ordnerstruktur:
        error/
          YYYYMMDD_HHMMSS_<stem>/
            <dateiname>.pdf   (oder .json)
            <dateiname>.json  (falls companion_json vorhanden)
            error_report.txt
    """
    timestamp  = datetime.now()
    ts_str     = timestamp.strftime("%Y%m%d_%H%M%S")
    folder_name = f"{ts_str}_{file_path.stem}"
    error_dir   = Path(config["ERROR_FOLDER"]) / folder_name
    error_dir.mkdir(parents=True, exist_ok=True)

    # Quelldatei verschieben
    for src in [file_path, companion_json]:
        if src and src.exists():
            try:
                shutil.move(str(src), str(error_dir / src.name))
            except Exception as e:
                logger.warning("Verschieben (error) fehlgeschlagen (%s): %s", src.name, e)

    # Fehler-Log-Datei erstellen
    _write_error_report(
        error_dir=error_dir,
        file_path=file_path,
        companion_json=companion_json,
        reason=reason,
        timestamp=timestamp,
        config=config,
    )

    logger.warning("→ error/%s/: %s", folder_name, file_path.name)


def _write_error_report(
    error_dir: Path,
    file_path: Path,
    companion_json: Optional[Path],
    reason: str,
    timestamp: datetime,
    config: dict,
) -> None:
    """Schreibt eine strukturierte Fehler-Log-Datei für eine fehlgeschlagene Rechnung."""
    report_path = error_dir / "error_report.txt"
    lines = [
        "XRechnung-Hintergrunddienst – Fehlerprotokoll",
        "=" * 52,
        f"Zeitstempel:   {timestamp.strftime('%d.%m.%Y %H:%M:%S')}",
        f"Quelldatei:    {file_path.name}",
    ]
    if companion_json:
        lines.append(f"Begleit-JSON:  {companion_json.name}")
    lines += [
        f"Fehlerordner:  {error_dir.name}",
        "",
        "Fehlerursache:",
        "-" * 52,
        reason if reason else "(kein Fehlergrund übermittelt)",
        "",
        "Log-Auszug (letzte Einträge dieses Dienstlaufs):",
        "-" * 52,
    ]

    # Letzte Log-Zeilen aus der konfigurierten Log-Datei lesen
    try:
        log_file = Path(config.get("LOG_FILE", ""))
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8", errors="replace") as lf:
                all_lines = lf.readlines()
            # Letzte 40 Zeilen, gefiltert auf den Dateinamen der Rechnung
            stem = file_path.stem
            relevant = [
                ln.rstrip()
                for ln in all_lines
                if stem in ln or "ERROR" in ln or "WARNING" in ln
            ][-40:]
            lines += relevant if relevant else ["(keine passenden Log-Einträge gefunden)"]
        else:
            lines.append("(Log-Datei nicht gefunden)")
    except Exception as e:
        lines.append(f"(Log-Auszug nicht verfügbar: {e})")

    lines += ["", "=" * 52]

    try:
        report_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        logger.warning("Fehler-Log-Datei konnte nicht erstellt werden: %s", e)


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

    Returns:
        (success: bool, xml_path: Path | None)
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
        _move_to_error(
            file_path, config,
            reason="Rechnungsnummer konnte nicht aus der Datei extrahiert werden.",
            companion_json=companion_json,
        )
        return False, None

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
        _move_to_error(
            file_path, config,
            reason=f"Keine Rechnungsdaten in der Datenbank für Rechnungsnummer: {invoice_number}",
            companion_json=companion_json,
        )
        return False, None

    # Schritt 3: Verkäuferdaten-Fallback
    _apply_seller_fallback(invoice_data, file_path, config)

    # Schritt 3b: Leistungsdatum aus PDF ermitteln (nur bei PDF-Eingabe)
    # Primär: Startdatum des Abrechnungszeitraums aus dem PDF-Text.
    # Fallback: Rechnungsdatum (behebt BR-DE-TMP-32 wenn kein Zeitraum angegeben).
    if not invoice_data.get("service_start") and file_path.suffix.lower() == ".pdf":
        try:
            from src.xrechnung.pdf_reader import extract_service_start_date
            pdf_service_start = extract_service_start_date(file_path)
            if pdf_service_start:
                invoice_data["service_start"] = pdf_service_start
                logger.info("Leistungsbeginn aus PDF: %s", pdf_service_start)
            else:
                logger.debug(
                    "Kein Abrechnungszeitraum im PDF — Fallback auf Rechnungsdatum"
                )
        except Exception as e:
            logger.warning("Leistungsdatum aus PDF nicht lesbar: %s", e)

    # Schritt 4: XML generieren
    try:
        from src.xrechnung.generator import generate
        # XML direkt in den Processed-Unterordner des Rechnungsstems erzeugen
        xml_out_dir = Path(config["PROCESSED_FOLDER"]) / file_path.stem
        xml_out_dir.mkdir(parents=True, exist_ok=True)
        xml_path = generate(invoice_data, xml_out_dir)
    except Exception as e:
        logger.error("XML-Generierung fehlgeschlagen: %s", e)
        xml_path = None

    if not xml_path:
        logger.error("XML-Generierung fehlgeschlagen: %s", invoice_number)
        _move_to_error(
            file_path, config,
            reason=f"XRechnung-XML konnte nicht erzeugt werden (Rechnungsnummer: {invoice_number}).",
            companion_json=companion_json,
        )
        return False, None

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
        _move_to_error(
            file_path, config,
            reason=f"XSD-Validierung fehlgeschlagen: {xml_path.name} entspricht nicht dem XRechnung-Schema.",
            companion_json=companion_json,
        )
        return False, None

    logger.info("XML-Validierung erfolgreich")


    # Schritt 7: Übertragen
    if dry_run:
        logger.info("[DRY-RUN] E-Mail-Versand übersprungen")
    else:
        try:
            from src.transmitter.transmitter import transmit
            if not transmit(xml_path, config):
                logger.error("Übertragung fehlgeschlagen: %s", xml_path.name)
                _move_to_error(
                    file_path, config,
                    reason=f"E-Mail-Versand an OZG-RE fehlgeschlagen (transmit() → False): {xml_path.name}",
                    companion_json=companion_json,
                )
                return False, None
        except Exception as e:
            logger.error("Übertragung fehlgeschlagen: %s", e)
            _move_to_error(
                file_path, config,
                reason=f"E-Mail-Versand an OZG-RE fehlgeschlagen (Exception): {e}",
                companion_json=companion_json,
            )
            return False, None
        logger.info("Übertragung erfolgreich")

    # Schritt 8: Quelldatei(en) und XML in processed/ verschieben
    _move_to_processed(
        file_path, config,
        companion_json=companion_json,
        xml_path=xml_path,
    )
    logger.info("Abgeschlossen: %s", file_path.name)
    return True, xml_path


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
    invoice_names: list = []
    failed_names:  list = []
    xml_paths:     list = []

    for file_path in files:
        companion = companion_map.get(file_path)
        success, xml_path = process_file(
            file_path, config, dry_run=dry_run, companion_json=companion
        )
        if success:
            processed += 1
            invoice_names.append(file_path.name)
            if xml_path:
                xml_paths.append(xml_path)
        else:
            failed += 1
            failed_names.append(file_path.name)

    # Protokoll-Mail nach Abschluss des Laufs (nur wenn REPORT_EMAIL konfiguriert)
    if not dry_run:
        try:
            from src.transmitter.transmitter import send_report
            send_report(
                config=config,
                processed=processed,
                failed=failed,
                invoice_names=invoice_names,
                failed_names=failed_names,
                xml_paths=xml_paths,
            )
        except Exception as e:
            logger.warning("Protokoll-Mail nicht gesendet: %s", e)

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