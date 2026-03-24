"""
Datenbankanbindung — XRechnung-Hintergrunddienst
=================================================
Greift auf dieselbe MySQL-Datenbank wie die Kundenverwaltung zu.
"""

import logging
from contextlib import contextmanager
from typing import Optional

import pymysql
import pymysql.cursors

from src.utils.config import load_config

logger = logging.getLogger("xrechnung.db")

_config: Optional[dict] = None


def _get_config() -> dict:
    global _config
    if _config is None:
        _config = load_config()
    return _config


@contextmanager
def get_connection():
    """Kontextmanager für eine DB-Verbindung (auto-close)."""
    cfg = _get_config()
    conn = pymysql.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        database=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


def test_connection() -> bool:
    """Prüft die Datenbankverbindung. Gibt True bei Erfolg zurück."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        logger.info("Datenbankverbindung erfolgreich")
        return True
    except Exception as e:
        logger.error(f"Datenbankverbindung fehlgeschlagen: {e}")
        return False


def get_invoice_full(invoice_number: str) -> Optional[dict]:
    """
    Lädt alle für eine XRechnung benötigten Daten:
    Rechnungskopf, Positionen, Kundendaten, Seller-Profil.

    Args:
        invoice_number: Rechnungsnummer (z. B. '20260105-001')

    Returns:
        Dictionary mit vollständigen Rechnungsdaten oder None bei Fehler.

    TODO: Implementierung nach Klärung des DB-Schemas
    """
    raise NotImplementedError("get_invoice_full — wird in Phase 2 implementiert")


def get_pending_export_jobs() -> list[dict]:
    """Gibt alle Export-Jobs mit Status 'pending' zurück."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM export_jobs "
                    "WHERE status = 'pending' "
                    "ORDER BY created_at ASC"
                )
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Fehler beim Laden der Export-Jobs: {e}")
        return []


def update_export_job_status(
    job_id: int,
    status: str,
    message: str = "",
    xml_path: str = "",
) -> bool:
    """
    Aktualisiert den Status eines Export-Jobs.

    Args:
        job_id:   ID des Export-Jobs
        status:   'processing' | 'done' | 'error'
        message:  Optionale Fehlermeldung
        xml_path: Pfad zur erzeugten XML-Datei
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE export_jobs
                    SET status     = %s,
                        message    = %s,
                        xml_path   = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (status, message, xml_path, job_id),
                )
        logger.debug(f"Export-Job {job_id} → {status}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren von Export-Job {job_id}: {e}")
        return False