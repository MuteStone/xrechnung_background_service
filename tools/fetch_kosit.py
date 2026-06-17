"""
Beschaffung der KoSIT-Validierungswerkzeuge (Build-Schritt, einmalig je Version)
================================================================================
Legt den Ordner ``kosit/`` im Projektstamm an, den der Dienst zur Laufzeit nutzt
und den die Setup.exe mitbündelt:

    kosit/
      jre/                      ← getrimmte Java-Laufzeit (per jlink)
      validator/<tool>.jar      ← KoSIT validationtool (standalone)
      scenario/scenarios.xml    ← XRechnung-Konfiguration inкл. resources/

Voraussetzungen auf dem BUILD-Rechner:
  * Internetzugang (GitHub-Releases)
  * Ein JDK mit ``jlink`` und ``jmods`` (JDK 11+). Wird über --jdk, $JAVA_HOME
    oder das im PATH gefundene jlink ermittelt.

Aufruf:
    python tools/fetch_kosit.py                 # neueste Releases automatisch
    python tools/fetch_kosit.py --jdk "C:/Program Files/Java/jdk-17"
    python tools/fetch_kosit.py --skip-jre      # nur Validator+Szenario (System-Java)

Dies ist ein Entwickler-/Build-Werkzeug — es wird NICHT in die EXE eingebunden.
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KOSIT_DIR = PROJECT_ROOT / "kosit"

VALIDATOR_REPO = "itplr-kosit/validator"
CONFIG_REPO = "itplr-kosit/validator-configuration-xrechnung"

# jlink-Modulsatz: java.se als Aggregator ist großzügig, aber sicher (keine
# ClassNotFound-Überraschungen zur Laufzeit). Bei Bedarf später per jdeps slimmen.
JLINK_MODULES = "java.se"


def log(msg: str) -> None:
    print(f"[fetch_kosit] {msg}", flush=True)


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fetch_kosit"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _latest_release(repo: str) -> dict:
    """Neuestes (nicht-Draft) Release inkl. Assets über die GitHub-API."""
    data = json.loads(_http_get(f"https://api.github.com/repos/{repo}/releases"))
    for rel in data:
        if not rel.get("draft"):
            return rel
    raise RuntimeError(f"Kein Release gefunden für {repo}")


def _pick_asset(release: dict, *patterns: str) -> dict:
    """Erstes Asset, dessen Name auf eines der Regex-Muster passt."""
    assets = release.get("assets", [])
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for a in assets:
            if rx.search(a["name"]):
                return a
    names = ", ".join(a["name"] for a in assets) or "(keine)"
    raise RuntimeError(
        f"Kein passendes Asset in Release {release.get('tag_name')}. "
        f"Muster={patterns} | vorhanden: {names}"
    )


def _download_to(url: str, dest: Path) -> None:
    log(f"Lade {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_http_get(url))


def fetch_validator_jar(dst_dir: Path) -> None:
    """validationtool-*-standalone.jar beschaffen (ggf. aus distribution.zip)."""
    rel = _latest_release(VALIDATOR_REPO)
    log(f"Validator-Release: {rel.get('tag_name')}")
    dst_dir.mkdir(parents=True, exist_ok=True)

    # Direktes Standalone-JAR bevorzugen, sonst Distribution-ZIP entpacken.
    try:
        asset = _pick_asset(rel, r"standalone.*\.jar$")
        _download_to(asset["browser_download_url"], dst_dir / asset["name"])
        log(f"Validator-JAR: {asset['name']}")
        return
    except RuntimeError:
        pass

    asset = _pick_asset(rel, r"distribution.*\.zip$", r"\.zip$")
    log(f"Entpacke Distribution-ZIP: {asset['name']}")
    zf = zipfile.ZipFile(io.BytesIO(_http_get(asset["browser_download_url"])))
    jar_name = next(
        (n for n in zf.namelist() if re.search(r"standalone.*\.jar$", n, re.I)),
        None,
    ) or next((n for n in zf.namelist() if n.lower().endswith(".jar")), None)
    if not jar_name:
        raise RuntimeError("Keine .jar im Validator-Distribution-ZIP gefunden.")
    (dst_dir / Path(jar_name).name).write_bytes(zf.read(jar_name))
    log(f"Validator-JAR: {Path(jar_name).name}")


def fetch_scenario(dst_dir: Path) -> None:
    """XRechnung-Konfiguration (scenarios.xml + resources/) beschaffen."""
    rel = _latest_release(CONFIG_REPO)
    log(f"Konfig-Release: {rel.get('tag_name')}")
    asset = _pick_asset(rel, r"validator-configuration.*\.zip$", r"\.zip$")
    log(f"Entpacke Konfiguration: {asset['name']}")

    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    zf = zipfile.ZipFile(io.BytesIO(_http_get(asset["browser_download_url"])))
    # scenarios.xml liegt evtl. in einem Unterordner — Top-Level ermitteln.
    sc = next((n for n in zf.namelist() if n.endswith("scenarios.xml")), None)
    if not sc:
        raise RuntimeError("scenarios.xml nicht im Konfigurations-ZIP gefunden.")
    prefix = sc[: sc.rfind("scenarios.xml")]  # z. B. "xrechnung-3.0.2/.../"

    for name in zf.namelist():
        if name.endswith("/"):
            continue
        if prefix and not name.startswith(prefix):
            continue
        rel_name = name[len(prefix):] if prefix else name
        target = dst_dir / rel_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zf.read(name))

    if not (dst_dir / "scenarios.xml").exists():
        raise RuntimeError("scenarios.xml landete nicht im Zielordner.")
    log("Szenario entpackt.")


def _resolve_jlink(jdk: str | None) -> tuple[Path, Path]:
    """Gibt (jlink-Pfad, jmods-Verzeichnis) zurück."""
    exe = "jlink.exe" if sys.platform.startswith("win") else "jlink"

    candidates: list[Path] = []
    if jdk:
        candidates.append(Path(jdk) / "bin" / exe)
    if os.environ.get("JAVA_HOME"):
        candidates.append(Path(os.environ["JAVA_HOME"]) / "bin" / exe)
    found = shutil.which("jlink")
    if found:
        candidates.append(Path(found))

    for jl in candidates:
        if jl.exists():
            jmods = jl.parent.parent / "jmods"
            if jmods.is_dir():
                return jl, jmods
            log(f"WARN: jmods fehlt neben {jl} — übersprungen")

    raise RuntimeError(
        "Kein JDK mit jlink+jmods gefunden. Bitte --jdk <Pfad-zum-JDK> angeben "
        "(JDK 11+, enthält bin/jlink und jmods/)."
    )


def build_jre(dst_dir: Path, jdk: str | None) -> None:
    jlink, jmods = _resolve_jlink(jdk)
    log(f"Baue JRE mit {jlink} (Module: {JLINK_MODULES})")
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    cmd = [
        str(jlink),
        "--module-path", str(jmods),
        "--add-modules", JLINK_MODULES,
        "--strip-debug", "--no-header-files", "--no-man-pages",
        "--compress=2",
        "--output", str(dst_dir),
    ]
    subprocess.run(cmd, check=True)
    log("JRE gebaut.")


def main() -> int:
    ap = argparse.ArgumentParser(description="KoSIT-Validierungswerkzeuge beschaffen")
    ap.add_argument("--jdk", help="Pfad zu einem JDK (mit bin/jlink und jmods/)")
    ap.add_argument("--skip-jre", action="store_true", help="JRE nicht bauen (System-Java nutzen)")
    args = ap.parse_args()

    log(f"Zielordner: {KOSIT_DIR}")
    try:
        fetch_validator_jar(KOSIT_DIR / "validator")
        fetch_scenario(KOSIT_DIR / "scenario")
        if args.skip_jre:
            log("JRE übersprungen (--skip-jre).")
        else:
            build_jre(KOSIT_DIR / "jre", args.jdk)
    except Exception as e:
        log(f"FEHLER: {e}")
        return 1

    log("Fertig. kosit/ ist bereit zum Bündeln (XRechnung-Setup.spec).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
