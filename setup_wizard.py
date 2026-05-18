"""
XRechnung-Setup-Assistent
=========================
Führt durch die Erstkonfiguration des XRechnung-Hintergrunddienstes:
  Seite 1 – Datenbankverbindung
  Seite 2 – SMTP / E-Mail
  Seite 3 – Ordnerpfade
  Seite 4 – Task Scheduler (optional) + Zusammenfassung
"""

import sys
import os
import shutil
import subprocess
import ctypes
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
    QCheckBox, QSpinBox, QTextEdit, QMessageBox, QGroupBox,
    QTimeEdit, QComboBox, QWidget,
)
from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QFont, QColor, QPalette, QIcon


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def base_dir() -> Path:
    """Installationsverzeichnis — funktioniert auch als PyInstaller-EXE."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def write_env(values: dict, path: Path) -> None:
    """Schreibt alle Konfigurationswerte in die .env-Datei."""
    def v(key, default=""):
        return str(values.get(key, default))

    lines = [
        "# XRechnung-Hintergrunddienst — Konfiguration",
        "# Erstellt durch XRechnung-Setup-Assistent",
        "",
        "# --- Datenbankverbindung ---",
        f"DB_HOST={v('DB_HOST')}",
        f"DB_PORT={v('DB_PORT')}",
        f"DB_NAME={v('DB_NAME')}",
        f"DB_USER={v('DB_USER')}",
        f"DB_PASSWORD={v('DB_PASSWORD')}",
        "",
        "# --- Pfade ---",
        f"WATCH_FOLDER={v('WATCH_FOLDER')}",
        f"OUTPUT_XML={v('OUTPUT_XML', 'output/xml')}",
        f"OUTPUT_PDF={v('OUTPUT_PDF', 'output/pdf')}",
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
        "# --- Scan & Ausgabe ---",
        f"SCAN_JSON={v('SCAN_JSON', 'false')}",
        f"ARCHIVE_PDF={v('ARCHIVE_PDF', 'false')}",
        f"EXPORT_CSV={v('EXPORT_CSV', 'false')}",
        f"OUTPUT_CSV={v('OUTPUT_CSV', 'output/csv')}",
        f"EXPORT_JSON_DATA={v('EXPORT_JSON_DATA', 'false')}",
        f"OUTPUT_JSON_DATA={v('OUTPUT_JSON_DATA', 'output/json_data')}",
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
        "",
        "# --- Logging ---",
        f"LOG_LEVEL={v('LOG_LEVEL', 'INFO')}",
        f"LOG_FILE={v('LOG_FILE', 'logs/xrechnung_dienst.log')}",
        f"LOG_MAX_BYTES={v('LOG_MAX_BYTES', '5242880')}",
        f"LOG_BACKUP_COUNT={v('LOG_BACKUP_COUNT', '3')}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def create_folders(base: Path, values: dict) -> list[str]:
    """Legt alle benötigten Ordner an. Gibt Liste der erstellten Ordner zurück."""
    created = []
    folders = [
        Path(values["OUTPUT_XML"]),
        Path(values["OUTPUT_PDF"]),
        Path(values["PROCESSED_FOLDER"]),
        Path(values["ERROR_FOLDER"]),
        Path(values["LOG_FILE"]).parent,
    ]
    for folder in folders:
        if not folder.is_absolute():
            folder = base / folder
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            created.append(str(folder))
    return created


def setup_task_scheduler(exe_path: Path, start_time: str) -> tuple[bool, str]:
    """Richtet den Windows Task Scheduler ein. Gibt (Erfolg, Meldung) zurück."""
    cmd = [
        "schtasks", "/create",
        "/tn", "XRechnung-Dienst",
        "/tr", str(exe_path),
        "/sc", "DAILY",
        "/st", start_time,
        "/f",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, "Task erfolgreich eingerichtet."
        else:
            return False, result.stderr.strip() or result.stdout.strip()
    except FileNotFoundError:
        return False, "schtasks.exe nicht gefunden (nur unter Windows verfügbar)."
    except subprocess.TimeoutExpired:
        return False, "Zeitüberschreitung beim Einrichten des Tasks."
    except Exception as e:
        return False, str(e)


def test_db_connection(values: dict) -> tuple[bool, str]:
    """Testet die Datenbankverbindung. Gibt (Erfolg, Meldung) zurück."""
    try:
        import pymysql
        conn = pymysql.connect(
            host=values["DB_HOST"],
            port=int(values["DB_PORT"]),
            user=values["DB_USER"],
            password=values["DB_PASSWORD"],
            database=values["DB_NAME"],
            connect_timeout=5,
        )
        conn.close()
        return True, "Verbindung erfolgreich."
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = """
QWizard {
    background-color: #F5F5F5;
}
QWizardPage {
    background-color: #F5F5F5;
}
QLabel {
    font-family: 'Trebuchet MS', Arial;
    font-size: 11pt;
    color: #2C2C2A;
}
QLabel#title {
    font-size: 14pt;
    font-weight: bold;
    color: #E05555;
    padding-bottom: 4px;
}
QLabel#subtitle {
    font-size: 10pt;
    color: #888888;
    padding-bottom: 12px;
}
QLineEdit, QSpinBox, QComboBox, QTimeEdit {
    font-family: 'Trebuchet MS', Arial;
    font-size: 11pt;
    padding: 5px 8px;
    border: 1px solid #CCCCCC;
    border-radius: 0px;
    background: #FFFFFF;
    color: #2C2C2A;
    min-height: 24px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {
    border: 1px solid #E05555;
}
QPushButton {
    font-family: 'Trebuchet MS', Arial;
    font-size: 11pt;
    padding: 6px 16px;
    border: 1px solid #CCCCCC;
    border-radius: 0px;
    background: #FFFFFF;
    color: #2C2C2A;
    min-height: 28px;
}
QPushButton:hover {
    background: #F0F0F0;
    border-color: #E05555;
}
QPushButton#primary {
    background: #E05555;
    color: #FFFFFF;
    border: none;
}
QPushButton#primary:hover {
    background: #C04040;
}
QGroupBox {
    font-family: 'Trebuchet MS', Arial;
    font-size: 11pt;
    font-weight: bold;
    color: #2C2C2A;
    border: 1px solid #CCCCCC;
    margin-top: 12px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QCheckBox {
    font-family: 'Trebuchet MS', Arial;
    font-size: 11pt;
    color: #2C2C2A;
    spacing: 8px;
}
QTextEdit {
    font-family: 'Courier New', monospace;
    font-size: 10pt;
    border: 1px solid #CCCCCC;
    background: #FAFAFA;
    color: #2C2C2A;
    padding: 6px;
}
"""


# ---------------------------------------------------------------------------
# Seite 1 – Datenbankverbindung
# ---------------------------------------------------------------------------

class PageDatabase(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Datenbankverbindung")

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("Datenbankverbindung")
        title.setObjectName("title")
        subtitle = QLabel("Verbindungsdaten zur MySQL-Datenbank der Kundenverwaltung")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self.host = QLineEdit("localhost")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(3306)
        self.port.setGroupSeparatorShown(False)
        self.dbname = QLineEdit()
        self.dbname.setPlaceholderText("z. B. kundenverwaltung")
        self.user = QLineEdit()
        self.user.setPlaceholderText("Datenbankbenutzer")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Passwort")

        form.addRow("Host:", self.host)
        form.addRow("Port:", self.port)
        form.addRow("Datenbankname:", self.dbname)
        form.addRow("Benutzer:", self.user)
        form.addRow("Passwort:", self.password)
        layout.addLayout(form)

        # Verbindungstest
        test_row = QHBoxLayout()
        self.btn_test = QPushButton("Verbindung testen")
        self.lbl_test = QLabel("")
        test_row.addWidget(self.btn_test)
        test_row.addWidget(self.lbl_test)
        test_row.addStretch()
        layout.addLayout(test_row)
        layout.addStretch()

        self.btn_test.clicked.connect(self._test_connection)

        # Felder registrieren
        self.registerField("DB_HOST*", self.host)
        self.registerField("DB_NAME*", self.dbname)
        self.registerField("DB_USER*", self.user)
        self.registerField("DB_PASSWORD", self.password)

        # Felder beobachten damit isComplete() neu bewertet wird
        self.host.textChanged.connect(self.completeChanged)
        self.dbname.textChanged.connect(self.completeChanged)
        self.user.textChanged.connect(self.completeChanged)

    def isComplete(self) -> bool:
        return bool(
            self.host.text().strip()
            and self.dbname.text().strip()
            and self.user.text().strip()
        )

    def _test_connection(self):
        values = {
            "DB_HOST": self.host.text().strip(),
            "DB_PORT": self.port.value(),
            "DB_NAME": self.dbname.text().strip(),
            "DB_USER": self.user.text().strip(),
            "DB_PASSWORD": self.password.text(),
        }
        ok, msg = test_db_connection(values)
        if ok:
            self.lbl_test.setText("✔ " + msg)
            self.lbl_test.setStyleSheet("color: #2E7D32; font-weight: bold;")
        else:
            self.lbl_test.setText("✘ " + msg)
            self.lbl_test.setStyleSheet("color: #E05555; font-weight: bold;")


# ---------------------------------------------------------------------------
# Seite 2 – SMTP / E-Mail
# ---------------------------------------------------------------------------

class PageSMTP(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("E-Mail / SMTP")

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("E-Mail-Konfiguration")
        title.setObjectName("title")
        subtitle = QLabel("Zugangsdaten für den ausgehenden Mailserver (SMTP)")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # SMTP-Gruppe
        grp_smtp = QGroupBox("Mailserver")
        form_smtp = QFormLayout(grp_smtp)
        form_smtp.setSpacing(8)
        form_smtp.setLabelAlignment(Qt.AlignRight)

        self.smtp_host = QLineEdit()
        self.smtp_host.setPlaceholderText("z. B. mail.firma.de oder smtp.gmail.com")
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(25)
        self.smtp_user = QLineEdit()
        self.smtp_user.setPlaceholderText("Benutzername (leer lassen wenn nicht benötigt)")
        self.smtp_password = QLineEdit()
        self.smtp_password.setEchoMode(QLineEdit.Password)
        self.smtp_password.setPlaceholderText("Passwort (leer lassen wenn nicht benötigt)")
        self.smtp_from = QLineEdit()
        self.smtp_from.setPlaceholderText("absender@firma.de")
        self.smtp_from_name = QLineEdit("XRechnung-Dienst")

        form_smtp.addRow("SMTP-Server:", self.smtp_host)
        form_smtp.addRow("Port:", self.smtp_port)
        form_smtp.addRow("Benutzername:", self.smtp_user)
        form_smtp.addRow("Passwort:", self.smtp_password)
        form_smtp.addRow("Absender-E-Mail:", self.smtp_from)
        form_smtp.addRow("Absendername:", self.smtp_from_name)
        layout.addWidget(grp_smtp)

        # OZG-RE-Gruppe
        grp_ozg = QGroupBox("OZG-RE Portal")
        form_ozg = QFormLayout(grp_ozg)
        form_ozg.setSpacing(8)
        form_ozg.setLabelAlignment(Qt.AlignRight)

        self.ozg_email = QLineEdit()
        self.ozg_email.setPlaceholderText("Empfängeradresse des OZG-RE Portals")
        self.ozg_subject = QLineEdit("XRechnung Einreichung")

        form_ozg.addRow("Empfänger-E-Mail:", self.ozg_email)
        form_ozg.addRow("E-Mail-Betreff:", self.ozg_subject)
        layout.addWidget(grp_ozg)
        layout.addStretch()

        self.registerField("SMTP_HOST*", self.smtp_host)
        self.registerField("SMTP_USER", self.smtp_user)
        self.registerField("SMTP_PASSWORD", self.smtp_password)
        self.registerField("SMTP_FROM*", self.smtp_from)
        self.registerField("SMTP_FROM_NAME", self.smtp_from_name)
        self.registerField("OZG_RE_EMAIL*", self.ozg_email)
        self.registerField("OZG_RE_SUBJECT", self.ozg_subject)

        self.smtp_host.textChanged.connect(self.completeChanged)
        self.smtp_from.textChanged.connect(self.completeChanged)
        self.ozg_email.textChanged.connect(self.completeChanged)

    def isComplete(self) -> bool:
        return bool(
            self.smtp_host.text().strip()
            and self.smtp_from.text().strip()
            and self.ozg_email.text().strip()
        )


# ---------------------------------------------------------------------------
# Seite 3 – Ordnerpfade
# ---------------------------------------------------------------------------

class PageFolders(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Ordnerpfade")

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("Ordnerpfade")
        title.setObjectName("title")
        subtitle = QLabel(
            "Wählen Sie zunächst den Installationsordner — "
            "alle Ausgabepfade werden automatisch befüllt."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignRight)

        def folder_row(default: str, placeholder: str = ""):
            row  = QHBoxLayout()
            edit = QLineEdit(default)
            if placeholder:
                edit.setPlaceholderText(placeholder)
            btn = QPushButton("…")
            btn.setFixedWidth(36)
            btn.clicked.connect(lambda _, e=edit: self._browse(e))
            row.addWidget(edit)
            row.addWidget(btn)
            return row, edit

        _default_install = str(Path("C:/Programme/XRechnung"))
        _data            = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "XRechnung"

        row_install, self.install_dir = folder_row(_default_install, "z. B. C:/Programme/XRechnung")
        row_watch,   self.watch       = folder_row("", "Exportordner der Kundenverwaltung")
        row_xml,     self.xml         = folder_row(str(_data / "output" / "xml"))
        row_pdf,     self.pdf         = folder_row(str(_data / "output" / "pdf"))
        row_proc,    self.proc        = folder_row(str(_data / "processed"))
        row_err,     self.err         = folder_row(str(_data / "error"))
        row_log,     self.log         = folder_row(str(_data / "logs" / "xrechnung_dienst.log"))

        form.addRow("Installationsordner:", row_install)
        form.addRow("Überwachungsordner (PDF-Eingang):", row_watch)
        form.addRow("XML-Ausgabeordner:", row_xml)
        form.addRow("PDF-Archivordner:", row_pdf)
        form.addRow("Ordner für verarbeitete PDFs:", row_proc)
        form.addRow("Fehlerordner:", row_err)
        form.addRow("Protokolldatei:", row_log)
        layout.addLayout(form)
        layout.addStretch()

        self.registerField("INSTALL_DIR*",     self.install_dir)
        self.registerField("WATCH_FOLDER*",    self.watch)
        self.registerField("OUTPUT_XML",       self.xml)
        self.registerField("OUTPUT_PDF",       self.pdf)
        self.registerField("PROCESSED_FOLDER", self.proc)
        self.registerField("ERROR_FOLDER",     self.err)
        self.registerField("LOG_FILE",         self.log)

        self.install_dir.textChanged.connect(self._auto_fill_paths)
        self.install_dir.textChanged.connect(self.completeChanged)
        self.watch.textChanged.connect(self.completeChanged)

    def _auto_fill_paths(self, text: str) -> None:
        if not text.strip():
            return
        data = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "XRechnung"
        self.xml.setText(str(data / "output" / "xml"))
        self.pdf.setText(str(data / "output" / "pdf"))
        self.proc.setText(str(data / "processed"))
        self.err.setText(str(data / "error"))
        self.log.setText(str(data / "logs" / "xrechnung_dienst.log"))

    def isComplete(self) -> bool:
        return bool(
            self.install_dir.text().strip()
            and self.watch.text().strip()
        )

    def _browse(self, edit: QLineEdit):
        start = edit.text() or str(Path("C:/"))
        folder = QFileDialog.getExistingDirectory(self, "Ordner auswählen", start)
        if folder:
            edit.setText(folder)


# ---------------------------------------------------------------------------
# Seite 4 – Scan & Ausgabe + Verkäuferdaten
# ---------------------------------------------------------------------------

class PageScanAndSeller(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Scan & Verkäuferdaten")

        from PySide6.QtWidgets import QScrollArea
        scroll  = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout  = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 4, 4, 4)

        title    = QLabel("Scan-Einstellungen & Ausgabedateien")
        title.setObjectName("title")
        subtitle = QLabel("Legen Sie fest, welche Dateiformate verarbeitet und welche Exporte erzeugt werden.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # ── Scan & Ausgabe ─────────────────────────────────────────────────
        scan_grp    = QGroupBox("Eingabe & Ausgabe")
        scan_layout = QVBoxLayout(scan_grp)
        scan_layout.setSpacing(6)

        self.chk_scan_json   = QCheckBox("JSON-Dateien scannen (*.json) — zusätzlich zu PDF")
        self.chk_archive_pdf = QCheckBox("PDF-Archivkopie in OUTPUT_PDF ablegen")
        self.chk_export_csv  = QCheckBox("CSV-Export erzeugen  (*.csv)")
        self.chk_export_json = QCheckBox("JSON-Datenexport erzeugen  (*_data.json)")

        scan_layout.addWidget(self.chk_scan_json)
        scan_layout.addWidget(self.chk_archive_pdf)
        scan_layout.addWidget(self.chk_export_csv)

        csv_row = QHBoxLayout()
        csv_row.setContentsMargins(28, 0, 0, 0)
        lbl_csv      = QLabel("CSV-Ordner:")
        lbl_csv.setFixedWidth(100)
        _data_base   = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "XRechnung"
        self.csv_dir = QLineEdit(str(_data_base / "output" / "csv"))
        btn_csv      = QPushButton("…")
        btn_csv.setFixedWidth(36)
        btn_csv.clicked.connect(lambda: self._browse(self.csv_dir))
        csv_row.addWidget(lbl_csv)
        csv_row.addWidget(self.csv_dir)
        csv_row.addWidget(btn_csv)
        scan_layout.addLayout(csv_row)

        scan_layout.addWidget(self.chk_export_json)

        json_row = QHBoxLayout()
        json_row.setContentsMargins(28, 0, 0, 0)
        lbl_json       = QLabel("JSON-Ordner:")
        lbl_json.setFixedWidth(100)
        self.json_dir  = QLineEdit(str(_data_base / "output" / "json_data"))
        btn_json       = QPushButton("…")
        btn_json.setFixedWidth(36)
        btn_json.clicked.connect(lambda: self._browse(self.json_dir))
        json_row.addWidget(lbl_json)
        json_row.addWidget(self.json_dir)
        json_row.addWidget(btn_json)
        scan_layout.addLayout(json_row)

        # Pfad-Felder nur aktivieren wenn Checkbox gesetzt
        self.chk_export_csv.toggled.connect(self.csv_dir.setEnabled)
        self.chk_export_csv.toggled.connect(btn_csv.setEnabled)
        self.chk_export_json.toggled.connect(self.json_dir.setEnabled)
        self.chk_export_json.toggled.connect(btn_json.setEnabled)
        self.csv_dir.setEnabled(False)
        btn_csv.setEnabled(False)
        self.json_dir.setEnabled(False)
        btn_json.setEnabled(False)

        layout.addWidget(scan_grp)

        # ── Verkäuferdaten ─────────────────────────────────────────────────
        seller_grp  = QGroupBox("Verkäuferdaten (Absender-Fallback)")
        seller_form = QFormLayout(seller_grp)
        seller_form.setSpacing(6)
        seller_form.setLabelAlignment(Qt.AlignRight)

        hint = QLabel(
            "Wird verwendet wenn die Datenbank keine Verkäuferdaten liefert.\n"
            "Reihenfolge: DB → Alternative DB-Tabellen → PDF-Extraktion → diese Felder."
        )
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        seller_form.addRow(hint)

        self.seller_name   = QLineEdit(); self.seller_name.setPlaceholderText("Firmenname GmbH & Co. KG")
        self.seller_street = QLineEdit(); self.seller_street.setPlaceholderText("Musterstraße 1a")
        self.seller_zip    = QLineEdit(); self.seller_zip.setPlaceholderText("12345")
        self.seller_city   = QLineEdit(); self.seller_city.setPlaceholderText("Musterstadt")
        self.seller_vat_id = QLineEdit(); self.seller_vat_id.setPlaceholderText("DE123456789")
        self.seller_iban   = QLineEdit(); self.seller_iban.setPlaceholderText("DE12 3456 7890 …")
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

        pdf_row = QHBoxLayout()
        self.btn_read_pdf  = QPushButton("Aus Rechnungs-PDF lesen …")
        self.lbl_pdf_read  = QLabel("")
        pdf_row.addWidget(self.btn_read_pdf)
        pdf_row.addWidget(self.lbl_pdf_read)
        pdf_row.addStretch()
        seller_form.addRow("", pdf_row)

        self.btn_read_pdf.clicked.connect(self._read_seller_from_pdf)
        layout.addWidget(seller_grp)
        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Felder registrieren
        self.registerField("SCAN_JSON",        self.chk_scan_json,   "checked", self.chk_scan_json.toggled)
        self.registerField("ARCHIVE_PDF",       self.chk_archive_pdf, "checked", self.chk_archive_pdf.toggled)
        self.registerField("EXPORT_CSV",        self.chk_export_csv,  "checked", self.chk_export_csv.toggled)
        self.registerField("OUTPUT_CSV",        self.csv_dir)
        self.registerField("EXPORT_JSON_DATA",  self.chk_export_json, "checked", self.chk_export_json.toggled)
        self.registerField("OUTPUT_JSON_DATA",  self.json_dir)
        self.registerField("SELLER_NAME",       self.seller_name)
        self.registerField("SELLER_STREET",     self.seller_street)
        self.registerField("SELLER_ZIP",        self.seller_zip)
        self.registerField("SELLER_CITY",       self.seller_city)
        self.registerField("SELLER_VAT_ID",     self.seller_vat_id)
        self.registerField("SELLER_IBAN",       self.seller_iban)
        self.registerField("SELLER_BIC",        self.seller_bic)
        self.registerField("SELLER_EMAIL",      self.seller_email)
        self.registerField("SELLER_PHONE",      self.seller_phone)

    def _browse(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Ordner auswählen", edit.text() or str(base_dir()))
        if folder:
            edit.setText(folder)

    def _read_seller_from_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Rechnungs-PDF auswählen", "", "PDF-Dateien (*.pdf)")
        if not path:
            return
        try:
            from pathlib import Path as _Path
            from src.xrechnung.pdf_seller_reader import extract_seller_from_pdf
            data = extract_seller_from_pdf(_Path(path))
        except Exception as e:
            self.lbl_pdf_read.setText(f"✘ {e}")
            self.lbl_pdf_read.setStyleSheet("color: #E05555; font-weight: bold;")
            return

        if not data:
            self.lbl_pdf_read.setText("Keine Daten gefunden")
            self.lbl_pdf_read.setStyleSheet("color: #E05555;")
            return

        mapping = {
            "seller_name":   self.seller_name,
            "seller_street": self.seller_street,
            "seller_zip":    self.seller_zip,
            "seller_city":   self.seller_city,
            "seller_vat_id": self.seller_vat_id,
            "seller_iban":   self.seller_iban,
            "seller_bic":    self.seller_bic,
            "seller_email":  self.seller_email,
            "seller_phone":  self.seller_phone,
        }
        filled = []
        for key, widget in mapping.items():
            val = data.get(key)
            if val:
                widget.setText(str(val))
                filled.append(key.replace("seller_", ""))

        if filled:
            self.lbl_pdf_read.setText(f"✔ {', '.join(filled)} erkannt")
            self.lbl_pdf_read.setStyleSheet("color: #2E7D32; font-weight: bold;")
        else:
            self.lbl_pdf_read.setText("Keine Daten erkannt")
            self.lbl_pdf_read.setStyleSheet("color: #888888;")


# ---------------------------------------------------------------------------
# Seite 5 – Task Scheduler + Zusammenfassung
# ---------------------------------------------------------------------------

class PageFinish(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Abschließen")
        self._applied = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("Konfiguration abschließen")
        title.setObjectName("title")
        subtitle = QLabel("Überprüfen Sie die Einstellungen und klicken Sie auf 'Übernehmen'.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Task-Scheduler-Option
        grp_task = QGroupBox("Windows Task Scheduler (optional)")
        task_layout = QVBoxLayout(grp_task)

        self.chk_task = QCheckBox("Task Scheduler automatisch einrichten")
        self.chk_task.setChecked(True)

        task_time_row = QHBoxLayout()
        lbl_time = QLabel("Tägliche Ausführungszeit:")
        self.task_time = QTimeEdit(QTime(6, 0))
        self.task_time.setDisplayFormat("HH:mm")
        self.task_time.setFixedWidth(100)
        task_time_row.addWidget(lbl_time)
        task_time_row.addWidget(self.task_time)
        task_time_row.addStretch()

        task_layout.addWidget(self.chk_task)
        task_layout.addLayout(task_time_row)
        layout.addWidget(grp_task)

        self.chk_task.toggled.connect(self.task_time.setEnabled)

        # Übernehmen-Button
        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("Übernehmen")
        self.btn_apply.setObjectName("primary")
        self.btn_apply.setFixedHeight(36)
        btn_row.addWidget(self.btn_apply)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Ergebnisanzeige
        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setMinimumHeight(160)
        layout.addWidget(self.result_box)

        self.btn_apply.clicked.connect(self._apply)

    def initializePage(self):
        """Wird aufgerufen wenn die Seite angezeigt wird — Zusammenfassung aufbauen."""
        w = self.wizard()
        def _yn(key):
            return "Ja" if w.field(key) else "Nein"

        lines = [
            "=== Zusammenfassung ===",
            "",
            f"Installationsordner: {w.field('INSTALL_DIR')}",
            f"Datenbank:       {w.field('DB_USER')}@{w.field('DB_HOST')}:{w.field('DB_PORT')}/{w.field('DB_NAME')}",
            f"SMTP:            {w.field('SMTP_HOST')}:{w.field('SMTP_PORT')}",
            f"Absender:        {w.field('SMTP_FROM')}",
            f"OZG-RE Empf.:    {w.field('OZG_RE_EMAIL')}",
            f"Überwachung:     {w.field('WATCH_FOLDER')}",
            f"XML-Ausgabe:     {w.field('OUTPUT_XML')}",
            f"Protokoll:       {w.field('LOG_FILE')}",
            "",
            f"JSON scannen:    {_yn('SCAN_JSON')}",
            f"PDF archivieren: {_yn('ARCHIVE_PDF')}",
            f"CSV-Export:      {_yn('EXPORT_CSV')}",
            f"JSON-Export:     {_yn('EXPORT_JSON_DATA')}",
            f"Verkäufer:       {w.field('SELLER_NAME') or '(nicht gesetzt)'}",
            "",
            "Klicken Sie auf 'Übernehmen' um die Konfiguration zu speichern.",
        ]
        self.result_box.setPlainText("\n".join(lines))
        self._applied = False
        self.completeChanged.emit()

    def _collect_values(self) -> dict:
        w         = self.wizard()
        db_page   = w.page(0)   # PageDatabase  — QSpinBox-Port direkt lesen
        smtp_page = w.page(1)   # PageSMTP      — QSpinBox-Port direkt lesen

        def _bool_str(key):
            val = w.field(key)
            return "true" if val else "false"

        return {
            "INSTALL_DIR":      w.field("INSTALL_DIR"),
            "DB_HOST":          w.field("DB_HOST"),
            "DB_PORT":          str(db_page.port.value()),
            "DB_NAME":          w.field("DB_NAME"),
            "DB_USER":          w.field("DB_USER"),
            "DB_PASSWORD":      w.field("DB_PASSWORD"),
            "WATCH_FOLDER":     w.field("WATCH_FOLDER"),
            "OUTPUT_XML":       w.field("OUTPUT_XML"),
            "OUTPUT_PDF":       w.field("OUTPUT_PDF"),
            "PROCESSED_FOLDER": w.field("PROCESSED_FOLDER"),
            "ERROR_FOLDER":     w.field("ERROR_FOLDER"),
            "SMTP_HOST":        w.field("SMTP_HOST"),
            "SMTP_PORT":        str(smtp_page.smtp_port.value()),
            "SMTP_USER":        w.field("SMTP_USER"),
            "SMTP_PASSWORD":    w.field("SMTP_PASSWORD"),
            "SMTP_FROM":        w.field("SMTP_FROM"),
            "SMTP_FROM_NAME":   w.field("SMTP_FROM_NAME"),
            "OZG_RE_EMAIL":     w.field("OZG_RE_EMAIL"),
            "OZG_RE_SUBJECT":   w.field("OZG_RE_SUBJECT"),
            "SCAN_JSON":        _bool_str("SCAN_JSON"),
            "ARCHIVE_PDF":      _bool_str("ARCHIVE_PDF"),
            "EXPORT_CSV":       _bool_str("EXPORT_CSV"),
            "OUTPUT_CSV":       w.field("OUTPUT_CSV") or str(Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "XRechnung" / "output" / "csv"),
            "EXPORT_JSON_DATA": _bool_str("EXPORT_JSON_DATA"),
            "OUTPUT_JSON_DATA": w.field("OUTPUT_JSON_DATA") or str(Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "XRechnung" / "output" / "json_data"),
            "SELLER_NAME":      w.field("SELLER_NAME"),
            "SELLER_STREET":    w.field("SELLER_STREET"),
            "SELLER_ZIP":       w.field("SELLER_ZIP"),
            "SELLER_CITY":      w.field("SELLER_CITY"),
            "SELLER_VAT_ID":    w.field("SELLER_VAT_ID"),
            "SELLER_IBAN":      w.field("SELLER_IBAN"),
            "SELLER_BIC":       w.field("SELLER_BIC"),
            "SELLER_EMAIL":     w.field("SELLER_EMAIL"),
            "SELLER_PHONE":     w.field("SELLER_PHONE"),
            "LOG_LEVEL":        "INFO",
            "LOG_FILE":         w.field("LOG_FILE"),
            "LOG_MAX_BYTES":    "5242880",
            "LOG_BACKUP_COUNT": "3",
        }

    def _apply(self):
        values      = self._collect_values()
        install_dir = Path(values.get("INSTALL_DIR") or base_dir())
        log         = []

        # Installationsordner anlegen
        try:
            install_dir.mkdir(parents=True, exist_ok=True)
            log.append(f"✔ Installationsordner: {install_dir}")
        except Exception as e:
            log.append(f"✘ Installationsordner konnte nicht angelegt werden: {e}")

        # EXEs aus dem Paket in den Installationsordner extrahieren / kopieren
        _exe_names = ["XRechnung-Dienst.exe", "XRechnung-Monitor.exe"]
        if getattr(sys, "frozen", False):
            _src_dir = Path(sys._MEIPASS)
        else:
            # Entwicklungsmodus: EXEs aus dist/ nehmen (falls bereits gebaut)
            _src_dir = base_dir() / "dist"

        for exe_name in _exe_names:
            src = _src_dir / exe_name
            dst = install_dir / exe_name
            if src.exists():
                try:
                    shutil.copy2(str(src), str(dst))
                    log.append(f"✔ {exe_name} → {install_dir}")
                except Exception as e:
                    log.append(f"✘ {exe_name} konnte nicht kopiert werden: {e}")
            else:
                log.append(f"⚠ {exe_name} nicht gefunden — bitte manuell in {install_dir} ablegen.")

        # .env in den Installationsordner schreiben
        try:
            env_path = install_dir / ".env"
            write_env(values, env_path)
            log.append(f"✔ .env geschrieben: {env_path}")
        except Exception as e:
            log.append(f"✘ .env konnte nicht geschrieben werden: {e}")

        # Ausgabe-Ordner anlegen
        try:
            created = create_folders(install_dir, values)
            if created:
                for f in created:
                    log.append(f"✔ Ordner angelegt: {f}")
            else:
                log.append("✔ Alle Ordner bereits vorhanden.")
        except Exception as e:
            log.append(f"✘ Fehler beim Anlegen der Ordner: {e}")

        # Task Scheduler (optional)
        if self.chk_task.isChecked():
            exe_path = install_dir / "XRechnung-Dienst.exe"
            if not exe_path.exists():
                log.append("⚠ XRechnung-Dienst.exe nicht im Installationsordner — Task nicht eingerichtet.")
            else:
                start_time = self.task_time.time().toString("HH:mm")
                ok, msg = setup_task_scheduler(exe_path, start_time)
                if ok:
                    log.append(f"✔ Task Scheduler eingerichtet (täglich {start_time} Uhr).")
                else:
                    log.append(f"⚠ Task Scheduler: {msg}")
                    log.append("  Hinweis: Administratorrechte erforderlich.")
        else:
            log.append("— Task Scheduler übersprungen (manuell einrichten).")

        log.append("")
        log.append(f"Installation abgeschlossen in: {install_dir}")
        log.append("Monitor starten:  XRechnung-Monitor.exe")
        self.result_box.setPlainText("\n".join(log))
        self._applied = True
        self.btn_apply.setEnabled(False)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._applied


# ---------------------------------------------------------------------------
# Haupt-Wizard
# ---------------------------------------------------------------------------

class SetupWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("XRechnung-Setup-Assistent")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(680, 560)
        self.setStyleSheet(STYLESHEET)

        self.setButtonText(QWizard.NextButton, "Weiter →")
        self.setButtonText(QWizard.BackButton, "← Zurück")
        self.setButtonText(QWizard.FinishButton, "Schließen")
        self.setButtonText(QWizard.CancelButton, "Abbrechen")

        self.addPage(PageDatabase())
        self.addPage(PageSMTP())
        self.addPage(PageFolders())
        self.addPage(PageScanAndSeller())
        self.addPage(PageFinish())

        # Seitenleiste mit Schritten
        self.setOption(QWizard.HaveCustomButton1, False)
        self.setOption(QWizard.IndependentPages, False)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _relaunch_as_admin() -> None:
    exe = sys.executable
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)


def main():
    if not _is_admin():
        _relaunch_as_admin()
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("XRechnung-Setup")
    app.setApplicationVersion("1.0")

    font = QFont("Trebuchet MS", 11)
    app.setFont(font)

    wizard = SetupWizard()
    wizard.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()