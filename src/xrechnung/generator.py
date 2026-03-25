"""
XRechnung-Generator (EN 16931, CII-Format)
==========================================
Erzeugt eine valide XRechnung-XML gemäß XRechnung 3.x / UN/CEFACT CII.
Eingabe: invoice_data-Dictionary aus get_invoice_full()
Ausgabe: XML-Datei im OUTPUT_XML-Ordner
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional
from datetime import date

from lxml import etree

logger = logging.getLogger("xrechnung.generator")

# XML-Namespaces (CII)
_NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


def _el(parent, ns: str, tag: str, text: str = None, **attrs):
    """Hilfsfunktion: Element mit Namespace erstellen."""
    elem = etree.SubElement(parent, f"{{{_NS[ns]}}}{tag}", **attrs)
    if text is not None:
        elem.text = str(text)
    return elem


def _fmt_date(d) -> str:
    """Datum in YYYYMMDD-Format (CII-Standard)."""
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    if isinstance(d, str):
        # ISO-Format YYYY-MM-DD → YYYYMMDD
        return d.replace("-", "")[:8]
    return ""


def _dec(value, places: int = 2) -> str:
    """Decimal-Wert auf N Stellen runden und als String zurückgeben."""
    if value is None:
        return "0.00"
    return str(Decimal(str(value)).quantize(
        Decimal("0." + "0" * places), rounding=ROUND_HALF_UP
    ))


def generate(invoice_data: dict, output_dir: Path) -> Optional[Path]:
    """
    Erzeugt eine XRechnung-XML-Datei aus den Rechnungsdaten.

    Args:
        invoice_data: Dictionary aus get_invoice_full()
        output_dir:   Zielordner für die XML-Datei

    Returns:
        Pfad zur erzeugten XML-Datei, oder None bei Fehler.
    """
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        invoice_number = invoice_data.get("invoice_number", "")
        xml_filename   = f"XRechnung_{invoice_number}.xml"
        xml_path       = output_dir / xml_filename

        root = _build_xml(invoice_data)

        tree = etree.ElementTree(root)
        tree.write(
            str(xml_path),
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )

        logger.info(f"XRechnung-XML erzeugt: {xml_path.name}")
        return xml_path

    except Exception as e:
        logger.error(f"Fehler bei der XML-Generierung: {e}")
        return None


def _build_xml(d: dict) -> etree._Element:
    """Baut den vollständigen CII-XML-Baum auf."""

    # ── Root-Element ──────────────────────────────────────────
    root = etree.Element(
        f"{{{_NS['rsm']}}}CrossIndustryInvoice",
        nsmap=_NS,
    )
    root.set(
        f"{{{_NS['xsi']}}}schemaLocation",
        "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100 "
        "CrossIndustryInvoice_100pD22B.xsd",
    )

    # ── ExchangedDocumentContext ───────────────────────────────
    ctx = _el(root, "rsm", "ExchangedDocumentContext")
    gid = _el(ctx,  "ram", "GuidelineSpecifiedDocumentContextParameter")
    _el(gid, "ram", "ID",
        "urn:cen.eu:en16931:2017#compliant#urn:xoev-de:kosit:standard:xrechnung_3.0")

    # ── ExchangedDocument ──────────────────────────────────────
    doc = _el(root, "rsm", "ExchangedDocument")
    _el(doc, "ram", "ID",   d.get("invoice_number", ""))
    _el(doc, "ram", "TypeCode", "380")  # 380 = Rechnung
    issue = _el(doc, "ram", "IssueDateTime")
    dts   = _el(issue, "udt", "DateTimeString", _fmt_date(d.get("invoice_date")),
                format="102")

    # ── SupplyChainTradeTransaction ────────────────────────────
    tx = _el(root, "rsm", "SupplyChainTradeTransaction")

    # Positionen
    for item in d.get("items", []):
        _build_line_item(tx, item)

    # HeaderTradeAgreement
    agr = _el(tx, "ram", "ApplicableHeaderTradeAgreement")

    # Buyer Reference (Leitweg-ID — Pflichtfeld BT-10)
    leitweg = d.get("leitweg_id", "")
    if leitweg:
        _el(agr, "ram", "BuyerReference", leitweg)

    # Seller (BG-4)
    seller = _el(agr, "ram", "SellerTradeParty")
    _el(seller, "ram", "Name", d.get("seller_name", ""))
    seller_addr = _el(seller, "ram", "PostalTradeAddress")
    _el(seller_addr, "ram", "PostcodeCode", d.get("seller_zip", ""))
    _el(seller_addr, "ram", "LineOne",      d.get("seller_street", ""))
    _el(seller_addr, "ram", "CityName",     d.get("seller_city", ""))
    _el(seller_addr, "ram", "CountryID",    d.get("seller_country", "DE"))
    if d.get("seller_vat_id"):
        s_tax = _el(seller, "ram", "SpecifiedTaxRegistration")
        _el(s_tax, "ram", "ID", d["seller_vat_id"], schemeID="VA")
    if d.get("seller_email"):
        s_uri = _el(seller, "ram", "EndPointURIUniversalCommunication")
        _el(s_uri, "ram", "URIID", d["seller_email"], schemeID="EM")
    # Buyer (BG-7)
    buyer = _el(agr, "ram", "BuyerTradeParty")
    name1 = d.get("billing_name1", "") or d.get("buyer_name", "")
    name2 = d.get("billing_name2", "") or d.get("buyer_name2", "")
    full_name = f"{name1}, {name2}".strip(", ") if name2 else name1
    _el(buyer, "ram", "Name", full_name)
    buyer_addr = _el(buyer, "ram", "PostalTradeAddress")
    _el(buyer_addr, "ram", "PostcodeCode", d.get("billing_zip", "") or d.get("buyer_zip", ""))
    _el(buyer_addr, "ram", "LineOne",      d.get("billing_street", "") or d.get("buyer_street", ""))
    _el(buyer_addr, "ram", "CityName",     d.get("billing_city", "") or d.get("buyer_city", ""))
    _el(buyer_addr, "ram", "CountryID",    d.get("buyer_country", "DE"))

    # HeaderTradeDelivery
    dlv = _el(tx, "ram", "ApplicableHeaderTradeDelivery")
    if d.get("service_start"):
        occ = _el(dlv, "ram", "ActualDeliverySupplyChainEvent")
        occ_dt = _el(occ, "ram", "OccurrenceDateTime")
        _el(occ_dt, "udt", "DateTimeString",
            _fmt_date(d.get("service_start")), format="102")

    # HeaderTradeSettlement
    stl = _el(tx, "ram", "ApplicableHeaderTradeSettlement")
    _el(stl, "ram", "InvoiceCurrencyCode", d.get("currency", "EUR"))

    # Zahlungsweise (IBAN/BIC — BG-17)
    if d.get("seller_iban"):
        pm = _el(stl, "ram", "SpecifiedTradeSettlementPaymentMeans")
        _el(pm, "ram", "TypeCode", "58")  # 58 = SEPA-Überweisung
        payer_acct = _el(pm, "ram", "PayeePartyCreditorFinancialAccount")
        _el(payer_acct, "ram", "IBANID", d["seller_iban"])
        if d.get("seller_bic"):
            fi = _el(pm, "ram", "PayeeSpecifiedCreditorFinancialInstitution")
            _el(fi, "ram", "BICID", d["seller_bic"])

    # Steuern (BG-23) — gruppiert nach Steuersatz
    tax_groups = _group_taxes(d.get("items", []))
    trade_tax  = _el(stl, "ram", "ApplicableTradeTax")
    for tax_rate, amounts in tax_groups.items():
        _el(trade_tax, "ram", "CalculatedAmount",
            _dec(amounts["tax_amount"]), currencyID="EUR")
        _el(trade_tax, "ram", "TypeCode", "VAT")
        _el(trade_tax, "ram", "BasisAmount",
            _dec(amounts["net_amount"]), currencyID="EUR")
        _el(trade_tax, "ram", "CategoryCode", "S")  # Standard-MwSt
        _el(trade_tax, "ram", "RateApplicablePercent", _dec(tax_rate))

    # Fälligkeit (BT-9)
    if d.get("due_date"):
        terms = _el(stl, "ram", "SpecifiedTradePaymentTerms")
        due   = _el(terms, "ram", "DueDateDateTime")
        _el(due, "udt", "DateTimeString",
            _fmt_date(d.get("due_date")), format="102")

    # Summen (BG-22)
    summary = _el(stl, "ram", "SpecifiedTradeSettlementHeaderMonetarySummation")
    _el(summary, "ram", "LineTotalAmount",
        _dec(d.get("total_net")), currencyID="EUR")
    _el(summary, "ram", "TaxBasisTotalAmount",
        _dec(d.get("total_net")), currencyID="EUR")
    _el(summary, "ram", "TaxTotalAmount",
        _dec(d.get("total_tax")), currencyID="EUR")
    _el(summary, "ram", "GrandTotalAmount",
        _dec(d.get("total_gross")), currencyID="EUR")
    _el(summary, "ram", "DuePayableAmount",
        _dec(d.get("total_gross")), currencyID="EUR")

    return root


def _build_line_item(tx: etree._Element, item: dict) -> None:
    """Erzeugt eine Rechnungsposition (BG-25)."""
    line = _el(tx, "ram", "IncludedSupplyChainTradeLineItem")

    # Positionsnummer
    doc_ref = _el(line, "ram", "AssociatedDocumentLineDocument")
    _el(doc_ref, "ram", "LineID", str(item.get("position_no", "")))

    # Produktbeschreibung
    product = _el(line, "ram", "SpecifiedTradeProduct")
    _el(product, "ram", "SellerAssignedID", str(item.get("item_code", "")))
    _el(product, "ram", "Name",             str(item.get("description", "")))

    # Preisvereinbarung
    agreement = _el(line, "ram", "SpecifiedLineTradeAgreement")
    net_price  = _el(agreement, "ram", "NetPriceProductTradePrice")
    _el(net_price, "ram", "ChargeAmount",
        _dec(item.get("unit_price_net")), currencyID="EUR")

    # Menge
    delivery = _el(line, "ram", "SpecifiedLineTradeDelivery")
    _el(delivery, "ram", "BilledQuantity",
        _dec(item.get("quantity"), places=2), unitCode="C62")  # C62 = Stück

    # Steuer auf Positionsebene
    settlement  = _el(line, "ram", "SpecifiedLineTradeSettlement")
    line_tax    = _el(settlement, "ram", "ApplicableTradeTax")
    _el(line_tax, "ram", "TypeCode", "VAT")
    _el(line_tax, "ram", "CategoryCode", "S")
    _el(line_tax, "ram", "RateApplicablePercent",
        _dec(item.get("tax_rate")))

    # Zeilensumme
    monetary = _el(settlement, "ram", "SpecifiedTradeSettlementLineMonetarySummation")
    _el(monetary, "ram", "LineTotalAmount",
        _dec(item.get("line_total_net")), currencyID="EUR")


def _group_taxes(items: list) -> dict:
    """
    Gruppiert Positionen nach Steuersatz und berechnet
    Nettobetrag und Steuerbetrag je Gruppe.
    """
    groups: dict[str, dict] = {}
    for item in items:
        rate = str(Decimal(str(item.get("tax_rate", 19))).quantize(Decimal("0.01")))
        net  = Decimal(str(item.get("line_total_net", 0)))
        if rate not in groups:
            groups[rate] = {"net_amount": Decimal("0"), "tax_amount": Decimal("0")}
        groups[rate]["net_amount"] += net
        groups[rate]["tax_amount"] += (net * Decimal(rate) / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return groups