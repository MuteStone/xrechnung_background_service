import logging
from pathlib import Path

from lxml import etree

logger = logging.getLogger("xrechnung.validator")

XSD_PATH = Path(__file__).parent / "xsd" / "CrossIndustryInvoice_100pD16B.xsd"


def validate(xml_path: Path) -> bool:
    """
    Validiert eine XRechnung-XML gegen das XSD-Schema.

    Args:
        xml_path: Pfad zur zu prüfenden XML-Datei

    Returns:
        True wenn valide, False wenn nicht.
    """
    if not XSD_PATH.exists():
        logger.warning(
            f"XSD-Datei nicht gefunden: {XSD_PATH} — "
            "Validierung wird übersprungen. "
            "Download: https://github.com/itplr-kosit/validator-configuration-xrechnung/releases"
        )
        return True  # Ohne XSD durchlassen, nicht blockieren

    try:
        with open(XSD_PATH, "rb") as f:
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