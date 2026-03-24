"""
XRechnung-Validator
====================
Prüft eine erzeugte XML-Datei gegen das offizielle XRechnung-XSD-Schema.

XSD-Download: https://github.com/itplr-kosit/xrechnung-artefakte

TODO: Implementierung in Phase 2
"""

import logging
from pathlib import Path

logger = logging.getLogger("xrechnung.validator")

XSD_PATH = Path(__file__).parent / "xsd" / "CrossIndustryInvoice_100pD22B.xsd"


def validate(xml_path: Path) -> bool:
    """
    Validiert eine XRechnung-XML gegen das XSD-Schema.

    Args:
        xml_path: Pfad zur zu prüfenden XML-Datei

    Returns:
        True wenn valide, False wenn nicht.

    TODO: Implementierung in Phase 2
    Benötigt:
      - lxml.etree.XMLSchema
      - XSD-Datei unter src/xrechnung/xsd/
    """
    raise NotImplementedError("validator.validate — wird in Phase 2 implementiert")