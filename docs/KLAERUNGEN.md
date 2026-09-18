# EarthX — Klärungen und Auslegungsregeln

Stand: 2026-09-18. Anlass: Die erste Kontrollrunde im neuen Chat-Projekt hat 17 Unklarheiten und Widersprüche in den Plandokumenten gefunden. Diese Datei löst sie auf.

**Rang:** Bei Widerspruch gilt diese Datei vor `architekturplan.md`, `projektplan.md`, `projektuebersicht.md` und den Übergabedateien. Die sieben Hard Constraints in `ADDING\_ESA\_DATASETS.md` stehen über allem.

**Status je Punkt:** *Festgelegt* = Korrektur eines Fehlers in den Dokumenten. *Vorschlag* = fachliche Auflösung durch Claude, gilt bis Otto widerspricht. *Otto* = Entscheidung steht aus und blockiert den genannten Schritt.

\---

## A. Entscheidungen, die bei Otto liegen

|#|Frage|Blockiert|Empfehlung|
|-|-|-|-|
|A1|Wortlaut von Hard Constraint 7 bestätigen oder korrigieren (in `ADDING\_ESA\_DATASETS.md` nur rekonstruiert)|Hard-Constraint-Tests in M0|Vorgeschlagener Wortlaut steht in der Datei; einmal lesen und bestätigen|
|A2|Repo öffentlich oder privat|GitHub-Einstellungen, Fixtures, Bug-Report-Issues|**Privat**, bis bewusst anders entschieden: Bug-Reports können personenbezogene Daten berühren, Fixtures sind lizenzrechtlich ungeklärt, Geschäftsmodell ist offen. Hinweis: Branch-Schutz für private Repos setzt bei GitHub nach aktuellem Kenntnisstand ein bezahltes Konto voraus; für Studierende ist GitHub Pro über das Education-Programm kostenlos. Vor M0 prüfen.|
|A3|Neues Monorepo oder `biomass-viewer` weiterführen|alle Pfade, CODEOWNERS|**Geändert gegenüber dem Projektplan: bestehendes Repo weiterführen und in `earthx` umbenennen.** Begründung: Hard Constraints 3 und 4 schützen Pfade, Defaults und Signaturen; der Prototyp muss lauffähig bleiben. Ein neues Repo bringt dafür nur Risiko. GitHub leitet alte URLs nach Umbenennung weiter.|
|A4|Wer zeichnet BIOMASS-Fixtures auf, und was darf ins Repo|Vertragstests in M0|Siehe B2: Otto zeichnet lokal auf; ins Repo kommen nur Metadaten-Antworten und Prüfsummen, keine BIOMASS-Pixel|

\---

## B. Auflösungen

### B1. Zustands-Audit: M0 oder M1? — *Festgelegt*

Der Audit selbst (Bericht, ADR-Entwurf, Stufe C) gehört zu **M0**. Die Entscheidung darüber und die Umsetzung der Konsequenzen gehören zu **M1**. Die M1-Tabelle im Projektplan meint "Konsequenzen aus dem Audit umsetzen".

### B2. "Identische Antworten" ohne Token prüfen — *Vorschlag*

Drei getrennte Testarten:

|Art|Was|Wo|Daten|
|-|-|-|-|
|Vertragstests|Form, Felder, Typen, Statuscodes aller Endpunkte aus Regel 1; Signaturen aus Regel 4|CI und Cloud-Sitzung|bereinigte, lokal aufgezeichnete JSON-Antworten von `/api/config`, `/api/search`, `/api/coverage` (reine Metadaten, klein)|
|Rechen-Tests|`decomp.py`, Stitching, Tile-Rendering rechnen korrekt und unverändert|CI und Cloud-Sitzung|**synthetische** Mini-Fixtures (per Skript erzeugtes kleines komplexes Quad-Pol-COG), keine echten BIOMASS-Pixel|
|Golden-Test BIOMASS|`/tiles`, `/decompose`, `/stitch`, `/download` liefern gegen echte Daten dasselbe wie vor der Änderung|**nur lokal bei Otto**, mit Token|verglichen werden Prüfsummen und Kennzahlen der Ausgaben; ins Repo kommen nur diese Referenzwerte|

Der Golden-Test ist ein Skript, das Otto vor dem Merge von Änderungen an BIOMASS-nahen Pfaden lokal ausführt; CODEOWNERS erzwingt für diese Pfade ohnehin sein Review. Ob echte BIOMASS-Ausschnitte überhaupt ins Repo dürften, ist lizenzrechtlich ungeklärt und wird mit diesem Vorgehen nicht benötigt.

### B3. Dateinamen und Ablage — *Festgelegt*

Es gibt genau einen Satz Namen, im Repo unter `docs/` und identisch im Projektwissen des Chats: `UEBERGABE.md` bzw. `UEBERGABE\_CHAT.md`, `projektplan.md`, `architekturplan.md`, `projektuebersicht.md`, `ADDING\_ESA\_DATASETS.md`, `KLAERUNGEN.md`, `ENTSCHEIDUNGSLOG.md`. Die Dateien mit Präfix `EarthX\_` sind dieselben Dokumente unter ihrem Download-Namen und werden nicht mehr verwendet. `UEBERGABE\_CHAT.md` gehört nur ins Projektwissen, nicht ins Repo.

### B4. ENTSCHEIDUNGSLOG und ADRs — *Festgelegt*

ADRs unter `docs/adr/` sind die maßgebliche Begründung für Architekturentscheidungen. `docs/ENTSCHEIDUNGSLOG.md` ist das chronologische Verzeichnis **aller** Entscheidungen (auch Scope, Geschäft, Recht): eine Zeile pro Entscheidung mit Datum, Kurzfassung, betroffenen Dokumenten und Verweis auf das ADR, falls es eines gibt. Es ersetzt keine ADRs.

### B5. Übergabe-Widerspruch "kein Repo" — *Festgelegt*

Es gibt ein Repo, und die Umsetzung läuft dort über Claude Code. Der Chat ist der Planungsraum daneben. Der Satz "kein Repo als gemeinsame Ablage" in der Chat-Übergabe ist gestrichen.

### B6. `decomp.py` und `stac.py` verschieben? — *Vorschlag*

**Nein, vorerst nicht.** Hard Constraint 4 verbietet Umbenennungen öffentlicher Funktionen; ein neuer Importpfad ist faktisch eine. Die Module aus Architekturplan 3.1 sind zunächst **logische** Module: Die Importprüfung ordnet bestehende Dateien per Pfadliste einem Modul zu (`decomp.py` → `datasets/biomass`, `stac.py` → `adapters`, `cog.py` → `readers`), ohne sie zu bewegen. Neuer Code entsteht in der Zielstruktur. Ein physisches Verschieben bestehender Dateien ist später nur mit Re-Export am alten Ort und nur mit Ottos Freigabe (Stufe B) erlaubt.

### B7. BIOMASS in pgstac — *Vorschlag*

* BIOMASS erscheint in pgstac ausschließlich als **Collection-Metadaten** (Beschreibung, Ausdehnung, Lizenz, Zugriffshinweis `token\_required`, `visibility: local`).
* pgstac liegt **nicht** im Anfragepfad von BIOMASS. Suche, Tiles, Download, Dekomposition laufen unverändert über `stac.search` und die bestehenden Routen (Hard Constraint 3).
* In jedem öffentlichen oder Cloud-Deployment wird BIOMASS nicht gelistet (`visibility: local`). Damit bleibt "nur token-freie Quellen" für die Plattform gewahrt und "BIOMASS bleibt lokales Einzelnutzer-Setup" ebenfalls.
* Zur Frage der anonymen Suche: Die Code-Inspektion vom 13.08.2026 ergab das Muster "offene STAC-Suche, token-gesicherter Pixelzugriff" für MAAP. Vor Verwendung erneut prüfen.

### B8. Was ist das Gateway technisch? — *Vorschlag*

Das Gateway ist **zwei Dinge in zwei Ausbaustufen**, weil GDAL und `pystac\_client` ihre HTTP-Zugriffe selbst ausführen:

1. **Bibliothek `gateway` (ab M1):** die einzige Stelle, die entscheidet, *ob* eine URL abgerufen werden darf (Host-Allowlist, Schema, Auflösung auf private Adressen, Limits pro Host), und die den HTTP-Client für eigene Requests stellt. Für Fremdbibliotheken gilt: Jede URL wird vor der Übergabe an rasterio/GDAL oder `pystac\_client` durch `gateway` geprüft; `gateway` setzt außerdem zentral die GDAL-Konfiguration (Timeouts, erlaubte Dateiendungen, Proxy) und die Sitzungsparameter für `pystac\_client`. Der bestehende Weg, den Token über die GDAL-Umgebung zu setzen, bleibt für BIOMASS unverändert.
2. **Egress-Proxy bzw. Netzwerk-Policy (ab M6, Cloud):** die eigentliche Durchsetzung. GDAL und alle anderen Clients laufen über einen Proxy mit derselben Allowlist; direkte Verbindungen nach außen sind auf Netzwerkebene gesperrt. Das deckt auch Redirects ab, die eine Bibliothek selbst verfolgt.

Der M1-Test "kein Request außerhalb des Gateways" besteht deshalb aus: (a) statischer Regel, dass HTTP-Bibliotheken nur in `gateway` importiert werden; (b) Tests, dass jede an rasterio oder `pystac\_client` übergebene URL vorher `gateway` passiert hat. Die netzwerkseitige Prüfung kommt mit M6.

### B9. "Reine Funktion" trotz I/O; lokaler Runner — *Festgelegt (Begriff präzisiert)*

Gemeint ist: Der Worker-Kern ist **plattformunabhängig und zustandslos**. Er hat keinen Zugriff auf Plattformdienste (Datenbank, Queue, Objektspeicher, interne APIs) und hält keinen Zustand zwischen Aufrufen. Lesender Zugriff auf die **Datenquellen** ist erlaubt und nötig, und zwar über die Bibliothek `gateway`, die deshalb auch im lokalen Runner mitläuft. Die Allowlist ergibt sich dort aus den aufgelösten Asset-Adressen des Rezepts. "Umgeht das Fetch-Gateway" im Architekturplan 7.7 meint nur: Die Zugriffe kommen von der IP des Nutzers statt von der Plattform.

### B10. Hard Constraint 6 und generische Operatoren — *Vorschlag (Auslegung)*

Regel 6 richtet sich gegen Funktionen, die stillschweigend für alle Datensätze gelten. Generische Operatoren (Band-Math, Reprojektion) verletzen sie nicht, weil Capability-Flags **im Eintrag des jeweiligen Datensatzes** gesetzt werden: Jeder Datensatz schaltet jede Fähigkeit weiterhin ausdrücklich frei. Datensatzspezifische Funktionen (z. B. Dekomposition) bleiben zusätzlich an die Dataset-ID gebunden. Zu `coverage` in `features`: Das Flag bleibt aus Gründen der Rückwärtskompatibilität des BIOMASS-Eintrags bestehen; eine Registry-Prüfung (Test) verlangt es für **jeden** Eintrag, womit Regel 7 durchgesetzt ist.

### B11. Lizenzregel — *Vorschlag (ersetzt den Satz in Projektübersicht §5)*

Drei Stufen, gesteuert über die Lizenz-Flags:

|Stufe|Voraussetzung|Was die Plattform tut|
|-|-|-|
|Katalogeintrag|keine (Metadaten + Verweis)|Beschreibung, Coverage Map aus Footprints, Link bzw. Weiterleitung zum Download bei der Quelle|
|Anzeige (Tiles, Quicklooks über eigene Dienste)|Weitergabe erlaubt **und** Bearbeitung erlaubt|dynamische Tiles, Stretch, Reprojektion|
|Processing|wie Anzeige; bei `commercial\_use = false` nur im Gratis-Tier|Operatoren, Jobs, Datacube|

ND-Datensätze (keine Bearbeitung) sind damit **nur als Katalogeintrag mit Link** zulässig, solange keine Rechtsberatung etwas anderes ergibt, weil schon reprojizierte Tiles eine Bearbeitung sein können. NC bleibt zulässig.

### B12. Pflichten pro Datensatz — *Festgelegt*

Maßgeblich ist die Onboarding-Checkliste in `projektuebersicht.md` §5, ergänzt um Punkt 10: "Zuletzt erfolgreich geprüft" ist gesetzt und sichtbar. Die Kurzliste in der Übergabe ist nur eine Zusammenfassung.

### B13. Registry: Dataclass oder YAML? — *Vorschlag*

Gestuft, mit gleichbleibender Schnittstelle:

1. **M1 bis M4:** `DatasetConfig` als Python-Dataclass in `datasets.py`, wie in `ADDING\_ESA\_DATASETS.md` beschrieben.
2. **Ab M5 (Harvester, Git-Review):** Kuratierte Definitionen liegen als YAML unter `catalog/`; `datasets.py` wird zum Lader, der daraus dieselben `DatasetConfig`-Objekte erzeugt. Aufrufer merken nichts. Der BIOMASS-Eintrag behält exakt seine Werte (Test).
3. pgstac wird aus derselben Quelle befüllt; es gibt nie zwei gepflegte Wahrheiten.

### B14. Skills — *Später*

Die drei Skills (`atomic-commits`, `code-cleanup`, `readme-updater`) liegen derzeit nur in Ottos persönlicher Claude-Code-Umgebung. Otto kopiert sie in M0 nach `.claude/skills/` im Repo. Der Chat braucht ihren Inhalt nicht; er verweist nur auf sie.

\---

## C. Folgen für M0

Reihenfolge der ersten Schritte, angepasst:

1. Otto entscheidet A2 und A3, bestätigt A1.
2. Repo umbenennen (falls A3 so entschieden), Dokumente nach `docs/`, `CLAUDE.md`, Skills, Branch-Schutz, CODEOWNERS mit den **bestehenden** Pfaden (`backend/app/decomp.py` usw., siehe B6).
3. Otto zeichnet lokal die drei Metadaten-Antworten auf und bereinigt sie (B2).
4. Claude Code: Klärung der Cloud-VM; Vertragstests und Rechen-Tests mit synthetischen Fixtures; Golden-Test-Skript für Otto; Zustands-Audit als ADR-Entwurf; Bug-Report-Pipeline Stufe 1.

