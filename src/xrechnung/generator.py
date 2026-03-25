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

_NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}


def _el(parent, ns, tag, text=None, **attrs):
    elem = etree.SubElement(parent, f"{{{_NS[ns]}}}{tag}", **attrs)
    if text is not None:
        elem.text = str(text)
    return elem


def _fmt_date(d):
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    if isinstance(d, str):
        return d.replace("-", "")[:8]
    return ""


def _dec(value, places=2):
    if value is None:
        return "0.00"
    return str(Decimal(str(value)).quantize(Decimal("0." + "0" * places), rounding=ROUND_HALF_UP))


def generate(invoice_data, output_dir):
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        invoice_number = invoice_data.get("invoice_number", "")
        xml_path = output_dir / f"{invoice_number}.xml"
        root = _build_xml(invoice_data)
        etree.ElementTree(root).write(str(xml_path), xml_declaration=True, encoding="UTF-8", pretty_print=True)
        logger.info(f"XRechnung-XML erzeugt: {xml_path.name}")
        return xml_path
    except Exception as e:
        logger.error(f"Fehler bei der XML-Generierung: {e}")
        return None


def _build_xml(d):
    root = etree.Element(f"{{{_NS['rsm']}}}CrossIndustryInvoice", nsmap=_NS)

    ctx = _el(root, "rsm", "ExchangedDocumentContext")
    bpctx = _el(ctx, "ram", "BusinessProcessSpecifiedDocumentContextParameter")
    _el(bpctx, "ram", "ID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    gid = _el(ctx, "ram", "GuidelineSpecifiedDocumentContextParameter")
    _el(gid, "ram", "ID", "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0")

    doc = _el(root, "rsm", "ExchangedDocument")
    _el(doc, "ram", "ID", d.get("invoice_number", ""))
    _el(doc, "ram", "TypeCode", "380")
    issue = _el(doc, "ram", "IssueDateTime")
    _el(issue, "udt", "DateTimeString", _fmt_date(d.get("invoice_date")), format="102")

    tx = _el(root, "rsm", "SupplyChainTradeTransaction")

    for item in d.get("items", []):
        _build_line_item(tx, item)

    agr = _el(tx, "ram", "ApplicableHeaderTradeAgreement")
    leitweg = d.get("leitweg_id", "")
    if leitweg:
        _el(agr, "ram", "BuyerReference", leitweg)

    # Seller — Reihenfolge: Name, DefinedTradeContact, PostalTradeAddress,
    #          SpecifiedTaxRegistration, EndPointURIUniversalCommunication
    seller = _el(agr, "ram", "SellerTradeParty")
    _el(seller, "ram", "Name", d.get("seller_name", ""))

    # BR-DE-2: DefinedTradeContact VOR PostalTradeAddress
    s_contact = _el(seller, "ram", "DefinedTradeContact")
    _el(s_contact, "ram", "PersonName", d.get("seller_name", ""))
    if d.get("seller_phone"):
        sp = _el(s_contact, "ram", "TelephoneUniversalCommunication")
        _el(sp, "ram", "CompleteNumber", d.get("seller_phone", ""))
    if d.get("seller_email"):
        su = _el(seller, "ram", "URIUniversalCommunication")
        _el(su, "ram", "URIID", d["seller_email"], schemeID="EM")

    sa = _el(seller, "ram", "PostalTradeAddress")
    _el(sa, "ram", "PostcodeCode", d.get("seller_zip", ""))
    _el(sa, "ram", "LineOne",      d.get("seller_street", ""))
    _el(sa, "ram", "CityName",     d.get("seller_city", ""))
    _el(sa, "ram", "CountryID",    d.get("seller_country", "DE"))

    if d.get("seller_vat_id"):
        st = _el(seller, "ram", "SpecifiedTaxRegistration")
        _el(st, "ram", "ID", d["seller_vat_id"], schemeID="VA")

    # BT-34: EndPointURIUniversalCommunication NACH SpecifiedTaxRegistration
    if d.get("seller_email"):
        su = _el(seller, "ram", "EndPointURIUniversalCommunication")
        _el(su, "ram", "URIID", d["seller_email"], schemeID="EM")

    # Buyer
    buyer = _el(agr, "ram", "BuyerTradeParty")
    name1 = d.get("billing_name1", "") or d.get("buyer_name", "")
    name2 = d.get("billing_name2", "") or d.get("buyer_name2", "")
    _el(buyer, "ram", "Name", f"{name1}, {name2}".strip(", ") if name2 else name1)

    ba = _el(buyer, "ram", "PostalTradeAddress")
    _el(ba, "ram", "PostcodeCode", d.get("billing_zip", "") or d.get("buyer_zip", ""))
    _el(ba, "ram", "LineOne",      d.get("billing_street", "") or d.get("buyer_street", ""))
    _el(ba, "ram", "CityName",     d.get("billing_city", "") or d.get("buyer_city", ""))
    _el(ba, "ram", "CountryID",    d.get("buyer_country", "DE"))

    # BT-49: URIUniversalCommunication NACH PostalTradeAddress
    buyer_email = d.get("buyer_email", "")
    if buyer_email:
        bu = _el(buyer, "ram", "URIUniversalCommunication")
        _el(bu, "ram", "URIID", buyer_email, schemeID="EM")
    elif leitweg:
        bu = _el(buyer, "ram", "URIUniversalCommunication")
        _el(bu, "ram", "URIID", leitweg, schemeID="0204")

    dlv = _el(tx, "ram", "ApplicableHeaderTradeDelivery")
    if d.get("service_start"):
        occ = _el(dlv, "ram", "ActualDeliverySupplyChainEvent")
        occ_dt = _el(occ, "ram", "OccurrenceDateTime")
        _el(occ_dt, "udt", "DateTimeString", _fmt_date(d.get("service_start")), format="102")

    stl = _el(tx, "ram", "ApplicableHeaderTradeSettlement")
    _el(stl, "ram", "InvoiceCurrencyCode", d.get("currency", "EUR"))

    if d.get("seller_iban"):
        pm = _el(stl, "ram", "SpecifiedTradeSettlementPaymentMeans")
        _el(pm, "ram", "TypeCode", "58")
        pa = _el(pm, "ram", "PayeePartyCreditorFinancialAccount")
        _el(pa, "ram", "IBANID", d["seller_iban"])
        if d.get("seller_bic"):
            fi = _el(pm, "ram", "PayeeSpecifiedCreditorFinancialInstitution")
            _el(fi, "ram", "BICID", d["seller_bic"])

    # Steuern — KEIN currencyID auf CalculatedAmount/BasisAmount (CII-DT-031)
    tax_groups = _group_taxes(d.get("items", []))
    tt = _el(stl, "ram", "ApplicableTradeTax")
    for tax_rate, amounts in tax_groups.items():
        _el(tt, "ram", "CalculatedAmount", _dec(amounts["tax_amount"]))
        _el(tt, "ram", "TypeCode", "VAT")
        _el(tt, "ram", "BasisAmount", _dec(amounts["net_amount"]))
        _el(tt, "ram", "CategoryCode", "S")
        _el(tt, "ram", "RateApplicablePercent", _dec(tax_rate))

    if d.get("due_date"):
        terms = _el(stl, "ram", "SpecifiedTradePaymentTerms")
        due = _el(terms, "ram", "DueDateDateTime")
        _el(due, "udt", "DateTimeString", _fmt_date(d.get("due_date")), format="102")

    # Summen — currencyID hier erlaubt
    sm = _el(stl, "ram", "SpecifiedTradeSettlementHeaderMonetarySummation")
    _el(sm, "ram", "LineTotalAmount",     _dec(d.get("total_net")))
    _el(sm, "ram", "TaxBasisTotalAmount", _dec(d.get("total_net")))
    _el(sm, "ram", "TaxTotalAmount",      _dec(d.get("total_tax")))
    _el(sm, "ram", "GrandTotalAmount",    _dec(d.get("total_gross")))
    _el(sm, "ram", "DuePayableAmount",    _dec(d.get("total_gross")))

    return root


def _build_line_item(tx, item):
    line = _el(tx, "ram", "IncludedSupplyChainTradeLineItem")
    dr = _el(line, "ram", "AssociatedDocumentLineDocument")
    _el(dr, "ram", "LineID", str(item.get("position_no", "")))
    prod = _el(line, "ram", "SpecifiedTradeProduct")
    _el(prod, "ram", "SellerAssignedID", str(item.get("item_code", "")))
    _el(prod, "ram", "Name",             str(item.get("description", "")))
    agr = _el(line, "ram", "SpecifiedLineTradeAgreement")
    np  = _el(agr,  "ram", "NetPriceProductTradePrice")
    _el(np, "ram", "ChargeAmount", _dec(item.get("unit_price_net")))
    dlv = _el(line, "ram", "SpecifiedLineTradeDelivery")
    _el(dlv, "ram", "BilledQuantity", _dec(item.get("quantity"), places=2), unitCode="C62")
    stl = _el(line, "ram", "SpecifiedLineTradeSettlement")
    lt  = _el(stl,  "ram", "ApplicableTradeTax")
    _el(lt, "ram", "TypeCode", "VAT")
    _el(lt, "ram", "CategoryCode", "S")
    _el(lt, "ram", "RateApplicablePercent", _dec(item.get("tax_rate")))
    mn = _el(stl, "ram", "SpecifiedTradeSettlementLineMonetarySummation")
    _el(mn, "ram", "LineTotalAmount", _dec(item.get("line_total_net")))


def _group_taxes(items):
    groups = {}
    for item in items:
        rate = str(Decimal(str(item.get("tax_rate", 19))).quantize(Decimal("0.01")))
        net  = Decimal(str(item.get("line_total_net", 0)))
        if rate not in groups:
            groups[rate] = {"net_amount": Decimal("0"), "tax_amount": Decimal("0")}
        groups[rate]["net_amount"] += net
        groups[rate]["tax_amount"] += (net * Decimal(rate) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return groups