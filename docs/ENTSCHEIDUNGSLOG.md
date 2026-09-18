# EarthX — Entscheidungslog

Chronologisches Verzeichnis aller Entscheidungen. Eine Zeile pro Entscheidung. Architekturentscheidungen verweisen auf ihr ADR unter `docs/adr/`, sobald es eines gibt.

Status:
- **fest**: von Otto entschieden.
- **Vorschlag**: gilt, bis Otto widerspricht.
- **offen**: noch nicht entschieden.
- **aufgehoben**: gilt nicht mehr; die Zeile bleibt als Historie stehen und nennt, was sie ersetzt.

Bei Widerspruch geht `ENTSCHEIDUNGEN_2026-09-18.md` allen anderen Dokumenten vor.

| Datum | Entscheidung | Status | Betroffene Dokumente |
|---|---|---|---|
| 2026-08-13 | Sieben Hard Constraints schützen das BIOMASS-Verhalten; `decomp.py` wird nie generalisiert | aufgehoben am 2026-09-18 | ADDING_ESA_DATASETS |
| 2026-08-13 | Format-Hierarchie Zarr > COG > Altformate; eigenes `zarr_reader.py`; `DatasetConfig`-Registry mit `format` | fest | ADDING_ESA_DATASETS, architekturplan |
| 2026-08 | Vorerst nur token-freie Datenquellen; Adapter-Interface entsteht aus realen Quellen | fest | projektuebersicht |
| 2026-09-18 | Alter Sechs-Phasen-Plan entfällt; es gelten Projektübersicht, Architekturplan, Projektplan | fest | alle |
| 2026-09-18 | Grundprinzip Skalierbarkeit und Cloud-Portabilität | fest | projektuebersicht 2.16, architekturplan 13 |
| 2026-09-18 | Nutzer wählt zwischen Cloud- und lokalem Processing; lokaler Runner als Container | fest | architekturplan 7.7 |
| 2026-09-18 | Umsetzung autonom mit Claude Code in der Cloud; Modellzuordnung nach Aufgabentyp | fest | projektplan 2, 3 |
| 2026-09-18 | Bug-Report-Pipeline von Anfang an: erst Triage (Bug oder Bedienfehler), Fix nur mit reproduzierendem Test und nur als PR | fest | projektplan 6.1 |
| 2026-09-18 | DOI wo vorhanden, sonst persistente Zitierangabe; Swipe-Vergleich statt freiem Skalieren; schlanker Export statt Plot-Editor | Vorschlag | projektuebersicht 15 |
| 2026-09-18 | Auflösungen B1 bis B14 in KLAERUNGEN | teilweise aufgehoben, siehe die folgenden Zeilen | KLAERUNGEN |
| 2026-09-18 | Die fertige Plattform enthält nichts, was einen Token braucht; BIOMASS kommt dort nicht vor; kein Aufwand, das BIOMASS-Verhalten zu erhalten | fest | ENTSCHEIDUNGEN_2026-09-18 §1; projektuebersicht, architekturplan, projektplan, UEBERGABE anzupassen |
| 2026-09-18 | Die sieben Hard Constraints sind als verbindliche Regeln aufgehoben; `ADDING_ESA_DATASETS.md` gilt nur noch als Beschreibung des Code-Stands vom 13.08.2026 (Abschnitt 1) | fest | ENTSCHEIDUNGEN §1; ADDING_ESA_DATASETS, KLAERUNGEN (Rangsatz) |
| 2026-09-18 | Aufgehoben: Hard-Constraint-Tests in M0, Golden-Test mit Token, CODEOWNERS für BIOMASS-Pfade, B2, B6 (nicht verschieben), B7 (BIOMASS in pgstac), A1, A4, KLAERUNGEN Abschnitt C. Bestehender Code darf umgebaut, verschoben und umbenannt werden | fest | ENTSCHEIDUNGEN §1; KLAERUNGEN |
| 2026-09-18 | Gelten weiter: B1, B3, B4, B5, B8, B9, B11, B12, B13, B14. Die BIOMASS-bezogenen Sätze darin (Token über GDAL-Umgebung in B8, BIOMASS-Eintrag behält seine Werte in B13) entfallen | fest | ENTSCHEIDUNGEN §5; KLAERUNGEN |
| 2026-09-18 | B10: Capability-Flags werden im Eintrag des jeweiligen Datensatzes gesetzt; jeder Datensatz schaltet jede Fähigkeit ausdrücklich frei. Die Begründung über Hard Constraint 6 und die Sonderregel für das `coverage`-Flag des BIOMASS-Eintrags entfallen | Vorschlag | KLAERUNGEN B10 |
| 2026-09-18 | Coverage Map bleibt Pflicht für jeden Datensatz, als Punkt der Onboarding-Checkliste statt als Hard Constraint | fest | ENTSCHEIDUNGEN §5; projektuebersicht §5 |
| 2026-09-18 | Der Prototyp bleibt wegen seiner Funktionen und Designentscheidungen erhalten, nicht wegen des Datensatzes; sie werden auf token-freie Datensätze übertragen | fest | ENTSCHEIDUNGEN §2 |
| 2026-09-18 | Der BIOMASS-Code bleibt als Referenz im Repo, bis seine Funktionen mit einem token-freien Datensatz laufen; das Entfernen entscheidet Otto (Stufe B). BIOMASS nur lokal bei Otto als Testdaten; nie in CI, Cloud-Sitzungen oder Fixtures | fest | ENTSCHEIDUNGEN §3 |
| 2026-09-18 | Token-Logik (`auth.py`, MAAP-OIDC, Token in der GDAL-Umgebung) wird nicht in die Zielarchitektur übernommen und nicht generalisiert; Token pro Connector ist fernes Zukunftsthema | fest | ENTSCHEIDUNGEN §3; architekturplan |
| 2026-09-18 | `decomp.py` wird als Operator mit Quad-Pol-Capability übernommen, nicht als allgemeine Funktion; bis eine token-freie Quelle existiert, ruht er mit synthetischen Tests | fest | ENTSCHEIDUNGEN §3; architekturplan 7.2 |
| 2026-09-18 | Repo ist öffentlich und bleibt es vorerst (entscheidet A2) | fest | ENTSCHEIDUNGEN §4; KLAERUNGEN A2 |
| 2026-09-18 | Bestehendes Repo wird in `earthX` umbenannt; kein neues Monorepo (entscheidet A3) | fest | ENTSCHEIDUNGEN §4; KLAERUNGEN A3, projektplan 2.1 |
| 2026-09-18 | Folgen der Öffentlichkeit: keine Secrets, Tokens, echten `.env`-Werte oder internen URLs in Repo, Issues, PRs und Logs; Git-History vor dem ersten autonomen Lauf auf Secrets prüfen; Fixtures nur synthetisch oder mit eindeutig offener Lizenz; Bug-Report-Issues nur bereinigt, Sicherheitsmeldungen nie öffentlich; Cloud-Sitzungen nur nach Prüfung teilen | fest | ENTSCHEIDUNGEN §4; projektplan 6.1 |
| 2026-09-18 | M0 neu: (1) Repo-Grundgerüst, CODEOWNERS für `.claude/`, `.github/`, `CLAUDE.md` und Sicherheitsmodule, Secret-Prüfung der History; (2) Cloud-VM klären, Testaufteilung; (3) Funktions- und Design-Inventar des Prototyps; (4) Zustands-Audit als ADR-Entwurf; (5) Bug-Report-Pipeline Stufe 1; (6) Vorschlag für den ersten token-freien Datensatz | fest | ENTSCHEIDUNGEN §6; projektplan M0 |
| 2026-09-18 | M0 Schritt 1 umgesetzt: `KLAERUNGEN.md` und die Plandokumente an die Entscheidungen vom 18.09. angepasst; `ADDING_ESA_DATASETS.md` als historisch gekennzeichnet | fest | KLAERUNGEN, projektplan, architekturplan, projektuebersicht, ADDING_ESA_DATASETS |
| 2026-09-18 | `CLAUDE.md` neu geschrieben: Rangfolge, unverrückbare Regeln, Arbeitsweise (ein Branch, ein Draft-PR, nie mergen, nie force-pushen), Schutz von `.github/`, `.claude/`, `CLAUDE.md`, `CODEOWNERS`, Fragenregel, Sprachregelung | fest | CLAUDE.md; projektplan 2.5 (Gerüst entfällt, verweist jetzt auf die Datei) |
| 2026-09-18 | Subagenten aus Projektplan 3.3 als Dateien unter `.claude/agents/` angelegt; `.claude/settings.json` mit Standardmodell Sonnet (auch für nicht zugeordnete Subagenten). Beim `reviewer` sind die Hard Constraints als Prüfpunkt gestrichen | fest | projektplan 3.3; .claude/ |
| 2026-09-18 | Git-History einmal auf Secrets geprüft (ENTSCHEIDUNGEN §4). Ergebnis und Behandlung des Fundes direkt an Otto, nicht öffentlich | fest | ENTSCHEIDUNGEN §4 |
| 2026-09-18 | Das fest eingetragene OIDC-Client-Secret in `backend/app/config.py` bleibt unverändert: kein Widerruf, keine Code-Änderung, keine History-Bereinigung. Bewusste, **befristete Ausnahme** von "keine Secrets im Repo"; sie endet mit dem Entfernen des BIOMASS-Codes | fest | CLAUDE.md; ENTSCHEIDUNGEN §4 |
| 2026-09-18 | Code-Lizenz: Wechsel von MIT auf **AGPL-3.0-or-later**. Bereits veröffentlichte Versionen bleiben unter MIT; keine Lizenz-Header in einzelnen Dateien | fest | LICENSE, README, frontend/package.json; ENTSCHEIDUNGEN §4 |
| 2026-09-18 | `ENTSCHEIDUNGEN` §2 neu gefasst: Aufzählung des zu Erhaltenden am Inventar ausgerichtet und erweitert (Upload/letzte AOI, Gruppierung, Layer-Manager, Darstellungssteuerung mit "Apply", Asset-Proxy mit Allowlist ohne Token, HUD-Design); Disk-Cache nur noch als Konzept, Umsetzung wird ersetzt; Coverage Map als Heatmap der Abdeckungsdichte mit Footprints, Ausdehnung und Zeit-Histogramm als Ergänzungen und eigenem Umsetzungs-ADR; neu zu bauen: Theme-Umschalter mit heller Basiskarte und Datei-Download des AOI-Zuschnitts | fest | ENTSCHEIDUNGEN §2; prototyp-inventar, architekturplan, projektuebersicht |
| 2026-09-18 | Coverage Map als Heatmap, reagiert auf Filter (Zeitraum, Suchkriterien) | fest | ENTSCHEIDUNGEN §2 |
| — | Technische Umsetzung der Coverage Map (Aggregation pro Anfrage, vorberechnete Zeitscheiben, Vektorkacheln oder anderes) | offen, ADR mit Recherche vor dem Bau | ENTSCHEIDUNGEN §2 |
| 2026-09-18 | M0 Schritt 4: Zustands-Audit des Prototyps als ADR-Entwurf `docs/adr/0001-zustand-im-prototyp.md` (Z1–Z9 Backend, FZ1–FZ7 Frontend). Empfehlung: zustandslose Dienste, Zustand in die Ebenen aus Architekturplan 12.3 — Item-Registry nach pgstac, Zuschnitte in den Objektspeicher mit Ablauf, Streckbereich in die Kachel-URL, LRU-Index und Token-Cache entfallen | Vorschlag, Entscheidung in M1 (B1) | adr/0001; architekturplan 3.2, 12.3, 13; KLAERUNGEN B1, B9 |
| 2026-09-18 | M0 Schritt 2, Befund: Die Cloud-Umgebung bietet Python 3.11 ohne conda, Node 22, die Backend-Abhängigkeiten per pip inklusive GDAL 3.10 aus den Wheels, Postgres 16 mit PostGIS 3.4 und pgstac. Docker startet, kann aber keine Images laden. Keine EO-Quelle und kein Geocoder erreichbar | fest (gemessen) | cloud-umgebung; projektplan 2.3 (Rückfallebene für Postgres entfällt) |
| 2026-09-18 | Setup-Skript `scripts/setup-cloud-session.sh` vorgeschlagen (venv per pip statt `environment.yml`, npm ci, Postgres mit PostGIS). Eintragen in die Cloud-Umgebung macht Otto selbst | Vorschlag | cloud-umgebung; projektplan 2.3 |
| 2026-09-18 | Testaufteilung als ADR-Entwurf `docs/adr/0002-testaufteilung.md`: T-A Unit/Rechen und T-B Verträge und T-C Integration mit Postgres laufen in Cloud-Sitzung und CI; T-D Live-Smoke nur zeitgesteuert in GitHub Actions; was Token, echte Szenen oder einen Container braucht, ist `local_only` und gilt als ungeprüft. Netzsperre in Tests per autouse-Fixture, die sich selbst prüft | Vorschlag | adr/0002; projektplan 2.4, 7 |
| 2026-09-18 | CI-Grundgerüst `.github/workflows/ci.yml`: Backend-Lint (ruff, zunächst enger Regelsatz E4/E7/E9/F/I/B) und pytest, Frontend-Lint (oxlint) und Typprüfung (tsc). Erste Tests: App startet, Konfiguration lädt, keine Netzwerkzugriffe. Kein Job braucht MAAP, BIOMASS oder ein Secret | fest | .github/workflows/ci.yml; pyproject.toml; backend/tests |
| 2026-09-18 | Modulgrenzen aus Architekturplan 3.1 als `.importlinter`-Verträge hinterlegt, aber **nicht scharf**: die Zielmodule gibt es noch nicht. Der Job `import-boundaries` läuft nur manuell; ein PR-Test hält die Verträge mit der Tabelle in 3.1 deckungsgleich. Scharfschalten mit M1 | Vorschlag | .importlinter; adr/0002; architekturplan 3.1 |
| — | Wurzelpaketname der Zielarchitektur (`.importlinter` nimmt vorläufig `app` an) | offen | adr/0002; architekturplan 3.1 |
| — | Ob `production.cloudfront.docker.com` und `pkg-containers.githubusercontent.com` in die Allowlist der Cloud-Umgebung sollen, damit Docker dort nutzbar wird. Empfehlung: vorerst nein | offen | cloud-umgebung §4 |
| — | Objektspeicher in Tests: Python-Double (`moto`) oder nur in CI | offen, wenn der erste Test ihn braucht | adr/0002 §2 |
| — | Schwachstelle in `Settings.host_allowed`: der `endswith`-Zweig lässt Hosts durch, die nur auf den erlaubten String enden (`evilmaap.eo.esa.int`). Als `xfail`-Test festgehalten; Behebung beim Umzug der Allowlist nach `gateway` | offen | backend/tests/test_config.py; KLAERUNGEN B8 |
| — | Erster token-freier Datensatz (Kandidat: EOPF Sentinel Zarr Samples) | offen, Entscheidungsvorlage in M0 | ENTSCHEIDUNGEN §6 |
| — | Token-freie Quelle für komplexe Quad-Pol-Daten (für den Dekompositions-Operator) | offen | ENTSCHEIDUNGEN §3 |
| — | ESA-only oder Quellenbreite; Registrierungspflicht; NC hinter Bezahlschranke; Job-Queue; Cloud-Anbieter | offen | projektplan 10 |
| — | **AGPL §13:** Die Plattform muss ihren Nutzern einen Link zum Quellcode anbieten. Umzusetzen mit dem ersten öffentlichen Deployment | offene Pflicht | LICENSE; architekturplan (Deployment), projektuebersicht |
