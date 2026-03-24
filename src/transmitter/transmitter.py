"""
Transmitter — XRechnung per E-Mail an OZG-RE übertragen
=========================================================
SMTP via Gmail (App-Passwort, STARTTLS, IPv4 erzwungen).
"""

import logging
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

logger = logging.getLogger("xrechnung.transmitter")


def transmit(xml_path: Path, config: dict) -> bool:
    """
    Versendet die XRechnung-XML als E-Mail-Anhang an das OZG-RE Testportal.

    Args:
        xml_path: Pfad zur validierten XML-Datei
        config:   Konfigurationsdictionary

    Returns:
        True bei Erfolg, False bei Fehler.
    """
    try:
        msg = _build_email(xml_path, config)
        _send(msg, config)
        logger.info(
            f"XRechnung übertragen: {xml_path.name} "
            f"→ {config['OZG_RE_EMAIL']}"
        )
        return True
    except Exception as e:
        logger.error(f"Übertragung fehlgeschlagen: {e}")
        return False


def _build_email(xml_path: Path, config: dict) -> MIMEMultipart:
    """Baut die E-Mail mit XML-Anhang zusammen."""
    msg = MIMEMultipart()
    msg["From"]    = f"{config['SMTP_FROM_NAME']} <{config['SMTP_FROM']}>"
    msg["To"]      = config["OZG_RE_EMAIL"]
    msg["Subject"] = config["OZG_RE_SUBJECT"]

    # E-Mail-Body
    msg.attach(MIMEText(
        "Sehr geehrte Damen und Herren,\n\n"
        "anbei übermitteln wir eine XRechnung gemäß EN 16931.\n\n"
        "Mit freundlichen Grüßen\n"
        f"{config['SMTP_FROM_NAME']}",
        "plain",
        "utf-8",
    ))

    # XML als Anhang
    with open(xml_path, "rb") as f:
        part = MIMEBase("application", "xml")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f'attachment; filename="{xml_path.name}"',
    )
    msg.attach(part)

    return msg


def _send(msg: MIMEMultipart, config: dict) -> None:
    """Sendet die E-Mail via SMTP (STARTTLS, IPv4 erzwungen)."""

    # IPv4 erzwingen (verhindert Probleme bei blockiertem IPv6)
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo_ipv4_only(*args, **kwargs):
        results = original_getaddrinfo(*args, **kwargs)
        return [r for r in results if r[0] == socket.AF_INET]

    socket.getaddrinfo = getaddrinfo_ipv4_only

    try:
        with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"]) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
            smtp.sendmail(
                config["SMTP_FROM"],
                config["OZG_RE_EMAIL"],
                msg.as_string(),
            )
    finally:
        socket.getaddrinfo = original_getaddrinfo