# EarthX — Klärungen und Auslegungsregeln

Stand: 2026-09-18, überarbeitet nach den Entscheidungen vom 18.09.2026. Anlass der Ursprungsfassung: Die erste Kontrollrunde im neuen Chat-Projekt hat 17 Unklarheiten und Widersprüche in den Plandokumenten gefunden. Diese Datei löst sie auf.

**Rang:** `ENTSCHEIDUNGEN_2026-09-18.md` geht allen Dokumenten vor, auch dieser Datei. Danach gilt diese Datei vor `architekturplan.md`, `projektplan.md`, `projektuebersicht.md` und den Übergabedateien. Die sieben Hard Constraints in `ADDING_ESA_DATASETS.md` sind **aufgehoben**; die Datei gilt nur noch als Beschreibung des Code-Stands vom 13.08.2026.

**Status je Punkt:** *Festgelegt* = Korrektur eines Fehlers in den Dokumenten. *Vorschlag* = fachliche Auflösung durch Claude, gilt bis Otto widerspricht. *Aufgehoben* = gilt nicht mehr; die Überschrift bleibt als Historie stehen und nennt, was sie ersetzt.

---

## A. Entscheidungen, die bei Otto lagen — alle entschieden

| # | Frage | Ergebnis |
|---|---|---|
| A1 | Wortlaut von Hard Constraint 7 bestätigen | **Aufgehoben.** Die Hard Constraints sind als verbindliche Regeln gestrichen (ENTSCHEIDUNGEN §1); der Wortlaut wird nicht mehr gebraucht. |
| A2 | Repo öffentlich oder privat | **Entschieden: öffentlich**, und bleibt es vorerst (ENTSCHEIDUNGEN §4). Folgen siehe unten, Abschnitt D. |
| A3 | Neues Monorepo oder `biomass-viewer` weiterführen | **Entschieden: bestehendes Repo weiterführen, umbenannt in `earthX`**; kein neues Monorepo (ENTSCHEIDUNGEN §4). |
| A4 | Wer zeichnet BIOMASS-Fixtures auf, und was darf ins Repo | **Aufgehoben.** Es werden keine BIOMASS-Antworten aufgezeichnet. Fixtures sind synthetisch oder eindeutig offen lizenziert; BIOMASS kommt in CI, Cloud-Sitzungen und Fixtures nicht vor (ENTSCHEIDUNGEN §3, §4). |

Offen bleiben stattdessen: die Code-Lizenz für das öffentliche Repo, der erste token-freie Datensatz und eine token-freie Quelle für komplexe Quad-Pol-Daten. Sie stehen im Entscheidungslog.

---

## B. Auflösungen

### B1. Zustands-Audit: M0 oder M1? — *Festgelegt*

Der Audit selbst (Bericht, ADR-Entwurf, Stufe C) gehört zu **M0**. Die Entscheidung darüber und die Umsetzung der Konsequenzen gehören zu **M1**. Die M1-Tabelle im Projektplan meint "Konsequenzen aus dem Audit umsetzen".

### B2. "Identische Antworten" ohne Token prüfen — *Aufgehoben*

Ersetzt durch ENTSCHEIDUNGEN §1 und §3: Es wird kein Aufwand betrieben, das BIOMASS-Verhalten zu erhalten. Vertragstests gegen aufgezeichnete BIOMASS-Antworten und der Golden-Test mit Token entfallen.

Was bleibt, gilt jetzt allgemein für jeden token-freien Datensatz:

| Art | Was | Wo | Daten |
|---|---|---|---|
| Vertragstests | Form, Felder, Typen, Statuscodes der eigenen Endpunkte | CI und Cloud-Sitzung | aufgezeichnete Antworten **token-freier** Quellen, klein und bereinigt |
| Rechen-Tests | Dekomposition, Stitching, Tile-Rendering rechnen korrekt und unverändert | CI und Cloud-Sitzung | **synthetische** Mini-Fixtures (per Skript erzeugt) |

### B3. Dateinamen und Ablage — *Festgelegt*

Es gibt genau einen Satz Namen, im Repo unter `docs/` und identisch im Projektwissen des Chats: `UEBERGABE.md` bzw. `UEBERGABE_CHAT.md`, `projektplan.md`, `architekturplan.md`, `projektuebersicht.md`, `ADDING_ESA_DATASETS.md`, `KLAERUNGEN.md`, `ENTSCHEIDUNGSLOG.md`, `ENTSCHEIDUNGEN_2026-09-18.md`. Die Dateien mit Präfix `EarthX_` sind dieselben Dokumente unter ihrem Download-Namen und werden nicht mehr verwendet. `UEBERGABE_CHAT.md` gehört nur ins Projektwissen, nicht ins Repo.

### B4. ENTSCHEIDUNGSLOG und ADRs — *Festgelegt*

ADRs unter `docs/adr/` sind die maßgebliche Begründung für Architekturentscheidungen. `docs/ENTSCHEIDUNGSLOG.md` ist das chronologische Verzeichnis **aller** Entscheidungen (auch Scope, Geschäft, Recht): eine Zeile pro Entscheidung mit Datum, Kurzfassung, betroffenen Dokumenten und Verweis auf das ADR, falls es eines gibt. Es ersetzt keine ADRs.

### B5. Übergabe-Widerspruch "kein Repo" — *Festgelegt*

Es gibt ein Repo, und die Umsetzung läuft dort über Claude Code. Der Chat ist der Planungsraum daneben. Der Satz "kein Repo als gemeinsame Ablage" in der Chat-Übergabe ist gestrichen.

### B6. `decomp.py` und `stac.py` verschieben? — *Aufgehoben*

Ersetzt durch ENTSCHEIDUNGEN §1: Bestehender Code darf umgebaut, verschoben und umbenannt werden. Die Module aus Architekturplan 3.1 sind die Zielstruktur; bestehende Dateien werden dorthin überführt, wenn es fachlich passt. Re-Exporte am alten Ort sind nicht nötig.

### B7. BIOMASS in pgstac — *Aufgehoben*

Ersetzt durch ENTSCHEIDUNGEN §1 und §3: BIOMASS kommt in der Plattform nicht vor und wird nicht nach pgstac aufgenommen — auch nicht als Collection-Metadaten. Der Prototyp-Code bleibt vorerst als Referenz im Repo und läuft unverändert lokal bei Otto weiter, außerhalb des Zielpfads.

### B8. Was ist das Gateway technisch? — *Vorschlag*

Das Gateway ist **zwei Dinge in zwei Ausbaustufen**, weil GDAL und `pystac_client` ihre HTTP-Zugriffe selbst ausführen:

1. **Bibliothek `gateway` (ab M1):** die einzige Stelle, die entscheidet, *ob* eine URL abgerufen werden darf (Host-Allowlist, Schema, Auflösung auf private Adressen, Limits pro Host), und die den HTTP-Client für eigene Requests stellt. Für Fremdbibliotheken gilt: Jede URL wird vor der Übergabe an rasterio/GDAL oder `pystac_client` durch `gateway` geprüft; `gateway` setzt außerdem zentral die GDAL-Konfiguration (Timeouts, erlaubte Dateiendungen, Proxy) und die Sitzungsparameter für `pystac_client`. Token-Logik ist nicht Teil des Gateways (ENTSCHEIDUNGEN §3).
2. **Egress-Proxy bzw. Netzwerk-Policy (ab M6, Cloud):** die eigentliche Durchsetzung. GDAL und alle anderen Clients laufen über einen Proxy mit derselben Allowlist; direkte Verbindungen nach außen sind auf Netzwerkebene gesperrt. Das deckt auch Redirects ab, die eine Bibliothek selbst verfolgt.

Der M1-Test "kein Request außerhalb des Gateways" besteht deshalb aus: (a) statischer Regel, dass HTTP-Bibliotheken nur in `gateway` importiert werden; (b) Tests, dass jede an rasterio oder `pystac_client` übergebene URL vorher `gateway` passiert hat. Die netzwerkseitige Prüfung kommt mit M6.

**Nachtrag 19.09.2026:** Im Zielpfad kommt `pystac_client` nicht mehr vor — `adr/0005` Regel IV schließt es aus (es folgt Redirects ungeprüft und verstößt damit gegen diese Auflösung) und setzt einen eigenen schmalen `httpx`-Client in `gateway`. Von den beiden Fremdbibliotheken oben bleibt damit GDAL/rasterio. Die Importregel nennt `pystac_client` weiterhin, damit es nicht durch die Hintertür zurückkommt.

### B9. "Reine Funktion" trotz I/O; lokaler Runner — *Festgelegt (Begriff präzisiert)*

Gemeint ist: Der Worker-Kern ist **plattformunabhängig und zustandslos**. Er hat keinen Zugriff auf Plattformdienste (Datenbank, Queue, Objektspeicher, interne APIs) und hält keinen Zustand zwischen Aufrufen. Lesender Zugriff auf die **Datenquellen** ist erlaubt und nötig, und zwar über die Bibliothek `gateway`, die deshalb auch im lokalen Runner mitläuft. Die Allowlist ergibt sich dort aus den aufgelösten Asset-Adressen des Rezepts. "Umgeht das Fetch-Gateway" im Architekturplan 7.7 meint nur: Die Zugriffe kommen von der IP des Nutzers statt von der Plattform.

### B10. Capability-Flags und generische Operatoren — *Vorschlag (Auslegung)*

Capability-Flags werden **im Eintrag des jeweiligen Datensatzes** gesetzt: Jeder Datensatz schaltet jede Fähigkeit ausdrücklich frei. Generische Operatoren (Band-Math, Reprojektion) sind damit unbedenklich, weil sie nirgends stillschweigend gelten. Datensatzspezifische Operatoren (z. B. die polarimetrische Dekomposition) bleiben zusätzlich an eine Capability gebunden, die nur Datensätze mit passenden Daten setzen — für `decomp.py` ist das komplexe Quad-Pol-Daten (ENTSCHEIDUNGEN §3). Eine Registry-Prüfung (Test) verlangt für jeden Eintrag vollständig gesetzte Flags.

### B11. Lizenzregel — *Vorschlag (ersetzt den Satz in Projektübersicht §5)*

Drei Stufen, gesteuert über die Lizenz-Flags:

| Stufe | Voraussetzung | Was die Plattform tut |
|---|---|---|
| Katalogeintrag | keine (Metadaten + Verweis) | Beschreibung, Coverage Map aus Footprints, Link bzw. Weiterleitung zum Download bei der Quelle |
| Anzeige (Tiles, Quicklooks über eigene Dienste) | Weitergabe erlaubt **und** Bearbeitung erlaubt | dynamische Tiles, Stretch, Reprojektion |
| Processing | wie Anzeige; bei `commercial_use = false` nur im Gratis-Tier | Operatoren, Jobs, Datacube |

ND-Datensätze (keine Bearbeitung) sind damit **nur als Katalogeintrag mit Link** zulässig, solange keine Rechtsberatung etwas anderes ergibt, weil schon reprojizierte Tiles eine Bearbeitung sein können. NC bleibt zulässig.

### B12. Pflichten pro Datensatz — *Festgelegt*

Maßgeblich ist die Onboarding-Checkliste in `projektuebersicht.md` §5, ergänzt um Punkt 10: "Zuletzt erfolgreich geprüft" ist gesetzt und sichtbar. Die Coverage Map ist dort Pflichtpunkt (ENTSCHEIDUNGEN §5). Die Kurzliste in der Übergabe ist nur eine Zusammenfassung.

### B13. Registry: Dataclass oder YAML? — *Vorschlag*

Gestuft, mit gleichbleibender Schnittstelle:

1. **M1 bis M4:** `DatasetConfig` als Python-Dataclass in `datasets.py`. Diese Datei liegt im Modul **`catalog`**, nicht unter `earthx/datasets/` (Otto am 19.09.2026, M1-04): `architekturplan.md` 3.1 hält `datasets/<id>` von allem Generischen isoliert, `catalog` könnte die Einträge dort nicht lesen. `earthx/datasets/<id>/` bleibt datensatzspezifischem **Code** vorbehalten, nicht den Metadaten.
2. **Ab M5 (Harvester, Git-Review):** Kuratierte Definitionen liegen als YAML unter `catalog/`; `datasets.py` wird zum Lader, der daraus dieselben `DatasetConfig`-Objekte erzeugt. Aufrufer merken nichts.
3. pgstac wird aus derselben Quelle befüllt; es gibt nie zwei gepflegte Wahrheiten.

### B14. Skills — *Vorerst nicht im Repo* (Stand 19.09.2026)

Die drei Skills (`atomic-commits`, `code-cleanup`, `readme-updater`) liegen weiterhin nur in Ottos persönlicher Claude-Code-Umgebung. Sie werden **vorerst nicht** ins Repo kopiert.

Folge: `CLAUDE.md` verweist nicht mehr auf sie, sondern sagt die Regel selbst — kleine, thematisch getrennte Commits mit aussagekräftiger Nachricht; vor dem PR die geänderten Dateien aufräumen. Eine Cloud-Sitzung darf sich auf keinen Skill verlassen, der nicht im Repo liegt. Kommen die Skills später doch dazu, ersetzt der Verweis die Regel wieder; bis dahin gilt der Text in `CLAUDE.md`.

---

## C. Folgen für M0 — *Aufgehoben*

Ersetzt durch `ENTSCHEIDUNGEN_2026-09-18.md` §6 ("M0 neu"). Dort steht die verbindliche Reihenfolge der M0-Schritte.

---

## D. Folgen der Öffentlichkeit des Repos

Aus ENTSCHEIDUNGEN §4, hier zum Nachschlagen:

- Keine Secrets, Tokens, echten `.env`-Werte oder internen URLs im Repo, in Issues, PRs oder Logs. Vor dem ersten autonomen Lauf die Git-History einmal auf versehentlich eingecheckte Secrets prüfen.
- Fixtures nur synthetisch oder aus Daten mit eindeutig offener Lizenz. BIOMASS-Daten kommen darin nicht vor.
- Bug-Report-Issues enthalten ausschließlich bereinigte technische Angaben; die vollständige Meldung bleibt außerhalb von GitHub (Projektplan 6.1). Sicherheitsmeldungen nie als öffentliches Issue.
- Cloud-Sitzungen nicht öffentlich teilen, ohne sie auf sensible Inhalte zu prüfen.
- Ohne geklärte Code-Lizenz ist öffentlich sichtbarer Code rechtlich nicht zur Nutzung freigegeben; die Lizenzentscheidung steht bei Otto aus.
