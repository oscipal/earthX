# EarthX — Entscheidungen von Otto (18.09.2026)

**Rang:** Dieses Dokument geht allen anderen vor, auch `ADDING_ESA_DATASETS.md`, `KLAERUNGEN.md`, den Übergabedateien und `CLAUDE.md`. Wo es ihnen widerspricht, gilt dieses Dokument; die anderen werden bei Gelegenheit angepasst.

---

## 1. BIOMASS bleibt nicht

- Die fertige Plattform enthält **nichts, was einen Token braucht**. BIOMASS kommt dort nicht vor.
- Der MAAP-Token läuft voraussichtlich bald aus. Es wird kein Aufwand betrieben, das BIOMASS-Verhalten zu erhalten.
- **Die sieben Hard Constraints aus `ADDING_ESA_DATASETS.md` sind als verbindliche Regeln aufgehoben.** Die Datei bleibt nur als Beschreibung des Code-Stands vom 13.08.2026 nützlich (Abschnitt 1).
- Damit entfallen: Hard-Constraint-Tests in M0, der Golden-Test mit Token, CODEOWNERS-Schutz für BIOMASS-Pfade, die Regel "bestehende Dateien nicht verschieben" (`KLAERUNGEN.md` B6), BIOMASS als Collection in pgstac (B7), der Wortlaut von Regel 7 (A1), das Aufzeichnen von BIOMASS-Antworten (A4). Bestehender Code darf umgebaut, verschoben und umbenannt werden.

## 2. Was vom Prototyp erhalten bleiben soll

Der Prototyp wird wegen seiner **Funktionen und Designentscheidungen** behalten, nicht wegen des Datensatzes. Sie sollen auf token-freie Datensätze übertragen werden. Nach den früheren Planungs-Chats gehören dazu (am Code zu prüfen und zu vervollständigen):

- AOI-Auswahl: Punkt, Rechteck, Polygon, Ortssuche per Geocoding
- Quicklook-Overlays mit Zeitleiste am unteren Bildschirmrand
- Ablauf "anklicken, auswählen, bestätigen" für den Download
- AOI-Zuschnitt über partielle COG-Reads statt Download ganzer Szenen; zweistufige Anzeige (georeferenziertes PNG-Overlay, dann dynamische XYZ-Tiles aus den COG-Overviews)
- Stitching mehrerer Szenen über eine AOI
- Coverage Map (Footprints) pro Datensatz
- Disk-Cache mit LRU-Verdrängung
- Dunkles, technisches Kartendesign mit Umschalter auf ein normales Thema
- Polarimetrische Auswertung (Pauli RGB und weitere Dekompositionen) als Beispiel für "häufigste Analysemethoden pro Datensatz"

**Erste Aufgabe in M0 ist deshalb ein Funktions- und Design-Inventar des Prototyps** (Stufe C): Was gibt es, wie ist es gelöst, was davon ist BIOMASS-spezifisch und was übertragbar? Das Inventar ersetzt die Hard-Constraint-Tests als Ausgangspunkt.

## 3. Umgang mit dem BIOMASS-Code bis dahin

- Der Code bleibt vorerst im Repo als Referenz und wird nicht vorschnell gelöscht. Er wird entfernt, sobald seine Funktionen mit einem token-freien Datensatz laufen (eigene Entscheidung von Otto, Stufe B).
- Solange der Token gilt, darf Otto BIOMASS lokal als Testdaten nutzen. In CI, Cloud-Sitzungen und Fixtures kommt BIOMASS nicht vor.
- Token-Logik (`auth.py`, MAAP-OIDC, Token in der GDAL-Umgebung) wird **nicht** in die Zielarchitektur übernommen und nicht generalisiert. Token pro Connector bleibt ein fernes Zukunftsthema.
- `decomp.py`: Die Mathematik gilt nur für komplexe Quad-Pol-Daten. Sie wird als Operator mit entsprechender Capability übernommen (nur für Datensätze, die solche Daten liefern), nicht als allgemeine Funktion. Offener Punkt: Es ist unklar, ob es dafür eine token-freie Quelle gibt (Sentinel-1 ist Dual-Pol). Bis dahin ruht der Operator mit synthetischen Tests.

## 4. Repository

- Das Repo ist **öffentlich und bleibt es vorerst**.
- Es wird in **`earthX`** umbenannt; es gibt kein neues Monorepo.
- Folgen der Öffentlichkeit, verbindlich:
  - Keine Secrets, Tokens, echten `.env`-Werte, internen URLs im Repo, in Issues, PRs oder Logs. Vor dem ersten autonomen Lauf die Git-History einmal auf versehentlich eingecheckte Secrets prüfen.
  - Fixtures nur synthetisch oder aus Daten mit eindeutig offener Lizenz.
  - Bug-Report-Issues enthalten ausschließlich bereinigte technische Angaben; die vollständige Meldung bleibt außerhalb von GitHub (Projektplan 6.1). Sicherheitsmeldungen nie als öffentliches Issue.
  - Cloud-Sitzungen nicht öffentlich teilen, ohne sie auf sensible Inhalte zu prüfen.
- Code-Lizenz: **AGPL-3.0-or-later** (entschieden am 18.09.2026). Die ursprüngliche Annahme dieses Abschnitts, es gebe keine `LICENSE`-Datei, war falsch: Seit dem ersten Commit lag eine MIT-Lizenz im Repo. Sie ist durch die AGPL ersetzt; bereits veröffentlichte Versionen bleiben unter MIT verfügbar. Aus der AGPL folgt eine offene Pflicht: Die Plattform muss ihren Nutzern einen Link zum Quellcode anbieten (AGPL §13), umzusetzen mit dem ersten öffentlichen Deployment.

## 5. Was weiter gilt

Alles, was hier nicht aufgehoben ist: die Prinzipien der Projektübersicht, die Architektur (Ebenen, STAC als Modell, zweistufiger Katalog, Rezept, Operator-Registry, lokaler Runner), die Auflösungen in `KLAERUNGEN.md` zu Gateway (B8), Worker-Kern (B9), Lizenzstufen (B11), Onboarding-Checkliste (B12), Registry gestuft (B13), ADR und Entscheidungslog (B4), die Arbeitsweise und Modellzuordnung des Projektplans, die Bug-Report-Pipeline.

Die Coverage Map bleibt Pflicht für jeden Datensatz, jetzt als Punkt der Onboarding-Checkliste statt als Hard Constraint.

## 6. M0 neu

1. Repo umbenennen, Dokumente nach `docs/`, `CLAUDE.md`, Skills nach `.claude/skills/`, Branch-Schutz, CODEOWNERS (für `.claude/`, `.github/`, `CLAUDE.md`, Sicherheitsmodule; nicht mehr für BIOMASS-Pfade), History auf Secrets prüfen.
2. Klären, was die Cloud-VM bereitstellt; Testaufteilung festlegen.
3. **Funktions- und Design-Inventar des Prototyps** (ersetzt die Hard-Constraint-Tests).
4. Zustands-Audit als ADR-Entwurf.
5. Bug-Report-Pipeline Stufe 1.
6. Vorschlag für den ersten token-freien Datensatz, auf den die Prototyp-Funktionen übertragen werden (Kandidat laut früherer Planung: EOPF Sentinel Zarr Samples), als Entscheidungsvorlage für Otto.

Alles Weitere klärt Otto direkt im neuen Chat.
