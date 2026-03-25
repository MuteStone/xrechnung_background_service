"""
Transmitter — XRechnung per E-Mail an OZG-RE übertragen
=========================================================
SMTP via Gmail (App-Passwort, STARTTLS, IPv4 erzwungen).
"""

import logging
import smtplib
import socket
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger("xrechnung.transmitter")


def transmit(xml_path: Path, config: dict) -> bool:
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


def _build_email(xml_path: Path, config: dict):
    """Baut die E-Mail mit XML-Anhang zusammen."""
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"]    = f"{config['SMTP_FROM_NAME']} <{config['SMTP_FROM']}>"
    msg["To"]      = config["OZG_RE_EMAIL"]
    msg["Subject"] = config["OZG_RE_SUBJECT"]

    with open(xml_path, "rb") as f:
        xml_data = f.read()

    msg.add_attachment(
        xml_data,
        maintype="application",
        subtype="xml",
        filename=xml_path.name,
    )

    return msg


def _send(msg, config: dict) -> None:
    """Sendet die E-Mail via SMTP (STARTTLS, IPv4 erzwungen)."""
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
            with open("debug_email.eml", "w") as f:
                f.write(msg.as_string())
            smtp.send_message(msg)
    finally:
        socket.getaddrinfo = original_getaddrinfo