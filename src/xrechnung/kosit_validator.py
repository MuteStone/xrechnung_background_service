"""
KoSIT-Validierung (XRechnung-Geschäftsregeln / Schematron)
==========================================================
Ruft den offiziellen KoSIT-Validator (Java) mit dem XRechnung-Szenario auf und
wertet den VARL-Report aus. Liefert ein eindeutiges accept/reject zurück.

Im Gegensatz zur reinen XSD-Prüfung ([validator.py]) deckt dies die normativen
Geschäftsregeln ab (BR-DE-*, EN 16931, CIUS/Extension XRechnung).

Bundling/Layout (neben der EXE bzw. im Projektstamm) — Ordner ``kosit/``:
    kosit/
      jre/                     ← getrimmte Java-Laufzeit (jre/bin/java(.exe))
      validator/<tool>.jar     ← validationtool-*-standalone.jar
      scenario/scenarios.xml   ← XRechnung-Konfiguration + resources/

Die eigentliche Beschaffung dieser Artefakte erledigt ``tools/fetch_kosit.py``.
"""

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple, Optional

from lxml import etree

logger = logging.getLogger("xrechnung.kosit")


class KositResult(NamedTuple):
    ok: bool                 # True nur wenn der Report eindeutig "accept" meldet
    available: bool          # True wenn die KoSIT-Werkzeuge gefunden wurden
    messages: list[str]      # Fehler-/Warnmeldungen aus dem Report (für Protokoll)
    detail: str = ""         # Kurztext für den Fehler-Report


def _kosit_dir() -> Path:
    """
    Verzeichnis mit den KoSIT-Artefakten.

    - Als EXE (frozen): neben der ausführbaren Datei (Wizard legt ``kosit/``
      ins Installationsverzeichnis, direkt neben Dienst/Monitor).
    - Im Entwicklungsbetrieb: ``kosit/`` im Projektstamm.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "kosit"
    return Path(__file__).resolve().parents[2] / "kosit"


def _find_java(base: Path) -> Optional[Path]:
    exe = "java.exe" if sys.platform.startswith("win") else "java"
    candidate = base / "jre" / "bin" / exe
    return candidate if candidate.exists() else None


def _find_jar(base: Path) -> Optional[Path]:
    vdir = base / "validator"
    if not vdir.is_dir():
        return None
    # Bevorzugt das Standalone-Tool, sonst die erste .jar
    jars = sorted(vdir.glob("*standalone*.jar")) or sorted(vdir.glob("*.jar"))
    return jars[0] if jars else None


def _find_scenarios(base: Path) -> Optional[Path]:
    candidate = base / "scenario" / "scenarios.xml"
    return candidate if candidate.exists() else None


def kosit_available() -> bool:
    """True, wenn Java-Laufzeit, Validator-JAR und Szenario vorhanden sind."""
    base = _kosit_dir()
    return bool(_find_java(base) and _find_jar(base) and _find_scenarios(base))


def _parse_report(report_path: Path) -> KositResult:
    """
    Wertet den VARL-Report versions-robust aus: gesucht wird per local-name nach
    einem ``reject``- bzw. ``accept``-Element. Eindeutiges ``accept`` → gültig.
    Alles andere (reject, fehlend, nicht parsebar) → ungültig (fail-closed).
    """
    try:
        tree = etree.parse(str(report_path))
    except Exception as e:
        return KositResult(False, True, [f"Report nicht lesbar: {e}"],
                           "KoSIT-Report konnte nicht ausgewertet werden.")

    root = tree.getroot()

    def _localnames(name: str):
        return root.iter("{*}" + name)

    rejected = any(True for _ in _localnames("reject"))
    accepted = any(True for _ in _localnames("accept"))

    # Fehler-/Warnmeldungen einsammeln (für das Protokoll)
    messages: list[str] = []
    for msg in _localnames("message"):
        level = (msg.get("level") or "").strip()
        text = " ".join((msg.text or "").split())
        if text and level.lower() in ("error", "fatal", ""):
            messages.append(f"[{level or 'error'}] {text}")

    if rejected or not accepted:
        n = len(messages)
        detail = (
            f"KoSIT-Validierung fehlgeschlagen ({n} Fehler)."
            if n else "KoSIT-Validierung: Dokument abgelehnt."
        )
        return KositResult(False, True, messages, detail)

    return KositResult(True, True, messages, "KoSIT-Validierung bestanden.")


def validate_kosit(xml_path: Path, timeout: int = 120) -> KositResult:
    """
    Validiert eine XRechnung-XML mit dem KoSIT-Validator.

    Returns:
        KositResult. ``available=False`` wenn die Werkzeuge fehlen — der Aufrufer
        entscheidet dann (bei aktivierter Prüfung: harter Abbruch / fail-closed).
    """
    base = _kosit_dir()
    java = _find_java(base)
    jar = _find_jar(base)
    scenarios = _find_scenarios(base)

    if not (java and jar and scenarios):
        fehlend = ", ".join(
            n for n, v in (("JRE", java), ("Validator-JAR", jar), ("Szenario", scenarios)) if not v
        )
        logger.error("KoSIT-Werkzeuge unvollständig (fehlt: %s) in %s", fehlend, base)
        return KositResult(False, False, [], f"KoSIT-Werkzeuge fehlen: {fehlend}")

    repository = scenarios.parent
    out_dir = Path(tempfile.mkdtemp(prefix="kosit_"))
    try:
        cmd = [
            str(java), "-jar", str(jar),
            "-r", str(repository),
            "-s", str(scenarios),
            "-o", str(out_dir),
            str(xml_path),
        ]
        logger.debug("KoSIT-Aufruf: %s", " ".join(cmd))
        # WICHTIG: leere Pipe als stdin (input="").
        # Der Validator prüft via System.in.available(), ob Daten gepiped werden.
        # Ohne stdin bzw. mit der Windows-NUL-Gerätedatei wirft available0() eine
        # "IOException: Unzulässige Funktion" und es entsteht kein Report. Eine
        # echte (leere) Pipe liefert sauber 0 → der Validator nutzt das Datei-Argument.
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            input="",
        )

        report = out_dir / f"{xml_path.stem}-report.xml"
        if not report.exists():
            # Report fehlt → Aufruf fehlgeschlagen (fail-closed)
            stderr = (proc.stderr or "").strip()[-500:]
            logger.error("KoSIT-Report nicht erzeugt (rc=%s): %s", proc.returncode, stderr)
            return KositResult(
                False, True, [stderr] if stderr else [],
                "KoSIT-Validator lieferte keinen Report.",
            )

        result = _parse_report(report)
        if result.ok:
            logger.info("KoSIT-Validierung bestanden: %s", xml_path.name)
        else:
            logger.warning("KoSIT-Validierung abgelehnt: %s — %s", xml_path.name, result.detail)
            for m in result.messages[:20]:
                logger.warning("  KoSIT: %s", m)
        return result

    except subprocess.TimeoutExpired:
        logger.error("KoSIT-Validierung Zeitüberschreitung: %s", xml_path.name)
        return KositResult(False, True, [], "KoSIT-Validierung: Zeitüberschreitung.")
    except Exception as e:
        logger.exception("KoSIT-Validierung Fehler: %s", e)
        return KositResult(False, True, [str(e)], f"KoSIT-Validierung Fehler: {e}")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
