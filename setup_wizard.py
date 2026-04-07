"""
XRechnung-Hintergrunddienst – Setup-Assistent
==============================================
Führt den Administrator Schritt für Schritt durch die Erstkonfiguration
und schreibt am Ende eine vollständige .env-Datei.

Standalone-Build (keine Python-Installation erforderlich):
    pip install pyinstaller
    pyinstaller --onefile --windowed --name "XRechnung-Setup" setup_wizard.py

Normaler Aufruf:
    python setup_wizard.py
"""

import sys
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QHBoxLayout, QFormLayout,
    QFileDialog, QMessageBox, QCheckBox,
)
from PySide6.QtCore import Qt

# .env wird neben der .exe bzw. neben setup_wizard.py abgelegt
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

ENV_PATH = BASE_DIR / ".env"


def browse_row(parent_page, label, default=""):
    edit = QLineEdit(default)
    btn = QPushButton("Durchsuchen …")
    btn.setFixedWidth(120)
    def _browse():
        path = QFileDialog.getExistingDirectory(parent_page, label, edit.text())
        if path:
            edit.setText(path)
    btn.clicked.connect(_browse)
    row = QHBoxLayout()
    row.addWidget(edit)
    row.addWidget(btn)
    return row, edit


class PageDatabase(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Datenbankverbindung")
        self.setSubTitle(
            "Geben Sie die Verbindungsdaten zur MySQL-Datenbank ein. "
            "Der Dienst greift ausschließlich lesend auf die Datenbank zu."
        )
        form = QFormLayout()
        form.setSpacing(8)
        self.host     = QLineEdit()
        self.port     = QLineEdit()
        self.name     = QLineEdit()
        self.user     = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        form.addRow("Host:", self.host)
        form.addRow("Port:", self.port)
        form.addRow("Datenbankname:", self.name)
        form.addRow("Benutzer:", self.user)
        form.addRow("Passwort:", self.password)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Verbindung testen")
        self.test_btn.setFixedWidth(150)
        self.test_btn.clicked.connect(self._test)
        self.status_lbl = QLabel("")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.status_lbl)
        test_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(12)
        layout.addLayout(test_row)
        layout.addStretch()

        self.registerField("db_host",     self.host)
        self.registerField("db_port",     self.port)
        self.registerField("db_name",     self.name)
        self.registerField("db_user",     self.user)
        self.registerField("db_password", self.password)

        for w in (self.host, self.port, self.name, self.user):
            w.textChanged.connect(self.completeChanged)

    def isComplete(self):
        return all([
            self.host.text().strip(),
            self.port.text().strip(),
            self.name.text().strip(),
            self.user.text().strip(),
        ])

    def _test(self):
        try:
            import pymysql
            conn = pymysql.connect(
                host=self.host.text().strip(),
                port=int(self.port.text().strip() or "3306"),
                database=self.name.text().strip(),
                user=self.user.text().strip(),
                password=self.password.text(),
                connect_timeout=5,
            )
            conn.close()
            self.status_lbl.setText("Verbindung erfolgreich")
            self.status_lbl.setStyleSheet("color: green; font-weight: bold;")
        except Exception as e:
            self.status_lbl.setText(f"Fehler: {e}")
            self.status_lbl.setStyleSheet("color: red;")


class PageSmtp(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("E-Mail-Versand (SMTP)")
        self.setSubTitle(
            "Der Dienst versendet fertige XRechnungen per E-Mail an das OZG-RE Portal. "
            "Tragen Sie die Zugangsdaten des Absender-Postfachs ein."
        )
        form = QFormLayout()
        form.setSpacing(8)
        self.smtp_host      = QLineEdit()
        self.smtp_port      = QLineEdit()
        self.smtp_user      = QLineEdit()
        self.smtp_password  = QLineEdit()
        self.smtp_password.setEchoMode(QLineEdit.Password)
        self.smtp_from      = QLineEdit()
        self.smtp_from_name = QLineEdit("XRechnung-Dienst")
        self.ozg_email      = QLineEdit("poststelle@bdr-portal.de")
        self.ozg_subject    = QLineEdit("XRechnung Einreichung")
        form.addRow("SMTP-Host:", self.smtp_host)
        form.addRow("SMTP-Port:", self.smtp_port)
        form.addRow("SMTP-Benutzer (E-Mail):", self.smtp_user)
        form.addRow("App-Passwort:", self.smtp_password)
        form.addRow("Absender-Adresse:", self.smtp_from)
        form.addRow("Absender-Name:", self.smtp_from_name)
        form.addRow("OZG-RE Empfänger:", self.ozg_email)
        form.addRow("Betreff:", self.ozg_subject)
        hint = QLabel(
            "Hinweis: Verwenden Sie bei aktivierter 2-Faktor-Authentifizierung (2FA) "
            "ein App-Passwort Ihres E-Mail-Anbieters, "
            "nicht Ihr reguläres Kontopasswort."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(8)
        layout.addWidget(hint)
        layout.addStretch()
        self.registerField("smtp_host",      self.smtp_host)
        self.registerField("smtp_port",      self.smtp_port)
        self.registerField("smtp_user",      self.smtp_user)
        self.registerField("smtp_password",  self.smtp_password)
        self.registerField("smtp_from",      self.smtp_from)
        self.registerField("smtp_from_name", self.smtp_from_name)
        self.registerField("ozg_email",      self.ozg_email)
        self.registerField("ozg_subject",    self.ozg_subject)
        for w in (self.smtp_user, self.smtp_password, self.smtp_from):
            w.textChanged.connect(self.completeChanged)

    def isComplete(self):
        return all([
            self.smtp_user.text().strip(),
            self.smtp_password.text(),
            self.smtp_from.text().strip(),
        ])


class PagePaths(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Ordner und Pfade")
        self.setSubTitle(
            "Legen Sie fest, wo der Dienst nach neuen PDFs sucht und "
            "wohin er erzeugte XMLs sowie Protokolldateien speichert."
        )
        form = QFormLayout()
        form.setSpacing(8)
        watch_row,  self.watch  = browse_row(self, "Überwachungsordner wählen")
        output_row, self.output = browse_row(self, "XML-Ausgabeordner wählen",
                                             str(BASE_DIR / "output" / "xml"))
        proc_row,   self.proc   = browse_row(self, "Ordner für verarbeitete PDFs",
                                             str(BASE_DIR / "processed"))
        error_row,  self.error  = browse_row(self, "Ordner für fehlerhafte PDFs",
                                             str(BASE_DIR / "error"))
        log_row, self.log = self._log_browse_row(
            str(BASE_DIR / "logs" / "xrechnung_dienst.log"))
        form.addRow("Überwachungsordner (PDFs):", watch_row)
        form.addRow("XML-Ausgabeordner:", output_row)
        form.addRow("Verarbeitete PDFs:", proc_row)
        form.addRow("Fehlerhafte PDFs:", error_row)
        form.addRow("Log-Datei:", log_row)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch()
        self.registerField("watch_folder",     self.watch)
        self.registerField("output_xml",       self.output)
        self.registerField("processed_folder", self.proc)
        self.registerField("error_folder",     self.error)
        self.registerField("log_file",         self.log)
        self.watch.textChanged.connect(self.completeChanged)

    def _log_browse_row(self, default=""):
        edit = QLineEdit(default)
        btn = QPushButton("Durchsuchen …")
        btn.setFixedWidth(120)
        def _browse():
            path, _ = QFileDialog.getSaveFileName(
                self, "Log-Datei wählen", edit.text(),
                "Log-Dateien (*.log);;Alle Dateien (*)"
            )
            if path:
                edit.setText(path)
        btn.clicked.connect(_browse)
        row = QHBoxLayout()
        row.addWidget(edit)
        row.addWidget(btn)
        return row, edit

    def isComplete(self):
        return bool(self.watch.text().strip())


class PageSummary(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Zusammenfassung")
        self.setSubTitle(
            'Überprüfen Sie die Einstellungen. '
            'Klicken Sie auf "Fertigstellen" um die .env-Datei zu schreiben.'
        )
        self.setFinalPage(True)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary.setStyleSheet(
            "font-family: 'Courier New', monospace; font-size: 11px;"
            "background: #f5f5f5; border: 1px solid #ccc; padding: 10px;"
        )
        self.scheduler_check = QCheckBox(
            "Windows Task Scheduler einrichten (täglich um 06:00 Uhr)"
        )
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addSpacing(10)
        layout.addWidget(self.scheduler_check)
        layout.addStretch()

    def initializePage(self):
        w = self.wizard()
        pw_len = len(w.field("db_password"))
        lines = [
            "# Datenbankverbindung",
            f"DB_HOST         = {w.field('db_host')}",
            f"DB_PORT         = {w.field('db_port')}",
            f"DB_NAME         = {w.field('db_name')}",
            f"DB_USER         = {w.field('db_user')}",
            f"DB_PASSWORD     = {'*' * pw_len}",
            "",
            "# E-Mail / SMTP",
            f"SMTP_HOST       = {w.field('smtp_host')}:{w.field('smtp_port')}",
            f"SMTP_USER       = {w.field('smtp_user')}",
            f"SMTP_FROM       = {w.field('smtp_from')}",
            f"SMTP_FROM_NAME  = {w.field('smtp_from_name')}",
            f"OZG_RE_EMAIL    = {w.field('ozg_email')}",
            "",
            "# Pfade",
            f"WATCH_FOLDER    = {w.field('watch_folder')}",
            f"OUTPUT_XML      = {w.field('output_xml')}",
            f"PROCESSED       = {w.field('processed_folder')}",
            f"ERROR           = {w.field('error_folder')}",
            f"LOG_FILE        = {w.field('log_file')}",
        ]
        self.summary.setText("\n".join(lines))


class SetupWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("XRechnung-Dienst - Ersteinrichtung")
        self.setMinimumSize(640, 480)
        self.setWizardStyle(QWizard.ModernStyle)
        self.setButtonText(QWizard.BackButton,   "< Zurück")
        self.setButtonText(QWizard.NextButton,   "Weiter >")
        self.setButtonText(QWizard.FinishButton, "Fertigstellen")
        self.setButtonText(QWizard.CancelButton, "Abbrechen")
        self.addPage(PageDatabase())
        self.addPage(PageSmtp())
        self.addPage(PagePaths())
        self.page_summary = PageSummary()
        self.addPage(self.page_summary)
        self.finished.connect(self._on_finish)

    def _on_finish(self, result):
        if result != QWizard.Accepted:
            return
        self._write_env()
        if self.page_summary.scheduler_check.isChecked():
            self._setup_scheduler()

    def _write_env(self):
        lines = [
            "# XRechnung-Hintergrunddienst - Konfiguration",
            "# Erstellt durch den Setup-Assistenten",
            "",
            "# Datenbankverbindung",
            f"DB_HOST={self.field('db_host')}",
            f"DB_PORT={self.field('db_port')}",
            f"DB_NAME={self.field('db_name')}",
            f"DB_USER={self.field('db_user')}",
            f"DB_PASSWORD={self.field('db_password')}",
            "",
            "# SMTP",
            f"SMTP_HOST={self.field('smtp_host')}",
            f"SMTP_PORT={self.field('smtp_port')}",
            f"SMTP_USER={self.field('smtp_user')}",
            f"SMTP_PASSWORD={self.field('smtp_password')}",
            f"SMTP_FROM={self.field('smtp_from')}",
            f"SMTP_FROM_NAME={self.field('smtp_from_name')}",
            "",
            "# OZG-RE Portal",
            f"OZG_RE_EMAIL={self.field('ozg_email')}",
            f"OZG_RE_SUBJECT={self.field('ozg_subject')}",
            "",
            "# Ordner und Pfade",
            f"WATCH_FOLDER={self.field('watch_folder')}",
            f"OUTPUT_XML={self.field('output_xml')}",
            "OUTPUT_PDF=output/pdf",
            f"PROCESSED_FOLDER={self.field('processed_folder')}",
            f"ERROR_FOLDER={self.field('error_folder')}",
            "",
            "# Logging",
            f"LOG_FILE={self.field('log_file')}",
            "LOG_LEVEL=INFO",
            "LOG_MAX_BYTES=5242880",
            "LOG_BACKUP_COUNT=3",
        ]
        try:
            ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
            QMessageBox.information(
                self, "Setup abgeschlossen",
                f".env-Datei wurde erfolgreich geschrieben:\n{ENV_PATH}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Fehler",
                f"Die .env-Datei konnte nicht geschrieben werden:\n{e}"
            )

    def _setup_scheduler(self):
        main_py = BASE_DIR / "main.py"
        if not main_py.exists():
            QMessageBox.warning(
                self, "Task Scheduler",
                f"main.py wurde nicht gefunden unter:\n{main_py}\n\n"
                "Bitte richten Sie den Task manuell ein."
            )
            return
        cmd = [
            "schtasks", "/create",
            "/tn", "XRechnung-Hintergrunddienst",
            "/tr", f'"{sys.executable}" "{main_py}"',
            "/sc", "DAILY", "/st", "06:00", "/f",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            QMessageBox.information(
                self, "Task Scheduler",
                "Der Task wurde erfolgreich eingerichtet.\n"
                "Der Dienst wird täglich um 06:00 Uhr ausgeführt."
            )
        except subprocess.CalledProcessError:
            QMessageBox.warning(
                self, "Task Scheduler",
                "Der Task konnte nicht automatisch eingerichtet werden.\n"
                "Bitte richten Sie ihn manuell ein (siehe Administratorhandbuch)."
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    wizard = SetupWizard()
    wizard.show()
    sys.exit(app.exec())