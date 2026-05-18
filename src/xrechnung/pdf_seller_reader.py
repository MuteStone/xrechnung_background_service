"""
Extraktion von Verkäufer-/Absenderdaten aus einem Rechnungs-PDF.

Sucht nach typischen deutschen Geschäftsdaten:
  IBAN, BIC, USt-IdNr., Firmenname, Adresse, E-Mail, Telefon.

Strategie:
  - Zuverlässig extrahierbar: IBAN, USt-IdNr., BIC, E-Mail, Telefon
  - Mit Einschränkungen: PLZ/Ort, Straße (erste Fundstelle im Dokument)
  - Unsicher: Firmenname (wird aus Kontoinhaber-Angabe oder GmbH/AG-Zeilen gewonnen)
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger("xrechnung.pdf_seller_reader")

# ── Reguläre Ausdrücke ───────────────────────────────────────────────────────

# Deutsches IBAN: DE + 2 Prüfziffern + 18 Stellen (mit optionalen Leerzeichen)
_RE_IBAN = re.compile(
    r"\bDE\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{2}\b"
)

# BIC/SWIFT nach Label
_RE_BIC = re.compile(
    r"(?:BIC|SWIFT)[:\s]+([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)"
)

# Umsatzsteuer-ID mit Label oder isoliert
_RE_VAT = re.compile(
    r"(?:USt\.?-?Id\.?(?:Nr\.?)?|Ust\.?Nr\.?|Umsatzsteuer-?I[Dd])[:\s]*"
    r"(DE\s*\d{3}\s*\d{3}\s*\d{3})"
    r"|"
    r"\b(DE\d{9})\b"
)

# E-Mail-Adresse
_RE_EMAIL = re.compile(
    r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"
)

# Telefonnummer nach Label
_RE_PHONE = re.compile(
    r"(?:Tel\.?(?:efon)?|Fon|Phone)[:\s]+([\+\d\s\/\-\(\)]{7,25})"
)

# PLZ + Ort: genau eine Wortgruppe nach der PLZ (bis Satzzeichen / Zeilenende / Zahl)
_RE_PLZ_ORT = re.compile(
    r"\b(\d{5})\s+"
    r"([A-ZÄÖÜ][a-zA-ZäöüÄÖÜß]+"          # erstes Wort (Pflicht, beginnt groß)
    r"(?:\s+[A-ZÄÖÜ][a-zA-ZäöüÄÖÜß]+)?)"   # optional: zweites Wort (z. B. "Bad Segeberg")
    r"(?=\s|\n|$|[^a-zA-ZäöüÄÖÜß])"        # gefolgt von Nicht-Buchstabe
)

# Straße + Hausnummer
_RE_STREET = re.compile(
    r"([A-ZÄÖÜ][a-zA-ZäöüÄÖÜß\-]{3,40}"
    r"(?:str(?:aße|\.)|gasse|weg|allee|platz|ring|damm|chaussee|ufer|steig)"
    r"[^\S\n]*\d+[a-zA-Z]?)"
)

# Kontoinhaber — typisch in Rechnungen direkt bei den Bankdaten
_RE_ACCOUNT_HOLDER = re.compile(
    r"(?:Kontoinhaber|Konto\s+lautend\s+auf|Kto\.?\s+Inhaber|Empfänger)[:\s]+"
    r"([^\n\r]{3,80})"
)

# Zeilen mit Rechtsform-Kürzel — zuverlässige Firmennamen-Hinweise
_RE_LEGAL_FORM = re.compile(
    r"([^\n\r]{2,60}"
    r"(?:GmbH(?:\s*&\s*Co\.?\s*KG)?|AG|UG\s*\(haftungsbeschränkt\)|e\.V\.|KG|OHG|GbR|mbH)"
    r"[^\n\r]{0,30})"
)

# Wörter die typisch NUR in Rechnungsinhalten/Empfängeradressen vorkommen — keine Firmennamen
_EXCLUDE_KEYWORDS = re.compile(
    r"\b(Rechnung|Invoice|Datum|Seite|Page|Betreff|Leistung|Menge|Preis|"
    r"Gesamt|Total|MwSt|Steuer|Netto|Brutto|Pos\.|Position|Beschreibung)\b",
    re.IGNORECASE,
)


def extract_seller_from_pdf(pdf_path: Path) -> dict:
    """
    Versucht Verkäuferdaten aus dem PDF-Text zu extrahieren.
    Gibt ein (ggf. unvollständiges) dict zurück.
    """
    result: dict = {}
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber nicht installiert — PDF-Extraktion übersprungen")
        return result

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(
                (page.extract_text() or "") for page in pdf.pages
            )
        result = _parse_seller_data(full_text, pdf_path.name)
    except Exception as e:
        logger.error("Fehler beim Lesen von %s: %s", pdf_path.name, e)

    return result


def _parse_seller_data(text: str, source: str = "") -> dict:
    result: dict = {}

    # ── IBAN ──────────────────────────────────────────────────────────────────
    iban_m = _RE_IBAN.search(text)
    if iban_m:
        result["seller_iban"] = re.sub(r"\s", "", iban_m.group())
        logger.debug("IBAN aus PDF: %s", result["seller_iban"])

    # ── BIC ───────────────────────────────────────────────────────────────────
    bic_m = _RE_BIC.search(text)
    if bic_m:
        result["seller_bic"] = bic_m.group(1).strip()
        logger.debug("BIC aus PDF: %s", result["seller_bic"])

    # ── USt-IdNr ──────────────────────────────────────────────────────────────
    vat_m = _RE_VAT.search(text)
    if vat_m:
        raw = (vat_m.group(1) or vat_m.group(2) or "").strip()
        result["seller_vat_id"] = re.sub(r"\s", "", raw)
        logger.debug("USt-IdNr aus PDF: %s", result["seller_vat_id"])

    # ── E-Mail ────────────────────────────────────────────────────────────────
    email_m = _RE_EMAIL.search(text)
    if email_m:
        result["seller_email"] = email_m.group(1)
        logger.debug("E-Mail aus PDF: %s", result["seller_email"])

    # ── Telefon ───────────────────────────────────────────────────────────────
    phone_m = _RE_PHONE.search(text)
    if phone_m:
        result["seller_phone"] = phone_m.group(1).strip()
        logger.debug("Telefon aus PDF: %s", result["seller_phone"])

    # ── PLZ + Ort ─────────────────────────────────────────────────────────────
    # Suche alle Treffer und nimm den, der NICHT direkt vor "Rechnung"/Typ-Worten steht
    for m in _RE_PLZ_ORT.finditer(text):
        city_candidate = m.group(2).strip()
        # Überspringen wenn der Ort-Kandidat ein Rechnungs-Schlüsselwort enthält
        if _EXCLUDE_KEYWORDS.search(city_candidate):
            continue
        result["seller_zip"]  = m.group(1)
        result["seller_city"] = city_candidate
        logger.debug("PLZ/Ort aus PDF: %s %s", result["seller_zip"], result["seller_city"])
        break

    # ── Straße ────────────────────────────────────────────────────────────────
    street_m = _RE_STREET.search(text)
    if street_m:
        result["seller_street"] = street_m.group(1).strip()
        logger.debug("Straße aus PDF: %s", result["seller_street"])

    # ── Firmenname ────────────────────────────────────────────────────────────
    # Priorität 1: Kontoinhaber-Zeile (direkt bei den Bankdaten — sehr zuverlässig)
    holder_m = _RE_ACCOUNT_HOLDER.search(text)
    if holder_m:
        name = holder_m.group(1).strip().rstrip(",;:")
        if not _EXCLUDE_KEYWORDS.search(name):
            result["seller_name"] = name
            logger.debug("Firmenname aus Kontoinhaber: %s", name)

    # Priorität 2: Zeile mit Rechtsform-Kürzel (GmbH, AG, …)
    if not result.get("seller_name"):
        legal_m = _RE_LEGAL_FORM.search(text)
        if legal_m:
            name = legal_m.group(1).strip()
            if not _EXCLUDE_KEYWORDS.search(name):
                result["seller_name"] = name
                logger.debug("Firmenname aus Rechtsform-Zeile: %s", name)

    # Priorität 3: Keine automatische Erkennung — Feld bleibt leer,
    # damit der Nutzer es manuell im Einstellungs-Tab befüllt.

    if result:
        logger.info(
            "Verkäuferdaten aus PDF %s extrahiert: %s", source, list(result.keys())
        )
    else:
        logger.warning("Keine Verkäuferdaten in %s gefunden", source)

    return result
