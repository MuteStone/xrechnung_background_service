"""
XRechnung-Generator (EN 16931, CII-Format)
==========================================
Erzeugt eine valide XRechnung-XML gemäß XRechnung 3.x / UN/CEFACT CII.
Eingabe: invoice_data-Dictionary aus get_invoice_full()
Ausgabe: XML-Datei im OUTPUT_XML-Ordner
"""

import logging
import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
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
    """Gibt ein YYYYMMDD-Datum zurück, oder '' wenn der Wert kein gültiges Datum ist."""
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    if isinstance(d, str):
        normalized = d.replace("-", "").replace(".", "").replace(" ", "")[:8]
        if len(normalized) == 8 and normalized.isdigit():
            return normalized
    return ""  # Ungültiger Wert (z. B. "Mai", "", None) → Element nicht erzeugen


def _to_decimal(value, default="0.00"):
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _quantize(value, places=2):
    dec = _to_decimal(value)
    pattern = "0." + ("0" * places)
    return dec.quantize(Decimal(pattern), rounding=ROUND_HALF_UP)


def _dec(value, places=2):
    return str(_quantize(value, places))


def generate(invoice_data, output_dir):
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        invoice_number = invoice_data.get("invoice_number", "") or "rechnung"
        xml_path = output_dir / f"{invoice_number}.xml"

        root = _build_xml(invoice_data)

        etree.ElementTree(root).write(
            str(xml_path),
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True
        )

        logger.info("XRechnung-XML erzeugt: %s", xml_path.name)
        return xml_path

    except Exception as e:
        logger.exception("Fehler bei der XML-Generierung: %s", e)
        return None


def _build_xml(d):
    root = etree.Element(f"{{{_NS['rsm']}}}CrossIndustryInvoice", nsmap=_NS)

    # ExchangedDocumentContext
    ctx = _el(root, "rsm", "ExchangedDocumentContext")
    bpctx = _el(ctx, "ram", "BusinessProcessSpecifiedDocumentContextParameter")
    _el(bpctx, "ram", "ID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")

    gid = _el(ctx, "ram", "GuidelineSpecifiedDocumentContextParameter")
    _el(
        gid,
        "ram",
        "ID",
        "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
    )

    # ExchangedDocument
    doc = _el(root, "rsm", "ExchangedDocument")
    _el(doc, "ram", "ID", d.get("invoice_number", ""))
    _el(doc, "ram", "TypeCode", "380")

    issue = _el(doc, "ram", "IssueDateTime")
    _el(issue, "udt", "DateTimeString", _fmt_date(d.get("invoice_date")), format="102")

    # SupplyChainTradeTransaction
    tx = _el(root, "rsm", "SupplyChainTradeTransaction")

    items = d.get("items", []) or []
    for item in items:
        _build_line_item(tx, item)

    # HeaderTradeAgreement
    agr = _el(tx, "ram", "ApplicableHeaderTradeAgreement")

    leitweg = d.get("leitweg_id", "")
    if leitweg:
        _el(agr, "ram", "BuyerReference", leitweg)

    # SellerTradeParty
    seller = _el(agr, "ram", "SellerTradeParty")
    _el(seller, "ram", "Name", d.get("seller_name", ""))

    seller_contact_name = d.get("seller_contact_name") or d.get("seller_name", "")
    seller_phone = d.get("seller_phone", "")
    seller_email = d.get("seller_email", "")

    s_contact = _el(seller, "ram", "DefinedTradeContact")
    _el(s_contact, "ram", "PersonName", seller_contact_name)

    if seller_phone:
        sp = _el(s_contact, "ram", "TelephoneUniversalCommunication")
        _el(sp, "ram", "CompleteNumber", seller_phone)

    if seller_email:
        se = _el(s_contact, "ram", "EmailURIUniversalCommunication")
        _el(se, "ram", "URIID", seller_email)

    sa = _el(seller, "ram", "PostalTradeAddress")
    _el(sa, "ram", "PostcodeCode", d.get("seller_zip", ""))
    _el(sa, "ram", "LineOne", d.get("seller_street", ""))
    _el(sa, "ram", "CityName", d.get("seller_city", ""))
    _el(sa, "ram", "CountryID", d.get("seller_country", "DE"))

    # BT-34: Seller electronic address
    if seller_email:
        su = _el(seller, "ram", "URIUniversalCommunication")
        _el(su, "ram", "URIID", seller_email, schemeID="EM")

    if d.get("seller_vat_id"):
        st = _el(seller, "ram", "SpecifiedTaxRegistration")
        _el(st, "ram", "ID", re.sub(r"\s", "", d["seller_vat_id"]), schemeID="VA")

    # BuyerTradeParty
    buyer = _el(agr, "ram", "BuyerTradeParty")

    name1 = d.get("billing_name1", "") or d.get("buyer_name", "")
    name2 = d.get("billing_name2", "") or d.get("buyer_name2", "")
    buyer_name = f"{name1}, {name2}".strip(", ") if name2 else name1
    _el(buyer, "ram", "Name", buyer_name)

    ba = _el(buyer, "ram", "PostalTradeAddress")
    _el(ba, "ram", "PostcodeCode", d.get("billing_zip", "") or d.get("buyer_zip", ""))
    _el(ba, "ram", "LineOne", d.get("billing_street", "") or d.get("buyer_street", ""))
    _el(ba, "ram", "CityName", d.get("billing_city", "") or d.get("buyer_city", ""))
    _el(ba, "ram", "CountryID", d.get("buyer_country", "DE"))

    # BT-49: Buyer electronic address
    buyer_email = d.get("buyer_email", "")
    if buyer_email:
        bu = _el(buyer, "ram", "URIUniversalCommunication")
        _el(bu, "ram", "URIID", buyer_email, schemeID="EM")
    elif leitweg:
        bu = _el(buyer, "ram", "URIUniversalCommunication")
        _el(bu, "ram", "URIID", leitweg, schemeID="0204")

    # HeaderTradeDelivery — BT-72 (Actual delivery date)
    # Primär: Liefer-/Leistungsdatum aus DB (lieferung-Feld).
    # Fallback: Rechnungsdatum, da bei FuxMedia-Rechnungen kein explizites
    # Lieferdatum angegeben wird (behebt BR-DE-TMP-32).
    dlv = _el(tx, "ram", "ApplicableHeaderTradeDelivery")
    delivery_date_fmt = _fmt_date(d.get("service_start")) or _fmt_date(d.get("invoice_date"))
    if delivery_date_fmt:
        occ = _el(dlv, "ram", "ActualDeliverySupplyChainEvent")
        occ_dt = _el(occ, "ram", "OccurrenceDateTime")
        _el(occ_dt, "udt", "DateTimeString", delivery_date_fmt, format="102")

    # HeaderTradeSettlement
    stl = _el(tx, "ram", "ApplicableHeaderTradeSettlement")
    _el(stl, "ram", "InvoiceCurrencyCode", d.get("currency", "EUR"))

    if d.get("seller_iban"):
        pm = _el(stl, "ram", "SpecifiedTradeSettlementPaymentMeans")
        _el(pm, "ram", "TypeCode", "58")

        pa = _el(pm, "ram", "PayeePartyCreditorFinancialAccount")
        _el(pa, "ram", "IBANID", re.sub(r"\s", "", d["seller_iban"]))

        if d.get("seller_bic"):
            fi = _el(pm, "ram", "PayeeSpecifiedCreditorFinancialInstitution")
            _el(fi, "ram", "BICID", d["seller_bic"])

    # Steuergruppen berechnen
    tax_groups = _group_taxes(items)

    # Pro Steuergruppe ein eigener ApplicableTradeTax-Block
    for tax_rate, amounts in tax_groups.items():
        tt = _el(stl, "ram", "ApplicableTradeTax")
        _el(tt, "ram", "CalculatedAmount", _dec(amounts["tax_amount"]))
        _el(tt, "ram", "TypeCode", "VAT")
        _el(tt, "ram", "BasisAmount", _dec(amounts["net_amount"]))
        _el(tt, "ram", "CategoryCode", amounts["category_code"])
        _el(tt, "ram", "RateApplicablePercent", _dec(tax_rate))

    if d.get("due_date"):
        terms = _el(stl, "ram", "SpecifiedTradePaymentTerms")
        due = _el(terms, "ram", "DueDateDateTime")
        _el(due, "udt", "DateTimeString", _fmt_date(d.get("due_date")), format="102")

    # Summen direkt aus Positionen / Steuergruppen berechnen
    sum_net = sum(
        (_to_decimal(item.get("line_total_net", 0)) for item in items),
        Decimal("0.00")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    sum_tax = sum(
        (amounts["tax_amount"] for amounts in tax_groups.values()),
        Decimal("0.00")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    sum_gross = (sum_net + sum_tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    logger.info("XRechnung Summen:")
    logger.info("  sum_net   = %s", _dec(sum_net))
    logger.info("  sum_tax   = %s", _dec(sum_tax))
    logger.info("  sum_gross = %s", _dec(sum_gross))

    for tax_rate, amounts in tax_groups.items():
        logger.info(
            "  VAT %s%% -> net=%s tax=%s",
            tax_rate,
            _dec(amounts["net_amount"]),
            _dec(amounts["tax_amount"])
        )

    sm = _el(stl, "ram", "SpecifiedTradeSettlementHeaderMonetarySummation")
    _el(sm, "ram", "LineTotalAmount", _dec(sum_net))
    _el(sm, "ram", "TaxBasisTotalAmount", _dec(sum_net))
    _el(sm, "ram", "TaxTotalAmount", _dec(sum_tax), currencyID=d.get("currency", "EUR"))
    _el(sm, "ram", "GrandTotalAmount", _dec(sum_gross))
    _el(sm, "ram", "DuePayableAmount", _dec(sum_gross))

    return root


def _build_line_item(tx, item):
    line = _el(tx, "ram", "IncludedSupplyChainTradeLineItem")

    dr = _el(line, "ram", "AssociatedDocumentLineDocument")
    _el(dr, "ram", "LineID", str(item.get("position_no", "")))

    prod = _el(line, "ram", "SpecifiedTradeProduct")
    _el(prod, "ram", "SellerAssignedID", str(item.get("item_code", "")))
    _el(prod, "ram", "Name", str(item.get("description", "")))

    agr = _el(line, "ram", "SpecifiedLineTradeAgreement")
    np = _el(agr, "ram", "NetPriceProductTradePrice")
    _el(np, "ram", "ChargeAmount", _dec(item.get("unit_price_net")))

    dlv = _el(line, "ram", "SpecifiedLineTradeDelivery")
    _el(
        dlv,
        "ram",
        "BilledQuantity",
        _dec(item.get("quantity"), places=2),
        unitCode=item.get("unit_code", "C62")
    )

    stl = _el(line, "ram", "SpecifiedLineTradeSettlement")
    lt = _el(stl, "ram", "ApplicableTradeTax")
    _el(lt, "ram", "TypeCode", "VAT")

    tax_rate = _quantize(item.get("tax_rate", 19), places=2)
    category_code = item.get("tax_category_code", "S")
    _el(lt, "ram", "CategoryCode", category_code)
    _el(lt, "ram", "RateApplicablePercent", _dec(tax_rate))

    mn = _el(stl, "ram", "SpecifiedTradeSettlementLineMonetarySummation")
    _el(mn, "ram", "LineTotalAmount", _dec(item.get("line_total_net")))


def _group_taxes(items):
    groups = {}

    for item in items:
        rate = _quantize(item.get("tax_rate", 19), places=2)
        rate_key = str(rate)

        category_code = item.get("tax_category_code", "S")
        net = _quantize(item.get("line_total_net", 0), places=2)

        if rate_key not in groups:
            groups[rate_key] = {
                "net_amount": Decimal("0.00"),
                "tax_amount": Decimal("0.00"),
                "category_code": category_code,
                "rate": rate,
            }

        groups[rate_key]["net_amount"] += net

    # Steuer erst nach dem Gruppieren aus der gesamten Nettosumme berechnen
    for group in groups.values():
        group["net_amount"] = group["net_amount"].quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
        group["tax_amount"] = (
            group["net_amount"] * group["rate"] / Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

    return groups