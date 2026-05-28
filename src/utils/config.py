import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def _base_dir() -> Path:
    """
    Gibt das Basisverzeichnis zurück – sowohl im normalen Python-Betrieb
    als auch wenn der Dienst als PyInstaller-EXE ausgeführt wird.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller-EXE: Verzeichnis der .exe
        return Path(sys.executable).parent
    # Normaler Betrieb: Projektstamm (zwei Ebenen über config.py)
    return Path(__file__).resolve().parents[2]


def load_config() -> dict:
    env_path = _base_dir() / ".env"
    if not env_path.exists():
        raise FileNotFoundError(
            f".env-Datei nicht gefunden: {env_path}\n"
            "Starten Sie XRechnung-Setup.exe zur Erstkonfiguration."
        )

    load_dotenv(dotenv_path=env_path)

    return {
        # Datenbank
        "DB_HOST":     os.getenv("DB_HOST", "localhost"),
        "DB_PORT":     int(os.getenv("DB_PORT", "3306")),
        "DB_NAME":     os.getenv("DB_NAME", ""),
        "DB_USER":     os.getenv("DB_USER", ""),
        "DB_PASSWORD": os.getenv("DB_PASSWORD", ""),
        # Pfade
        "WATCH_FOLDER":     os.getenv("WATCH_FOLDER", ""),
        "PROCESSED_FOLDER": os.getenv("PROCESSED_FOLDER", "processed"),
        "ERROR_FOLDER":     os.getenv("ERROR_FOLDER", "error"),
        # SMTP
        "SMTP_HOST":      os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "SMTP_PORT":      int(os.getenv("SMTP_PORT", "587")),
        "SMTP_USER":      os.getenv("SMTP_USER", ""),
        "SMTP_PASSWORD":  os.getenv("SMTP_PASSWORD", ""),
        "SMTP_FROM":      os.getenv("SMTP_FROM", ""),
        "SMTP_FROM_NAME": os.getenv("SMTP_FROM_NAME", "XRechnung-Dienst"),
        # OZG-RE
        "OZG_RE_EMAIL":   os.getenv("OZG_RE_EMAIL", "poststelle@bdr-portal.de"),
        "OZG_RE_SUBJECT": os.getenv("OZG_RE_SUBJECT", "XRechnung Einreichung"),
        # Verkäuferdaten (Fallback wenn PDF keine Verkäuferdaten enthält)
        "SELLER_NAME":    os.getenv("SELLER_NAME", ""),
        "SELLER_STREET":  os.getenv("SELLER_STREET", ""),
        "SELLER_ZIP":     os.getenv("SELLER_ZIP", ""),
        "SELLER_CITY":    os.getenv("SELLER_CITY", ""),
        "SELLER_VAT_ID":  os.getenv("SELLER_VAT_ID", ""),
        "SELLER_IBAN":    os.getenv("SELLER_IBAN", ""),
        "SELLER_BIC":     os.getenv("SELLER_BIC", ""),
        "SELLER_EMAIL":   os.getenv("SELLER_EMAIL", ""),
        "SELLER_PHONE":   os.getenv("SELLER_PHONE", ""),
        # Scan-Einstellungen
        "SCAN_JSON":        os.getenv("SCAN_JSON", "false"),
        # Protokoll-Mail (interner Bericht nach Verarbeitungslauf)
        "REPORT_EMAIL":       os.getenv("REPORT_EMAIL", ""),
        "REPORT_ATTACH_XML":  os.getenv("REPORT_ATTACH_XML", "false"),
        # Logging
        "LOG_LEVEL":        os.getenv("LOG_LEVEL", "INFO"),
        "LOG_FILE":         os.getenv("LOG_FILE", "logs/xrechnung_dienst.log"),
        "LOG_MAX_BYTES":    int(os.getenv("LOG_MAX_BYTES", "5242880")),
        "LOG_BACKUP_COUNT": int(os.getenv("LOG_BACKUP_COUNT", "3")),
    }