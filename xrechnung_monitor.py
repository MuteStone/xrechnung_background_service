"""
XRechnung-Monitor
=================
Grafische Benutzeroberfläche zur Überwachung und Steuerung
des XRechnung-Hintergrunddienstes.

Enthält den vollständigen Funktionsumfang des Hintergrunddienstes plus:
  - Echtzeit-Protokollanzeige
  - Manuelles Auslösen der Verarbeitung
  - Dauerhafter Datei-Watcher
  - Konfiguration der Ausgabedateien (CSV, JSON-Export)
  - JSON-Datei-Unterstützung als Eingangsformat
  - Einstellbarer Eingangsordner
"""

import sys
import os
import json
import logging
import re
import shutil
import csv
import time
from pathlib import Path
from typing import Optional

# --- Pfad-Setup (PyInstaller-kompatibel) ---
_APPDIR = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
if str(_APPDIR) not in sys.path:
    sys.path.insert(0, str(_APPDIR))


def _find_icon(*names: str):
    """
    Sucht Icon-Dateien in dieser Reihenfolge:
      1. sys._MEIPASS  — PyInstaller --onefile entpackt datas hierhin
      2. _APPDIR       — Entwicklungsmodus oder --onedir
    Gibt den ersten gefundenen Pfad zurück, oder None.
    """
    search_dirs = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        search_dirs.append(Path(sys._MEIPASS))
    search_dirs.append(_APPDIR)
    for directory in search_dirs:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return candidate
    return None

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
    QCheckBox, QSpinBox, QTextEdit, QMessageBox, QGroupBox,
    QTabWidget, QScrollArea, QComboBox, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QMutex, QMutexLocker
from PySide6.QtGui import QFont, QTextCursor, QIcon

# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = """
/* ═══════════════════════════════════════════════════════════════
   XRechnung-Monitor — Modernes Dark-Sidebar-Theme
   Akzentfarbe : #4A9EFF  (Blau)
   Hintergrund : #1C1C1E  (fast schwarz)
   Surface     : #2C2C2E  (dunkelgrau)
   Border      : #3A3A3C
   Text primary: #F2F2F7
   Text muted  : #8E8E93
═══════════════════════════════════════════════════════════════ */

QMainWindow, QDialog {
    background-color: #1C1C1E;
}

QWidget {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 10pt;
    color: #F2F2F7;
    background-color: transparent;
}

/* ── Scrollbereiche ──────────────────────────────────────────── */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}

QScrollBar:vertical {
    width: 6px;
    background: transparent;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3A3A3C;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #4A9EFF;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

/* ── Tabs ────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: none;
    background: #1C1C1E;
}
QTabBar {
    background: #2C2C2E;
}
QTabBar::tab {
    padding: 10px 28px;
    background: #2C2C2E;
    color: #8E8E93;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 10pt;
    font-weight: 500;
    min-width: 110px;
}
QTabBar::tab:selected {
    color: #4A9EFF;
    border-bottom: 2px solid #4A9EFF;
    background: #2C2C2E;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    color: #F2F2F7;
    background: #3A3A3C;
}

/* ── GroupBox = Card ─────────────────────────────────────────── */
QGroupBox {
    background-color: #2C2C2E;
    border: 1px solid #3A3A3C;
    border-radius: 10px;
    margin-top: 18px;
    padding: 14px 14px 10px 14px;
    font-weight: 600;
    font-size: 10pt;
    color: #F2F2F7;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: -1px;
    padding: 2px 6px;
    background-color: #2C2C2E;
    color: #8E8E93;
    font-size: 9pt;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* ── Labels ──────────────────────────────────────────────────── */
QLabel {
    color: #F2F2F7;
    background: transparent;
}
QLabel#title {
    font-size: 14pt;
    font-weight: 700;
    color: #F2F2F7;
    letter-spacing: -0.3px;
}
QLabel#subtitle {
    font-size: 9pt;
    color: #8E8E93;
}
QLabel#section_label {
    font-size: 9pt;
    font-weight: 600;
    color: #8E8E93;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* ── Eingabefelder ───────────────────────────────────────────── */
QLineEdit, QSpinBox, QComboBox {
    padding: 7px 10px;
    border: 1px solid #3A3A3C;
    border-radius: 7px;
    background: #1C1C1E;
    color: #F2F2F7;
    min-height: 20px;
    selection-background-color: #4A9EFF;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #4A9EFF;
    background: #1C1C1E;
}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {
    border-color: #555558;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    background: #2C2C2E;
    color: #48484A;
    border-color: #3A3A3C;
}
QLineEdit[echoMode="2"] {
    lineedit-password-character: 9679;
}

QSpinBox::up-button, QSpinBox::down-button {
    width: 18px;
    border: none;
    background: #3A3A3C;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background: #4A9EFF;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
    background: transparent;
}
QComboBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8E8E93;
}
QComboBox QAbstractItemView {
    background: #2C2C2E;
    border: 1px solid #3A3A3C;
    color: #F2F2F7;
    selection-background-color: #4A9EFF;
    selection-color: #FFFFFF;
    border-radius: 6px;
}

/* ── Buttons ─────────────────────────────────────────────────── */
QPushButton {
    padding: 7px 18px;
    border: 1px solid #3A3A3C;
    border-radius: 7px;
    background: #3A3A3C;
    color: #F2F2F7;
    font-weight: 500;
    min-height: 28px;
}
QPushButton:hover {
    background: #48484A;
    border-color: #555558;
}
QPushButton:pressed {
    background: #2C2C2E;
}
QPushButton#primary {
    background: #4A9EFF;
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}
QPushButton#primary:hover {
    background: #5AABFF;
}
QPushButton#primary:pressed {
    background: #3A8EEF;
}
QPushButton#primary:disabled {
    background: #1C3A5E;
    color: #4A6A8E;
}
QPushButton:disabled {
    background: #2C2C2E;
    color: #48484A;
    border-color: #3A3A3C;
}
QPushButton#danger {
    background: #3A1C1C;
    color: #FF6B6B;
    border: 1px solid #5A2C2C;
}
QPushButton#danger:hover {
    background: #4A2424;
}

/* ── Checkboxen mit echtem Häkchen ───────────────────────────── */
QCheckBox {
    color: #F2F2F7;
    spacing: 10px;
    font-size: 10pt;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1.5px solid #3A3A3C;
    border-radius: 5px;
    background: #1C1C1E;
}
QCheckBox::indicator:hover {
    border-color: #4A9EFF;
}
QCheckBox::indicator:checked {
    background: #4A9EFF;
    border-color: #4A9EFF;
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMiA2TDQuNSA4LjVMMTAgMyIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPjwvc3ZnPg==);
}
QCheckBox::indicator:disabled {
    background: #2C2C2E;
    border-color: #3A3A3C;
}
QCheckBox:disabled {
    color: #48484A;
}

/* ── Log-Fenster ─────────────────────────────────────────────── */
QTextEdit#log_view {
    font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace;
    font-size: 9pt;
    border: 1px solid #3A3A3C;
    border-radius: 8px;
    background: #131315;
    color: #A8B8C8;
    padding: 8px;
    line-height: 1.5;
}

/* ── FormLayout Labels ───────────────────────────────────────── */
QFormLayout QLabel {
    color: #8E8E93;
    font-size: 9pt;
    font-weight: 500;
}

/* ── Statusleiste ────────────────────────────────────────────── */
QStatusBar {
    background: #2C2C2E;
    color: #8E8E93;
    font-size: 9pt;
    border-top: 1px solid #3A3A3C;
}
QStatusBar::item {
    border: none;
}

/* ── Separator ───────────────────────────────────────────────── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {
    color: #3A3A3C;
    background: #3A3A3C;
    border: none;
    max-height: 1px;
}
"""


# ---------------------------------------------------------------------------
# Logging-Handler für die GUI
# ---------------------------------------------------------------------------

class QtLogHandler(logging.Handler):
    """Leitet Log-Einträge als Qt-Signal an die GUI weiter."""

    class _Signaller(QObject):
        record = Signal(str, str)  # (level, formatted_message)

    def __init__(self):
        super().__init__()
        self.signaller = self._Signaller()
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.signaller.record.emit(record.levelname, msg)
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Konfiguration laden / speichern
# ---------------------------------------------------------------------------

def load_config_safe() -> Optional[dict]:
    """Lädt .env-Konfiguration; gibt None zurück wenn nicht vorhanden."""
    try:
        from src.utils.config import load_config
        cfg = load_config()
    except Exception:
        return None

    # Monitor-spezifische Felder nachladen (dotenv hat sie bereits in os.environ)
    cfg["SCAN_JSON"]        = os.getenv("SCAN_JSON", "false")
    cfg["REPORT_EMAIL"]     = os.getenv("REPORT_EMAIL", "")
    cfg["REPORT_ATTACH_XML"]= os.getenv("REPORT_ATTACH_XML", "false")
    return cfg


def save_config(values: dict, env_path: Path) -> None:
    """Schreibt alle Konfigurationswerte in die .env-Datei."""
    def v(key, default=""):
        return str(values.get(key, default))

    lines = [
        "# XRechnung-Hintergrunddienst — Konfiguration",
        "# Erstellt/aktualisiert durch XRechnung-Monitor",
        "",
        "# --- Datenbankverbindung ---",
        f"DB_HOST={v('DB_HOST', 'localhost')}",
        f"DB_PORT={v('DB_PORT', '3306')}",
        f"DB_NAME={v('DB_NAME')}",
        f"DB_USER={v('DB_USER')}",
        f"DB_PASSWORD={v('DB_PASSWORD')}",
        "",
        "# --- Pfade ---",
        f"WATCH_FOLDER={v('WATCH_FOLDER')}",
        f"PROCESSED_FOLDER={v('PROCESSED_FOLDER', 'processed')}",
        f"ERROR_FOLDER={v('ERROR_FOLDER', 'error')}",
        "",
        "# --- SMTP ---",
        f"SMTP_HOST={v('SMTP_HOST')}",
        f"SMTP_PORT={v('SMTP_PORT', '25')}",
        f"SMTP_USER={v('SMTP_USER')}",
        f"SMTP_PASSWORD={v('SMTP_PASSWORD')}",
        f"SMTP_FROM={v('SMTP_FROM')}",
        f"SMTP_FROM_NAME={v('SMTP_FROM_NAME', 'XRechnung-Dienst')}",
        "",
        "# --- OZG-RE Portal ---",
        f"OZG_RE_EMAIL={v('OZG_RE_EMAIL')}",
        f"OZG_RE_SUBJECT={v('OZG_RE_SUBJECT', 'XRechnung Einreichung')}",
        "",
        "# --- Logging ---",
        f"LOG_LEVEL={v('LOG_LEVEL', 'INFO')}",
        f"LOG_FILE={v('LOG_FILE', 'logs/xrechnung_dienst.log')}",
        f"LOG_MAX_BYTES={v('LOG_MAX_BYTES', '5242880')}",
        f"LOG_BACKUP_COUNT={v('LOG_BACKUP_COUNT', '3')}",
        "",
        "# --- Scan-Einstellungen ---",
        f"SCAN_JSON={v('SCAN_JSON', 'false')}",
        "",
        "# --- Protokoll-Mail ---",
        f"REPORT_EMAIL={v('REPORT_EMAIL')}",
        f"REPORT_ATTACH_XML={v('REPORT_ATTACH_XML', 'false')}",
        "",
        "# --- Verkäuferdaten (Fallback wenn Datenbanktabelle fehlt) ---",
        f"SELLER_NAME={v('SELLER_NAME')}",
        f"SELLER_STREET={v('SELLER_STREET')}",
        f"SELLER_ZIP={v('SELLER_ZIP')}",
        f"SELLER_CITY={v('SELLER_CITY')}",
        f"SELLER_VAT_ID={v('SELLER_VAT_ID')}",
        f"SELLER_IBAN={v('SELLER_IBAN')}",
        f"SELLER_BIC={v('SELLER_BIC')}",
        f"SELLER_EMAIL={v('SELLER_EMAIL')}",
        f"SELLER_PHONE={v('SELLER_PHONE')}",
    ]
    env_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Zusätzliche Exporte
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Verarbeitungs-Pipeline
# ---------------------------------------------------------------------------

def _excluded_dirs(config: dict) -> list:
    """
    Liefert die aufgelösten Ausgabe-Ordner (processed/error/output), die beim
    rekursiven Scan übersprungen werden müssen — andernfalls würden bereits
    verschobene Dateien erneut eingelesen, falls diese Ordner innerhalb des
    Eingangsordners liegen.
    """
    dirs = []
    for key in ("PROCESSED_FOLDER", "ERROR_FOLDER", "OUTPUT_XML", "OUTPUT_PDF"):
        val = config.get(key)
        if val:
            try:
                dirs.append(Path(val).resolve())
            except Exception:
                pass
    return dirs


def _is_excluded(path: Path, excluded: list) -> bool:
    """True, wenn path innerhalb eines der ausgeschlossenen Ordner liegt."""
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for d in excluded:
        try:
            if resolved == d or d in resolved.parents:
                return True
        except Exception:
            continue
    return False


def _move_to_processed(
    file_path: Path,
    config: dict,
    companion_json: Optional[Path] = None,
) -> None:
    """Verschiebt alle Dateien einer erfolgreich verarbeiteten Rechnung in einen Unterordner."""
    folder_name   = file_path.stem
    processed_dir = Path(config["PROCESSED_FOLDER"]) / folder_name
    processed_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("xrechnung.monitor")
    for src in [file_path, companion_json]:
        if src and src.exists():
            try:
                shutil.move(str(src), str(processed_dir / src.name))
            except Exception as e:
                log.warning("Verschieben (processed) fehlgeschlagen (%s): %s", src.name, e)
    log.debug("→ processed/%s/: %s", folder_name, file_path.name)


def _move_to_error(
    file_path: Path,
    config: dict,
    reason: str = "",
    companion_json: Optional[Path] = None,
) -> None:
    """Verschiebt fehlgeschlagene Rechnung in einen Unterordner und erstellt Fehlerprotokoll."""
    from datetime import datetime
    timestamp   = datetime.now()
    ts_str      = timestamp.strftime("%Y%m%d_%H%M%S")
    error_dir   = Path(config["ERROR_FOLDER"]) / f"{ts_str}_{file_path.stem}"
    error_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("xrechnung.monitor")
    for src in [file_path, companion_json]:
        if src and src.exists():
            try:
                shutil.move(str(src), str(error_dir / src.name))
            except Exception as e:
                log.warning("Verschieben (error) fehlgeschlagen (%s): %s", src.name, e)
    # Fehlerprotokoll
    report_lines = [
        "XRechnung-Monitor – Fehlerprotokoll",
        "=" * 52,
        f"Zeitstempel:  {timestamp.strftime('%d.%m.%Y %H:%M:%S')}",
        f"Quelldatei:   {file_path.name}",
    ]
    if companion_json:
        report_lines.append(f"Begleit-JSON: {companion_json.name}")
    report_lines += [
        "",
        "Fehlerursache:",
        "-" * 52,
        reason if reason else "(kein Fehlergrund übermittelt)",
        "=" * 52,
    ]
    try:
        (error_dir / "error_report.txt").write_text("\n".join(report_lines), encoding="utf-8")
    except Exception as e:
        log.warning("Fehlerprotokoll konnte nicht erstellt werden: %s", e)
    log.warning("→ error/%s_%s/: %s", ts_str, file_path.stem, file_path.name)


def _apply_seller_fallback(
    invoice_data: dict,
    file_path: Path,
    config: dict,
    log: logging.Logger,
) -> None:
    """
    Ergänzt fehlende Verkäuferdaten in invoice_data.

    Fallback-Kette (erste Quelle mit Daten gewinnt):
      1. DB hat bereits Daten → nichts zu tun
      2. PDF-Extraktion aus der aktuellen Rechnungs-PDF
      3. SELLER_*-Werte aus der .env-Konfiguration
    """
    if invoice_data.get("seller_name"):
        return  # DB-Daten vorhanden, kein Fallback nötig

    log.info("Keine Verkäuferdaten aus DB — versuche Fallback-Quellen …")

    # ── Fallback 2: Aus der PDF extrahieren ─────────────────────────────────
    if file_path.suffix.lower() == ".pdf":
        try:
            from src.xrechnung.pdf_seller_reader import extract_seller_from_pdf
            pdf_seller = extract_seller_from_pdf(file_path)
            if pdf_seller.get("seller_name") or pdf_seller.get("iban"):
                # Felder ins invoice_data übernehmen (nur leere Felder befüllen)
                for pdf_key, inv_key in [
                    ("seller_name",   "seller_name"),
                    ("seller_street", "seller_street"),
                    ("seller_zip",    "seller_zip"),
                    ("seller_city",   "seller_city"),
                    ("vat_id",        "seller_vat_id"),
                    ("iban",          "seller_iban"),
                    ("bic",           "seller_bic"),
                    ("contact_email", "seller_email"),
                    ("contact_phone", "seller_phone"),
                ]:
                    if not invoice_data.get(inv_key):
                        val = pdf_seller.get(pdf_key) or pdf_seller.get(inv_key)
                        if val:
                            invoice_data[inv_key] = val
                log.info("Verkäuferdaten aus PDF ergänzt")
                if invoice_data.get("seller_name"):
                    return
        except Exception as e:
            log.debug("PDF-Seller-Extraktion fehlgeschlagen: %s", e)

    # ── Fallback 3: SELLER_*-Werte aus .env ─────────────────────────────────
    env_seller = {
        "seller_name":    config.get("SELLER_NAME", ""),
        "seller_street":  config.get("SELLER_STREET", ""),
        "seller_zip":     config.get("SELLER_ZIP", ""),
        "seller_city":    config.get("SELLER_CITY", ""),
        "seller_vat_id":  config.get("SELLER_VAT_ID", ""),
        "seller_iban":    config.get("SELLER_IBAN", ""),
        "seller_bic":     config.get("SELLER_BIC", ""),
        "seller_email":   config.get("SELLER_EMAIL", ""),
        "seller_phone":   config.get("SELLER_PHONE", ""),
    }
    if env_seller.get("seller_name") or env_seller.get("seller_iban"):
        for key, val in env_seller.items():
            if val and not invoice_data.get(key):
                invoice_data[key] = val
        log.info("Verkäuferdaten aus Einstellungen (.env) übernommen")
    else:
        log.warning(
            "Keine Verkäuferdaten verfügbar — XML wird ohne Absenderdaten erzeugt. "
            "Bitte im Tab 'Einstellungen → Verkäuferdaten' ausfüllen."
        )


def _check_pairs_for_discrepancies(companion_map: dict, config: dict) -> str:
    """
    Vergleicht für jedes PDF+JSON-Paar die JSON-Positionen mit der Datenbank.
    Gibt einen lesbaren Warntext zurück; leer = keine Abweichungen.
    """
    from decimal import Decimal
    warnings = []

    for _pdf_path, json_path in companion_map.items():
        try:
            from src.xrechnung.json_reader import extract_from_json
            invoice_number, json_data = extract_from_json(json_path)
        except Exception:
            continue

        if not json_data or not invoice_number:
            continue
        # ePost-JSON hat keine items — kein Positions-Vergleich möglich
        if not json_data.get("items"):
            continue

        try:
            from src.database.db import get_invoice_full
            db_data = get_invoice_full(invoice_number)
        except Exception:
            continue

        if not db_data:
            continue

        diffs = []

        json_items = json_data.get("items", [])
        db_items   = db_data.get("items", [])
        if len(json_items) != len(db_items):
            diffs.append(f"  Positionen: JSON={len(json_items)}, DB={len(db_items)}")

        def _sum_net(data):
            return sum(
                Decimal(str(i.get("line_total_net") or 0))
                for i in data.get("items", [])
            )

        json_net = _sum_net(json_data)
        db_net   = _sum_net(db_data)
        if abs(json_net - db_net) > Decimal("0.01"):
            diffs.append(f"  Nettosumme: JSON={json_net:.2f} €, DB={db_net:.2f} €")

        if diffs:
            warnings.append(f"Rechnung {invoice_number} ({json_path.name}):")
            warnings.extend(diffs)

    return "\n".join(warnings)


def process_file(
    file_path: Path,
    config: dict,
    dry_run: bool = False,
    options: Optional[dict] = None,
    companion_json: Optional[Path] = None,
) -> bool:
    """
    Verarbeitungs-Pipeline für eine einzelne Rechnung (PDF oder JSON).

    Schritte:
      1  Rechnungsnummer extrahieren (aus Dateiname, Inhalt oder JSON)
      2  Rechnungsdaten laden (JSON-Positionen + DB-Ergänzung, oder nur DB)
      3  XRechnung-XML generieren
      4  XML gegen XSD validieren
      4b Zusatzexporte (CSV, JSON-Daten, PDF-Archivkopie)
      5  XML per E-Mail übertragen (außer bei dry_run)
      6  Quelldatei in processed/ oder error/ verschieben
    """
    log = logging.getLogger("xrechnung.monitor")
    options = options or {}

    log.info("Verarbeite: %s", file_path.name)

    # ── Schritt 1: Rechnungsnummer ──────────────────────────────────────────
    invoice_data_from_json = None

    if file_path.suffix.lower() == ".json":
        try:
            from src.xrechnung.json_reader import extract_from_json
            invoice_number, invoice_data_from_json = extract_from_json(file_path)
        except Exception as e:
            log.error("JSON-Lesefehler: %s", e)
            invoice_number = None
    else:
        try:
            from src.xrechnung.pdf_reader import extract_invoice_number
            invoice_number = extract_invoice_number(file_path)
        except Exception as e:
            log.error("PDF-Lesefehler: %s", e)
            invoice_number = None

    if not invoice_number:
        log.error("Rechnungsnummer nicht gefunden: %s", file_path.name)
        _move_to_error(file_path, config,
            reason="Rechnungsnummer konnte nicht aus der Datei extrahiert werden.",
            companion_json=companion_json)
        return False

    log.info("Rechnungsnummer: %s", invoice_number)

    # ── Schritt 2: Daten zusammenführen (PDF → JSON → DB) ─────────────────
    invoice_data: dict = {}
    is_pdf = file_path.suffix.lower() == ".pdf"

    # 2a: PDF — Adressblock, Lizenznehmer-ID, Leistungsdatum
    if is_pdf:
        try:
            from src.xrechnung.pdf_reader import (
                extract_buyer_address, extract_lizenznehmer_id, extract_service_start_date,
            )
            pdf_buyer = extract_buyer_address(file_path)
            if pdf_buyer:
                invoice_data.update(pdf_buyer)
                log.info("Empfängeradresse aus PDF: %s", pdf_buyer.get("buyer_name", "?"))
            lizenznehmer_id = extract_lizenznehmer_id(file_path)
            if lizenznehmer_id:
                invoice_data["_lizenznehmer_id"] = lizenznehmer_id
            pdf_service_start = extract_service_start_date(file_path)
            if pdf_service_start:
                invoice_data["service_start"] = pdf_service_start
        except Exception as e:
            log.warning("PDF-Extraktion fehlgeschlagen: %s", e)

    # 2b: JSON (companion oder Standalone)
    json_data   = None
    dokumenteid = None
    epost_json_path = companion_json if companion_json else (
        file_path if file_path.suffix.lower() == ".json" else None
    )
    if epost_json_path:
        try:
            from src.xrechnung.json_reader import extract_from_json
            _, json_data = extract_from_json(epost_json_path)
        except Exception as e:
            log.warning("JSON nicht lesbar (%s): %s", epost_json_path.name, e)

    if json_data:
        dokumenteid = json_data.get("_dokumenteid")
        for key in [
            "buyer_name", "buyer_name2", "buyer_name3",
            "buyer_street", "buyer_zip", "buyer_city", "buyer_country",
            "buyer_customer_number",
        ]:
            val = json_data.get(key)
            if val:
                invoice_data[key] = val
        if json_data.get("leitweg_id"):
            invoice_data["leitweg_id"] = json_data["leitweg_id"]
            log.info("Leitweg-ID aus JSON: %s", invoice_data["leitweg_id"])
        if json_data.get("items"):
            invoice_data["items"] = json_data["items"]

    # 2c: DB — Positionen und Kopfdaten
    db_data = None
    try:
        if dokumenteid:
            from src.database.db import get_invoice_by_dokumenteid
            db_data = get_invoice_by_dokumenteid(dokumenteid)
        else:
            from src.database.db import get_invoice_full
            db_data = get_invoice_full(invoice_number)
    except Exception as e:
        log.error("Datenbankfehler: %s", e)

    _BUYER_KEYS = {
        "buyer_name", "buyer_name2", "buyer_name3",
        "buyer_street", "buyer_zip", "buyer_city", "buyer_country",
        "buyer_customer_number", "leitweg_id",
    }
    if db_data:
        for key, val in db_data.items():
            if key in _BUYER_KEYS:
                if not invoice_data.get(key) and val is not None and val != "":
                    invoice_data[key] = val
            elif key == "items":
                if not invoice_data.get("items") and val:
                    invoice_data[key] = val
            else:
                if val is not None and val != "":
                    invoice_data[key] = val

    # 2d: Leitweg-ID via Lizenznehmer-ID aus PDF
    if not invoice_data.get("leitweg_id"):
        lizenznehmer_id = invoice_data.get("_lizenznehmer_id")
        if lizenznehmer_id:
            try:
                from src.database.db import get_leitweg_id_by_kundenid
                leitweg_id = get_leitweg_id_by_kundenid(int(lizenznehmer_id))
                if leitweg_id:
                    invoice_data["leitweg_id"] = leitweg_id
                    log.info("Leitweg-ID via Lizenznehmer %s: %s", lizenznehmer_id, leitweg_id)
            except Exception as e:
                log.warning("Leitweg-ID-Lookup fehlgeschlagen: %s", e)

    invoice_data.pop("_lizenznehmer_id", None)
    invoice_data.pop("_dokumenteid", None)

    if not invoice_data.get("items"):
        log.error("Keine Rechnungspositionen für %s", invoice_number)
        _move_to_error(file_path, config,
            reason=f"Keine Rechnungspositionen gefunden für: {invoice_number}",
            companion_json=companion_json)
        return False

    if not invoice_data.get("invoice_number"):
        invoice_data["invoice_number"] = invoice_number

    # ── Schritt 2b: Verkäuferdaten-Fallback ────────────────────────────────
    _apply_seller_fallback(invoice_data, file_path, config, log)

    # ── Schritt 3: XML erzeugen ─────────────────────────────────────────────
    try:
        from src.xrechnung.generator import generate
        xml_out_dir = Path(config["PROCESSED_FOLDER"]) / file_path.stem
        xml_out_dir.mkdir(parents=True, exist_ok=True)
        # Original-PDF in die XML einbetten (BT-125), damit OZG-RE sie an den
        # Empfänger weiterreicht. Bei JSON-Quellen gibt es keine PDF.
        source_pdf = file_path if file_path.suffix.lower() == ".pdf" else None
        xml_path = generate(invoice_data, xml_out_dir, pdf_path=source_pdf)
        xml_error = None
    except Exception as e:
        log.error("XML-Generierung fehlgeschlagen: %s", e)
        xml_path = None
        xml_error = str(e)

    if not xml_path:
        reason = (
            f"Vorgang abgebrochen ({invoice_number}): {xml_error}"
            if xml_error else
            f"XML konnte nicht erzeugt werden ({invoice_number})."
        )
        log.error(reason)
        _move_to_error(file_path, config, reason=reason, companion_json=companion_json)
        return False

    log.info("XML erzeugt: %s", xml_path.name)

    # ── Schritt 4: XML validieren ───────────────────────────────────────────
    try:
        from src.xrechnung.validator import validate
        valid = validate(xml_path)
    except Exception as e:
        log.warning("XSD-Validierung nicht möglich: %s", e)
        valid = True

    if not valid:
        log.error("XML-Validierung fehlgeschlagen: %s", xml_path.name)
        _move_to_error(file_path, config,
            reason=f"XSD-Validierung fehlgeschlagen: {xml_path.name}",
            companion_json=companion_json)
        return False

    log.info("XML-Validierung erfolgreich")

    # ── Schritt 4b: KoSIT-Validierung (Geschäftsregeln/Schematron) ──────────
    # Harter Abbruch bei Ablehnung ODER wenn die Prüfung aktiviert, aber nicht
    # verfügbar ist (fail-closed): lieber gar nicht versenden als fehlerhaft.
    if str(config.get("KOSIT_VALIDATION", "true")).lower() == "true":
        from src.xrechnung.kosit_validator import validate_kosit
        kosit = validate_kosit(xml_path)
        if not kosit.ok:
            grund = kosit.detail
            if kosit.messages:
                grund += " | " + " ; ".join(kosit.messages[:5])
            log.error("KoSIT-Validierung abgebrochen: %s — %s", xml_path.name, grund)
            _move_to_error(file_path, config, reason=grund, companion_json=companion_json)
            return False
        log.info("KoSIT-Validierung bestanden")

    # ── Schritt 5: Übertragen ───────────────────────────────────────────────
    if dry_run:
        log.info("[DRY-RUN] E-Mail-Versand übersprungen")
    else:
        try:
            from src.transmitter.transmitter import transmit
            if not transmit(xml_path, config):
                log.error("Übertragung fehlgeschlagen: %s", xml_path.name)
                _move_to_error(file_path, config,
                    reason=f"E-Mail-Versand fehlgeschlagen: {xml_path.name}",
                    companion_json=companion_json)
                return False
        except Exception as e:
            log.error("Übertragung fehlgeschlagen: %s", e)
            _move_to_error(file_path, config,
                reason=f"E-Mail-Versand fehlgeschlagen (Exception): {e}",
                companion_json=companion_json)
            return False
        log.info("Übertragung erfolgreich")

    # ── Schritt 6: Quelldatei(en) in processed/ verschieben ─────────────────
    _move_to_processed(file_path, config, companion_json=companion_json)
    log.info("Abgeschlossen: %s", file_path.name)
    return True


# ---------------------------------------------------------------------------
# Hintergrund-Threads
# ---------------------------------------------------------------------------

class ProcessWorker(QThread):
    """Verarbeitet eine Liste von Dateien in einem Hintergrund-Thread."""

    file_started = Signal(str)
    file_done    = Signal(str)
    file_error   = Signal(str)
    all_done     = Signal(int, int)   # (processed, failed)

    def __init__(self, files: list, config: dict, dry_run: bool = False,
                 options: Optional[dict] = None, companion_map: Optional[dict] = None):
        super().__init__()
        self._files         = files
        self._config        = config
        self._dry_run       = dry_run
        self._options       = options or {}
        self._companion_map = companion_map or {}
        self._stop          = False

    def request_stop(self):
        self._stop = True

    def run(self):
        from src.utils.logger import setup_run_logger, close_run_logger
        from src.transmitter.transmitter import send_report
        import logging as _logging

        # Lauf-Log anlegen
        log_file = self._config.get("LOG_FILE", "logs/xrechnung_dienst.log")
        run_handler = setup_run_logger(log_file=log_file)

        processed    = failed = 0
        invoice_names: list = []
        failed_names:  list = []
        xml_paths:     list = []

        for fp in self._files:
            if self._stop:
                break
            self.file_started.emit(fp.name)
            companion = self._companion_map.get(fp)
            ok = process_file(fp, self._config, self._dry_run, self._options,
                              companion_json=companion)
            if ok:
                processed += 1
                invoice_names.append(fp.name)
                # XML-Pfad aus processed/<stem>/ ermitteln
                xml_candidate = (
                    Path(self._config.get("PROCESSED_FOLDER", "processed"))
                    / fp.stem / f"{fp.stem}.xml"
                )
                if xml_candidate.exists():
                    xml_paths.append(xml_candidate)
                self.file_done.emit(fp.name)
            else:
                failed += 1
                failed_names.append(fp.name)
                self.file_error.emit(fp.name)

        # Protokoll-Mail senden (nur bei echtem Lauf)
        if not self._dry_run:
            report_email = self._config.get("REPORT_EMAIL", "").strip()
            if not report_email:
                _logging.getLogger("xrechnung.monitor").debug(
                    "Protokoll-Mail deaktiviert (REPORT_EMAIL nicht gesetzt)"
                )
            else:
                _logging.getLogger("xrechnung.monitor").info(
                    "Sende Protokoll-Mail an: %s", report_email
                )
                try:
                    run_log_path = None
                    for handler in _logging.getLogger("xrechnung").handlers:
                        if (
                            isinstance(handler, _logging.FileHandler)
                            and "runs" in str(getattr(handler, "baseFilename", ""))
                        ):
                            run_log_path = Path(handler.baseFilename)
                            break
                    ok_mail = send_report(
                        config=self._config,
                        processed=processed,
                        failed=failed,
                        invoice_names=invoice_names,
                        failed_names=failed_names,
                        xml_paths=xml_paths,
                        run_log_path=run_log_path,
                    )
                    if ok_mail:
                        _logging.getLogger("xrechnung.monitor").info(
                            "Protokoll-Mail erfolgreich gesendet"
                        )
                    else:
                        _logging.getLogger("xrechnung.monitor").error(
                            "Protokoll-Mail fehlgeschlagen — prüfe SMTP und REPORT_EMAIL"
                        )
                except Exception as e:
                    _logging.getLogger("xrechnung.monitor").error(
                        "Protokoll-Mail fehlgeschlagen (Exception): %s", e
                    )

        close_run_logger(run_handler)
        self.all_done.emit(processed, failed)


class WatchWorker(QThread):
    """Überwacht einen Ordner dauerhaft auf neue Dateien."""

    files_detected = Signal(list)

    def __init__(self, watch_folder: str, scan_json: bool = False,
                 excluded: Optional[list] = None):
        super().__init__()
        self._folder    = Path(watch_folder)
        self._scan_json = scan_json
        self._excluded  = excluded or []
        self._stop      = False

    def request_stop(self):
        self._stop = True

    def run(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            logging.getLogger("xrechnung.monitor").error(
                "watchdog nicht installiert — Watcher-Modus nicht verfügbar"
            )
            return

        outer = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                p = Path(event.src_path)
                ext = p.suffix.lower()
                if _is_excluded(p, outer._excluded):
                    return
                if ext == ".pdf" or (ext == ".json" and outer._scan_json):
                    time.sleep(0.5)
                    outer.files_detected.emit([p])

        observer = Observer()
        observer.schedule(_Handler(), str(self._folder), recursive=True)
        observer.start()
        try:
            while not self._stop:
                time.sleep(0.5)
        finally:
            observer.stop()
            observer.join()


# ---------------------------------------------------------------------------
# Dashboard-Tab
# ---------------------------------------------------------------------------

class DashboardTab(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Eingangsordner ─────────────────────────────────────────────────
        folder_grp = QGroupBox("Eingangsordner")
        folder_row = QHBoxLayout(folder_grp)
        folder_row.setSpacing(8)

        self.lbl_folder = QLabel("—")
        self.lbl_folder.setWordWrap(True)
        self.lbl_folder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.btn_change_folder = QPushButton("Ordner ändern …")

        folder_row.addWidget(QLabel("Pfad:"))
        folder_row.addWidget(self.lbl_folder, 1)
        folder_row.addWidget(self.btn_change_folder)
        root.addWidget(folder_grp)

        # ── Aktionen ───────────────────────────────────────────────────────
        action_grp = QGroupBox("Verarbeitung")
        action_layout = QVBoxLayout(action_grp)

        btn_row = QHBoxLayout()
        self.btn_run_once = QPushButton("▶  Einmaliger Durchlauf")
        self.btn_run_once.setObjectName("primary")
        self.btn_run_once.setFixedHeight(36)
        self.btn_watch_start = QPushButton("⏵  Watcher starten")
        self.btn_watch_start.setFixedHeight(36)
        self.btn_watch_stop = QPushButton("⏹  Watcher stoppen")
        self.btn_watch_stop.setFixedHeight(36)
        self.btn_watch_stop.setEnabled(False)
        btn_row.addWidget(self.btn_run_once)
        btn_row.addWidget(self.btn_watch_start)
        btn_row.addWidget(self.btn_watch_stop)
        btn_row.addStretch()
        action_layout.addLayout(btn_row)

        opt_row = QHBoxLayout()
        self.chk_dryrun = QCheckBox("Dry-Run (kein E-Mail-Versand)")
        opt_row.addWidget(self.chk_dryrun)
        opt_row.addStretch()

        self.lbl_status = QLabel("● Bereit")
        self.lbl_status.setStyleSheet("color: #30D158; font-weight: 600;")
        opt_row.addWidget(self.lbl_status)
        action_layout.addLayout(opt_row)
        root.addWidget(action_grp)

        # ── Protokoll ──────────────────────────────────────────────────────
        log_grp = QGroupBox("Protokoll")
        log_layout = QVBoxLayout(log_grp)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("log_view")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(280)
        log_layout.addWidget(self.log_view)

        bottom_row = QHBoxLayout()
        self.lbl_stats = QLabel("Verarbeitet: 0 | Fehler: 0")
        self.lbl_stats.setStyleSheet("color: #8E8E93; font-size: 9pt; font-family: 'Segoe UI';")
        bottom_row.addWidget(self.lbl_stats)
        bottom_row.addStretch()
        self.btn_clear = QPushButton("Protokoll leeren")
        self.btn_clear.clicked.connect(self.log_view.clear)
        bottom_row.addWidget(self.btn_clear)
        log_layout.addLayout(bottom_row)
        root.addWidget(log_grp, 1)

        self._processed = 0
        self._failed    = 0

    def append_log(self, level: str, message: str) -> None:
        colors = {
            "DEBUG":    "#888888",
            "INFO":     "#D4D4D4",
            "WARNING":  "#DCDCAA",
            "ERROR":    "#F44747",
            "CRITICAL": "#FF4444",
        }
        color = colors.get(level, "#D4D4D4")
        # HTML-escape angle brackets but keep the rest readable
        safe_msg = (message
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))
        self.log_view.append(f'<span style="color:{color}">{safe_msg}</span>')
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cursor)

    def update_stats(self, processed: int, failed: int) -> None:
        self._processed += processed
        self._failed    += failed
        self.lbl_stats.setText(
            f"Verarbeitet: {self._processed} | Fehler: {self._failed}"
        )

    def set_status(self, text: str, ok: bool = True) -> None:
        color = "#2E7D32" if ok else "#E05555"
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")


# ---------------------------------------------------------------------------
# Einstellungen-Tab
# ---------------------------------------------------------------------------

def _folder_row(edit: QLineEdit, browse_cb) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(4)
    btn = QPushButton("…")
    btn.setFixedWidth(36)
    btn.clicked.connect(lambda: browse_cb(edit))
    row.addWidget(edit)
    row.addWidget(btn)
    return row


class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Datenbank ──────────────────────────────────────────────────────
        db_grp = QGroupBox("Datenbankverbindung")
        db_form = QFormLayout(db_grp)
        db_form.setSpacing(6)
        db_form.setLabelAlignment(Qt.AlignRight)

        self.db_host = QLineEdit()
        self.db_host.setPlaceholderText("localhost")
        self.db_port = QSpinBox()
        self.db_port.setRange(1, 65535)
        self.db_port.setValue(3306)
        self.db_port.setGroupSeparatorShown(False)
        self.db_name = QLineEdit()
        self.db_name.setPlaceholderText("Datenbankname")
        self.db_user = QLineEdit()
        self.db_user.setPlaceholderText("Benutzername")
        self.db_pw = QLineEdit()
        self.db_pw.setEchoMode(QLineEdit.Password)
        self.db_pw.setPlaceholderText("Passwort")

        db_form.addRow("Host:", self.db_host)
        db_form.addRow("Port:", self.db_port)
        db_form.addRow("Datenbankname:", self.db_name)
        db_form.addRow("Benutzer:", self.db_user)
        db_form.addRow("Passwort:", self.db_pw)

        test_row = QHBoxLayout()
        self.btn_test_db = QPushButton("Verbindung testen")
        self.lbl_test_db = QLabel("")
        test_row.addWidget(self.btn_test_db)
        test_row.addWidget(self.lbl_test_db)
        test_row.addStretch()
        db_form.addRow("", test_row)
        layout.addWidget(db_grp)

        # ── SMTP ───────────────────────────────────────────────────────────
        smtp_grp = QGroupBox("E-Mail / SMTP")
        smtp_form = QFormLayout(smtp_grp)
        smtp_form.setSpacing(6)
        smtp_form.setLabelAlignment(Qt.AlignRight)

        self.smtp_host = QLineEdit()
        self.smtp_host.setPlaceholderText("z. B. mail.firma.de")
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(25)
        self.smtp_port.setGroupSeparatorShown(False)
        self.smtp_user = QLineEdit()
        self.smtp_user.setPlaceholderText("Benutzername (leer = kein Login)")
        self.smtp_pw = QLineEdit()
        self.smtp_pw.setEchoMode(QLineEdit.Password)
        self.smtp_pw.setPlaceholderText("Passwort (leer = kein Login)")
        self.smtp_from = QLineEdit()
        self.smtp_from.setPlaceholderText("absender@firma.de")
        self.smtp_from_name = QLineEdit()
        self.smtp_from_name.setPlaceholderText("XRechnung-Dienst")

        smtp_form.addRow("SMTP-Server:", self.smtp_host)
        smtp_form.addRow("Port:", self.smtp_port)
        smtp_form.addRow("Benutzername:", self.smtp_user)
        smtp_form.addRow("Passwort:", self.smtp_pw)
        smtp_form.addRow("Absender-E-Mail:", self.smtp_from)
        smtp_form.addRow("Absendername:", self.smtp_from_name)
        layout.addWidget(smtp_grp)

        # ── OZG-RE ─────────────────────────────────────────────────────────
        ozg_grp = QGroupBox("OZG-RE Portal")
        ozg_form = QFormLayout(ozg_grp)
        ozg_form.setSpacing(6)
        ozg_form.setLabelAlignment(Qt.AlignRight)

        self.ozg_email   = QLineEdit()
        self.ozg_subject = QLineEdit()
        self.ozg_subject.setPlaceholderText("XRechnung Einreichung")

        ozg_form.addRow("Empfänger-E-Mail:", self.ozg_email)
        ozg_form.addRow("Betreff:", self.ozg_subject)
        layout.addWidget(ozg_grp)

        # ── Ordnerpfade ────────────────────────────────────────────────────
        paths_grp = QGroupBox("Ordnerpfade")
        paths_form = QFormLayout(paths_grp)
        paths_form.setSpacing(6)
        paths_form.setLabelAlignment(Qt.AlignRight)

        def mk_edit(placeholder=""):
            e = QLineEdit()
            e.setPlaceholderText(placeholder)
            return e

        self.watch_folder     = mk_edit("Eingangsordner für PDF/JSON-Dateien")
        self.processed_folder = mk_edit("processed")
        self.error_folder     = mk_edit("error")
        self.log_file         = mk_edit("logs/xrechnung_dienst.log")

        def browse(edit: QLineEdit):
            folder = QFileDialog.getExistingDirectory(
                self, "Ordner auswählen", edit.text() or str(_APPDIR)
            )
            if folder:
                edit.setText(folder)

        paths_form.addRow("Eingangsordner:", _folder_row(self.watch_folder, browse))
        paths_form.addRow("Verarbeitet:", _folder_row(self.processed_folder, browse))
        paths_form.addRow("Fehler:", _folder_row(self.error_folder, browse))
        paths_form.addRow("Protokolldatei:", _folder_row(self.log_file, browse))
        layout.addWidget(paths_grp)

        # ── Logging ────────────────────────────────────────────────────────
        log_grp = QGroupBox("Protokollierung")
        log_form = QFormLayout(log_grp)
        log_form.setSpacing(6)
        log_form.setLabelAlignment(Qt.AlignRight)

        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level.setCurrentText("INFO")
        log_form.addRow("Log-Level:", self.log_level)
        layout.addWidget(log_grp)

        # ── Protokoll-Mail ─────────────────────────────────────────────────
        report_grp  = QGroupBox("Protokoll-Mail")
        report_form = QFormLayout(report_grp)
        report_form.setSpacing(6)
        report_form.setLabelAlignment(Qt.AlignRight)

        report_hint = QLabel(
            "Nach jedem Verarbeitungslauf wird ein Protokoll an diese Adresse gesendet.\n"
            "Leer lassen = kein Protokoll."
        )
        report_hint.setObjectName("subtitle")
        report_hint.setWordWrap(True)
        report_form.addRow(report_hint)

        self.report_email = QLineEdit()
        self.report_email.setPlaceholderText("buchhaltung@firma.de")
        report_form.addRow("Protokoll-E-Mail:", self.report_email)

        self.report_attach_xml = QCheckBox("Erzeugte XML-Dateien als Anhang beifügen")
        report_form.addRow("", self.report_attach_xml)

        layout.addWidget(report_grp)

        # ── Verkäuferdaten ─────────────────────────────────────────────────
        seller_grp = QGroupBox("Verkäuferdaten (Absender-Fallback)")
        seller_form = QFormLayout(seller_grp)
        seller_form.setSpacing(6)
        seller_form.setLabelAlignment(Qt.AlignRight)

        seller_hint = QLabel(
            "Wird verwendet wenn die Datenbank keine Verkäuferdaten liefert.\n"
            "Reihenfolge: Datenbank → Alternative DB-Tabellen → PDF-Extraktion → diese Felder."
        )
        seller_hint.setObjectName("subtitle")
        seller_hint.setWordWrap(True)
        seller_form.addRow(seller_hint)

        self.seller_name   = QLineEdit(); self.seller_name.setPlaceholderText("Firmenname")
        self.seller_street = QLineEdit(); self.seller_street.setPlaceholderText("Straße + Hausnummer")
        self.seller_zip    = QLineEdit(); self.seller_zip.setPlaceholderText("PLZ")
        self.seller_city   = QLineEdit(); self.seller_city.setPlaceholderText("Ort")
        self.seller_vat_id = QLineEdit(); self.seller_vat_id.setPlaceholderText("DE123456789")
        self.seller_iban   = QLineEdit(); self.seller_iban.setPlaceholderText("DE12 3456 …")
        self.seller_bic    = QLineEdit(); self.seller_bic.setPlaceholderText("DEUTDEDB")
        self.seller_email  = QLineEdit(); self.seller_email.setPlaceholderText("info@firma.de")
        self.seller_phone  = QLineEdit(); self.seller_phone.setPlaceholderText("+49 …")

        seller_form.addRow("Firmenname:",  self.seller_name)
        seller_form.addRow("Straße:",      self.seller_street)
        seller_form.addRow("PLZ:",         self.seller_zip)
        seller_form.addRow("Ort:",         self.seller_city)
        seller_form.addRow("USt-IdNr.:",   self.seller_vat_id)
        seller_form.addRow("IBAN:",        self.seller_iban)
        seller_form.addRow("BIC:",         self.seller_bic)
        seller_form.addRow("E-Mail:",      self.seller_email)
        seller_form.addRow("Telefon:",     self.seller_phone)

        # "Aus PDF lesen"-Button
        pdf_btn_row = QHBoxLayout()
        self.btn_read_pdf = QPushButton("Aus Rechnungs-PDF lesen …")
        self.lbl_pdf_read = QLabel("")
        pdf_btn_row.addWidget(self.btn_read_pdf)
        pdf_btn_row.addWidget(self.lbl_pdf_read)
        pdf_btn_row.addStretch()
        seller_form.addRow("", pdf_btn_row)

        layout.addWidget(seller_grp)

        self.btn_read_pdf.clicked.connect(self._read_seller_from_pdf)

        # ── Speichern ──────────────────────────────────────────────────────
        save_row = QHBoxLayout()
        self.btn_save = QPushButton("Einstellungen speichern")
        self.btn_save.setObjectName("primary")
        self.btn_save.setFixedHeight(36)
        self.lbl_save = QLabel("")
        save_row.addWidget(self.btn_save)
        save_row.addWidget(self.lbl_save)
        save_row.addStretch()
        layout.addLayout(save_row)
        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.btn_test_db.clicked.connect(self._test_db)

    def _test_db(self) -> None:
        try:
            import pymysql
            conn = pymysql.connect(
                host=self.db_host.text().strip(),
                port=self.db_port.value(),
                user=self.db_user.text().strip(),
                password=self.db_pw.text(),
                database=self.db_name.text().strip(),
                connect_timeout=5,
            )
            conn.close()
            self.lbl_test_db.setText("✔ Verbindung erfolgreich")
            self.lbl_test_db.setStyleSheet("color: #30D158; font-weight: 600;")
        except Exception as e:
            self.lbl_test_db.setText(f"✘ {e}")
            self.lbl_test_db.setStyleSheet("color: #FF6B6B; font-weight: 600;")

    def _read_seller_from_pdf(self) -> None:
        """Öffnet einen PDF-Dialog und befüllt die Verkäufer-Felder automatisch."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Rechnungs-PDF auswählen", "", "PDF-Dateien (*.pdf)"
        )
        if not path:
            return
        try:
            from src.xrechnung.pdf_seller_reader import extract_seller_from_pdf
            data = extract_seller_from_pdf(Path(path))
        except Exception as e:
            self.lbl_pdf_read.setText(f"✘ {e}")
            self.lbl_pdf_read.setStyleSheet("color: #FF6B6B; font-weight: 600;")
            return

        if not data:
            self.lbl_pdf_read.setText("Keine Daten gefunden")
            self.lbl_pdf_read.setStyleSheet("color: #FF6B6B;")
            return

        filled = []
        mapping = {
            "seller_name":  self.seller_name,
            "seller_street": self.seller_street,
            "seller_zip":   self.seller_zip,
            "seller_city":  self.seller_city,
            "vat_id":       self.seller_vat_id,
            "iban":         self.seller_iban,
            "bic":          self.seller_bic,
            "contact_email":self.seller_email,
            "contact_phone":self.seller_phone,
        }
        for pdf_key, widget in mapping.items():
            val = data.get(pdf_key) or data.get(pdf_key.replace("seller_", ""))
            if val:
                widget.setText(str(val))
                filled.append(pdf_key.replace("seller_", "").replace("contact_", ""))

        if filled:
            self.lbl_pdf_read.setText(f"✔ {', '.join(filled)} erkannt")
            self.lbl_pdf_read.setStyleSheet("color: #30D158; font-weight: 600;")
        else:
            self.lbl_pdf_read.setText("Keine Daten erkannt")
            self.lbl_pdf_read.setStyleSheet("color: #8E8E93;")

    def load_from_config(self, cfg: dict) -> None:
        self.db_host.setText(cfg.get("DB_HOST", "localhost"))
        self.db_port.setValue(int(cfg.get("DB_PORT", 3306)))
        self.db_name.setText(cfg.get("DB_NAME", ""))
        self.db_user.setText(cfg.get("DB_USER", ""))
        self.db_pw.setText(cfg.get("DB_PASSWORD", ""))
        self.smtp_host.setText(cfg.get("SMTP_HOST", ""))
        self.smtp_port.setValue(int(cfg.get("SMTP_PORT", 25)))
        self.smtp_user.setText(cfg.get("SMTP_USER", ""))
        self.smtp_pw.setText(cfg.get("SMTP_PASSWORD", ""))
        self.smtp_from.setText(cfg.get("SMTP_FROM", ""))
        self.smtp_from_name.setText(cfg.get("SMTP_FROM_NAME", "XRechnung-Dienst"))
        self.ozg_email.setText(cfg.get("OZG_RE_EMAIL", ""))
        self.ozg_subject.setText(cfg.get("OZG_RE_SUBJECT", "XRechnung Einreichung"))
        self.watch_folder.setText(cfg.get("WATCH_FOLDER", ""))
        self.processed_folder.setText(cfg.get("PROCESSED_FOLDER", "processed"))
        self.error_folder.setText(cfg.get("ERROR_FOLDER", "error"))
        self.log_file.setText(cfg.get("LOG_FILE", "logs/xrechnung_dienst.log"))
        self.log_level.setCurrentText(cfg.get("LOG_LEVEL", "INFO"))
        # Protokoll-Mail
        self.report_email.setText(cfg.get("REPORT_EMAIL", ""))
        self.report_attach_xml.setChecked(
            str(cfg.get("REPORT_ATTACH_XML", "false")).lower() == "true"
        )
        # Verkäuferdaten
        self.seller_name.setText(cfg.get("SELLER_NAME", ""))
        self.seller_street.setText(cfg.get("SELLER_STREET", ""))
        self.seller_zip.setText(cfg.get("SELLER_ZIP", ""))
        self.seller_city.setText(cfg.get("SELLER_CITY", ""))
        self.seller_vat_id.setText(cfg.get("SELLER_VAT_ID", ""))
        self.seller_iban.setText(cfg.get("SELLER_IBAN", ""))
        self.seller_bic.setText(cfg.get("SELLER_BIC", ""))
        self.seller_email.setText(cfg.get("SELLER_EMAIL", ""))
        self.seller_phone.setText(cfg.get("SELLER_PHONE", ""))

    def get_values(self) -> dict:
        return {
            "DB_HOST":          self.db_host.text().strip(),
            "DB_PORT":          str(self.db_port.value()),
            "DB_NAME":          self.db_name.text().strip(),
            "DB_USER":          self.db_user.text().strip(),
            "DB_PASSWORD":      self.db_pw.text(),
            "SMTP_HOST":        self.smtp_host.text().strip(),
            "SMTP_PORT":        str(self.smtp_port.value()),
            "SMTP_USER":        self.smtp_user.text().strip(),
            "SMTP_PASSWORD":    self.smtp_pw.text(),
            "SMTP_FROM":        self.smtp_from.text().strip(),
            "SMTP_FROM_NAME":   self.smtp_from_name.text().strip() or "XRechnung-Dienst",
            "OZG_RE_EMAIL":     self.ozg_email.text().strip(),
            "OZG_RE_SUBJECT":   self.ozg_subject.text().strip() or "XRechnung Einreichung",
            "WATCH_FOLDER":     self.watch_folder.text().strip(),
            "PROCESSED_FOLDER": self.processed_folder.text().strip() or "processed",
            "ERROR_FOLDER":     self.error_folder.text().strip() or "error",
            "LOG_FILE":         self.log_file.text().strip() or "logs/xrechnung_dienst.log",
            "LOG_LEVEL":        self.log_level.currentText(),
            "LOG_MAX_BYTES":    "5242880",
            "LOG_BACKUP_COUNT": "3",
            # Protokoll-Mail
            "REPORT_EMAIL":      self.report_email.text().strip(),
            "REPORT_ATTACH_XML": str(self.report_attach_xml.isChecked()).lower(),
            # Verkäuferdaten
            "SELLER_NAME":    self.seller_name.text().strip(),
            "SELLER_STREET":  self.seller_street.text().strip(),
            "SELLER_ZIP":     self.seller_zip.text().strip(),
            "SELLER_CITY":    self.seller_city.text().strip(),
            "SELLER_VAT_ID":  self.seller_vat_id.text().strip(),
            "SELLER_IBAN":    self.seller_iban.text().strip(),
            "SELLER_BIC":     self.seller_bic.text().strip(),
            "SELLER_EMAIL":   self.seller_email.text().strip(),
            "SELLER_PHONE":   self.seller_phone.text().strip(),
        }


# ---------------------------------------------------------------------------
# Ausgabedateien-Tab  (nur noch Scan-Einstellungen)
# ---------------------------------------------------------------------------

class OutputFilesTab(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("Scan-Einstellungen")
        title.setObjectName("title")
        root.addWidget(title)

        subtitle = QLabel(
            "Legen Sie fest, welche Dateiformate aus dem Eingangsordner verarbeitet werden.\n"
            "Alle erzeugten Dateien (XML, PDF, JSON) werden automatisch in den Verarbeitet-Ordner abgelegt."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # ── Eingabe-Scan ───────────────────────────────────────────────────
        scan_grp = QGroupBox("Eingabe-Scan")
        scan_layout = QVBoxLayout(scan_grp)
        scan_layout.setSpacing(6)

        self.chk_scan_pdf = QCheckBox("PDF-Dateien scannen (*.pdf)  — immer aktiv")
        self.chk_scan_pdf.setChecked(True)
        self.chk_scan_pdf.setEnabled(False)
        scan_layout.addWidget(self.chk_scan_pdf)

        self.chk_scan_json = QCheckBox("JSON-Dateien scannen (*.json)")
        scan_layout.addWidget(self.chk_scan_json)

        json_hint = QLabel(
            "JSON-Format — mindestens einer dieser Schlüssel muss vorhanden sein:\n"
            "  invoice_number · rechnungsnummer · nummer · belegnummer\n"
            'Beispiel minimal: {"invoice_number": "20260105-001"}\n'
            'Beispiel komplett: {"invoice_number": "20260105-001", "items": [...]}'
        )
        json_hint.setStyleSheet(
            "color: #6E6E73; font-size: 9pt; padding: 8px 8px 8px 28px;"
            "background: #131315; border-radius: 6px; margin-left: 28px;"
            "font-family: 'Courier New', monospace;"
        )
        json_hint.setWordWrap(True)
        scan_layout.addWidget(json_hint)
        root.addWidget(scan_grp)

        # ── Hinweis Ausgabe ────────────────────────────────────────────────
        out_grp = QGroupBox("Ausgabe")
        out_layout = QVBoxLayout(out_grp)
        out_layout.setSpacing(6)

        out_info = QLabel(
            "Alle zu einer Rechnung gehörenden Dateien werden nach erfolgreicher Verarbeitung\n"
            "automatisch in einen eigenen Unterordner im Verarbeitet-Ordner abgelegt:\n\n"
            "  verarbeitet/<rechnungsnummer>/\n"
            "    <rechnungsnummer>.pdf\n"
            "    <rechnungsnummer>.json   (falls vorhanden)\n"
            "    <rechnungsnummer>.xml\n\n"
            "Fehlgeschlagene Rechnungen landen mit Fehlerprotokoll unter Fehler/<timestamp_name>/."
        )
        out_info.setStyleSheet(
            "color: #8E8E93; font-size: 9pt; padding: 4px;"
            "font-family: 'Courier New', monospace;"
        )
        out_info.setWordWrap(True)
        out_layout.addWidget(out_info)
        root.addWidget(out_grp)

        root.addStretch()

    def load_from_config(self, cfg: dict) -> None:
        scan_json = str(cfg.get("SCAN_JSON", "false")).lower() == "true"
        self.chk_scan_json.setChecked(scan_json)

    def get_options(self) -> dict:
        return {
            "scan_json": self.chk_scan_json.isChecked(),
        }

    def get_extra_config(self) -> dict:
        return {
            "SCAN_JSON": str(self.chk_scan_json.isChecked()).lower(),
        }


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color: #DDDDDD;")
    return line


# ---------------------------------------------------------------------------
# Hauptfenster
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("XRechnung-Monitor")
        self.setMinimumSize(920, 680)
        self.resize(1020, 740)
        # App-Icon setzen — Suche in _MEIPASS (EXE) dann _APPDIR (Entwicklung)
        _icon_path = _find_icon("fuxmedia_dark.ico", "fuxmedia_dark_256.png")
        if _icon_path:
            self.setWindowIcon(QIcon(str(_icon_path)))

        self._config       : dict             = {}
        self._worker       : Optional[ProcessWorker]  = None
        self._watch_worker : Optional[WatchWorker]    = None

        # Qt-Log-Handler
        self._log_handler = QtLogHandler()
        self._log_handler.setLevel(logging.DEBUG)

        # ── Zentral-Widget ─────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Kopfzeile
        header = QWidget()
        header.setStyleSheet(
            "background-color: #2C2C2E;"
            "border-bottom: 1px solid #3A3A3C;"
        )
        header.setFixedHeight(56)
        hdr_row = QHBoxLayout(header)
        hdr_row.setContentsMargins(20, 0, 20, 0)

        # Blauer Akzentpunkt
        dot = QLabel("●")
        dot.setStyleSheet("color: #4A9EFF; font-size: 10pt; margin-right: 4px;")
        hdr_row.addWidget(dot)

        lbl_appname = QLabel("XRechnung-Monitor")
        lbl_appname.setStyleSheet(
            "color: #F2F2F7; font-size: 13pt; font-weight: 600;"
            "font-family: 'Segoe UI', Arial; letter-spacing: -0.3px;"
        )
        hdr_row.addWidget(lbl_appname)
        hdr_row.addStretch()

        lbl_version = QLabel("v1.0")
        lbl_version.setStyleSheet(
            "color: #48484A; font-size: 9pt;"
            "background: #3A3A3C; border-radius: 4px; padding: 2px 8px;"
        )
        hdr_row.addWidget(lbl_version)
        root.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.dashboard_tab = DashboardTab()
        self.settings_tab  = SettingsTab()
        self.output_tab    = OutputFilesTab()

        self.tabs.addTab(self.dashboard_tab, "  Dashboard  ")
        self.tabs.addTab(self.settings_tab,  "  Einstellungen  ")
        self.tabs.addTab(self.output_tab,    "  Ausgabedateien  ")
        root.addWidget(self.tabs)

        # Status-Leiste
        self.statusBar().showMessage("Bereit")

        # ── Signale verbinden ─────────────────────────────────────────────
        self._log_handler.signaller.record.connect(self.dashboard_tab.append_log)

        self.dashboard_tab.btn_run_once.clicked.connect(self._run_once)
        self.dashboard_tab.btn_watch_start.clicked.connect(self._start_watch)
        self.dashboard_tab.btn_watch_stop.clicked.connect(self._stop_watch)
        self.dashboard_tab.btn_change_folder.clicked.connect(self._change_folder)

        self.settings_tab.btn_save.clicked.connect(self._save_settings)

        # ── Logging einrichten ────────────────────────────────────────────
        root_log = logging.getLogger("xrechnung")
        root_log.addHandler(self._log_handler)
        root_log.setLevel(logging.DEBUG)

        # Auch Monitor-Logger
        mon_log = logging.getLogger("xrechnung.monitor")
        mon_log.setLevel(logging.DEBUG)

        # ── Konfiguration laden ───────────────────────────────────────────
        self._reload_config()

    # ── Konfiguration ──────────────────────────────────────────────────────

    def _reload_config(self) -> None:
        cfg = load_config_safe()
        if cfg:
            self._config = cfg
            self.settings_tab.load_from_config(cfg)
            self.output_tab.load_from_config(cfg)
            folder = cfg.get("WATCH_FOLDER", "—")
            self.dashboard_tab.lbl_folder.setText(folder)
            self.statusBar().showMessage(f"Konfiguration geladen  |  Ordner: {folder}")
        else:
            self.statusBar().showMessage(
                "Keine .env-Konfiguration gefunden — bitte Einstellungen ausfüllen"
            )
            self.tabs.setCurrentIndex(1)

    def _save_settings(self) -> None:
        values = self.settings_tab.get_values()
        values.update(self.output_tab.get_extra_config())

        env_path = _APPDIR / ".env"
        try:
            save_config(values, env_path)
            self.settings_tab.lbl_save.setText("✔ Gespeichert")
            self.settings_tab.lbl_save.setStyleSheet("color: #30D158; font-weight: 600;")
            self._reload_config()
        except Exception as e:
            self.settings_tab.lbl_save.setText(f"✘ {e}")
            self.settings_tab.lbl_save.setStyleSheet("color: #FF6B6B; font-weight: 600;")

    def _change_folder(self) -> None:
        current = self._config.get("WATCH_FOLDER", str(_APPDIR))
        folder = QFileDialog.getExistingDirectory(self, "Eingangsordner auswählen", current)
        if folder:
            self._config["WATCH_FOLDER"] = folder
            self.dashboard_tab.lbl_folder.setText(folder)
            self.settings_tab.watch_folder.setText(folder)

    # ── Einmaliger Durchlauf ───────────────────────────────────────────────

    def _run_once(self) -> None:
        if not self._config.get("WATCH_FOLDER"):
            QMessageBox.warning(self, "Kein Eingangsordner",
                                "Bitte zunächst den Eingangsordner in den Einstellungen festlegen.")
            self.tabs.setCurrentIndex(1)
            return

        watch_folder = Path(self._config["WATCH_FOLDER"])
        if not watch_folder.exists():
            QMessageBox.warning(self, "Ordner nicht gefunden",
                                f"Der Eingangsordner wurde nicht gefunden:\n{watch_folder}")
            return

        options = self.output_tab.get_options()

        # Dateien nach Rechnungsnummer gruppieren (inkl. Unterordner)
        _inv_re  = re.compile(r'(\d{8}-\d{3})')
        pdf_map  : dict = {}   # key → pdf_path
        json_map : dict = {}   # key → json_path
        excluded = _excluded_dirs({**self._config, **self.output_tab.get_extra_config()})

        for p in watch_folder.rglob("*.pdf"):
            if _is_excluded(p, excluded):
                continue
            m = _inv_re.search(p.stem)
            pdf_map[(m.group(1) if m else p.stem).lower()] = p

        if options.get("scan_json"):
            for p in watch_folder.rglob("*.json"):
                if _is_excluded(p, excluded):
                    continue
                m = _inv_re.search(p.stem)
                json_map[(m.group(1) if m else p.stem).lower()] = p

        # Paare bilden (PDF + begleitende JSON) und reine JSON-only-Dateien sammeln
        companion_map : dict = {}   # pdf_path → json_path
        files : list = []

        for key, pdf in pdf_map.items():
            files.append(pdf)
            if key in json_map:
                companion_map[pdf] = json_map[key]

        for key, json_path in json_map.items():
            if key not in pdf_map:
                files.append(json_path)

        if not files:
            logging.getLogger("xrechnung.monitor").info(
                "Keine Dateien im Eingangsordner gefunden."
            )
            self.statusBar().showMessage("Keine Dateien gefunden.")
            return

        # Abgleich: Paare auf Abweichungen zwischen JSON und DB prüfen
        if companion_map:
            config_pre = {**self._config, **self.output_tab.get_extra_config()}
            warn_text  = _check_pairs_for_discrepancies(companion_map, config_pre)
            if warn_text:
                msg = QMessageBox(self)
                msg.setWindowTitle("Abweichungen zwischen JSON und Datenbank")
                msg.setIcon(QMessageBox.Warning)
                msg.setText(
                    "Bei folgenden Rechnungen weichen JSON-Daten und Datenbank voneinander ab.\n"
                    "JSON-Positionen haben Vorrang — die Datenbank ergänzt nur fehlende Felder."
                )
                msg.setDetailedText(warn_text)
                msg.setInformativeText("Soll die Verarbeitung trotzdem fortgesetzt werden?")
                btn_proceed = msg.addButton("Fortfahren", QMessageBox.AcceptRole)
                msg.addButton("Abbrechen",  QMessageBox.RejectRole)
                msg.exec()
                if msg.clickedButton() is not btn_proceed:
                    return

        logging.getLogger("xrechnung.monitor").info(
            "%d Datei(en) gefunden (%d Paare PDF+JSON) — starte Verarbeitung …",
            len(files), len(companion_map)
        )

        config = {**self._config, **self.output_tab.get_extra_config()}
        dry    = self.dashboard_tab.chk_dryrun.isChecked()

        self._worker = ProcessWorker(files, config, dry_run=dry, options=options,
                                     companion_map=companion_map)
        self._worker.all_done.connect(self._on_done)
        self._worker.started.connect(lambda: self._set_busy(True))
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._worker.start()

    def _on_done(self, processed: int, failed: int) -> None:
        self.dashboard_tab.update_stats(processed, failed)
        msg = f"Abgeschlossen: {processed} verarbeitet"
        if failed:
            msg += f",  {failed} fehlgeschlagen"
        self.statusBar().showMessage(msg)

    # ── Watcher ───────────────────────────────────────────────────────────

    def _start_watch(self) -> None:
        folder = self._config.get("WATCH_FOLDER", "")
        if not folder or not Path(folder).exists():
            QMessageBox.warning(self, "Fehler",
                                "Eingangsordner nicht gefunden. Bitte Einstellungen prüfen.")
            return

        options  = self.output_tab.get_options()
        excluded = _excluded_dirs({**self._config, **self.output_tab.get_extra_config()})
        self._watch_worker = WatchWorker(
            folder,
            scan_json=options.get("scan_json", False),
            excluded=excluded,
        )
        self._watch_worker.files_detected.connect(self._on_files_detected)
        self._watch_worker.start()

        self.dashboard_tab.btn_watch_start.setEnabled(False)
        self.dashboard_tab.btn_watch_stop.setEnabled(True)
        self.dashboard_tab.set_status("● Watcher aktiv", ok=True)
        self.statusBar().showMessage(f"Watcher aktiv  |  {folder}")
        logging.getLogger("xrechnung.monitor").info("Watcher gestartet: %s", folder)

    def _stop_watch(self) -> None:
        if self._watch_worker:
            self._watch_worker.request_stop()
            self._watch_worker.wait(3000)
            self._watch_worker = None

        self.dashboard_tab.btn_watch_start.setEnabled(True)
        self.dashboard_tab.btn_watch_stop.setEnabled(False)
        self.dashboard_tab.set_status("● Bereit", ok=True)
        self.statusBar().showMessage("Watcher gestoppt")
        logging.getLogger("xrechnung.monitor").info("Watcher gestoppt")

    def _on_files_detected(self, files: list) -> None:
        if self._worker and self._worker.isRunning():
            return  # Noch in Verarbeitung — neue Dateien warten
        dry    = self.dashboard_tab.chk_dryrun.isChecked()
        options= self.output_tab.get_options()
        config = {**self._config, **self.output_tab.get_extra_config()}
        self._worker = ProcessWorker(files, config, dry_run=dry, options=options)
        self._worker.all_done.connect(self._on_done)
        self._worker.start()

    # ── Hilfsmethoden ────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self.dashboard_tab.btn_run_once.setEnabled(not busy)
        if busy:
            self.dashboard_tab.set_status("● Verarbeitung läuft …", ok=True)
        else:
            if not self._watch_worker:
                self.dashboard_tab.set_status("● Bereit", ok=True)

    def closeEvent(self, event) -> None:
        if self._watch_worker:
            self._watch_worker.request_stop()
            self._watch_worker.wait(2000)
        if self._worker and self._worker.isRunning():
            self._worker.wait(3000)
        event.accept()


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("XRechnung-Monitor")
    app.setApplicationVersion("1.0")
    _app_icon_path = _find_icon("fuxmedia_dark.ico", "fuxmedia_dark_256.png")
    if _app_icon_path:
        app.setWindowIcon(QIcon(str(_app_icon_path)))
    app.setFont(QFont("Trebuchet MS", 11))
    app.setStyleSheet(STYLESHEET)

    # Basis-Logger initialisieren
    logging.getLogger("xrechnung").setLevel(logging.DEBUG)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()