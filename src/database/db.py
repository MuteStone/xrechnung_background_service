import logging
from contextlib import contextmanager
from typing import Optional

import pymysql
import pymysql.cursors

from src.utils.config import load_config

logger = logging.getLogger("xrechnung.db")

# Konstanten (identisch zur Kundenverwaltung)
_PROPERTY_ROUTING_ID    = 29
_PROPERTY_INVOICE_EMAIL = 27
_TYPE_INVOICE           = 3

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
    """Prüft die Datenbankverbindung."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        logger.info("Datenbankverbindung erfolgreich")
        return True
    except Exception as e:
        logger.error(f"Datenbankverbindung fehlgeschlagen: {e}")
        return False


# ──────────────────────────────────────────────────────────────
# Interne Hilfsfunktionen (analog zur Kundenverwaltung)
# ──────────────────────────────────────────────────────────────

def _fetch_leitweg_id(cur, kundenid: int) -> str:
    cur.execute(
        "SELECT wert FROM tb_kundenzusatz "
        "WHERE kundenid=%s AND eigenschaft=%s LIMIT 1",
        (kundenid, _PROPERTY_ROUTING_ID),
    )
    row = cur.fetchone()
    return (row.get("wert") if row else None) or ""


def _fetch_rechnung_mail(cur, kundenid: int) -> str:
    cur.execute(
        "SELECT wert FROM tb_kundenzusatz "
        "WHERE kundenid=%s AND eigenschaft=%s LIMIT 1",
        (kundenid, _PROPERTY_INVOICE_EMAIL),
    )
    row = cur.fetchone()
    return (row.get("wert") if row else None) or ""


def _fetch_billing_address(cur, kundenid: int) -> dict:
    """Rechnungsadresse aus tb_kunden_adressen (adressenart=2)."""
    cur.execute(
        """SELECT name1, name2, name3, name4, strasse, plz, ort
           FROM tb_kunden_adressen
           WHERE kundenid=%s AND adressenart=2 LIMIT 1""",
        (kundenid,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    return {
        "billing_name1":  row.get("name1") or "",
        "billing_name2":  row.get("name2") or "",
        "billing_name3":  row.get("name3") or "",
        "billing_name4":  row.get("name4") or "",
        "billing_street": row.get("strasse") or "",
        "billing_zip":    row.get("plz") or "",
        "billing_city":   row.get("ort") or "",
    }


def _fetch_seller_profile(cur) -> dict:
    """
    Lädt das Seller-Profil.  Fallback-Kette:
      1. seller_profiles (Standard)
      2. Bekannte alternative Tabellennamen (tb_firma, firmen, stammdaten, …)
    """
    # ── 1. Primäre Tabelle ──────────────────────────────────────────────────
    try:
        cur.execute("SELECT * FROM seller_profiles WHERE is_default=1 LIMIT 1")
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT * FROM seller_profiles LIMIT 1")
            row = cur.fetchone()
        if row:
            return row
    except Exception as e:
        logger.warning("seller_profiles nicht verfügbar: %s", e)

    # ── 2. Alternative Tabellen ─────────────────────────────────────────────
    return _fetch_seller_from_alternative_tables(cur)


# Bekannte Spaltennamen verschiedener Kundenverwaltungs-Systeme,
# geordnet nach Priorität (erster Treffer gewinnt).
_SELLER_COL_MAP = {
    "seller_name":         ["seller_name", "firmenname", "firma", "name", "bezeichnung",
                            "company", "unternehmensname"],
    "seller_street":       ["seller_street", "strasse", "street", "anschrift"],
    "seller_house_number": ["seller_house_number", "hausnummer", "hnr", "house_number"],
    "seller_zip":          ["seller_zip", "plz", "postleitzahl", "zip", "postal_code"],
    "seller_city":         ["seller_city", "ort", "stadt", "city"],
    "vat_id":              ["vat_id", "ustidnr", "ust_id", "umsatzsteuerid",
                            "usteuernr", "steuernummer", "tax_id"],
    "iban":                ["iban", "bankverbindung_iban"],
    "bic":                 ["bic", "swift", "bankverbindung_bic"],
    "contact_email":       ["contact_email", "email", "e_mail", "mail"],
    "contact_phone":       ["contact_phone", "telefon", "tel", "phone", "fon"],
}

_ALT_TABLES = [
    "tb_firma", "firma", "firmen",
    "stammdaten", "tb_stammdaten",
    "tb_mandant", "mandanten",
    "einstellungen", "konfiguration", "settings",
    "tb_absender",
]


def _fetch_seller_from_alternative_tables(cur) -> dict:
    """Durchsucht bekannte alternative Tabellen nach Verkäuferdaten."""
    # Zuerst vorhandene Tabellen ermitteln
    try:
        cur.execute("SHOW TABLES")
        existing = {list(row.values())[0].lower() for row in cur.fetchall()}
    except Exception:
        existing = set()

    for table in _ALT_TABLES:
        if table.lower() not in existing:
            continue
        try:
            cur.execute(f"SELECT * FROM `{table}` LIMIT 1")
            row = cur.fetchone()
            if not row:
                continue

            # Spaltennamen ermitteln (case-insensitive)
            row_lower = {k.lower(): v for k, v in row.items()}

            mapped = {}
            for target_key, candidates in _SELLER_COL_MAP.items():
                for col in candidates:
                    val = row_lower.get(col)
                    if val:
                        mapped[target_key] = val
                        break

            if mapped.get("seller_name") or mapped.get("iban"):
                logger.info(
                    "Verkäuferdaten aus alternativer Tabelle '%s' geladen", table
                )
                # Straße + Hausnummer zusammenführen (falls getrennt)
                street = str(mapped.get("seller_street", ""))
                hnr    = str(mapped.get("seller_house_number", ""))
                if hnr and hnr not in street:
                    mapped["seller_street"] = f"{street} {hnr}".strip()
                return mapped

        except Exception as e:
            logger.debug("Tabelle '%s' nicht verwendbar: %s", table, e)

    logger.warning(
        "Keine Verkäuferdaten in alternativen Tabellen gefunden: %s",
        [t for t in _ALT_TABLES if t.lower() in existing] or "keine bekannte Tabelle vorhanden",
    )
    return {}


# ──────────────────────────────────────────────────────────────
# Hauptfunktion: Vollständige Rechnungsdaten für XRechnung
# ──────────────────────────────────────────────────────────────

def get_invoice_full(invoice_number: str) -> Optional[dict]:
    """
    Lädt alle für eine XRechnung benötigten Daten:
    Rechnungskopf, Positionen, Kundendaten, Seller-Profil,
    Leitweg-ID und Rechnungsadresse.

    Args:
        invoice_number: Rechnungsnummer aus dem PDF-Dateinamen
                        (z. B. '20260105-001')

    Returns:
        Dictionary mit vollständigen Rechnungsdaten oder None bei Fehler.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                # --- Rechnungskopf ---
                cur.execute(
                    """SELECT d.dokumenteid, d.nummernkreis AS invoice_number,
                              d.kundenid, d.dokumentdatum AS invoice_date,
                              d.zieldatum AS due_date,
                              d.nettobetrag AS total_net,
                              d.mwstregelsatz AS total_tax,
                              (COALESCE(d.nettobetrag,0)+COALESCE(d.mwstregelsatz,0))
                                  AS total_gross,
                              d.lieferung AS service_start,
                              d.kommunikation AS payment_reference,
                              d.dokumentstatus, d.mahnstufe
                       FROM tb_dokumente d
                       WHERE d.nummernkreis=%s AND d.typ=%s LIMIT 1""",
                    (invoice_number, _TYPE_INVOICE),
                )
                inv = cur.fetchone()
                if not inv:
                    logger.warning(f"Rechnung nicht gefunden: {invoice_number}")
                    return None

                kundenid    = inv["kundenid"]
                dokumenteid = inv["dokumenteid"]

                # --- Rechnungspositionen ---
                cur.execute(
                    """SELECT dp.positionenid AS position_no,
                              dp.artikelcode  AS item_code,
                              dp.bezeichnung  AS description,
                              dp.anzahl       AS quantity,
                              dp.einzelpreis  AS unit_price_net,
                              dp.mwstsatz     AS tax_rate,
                              dp.gesamt       AS line_total_net
                       FROM tb_dokpositionen dp
                       WHERE dp.dokumenteid=%s
                       ORDER BY dp.positionenid ASC""",
                    (dokumenteid,),
                )
                inv["items"] = cur.fetchall()

                # --- Kundenstammdaten ---
                cur.execute(
                    """SELECT name1, name2, name3, name4,
                              strasse, plz, ort, land, bundesland
                       FROM tb_kunden WHERE kundenid=%s LIMIT 1""",
                    (kundenid,),
                )
                kunde = cur.fetchone() or {}

                # --- Bundesland-Name auflösen ---
                bl_name = ""
                bl_id = kunde.get("bundesland") or 0
                if bl_id:
                    cur.execute(
                        "SELECT bdld_bezeichnung FROM tb_bundeslaender "
                        "WHERE bundeslaenderid=%s LIMIT 1",
                        (bl_id,),
                    )
                    bl_row = cur.fetchone()
                    bl_name = (bl_row.get("bdld_bezeichnung") if bl_row else None) or ""

                # --- Leitweg-ID & Rechnungsmail ---
                leitweg_id    = _fetch_leitweg_id(cur, kundenid)
                rechnung_mail = _fetch_rechnung_mail(cur, kundenid)

                # --- Rechnungsadresse (Fallback: Hauptadresse) ---
                billing = _fetch_billing_address(cur, kundenid)
                if not billing.get("billing_name1"):
                    billing = {
                        "billing_name1":  kunde.get("name1") or "",
                        "billing_name2":  kunde.get("name2") or "",
                        "billing_name3":  kunde.get("name3") or "",
                        "billing_name4":  kunde.get("name4") or "",
                        "billing_street": kunde.get("strasse") or "",
                        "billing_zip":    kunde.get("plz") or "",
                        "billing_city":   kunde.get("ort") or "",
                    }

                # --- Seller-Profil ---
                seller = _fetch_seller_profile(cur)

                # --- Alles zusammenführen ---
                inv.update({
                    "currency":              "EUR",
                    "buyer_name":            kunde.get("name1") or "",
                    "buyer_name2":           kunde.get("name2") or "",
                    "buyer_name3":           kunde.get("name3") or "",
                    "buyer_name4":           kunde.get("name4") or "",
                    "buyer_street":          kunde.get("strasse") or "",
                    "buyer_zip":             kunde.get("plz") or "",
                    "buyer_city":            kunde.get("ort") or "",
                    "buyer_state":           bl_name,
                    "buyer_country":         "DE" if (kunde.get("land") or "D") == "D" else (kunde.get("land") or "DE"),
                    "buyer_customer_number": str(kundenid),
                    "leitweg_id":            leitweg_id,
                    "buyer_email":           rechnung_mail,
                    **billing,
                    "seller_name":           seller.get("seller_name") or "",
                    "seller_street": (
                        (seller.get("seller_street") or "") + " " +
                        (seller.get("seller_house_number") or "")
                    ).strip(),
                    "seller_zip":            seller.get("seller_zip") or "",
                    "seller_city":           seller.get("seller_city") or "",
                    "seller_country":        "DE",
                    "seller_vat_id":         seller.get("vat_id") or "",
                    "seller_iban":           seller.get("iban") or "",
                    "seller_bic":            seller.get("bic") or "",
                    "seller_email":          seller.get("contact_email") or "",
                    "seller_phone":          seller.get("contact_phone") or "",
                })

                logger.info(
                    f"Rechnungsdaten geladen: {invoice_number} "
                    f"(Kunde {kundenid})"
                )
                return inv

    except Exception as e:
        logger.error(f"Fehler beim Laden der Rechnung {invoice_number}: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Export-Job-Verwaltung
# ──────────────────────────────────────────────────────────────

def get_export_job_by_pdf_path(pdf_path: str) -> Optional[dict]:
    """Lädt einen Export-Job anhand des PDF-Pfads."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT ej.*, d.nummernkreis AS invoice_number
                       FROM export_jobs ej
                       JOIN tb_dokumente d ON d.dokumenteid = ej.dokumenteid
                       WHERE ej.pdf_path=%s LIMIT 1""",
                    (pdf_path,),
                )
                return cur.fetchone()
    except Exception as e:
        logger.error(f"Fehler beim Laden des Export-Jobs ({pdf_path}): {e}")
        return None


def get_pending_export_jobs() -> list[dict]:
    """Gibt alle Export-Jobs mit Status 'pending' zurück."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT ej.*, d.nummernkreis AS invoice_number
                       FROM export_jobs ej
                       JOIN tb_dokumente d ON d.dokumenteid = ej.dokumenteid
                       WHERE ej.status = 'pending'
                       ORDER BY ej.created_at ASC"""
                )
                return cur.fetchall()
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
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE export_jobs
                       SET status=%s, message=%s, xml_path=%s, updated_at=NOW()
                       WHERE id=%s""",
                    (status, message, xml_path or None, job_id),
                )
        logger.debug(f"Export-Job {job_id} → {status}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren von Export-Job {job_id}: {e}")
        return False