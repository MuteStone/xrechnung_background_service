import logging
import smtplib
import socket
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

logger = logging.getLogger("xrechnung.transmitter")


def transmit(xml_path: Path, config: dict, pdf_path: Path = None) -> bool:
    try:
        msg = _build_email(xml_path, config, pdf_path)
        _send(msg, config)
        logger.info(
            f"XRechnung übertragen: {xml_path.name} "
            f"→ {config['OZG_RE_EMAIL']}"
        )
        if pdf_path:
            logger.info(f"PDF mitgesendet: {pdf_path.name}")
        return True
    except Exception as e:
        logger.error(f"Übertragung fehlgeschlagen: {e}")
        return False


def _build_email(xml_path: Path, config: dict, pdf_path: Path = None):
    """Baut die E-Mail mit XML-Anhang (und optional PDF-Anhang) zusammen."""
    msg = EmailMessage()
    msg["From"]    = f"{config['SMTP_FROM_NAME']} <{config['SMTP_FROM']}>"
    msg["To"]      = config["OZG_RE_EMAIL"]
    msg["Subject"] = config["OZG_RE_SUBJECT"]

    # Anhang 1: XRechnung-XML (Pflicht)
    with open(xml_path, "rb") as f:
        xml_data = f.read()

    msg.add_attachment(
        xml_data,
        maintype="application",
        subtype="xml",
        filename=xml_path.name,
    )

    # Anhang 2: Original-PDF (optional, wenn Pfad übergeben wurde)
    if pdf_path and pdf_path.exists():
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        msg.add_attachment(
            pdf_data,
            maintype="application",
            subtype="pdf",
            filename=pdf_path.name,
        )

    return msg


def _send(msg, config: dict) -> None:
    """Sendet die E-Mail via SMTP (intern, kein TLS, IPv4 erzwungen)."""
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo_ipv4_only(*args, **kwargs):
        results = original_getaddrinfo(*args, **kwargs)
        return [r for r in results if r[0] == socket.AF_INET]

    socket.getaddrinfo = getaddrinfo_ipv4_only

    try:
        with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"]) as smtp:
            smtp.ehlo()
            # Kein starttls() — intern ohne TLS
            # Login nur wenn SMTP_USER gesetzt und nicht leer
            if config.get("SMTP_USER"):
                smtp.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
            smtp.send_message(msg)
    finally:
        socket.getaddrinfo = original_getaddrinfo


# ---------------------------------------------------------------------------
# Protokoll-Mail (interner Bericht nach dem Verarbeitungslauf)
# ---------------------------------------------------------------------------

def send_report(
    config: dict,
    processed: int,
    failed: int,
    invoice_names: list[str],
    failed_names: list[str],
    xml_paths: Optional[list[Path]] = None,
) -> bool:
    """
    Sendet eine Protokoll-Mail an REPORT_EMAIL nach Abschluss des Verarbeitungslaufs.

    Enthält:
    - Zeitstempel, Statistik (verarbeitet / fehlgeschlagen)
    - Liste der erfolgreich übertragenen Rechnungen
    - Liste der fehlgeschlagenen Dateien (sofern vorhanden)
    - Optional: erzeugte XML-Dateien als Anhänge (REPORT_ATTACH_XML=true)

    Wird nur gesendet wenn REPORT_EMAIL in der Konfiguration gesetzt ist.
    """
    report_email = config.get("REPORT_EMAIL", "").strip()
    if not report_email:
        return True  # Kein Bericht konfiguriert — kein Fehler

    try:
        msg = _build_report_email(
            config, processed, failed, invoice_names, failed_names, xml_paths
        )
        _send(msg, config)
        logger.info("Protokoll-Mail gesendet → %s", report_email)
        return True
    except Exception as e:
        logger.warning("Protokoll-Mail fehlgeschlagen: %s", e)
        return False


def _build_report_email(
    config: dict,
    processed: int,
    failed: int,
    invoice_names: list[str],
    failed_names: list[str],
    xml_paths: Optional[list[Path]],
) -> EmailMessage:
    """Baut die Protokoll-Mail zusammen."""
    report_email  = config["REPORT_EMAIL"].strip()
    attach_xml    = str(config.get("REPORT_ATTACH_XML", "false")).lower() == "true"
    timestamp     = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    total         = processed + failed
    status_emoji  = "✅" if failed == 0 else ("⚠️" if processed > 0 else "❌")

    subject = (
        f"{status_emoji} XRechnung-Dienst – Protokoll {datetime.now().strftime('%d.%m.%Y')}"
        f" ({processed}/{total} erfolgreich)"
    )

    # --- Textkörper ---
    lines = [
        f"XRechnung-Hintergrunddienst – Verarbeitungsprotokoll",
        f"Zeitstempel:     {timestamp}",
        f"",
        f"Ergebnis:        {processed} erfolgreich  |  {failed} fehlgeschlagen  |  {total} gesamt",
        f"",
    ]

    if invoice_names:
        lines.append("Erfolgreich übertragen:")
        for name in invoice_names:
            lines.append(f"  ✓  {name}")
        lines.append("")

    if failed_names:
        lines.append("Fehlgeschlagen (→ error/):")
        for name in failed_names:
            lines.append(f"  ✗  {name}")
        lines.append("")

    if attach_xml and xml_paths:
        lines.append(f"{len(xml_paths)} XML-Datei(en) als Anhang beigefügt.")
        lines.append("")

    lines += [
        "---",
        f"Versandadresse OZG-RE: {config.get('OZG_RE_EMAIL', '')}",
        f"Absender:              {config.get('SMTP_FROM', '')}",
    ]

    body = "\n".join(lines)

    msg = EmailMessage()
    msg["From"]    = f"{config['SMTP_FROM_NAME']} <{config['SMTP_FROM']}>"
    msg["To"]      = report_email
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")

    # Optional: XML-Dateien anhängen
    if attach_xml and xml_paths:
        for xml_path in xml_paths:
            if xml_path and xml_path.exists():
                try:
                    with open(xml_path, "rb") as f:
                        xml_data = f.read()
                    msg.add_attachment(
                        xml_data,
                        maintype="application",
                        subtype="xml",
                        filename=xml_path.name,
                    )
                except Exception as e:
                    logger.debug("XML-Anhang fehlgeschlagen (%s): %s", xml_path.name, e)

    return msg