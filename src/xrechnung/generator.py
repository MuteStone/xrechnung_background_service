"""
XRechnung-Generator (EN 16931, CII-Format)
==========================================
Erzeugt eine valide XRechnung-XML aus den Rechnungsdaten der DB.

TODO: Implementierung in Phase 2
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("xrechnung.generator")


def generate(invoice_data: dict, output_dir: Path) -> Optional[Path]:
    """
    Erzeugt eine XRechnung-XML-Datei.

    Args:
        invoice_data: Vollständige Rechnungsdaten (aus get_invoice_full())
        output_dir:   Zielordner für die XML-Datei

    Returns:
        Pfad zur erzeugten XML-Datei, oder None bei Fehler.

    TODO: Implementierung in Phase 2
    Benötigt:
      - lxml.etree für XML-Erzeugung
      - Mapping invoice_data → CII XML-Struktur
      - Namespaces: rsm, ram, udt, qdt, xsi
    """
    raise NotImplementedError("generator.generate — wird in Phase 2 implementiert")