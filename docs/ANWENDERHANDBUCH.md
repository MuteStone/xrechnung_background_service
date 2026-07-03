# XRechnung-Hintergrunddienst — Anwenderhandbuch

Dieses Handbuch richtet sich an **Anwender und Administratoren**, die den Dienst
installieren, konfigurieren und im Alltag betreiben. Für die technische
Weiterentwicklung siehe [ENTWICKLERHANDBUCH.md](ENTWICKLERHANDBUCH.md).

**Repository:** https://github.com/MuteStone/xrechnung_background_service ·
**Branch:** [`exe`](https://github.com/MuteStone/xrechnung_background_service/tree/exe)

> Stand: Übergabe zum Praktikumsende. Ergänzt die vorhandene `README.md` um die
> neuen Funktionen **PDF-Einbettung** und **KoSIT-Validierung**.

---

## 1. Was macht die Software?

Der Dienst überwacht einen Ordner, in den die Kundenverwaltung Rechnungs-PDFs
exportiert. Für jede neue PDF:

1. liest er die Rechnungsnummer aus,
2. lädt die vollständigen Rechnungsdaten aus der MySQL-Datenbank,
3. erzeugt daraus eine gültige **XRechnung-XML** (EN 16931, CII-Format, XRechnung 3.0.2),
4. **bettet die Original-PDF in die XML ein** (damit der Empfänger sie erhält),
5. prüft die XML gegen das **XSD-Schema** und die **KoSIT-Geschäftsregeln**,
6. versendet die XML per E-Mail an das OZG-RE-Portal (oder eine andere Eingangsadresse),
7. verschiebt die PDF nach `processed/` (Erfolg) oder `error/` (Fehler).

**Zentrales Prinzip:** Es wird entweder eine **vollständige, geprüfte** Rechnung
versendet — oder **gar nichts**. Schlägt eine Prüfung fehl, landet die Rechnung in
`error/` und wird **nicht** verschickt.

---

## 2. Die drei Komponenten

| Programm | Zweck |
|---|---|
| **XRechnung-Setup.exe** | Einrichtungsassistent. Führt durch die Erstkonfiguration, schreibt die `.env` und legt Dienst + Monitor + Validierungswerkzeuge (`kosit/`) ins Installationsverzeichnis. |
| **XRechnung-Dienst.exe** | Der eigentliche Hintergrunddienst. Verarbeitet PDFs (Konsolenfenster). Für Automatisierung per Task Scheduler. |
| **XRechnung-Monitor.exe** | Grafische Oberfläche. Zeigt Verarbeitungsstatus, Logs und Export-Jobs und stößt die Verarbeitung an. Kein Konsolenfenster. |

Die Setup.exe enthält alle anderen Bestandteile eingebettet — es genügt, sie zu
verteilen. **Auf dem Zielrechner ist kein vorinstalliertes Java und kein Python nötig.**

---

## 3. Installation

### 3.1 Standardfall: mit Installationsrechten

1. `XRechnung-Setup.exe` **als Administrator** ausführen.
2. Assistenten durchlaufen (Datenbank, SMTP, OZG-RE-Adresse, Ordner, Verkäuferdaten).
3. Der Assistent legt im gewählten Installationsordner ab:
   - `XRechnung-Dienst.exe`, `XRechnung-Monitor.exe`
   - `kosit/` (Java-Laufzeit + KoSIT-Validator + XRechnung-Szenario)
   - `.env` (die Konfiguration)
4. Optional richtet er einen Windows-Task-Scheduler-Eintrag ein.

### 3.2 Server ohne Installationsrechte (nur Datenzugriff)

Weil die Programme **portabel** sind (sie suchen `.env` und `kosit/` immer neben
sich), lässt sich der Dienst ohne Installer betreiben:

1. Lokal (mit Adminrechten) per Setup.exe installieren — oder den Ordner manuell
   zusammenstellen.
2. **Den kompletten Ordner** auf den Server kopieren. Er muss enthalten:

   ```
   <Zielordner>\
     ├─ XRechnung-Monitor.exe      (und/oder XRechnung-Dienst.exe)
     ├─ kosit\                     ← MUSS mitkopiert werden
     └─ .env                       ← für den Server angepasst (s. u.)
   ```

3. Auf dem Server die `.env` an die dortigen Pfade anpassen (Abschnitt 4).
4. Programm starten (Monitor per Doppelklick, Dienst per Task Scheduler).

> **Wichtig:** Fehlt der Ordner `kosit/`, kann die KoSIT-Prüfung nicht laufen.
> Bei `KOSIT_VALIDATION=true` (Standard) wird dann **jede** Rechnung abgebrochen
> (Schutz vor ungeprüftem Versand).

### 3.3 Produktivumgebung (Netzlaufwerk P:)

Der produktive Ablageort ist `P:\Kundenverwaltung\XRechnung Automatisierung`. Dort
liegen `XRechnung-Dienst.exe`, `XRechnung-Monitor.exe`, `kosit\` und die produktive
`.env`.

- **Update (neue Programmversion):** nur die beiden **neu gebauten EXEs** dorthin
  kopieren. `kosit\` und `.env` bleiben unverändert.
- **Erstinstallation:** `XRechnung-Setup.exe` **lokal mit Administratorrechten**
  ausführen (auf dem Netzlaufwerk nicht möglich), danach den installierten Ordner
  nach P: kopieren.

> ⚠️ **Achtung `.env`:** Das Setup erkennt keine bestehende Installation und beginnt
> mit **leeren Feldern**. Beim Update daher **nur die EXEs** kopieren und die
> vorhandene Produktiv-`.env` **nicht** überschreiben (im Zweifel vorher sichern).

---

## 4. Konfiguration (`.env`)

Die `.env` liegt **neben der EXE**. Alle Einstellungen:

### Datenbank
| Schlüssel | Bedeutung |
|---|---|
| `DB_HOST`, `DB_PORT` | MySQL-Server (muss **vom Dienst-Rechner aus** erreichbar sein) |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Zugangsdaten (empfohlen: eigener Benutzer mit Leserechten) |

### Pfade
| Schlüssel | Bedeutung |
|---|---|
| `WATCH_FOLDER` | Ordner, in den die Kundenverwaltung die Rechnungs-PDFs legt |
| `PROCESSED_FOLDER` | Ziel erfolgreich verarbeiteter PDFs (+ erzeugte XML je Rechnung) |
| `ERROR_FOLDER` | Ziel fehlgeschlagener PDFs |
| `LOG_FILE` | Pfad der Protokolldatei |

> Alle Pfade müssen auf dem jeweiligen Rechner **existieren und beschreibbar** sein.

### E-Mail / OZG-RE
| Schlüssel | Bedeutung |
|---|---|
| `SMTP_HOST`, `SMTP_PORT` | Postausgangsserver |
| `SMTP_USER`, `SMTP_PASSWORD` | Zugangsdaten (leer lassen, wenn der Server ohne Login annimmt) |
| `SMTP_FROM`, `SMTP_FROM_NAME` | Absenderadresse und -name |
| `OZG_RE_EMAIL` | **Empfängeradresse** (OZG-RE-Postfach oder andere Eingangsadresse) |
| `OZG_RE_SUBJECT` | Betreff der Versand-E-Mail |

### Verkäuferdaten (Absender der Rechnung)
`SELLER_NAME`, `SELLER_STREET`, `SELLER_ZIP`, `SELLER_CITY`, `SELLER_VAT_ID`,
`SELLER_IBAN`, `SELLER_BIC`, `SELLER_EMAIL`, **`SELLER_PHONE`**

> ⚠️ **`SELLER_PHONE` ist Pflicht** (XRechnung-Regel BR-DE-6). Fehlt die
> Telefonnummer, lehnt die KoSIT-Prüfung **jede** Rechnung ab. Ebenso müssen
> Verkäufer-Name und -E-Mail gesetzt sein (BR-DE-5/7). Diese Felder dienen als
> Fallback, wenn die Datenbank keine Verkäuferdaten liefert.

### Prüfung & Verhalten
| Schlüssel | Bedeutung | Standard |
|---|---|---|
| `KOSIT_VALIDATION` | KoSIT-Geschäftsregelprüfung vor dem Versand (`true`/`false`) | `true` |
| `SCAN_JSON` | Zusätzlich `*.json`-Dateien verarbeiten | `false` |
| `REPORT_EMAIL` | Adresse für die Protokoll-Mail nach jedem Lauf (leer = keine) | leer |
| `REPORT_ATTACH_XML` | Erzeugte XMLs an die Protokoll-Mail anhängen | `false` |

### Logging
`LOG_LEVEL` (`DEBUG`/`INFO`/`WARNING`/`ERROR`), `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`.

---

## 5. Täglicher Betrieb

### Auslösen der Verarbeitung
- **Manuell:** `XRechnung-Monitor.exe` starten → die Oberfläche zeigt Status und Logs.
- **Automatisch:** Windows Task Scheduler startet `XRechnung-Dienst.exe` (bzw. den
  Monitor) zeitgesteuert. Der Dienst verarbeitet dann alle vorliegenden PDFs und
  beendet sich wieder (einmaliger Durchlauf).

### Ablauf pro Rechnung (vereinfacht)
```
PDF im Watch-Ordner
   → Rechnungsnummer lesen → Daten aus DB laden
   → XRechnung-XML erzeugen + PDF einbetten
   → XSD-Prüfung → KoSIT-Prüfung
   → [bestanden] E-Mail an OZG-RE  → PDF nach processed/
   → [abgelehnt] KEIN Versand      → PDF nach error/
```

---

## 6. Fehlerbehandlung

Landet eine Rechnung in `error/`, steht der **Grund im Protokoll** (`LOG_FILE`)
und in der Protokoll-Mail (falls `REPORT_EMAIL` gesetzt). Typische Meldungen:

| Meldung im Log | Bedeutung / Abhilfe |
|---|---|
| `KoSIT-Validierung abgebrochen … [BR-DE-6] …` | Pflichtfeld fehlt (hier: Verkäufer-Telefon). Verkäuferdaten vervollständigen. |
| `KoSIT-Validierung abgebrochen … [BR-…]` | Ein anderer Geschäftsregelverstoß. Der Code (z. B. BR-CO-25) benennt das fehlende/falsche Feld. |
| `XRechnungs-Datei zu groß für OZG-RE-Versand` | Die eingebettete PDF ist zu groß (Gesamt-XML > 10 MB). PDF verkleinern. |
| `Rechnungs-PDF nicht gefunden …` | Die Quell-PDF war beim Einbetten nicht lesbar. |
| `Keine Rechnungspositionen gefunden …` | Zur Rechnungsnummer wurden in der DB keine Positionen gefunden. Rechnungsnummer/DB prüfen. |
| `KoSIT-Werkzeuge fehlen: …` | Der Ordner `kosit/` fehlt oder ist unvollständig. Neben die EXE kopieren. |
| `Datenbankverbindung fehlgeschlagen` | DB-Zugangsdaten/Erreichbarkeit prüfen. |
| `E-Mail-Versand fehlgeschlagen` | SMTP-Zugangsdaten/Erreichbarkeit prüfen. |

**Korrektur:** Ursache beheben, dann die PDF aus `error/` zurück in den
`WATCH_FOLDER` legen — beim nächsten Lauf wird sie erneut verarbeitet.

### Automatische Korrekturen

Einige typische Konfigurations-/Datenfehler fängt der Dienst selbst ab:

- **Leerzeichen in der Leitweg-ID** werden automatisch entfernt. Das ist wichtig,
  weil das OZG-RE-Portal eine Leitweg-ID mit Leerzeichen sonst nicht erkennt.
- **`LOG_FILE` zeigt versehentlich auf einen Ordner** statt auf eine Datei: Der
  Dienst hängt dann automatisch den Standard-Dateinamen an, statt beim Start
  abzubrechen.
- **DB-Host nicht erreichbar:** Der Verbindungsversuch bricht nach 10 Sekunden mit
  einer Fehlermeldung ab, statt endlos zu hängen.

---

## 7. Kommt die PDF beim Empfänger an?

Ja — die Original-PDF wird **in die XRechnung-XML eingebettet** (Standardfeld
BT-125). Das ist der einzige vom OZG-RE-Portal unterstützte Weg: Ein *separater*
E-Mail-Anhang würde vom Portal **verworfen**. Deshalb enthält die Versand-E-Mail
bewusst **nur die XML** (mit der PDF darin) und keinen zweiten Anhang.

Grenzen (laut OZG-RE-Leitfaden): Beim E-Mail-Versand darf die XRechnungs-Datei
**10 MB** nicht überschreiten. Da die eingebettete PDF um ca. 33 % „aufgebläht"
wird, sollte die PDF selbst **~7 MB** nicht überschreiten.

---

## 8. Erster Echtversand — Empfehlung

1. Eine echte Rechnung verarbeiten (ohne Dry-Run).
2. Im Log auf `KoSIT-Validierung bestanden` und die Versandzeile achten.
3. Im OZG-RE-Portal / beim Empfänger kontrollieren, dass **XML und PDF** ankommen.

Für einen gefahrlosen Test ohne Versand siehe Dry-Run im
[ENTWICKLERHANDBUCH.md](ENTWICKLERHANDBUCH.md) (`--dry-run`).
