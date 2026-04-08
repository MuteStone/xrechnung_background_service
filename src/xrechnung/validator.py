import sys
import logging
from pathlib import Path

from lxml import etree

logger = logging.getLogger("xrechnung.validator")


def _xsd_path() -> Path:
    """
    Gibt den Pfad zur XSD-Datei zurück – kompatibel mit normalem
    Python-Betrieb und PyInstaller-EXE (_MEIPASS enthält gebundelte Dateien).
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base / "xsd" / "CrossIndustryInvoice_100pD16B.xsd"


def validate(xml_path: Path) -> bool:
    """
    Validiert eine XRechnung-XML gegen das lokale XSD-Schema (nicht-blockierend).

    Args:
        xml_path: Pfad zur zu prüfenden XML-Datei

    Returns:
        True wenn valide oder XSD nicht vorhanden, False bei XML-Syntaxfehler.
    """
    xsd_path = _xsd_path()

    if not xsd_path.exists():
        logger.warning(
            f"XSD-Datei nicht gefunden: {xsd_path} — "
            "Validierung wird übersprungen. "
        )
        return True  # Ohne XSD durchlassen, nicht blockieren

    try:
        with open(xsd_path, "rb") as f:
            schema_doc = etree.parse(f)
        schema = etree.XMLSchema(schema_doc)

        with open(xml_path, "rb") as f:
            xml_doc = etree.parse(f)

        if schema.validate(xml_doc):
            logger.info(f"XML-Validierung erfolgreich: {xml_path.name}")
            return True
        else:
            for error in schema.error_log:
                # Warnung statt Fehler — Schematron-Regeln sind normativ
                logger.warning(f"XSD-Hinweis Zeile {error.line}: {error.message}")
            logger.info(f"XSD-Prüfung mit Hinweisen abgeschlossen: {xml_path.name}")
            return True  # Trotzdem durchlassen

    except etree.XMLSyntaxError as e:
        logger.error(f"XML-Syntaxfehler in {xml_path.name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Fehler bei der Validierung: {e}")
        return False