"""
Konfiguration laden aus .env-Datei.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


def load_config() -> dict:
    """
    Lädt Konfiguration aus der .env-Datei im Projektstamm.
    Gibt alle Werte als Dictionary zurück.
    """
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        raise FileNotFoundError(
            f".env-Datei nicht gefunden: {env_path}\n"
            "Kopiere .env.example nach .env und trage deine Werte ein."
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
        "OUTPUT_XML":       os.getenv("OUTPUT_XML", "output/xml"),
        "OUTPUT_PDF":       os.getenv("OUTPUT_PDF", "output/pdf"),
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
        # Logging
        "LOG_LEVEL":        os.getenv("LOG_LEVEL", "INFO"),
        "LOG_FILE":         os.getenv("LOG_FILE", "logs/xrechnung_dienst.log"),
        "LOG_MAX_BYTES":    int(os.getenv("LOG_MAX_BYTES", "5242880")),
        "LOG_BACKUP_COUNT": int(os.getenv("LOG_BACKUP_COUNT", "3")),
    }