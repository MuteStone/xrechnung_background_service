"""
Unit-Tests für den XRechnung-Hintergrunddienst
===============================================
Getestet werden die kritischen Hilfsfunktionen des Generators
sowie die Rechnungsnummer-Extraktion des PDF-Parsers.

Ausführung:
    pytest tests/test_generator.py -v
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.xrechnung.generator import _fmt_date, _dec, _group_taxes
from src.xrechnung.pdf_reader import extract_invoice_number


# ─────────────────────────────────────────────
# _fmt_date — Datumsformatierung
# ─────────────────────────────────────────────

class TestFmtDate:
    def test_date_object(self):
        """date-Objekt wird korrekt in YYYYMMDD formatiert."""
        assert _fmt_date(date(2026, 1, 5)) == "20260105"

    def test_date_object_einstellig(self):
        """Einstellige Monats- und Tagangaben werden korrekt mit führender Null formatiert."""
        assert _fmt_date(date(2026, 3, 1)) == "20260301"

    def test_string_mit_bindestrichen(self):
        """String im Format YYYY-MM-DD wird korrekt konvertiert."""
        assert _fmt_date("2026-01-05") == "20260105"

    def test_string_bereits_korrekt(self):
        """String ohne Bindestriche wird unverändert zurückgegeben."""
        assert _fmt_date("20260105") == "20260105"

    def test_none_gibt_leerstring(self):
        """None gibt einen leeren String zurück."""
        assert _fmt_date(None) == ""


# ─────────────────────────────────────────────
# _dec — Dezimalrundung
# ─────────────────────────────────────────────

class TestDec:
    def test_ganzzahl(self):
        """Ganzzahl wird mit zwei Nachkommastellen ausgegeben."""
        assert _dec(100) == "100.00"

    def test_eine_nachkommastelle(self):
        """Wert mit einer Nachkommastelle wird korrekt aufgefüllt."""
        assert _dec(10.5) == "10.50"

    def test_zwei_nachkommastellen(self):
        """Wert mit zwei Nachkommastellen bleibt unverändert."""
        assert _dec(19.99) == "19.99"

    def test_kaufmaennisches_runden(self):
        """Kaufmännisches Runden: 0.005 wird auf 0.01 gerundet."""
        assert _dec("0.005") == "0.01"

    def test_string_eingabe(self):
        """String-Eingabe wird korrekt verarbeitet."""
        assert _dec("123.456") == "123.46"

    def test_none_gibt_null(self):
        """None gibt '0.00' zurück."""
        assert _dec(None) == "0.00"

    def test_decimal_eingabe(self):
        """Decimal-Eingabe wird korrekt verarbeitet."""
        assert _dec(Decimal("99.9")) == "99.90"


# ─────────────────────────────────────────────
# _group_taxes — Steuergruppierung
# ─────────────────────────────────────────────

class TestGroupTaxes:
    def test_eine_steuergruppe(self):
        """Zwei Positionen mit gleichem Steuersatz werden zusammengefasst."""
        items = [
            {"tax_rate": 19, "line_total_net": 100.00, "tax_category_code": "S"},
            {"tax_rate": 19, "line_total_net":  50.00, "tax_category_code": "S"},
        ]
        result = _group_taxes(items)
        assert "19.00" in result
        assert result["19.00"]["net_amount"] == Decimal("150.00")

    def test_zwei_steuergruppen(self):
        """Positionen mit unterschiedlichen Steuersätzen bilden separate Gruppen."""
        items = [
            {"tax_rate": 19, "line_total_net": 100.00, "tax_category_code": "S"},
            {"tax_rate":  7, "line_total_net":  50.00, "tax_category_code": "S"},
        ]
        result = _group_taxes(items)
        assert "19.00" in result
        assert "7.00" in result
        assert result["19.00"]["net_amount"] == Decimal("100.00")
        assert result["7.00"]["net_amount"] == Decimal("50.00")

    def test_steuerberechnung(self):
        """Steuerbetrag wird korrekt aus Nettobetrag und Steuersatz berechnet."""
        items = [
            {"tax_rate": 19, "line_total_net": 100.00, "tax_category_code": "S"},
        ]
        result = _group_taxes(items)
        assert result["19.00"]["tax_amount"] == Decimal("19.00")

    def test_leere_liste(self):
        """Leere Positionsliste ergibt leeres Ergebnis-Dict."""
        assert _group_taxes([]) == {}


# ─────────────────────────────────────────────
# extract_invoice_number — PDF-Parser
# ─────────────────────────────────────────────

class TestExtractInvoiceNumber:
    def test_korrekter_dateiname(self, tmp_path):
        """Rechnungsnummer wird korrekt aus einem validen Dateinamen extrahiert."""
        pdf = tmp_path / "Rechnung_20260105-001.pdf"
        pdf.write_bytes(b"")
        assert extract_invoice_number(pdf) == "20260105-001"

    def test_anderer_gueltiger_dateiname(self, tmp_path):
        """Auch andere valide Dateinamen werden korrekt verarbeitet."""
        pdf = tmp_path / "Rechnung_20260325-003.pdf"
        pdf.write_bytes(b"")
        assert extract_invoice_number(pdf) == "20260325-003"

    def test_falsches_format_gibt_none(self, tmp_path):
        """Dateiname ohne korrektes Format gibt None zurück (kein Absturz)."""
        pdf = tmp_path / "rechnung.pdf"
        pdf.write_bytes(b"")
        result = extract_invoice_number(pdf)
        assert result is None

    def test_kleinschreibung_kein_match(self, tmp_path):
        """Dateiname mit Kleinbuchstaben 'r' passt nicht zum erwarteten Format."""
        pdf = tmp_path / "rechnung_20260105-001.pdf"
        pdf.write_bytes(b"")
        result = extract_invoice_number(pdf)
        assert result is None