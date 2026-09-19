# M1 — Fundament: Aufgabenschnitt

**Status:** Vorschlag vom 19.09.2026. Gilt nach Ottos Entscheidung über Abschnitt 1.
**Ort im Repo:** `docs/plans/m1-fundament.md`
**Grundlagen:** `projektplan.md` 4 (M1), `architekturplan.md` 3.1, 5, 6.5, 12, 13, 15.1;
`adr/0001` (Zustand), `adr/0002` (Tests), `adr/0003` (erster Datensatz); `ENTSCHEIDUNGSLOG.md`.

Eine Sitzung startet eine Aufgabe mit: „Führe Aufgabe M1-xx aus `docs/plans/m1-fundament.md` aus.“
Jede Aufgabe ist ohne dieses Gespräch verständlich und endet mit genau einem Draft-PR.

---

## 0. Ziel in einem Satz

Die Zieltopologie steht neben dem Prototyp und trägt Sentinel-2 L2A (Earth Search) als
ersten token-freien Datensatz: Collection im eigenen pgstac, Items föderiert über einen
Adapter, alles Ausgehende über `gateway`, nach außen eine STAC-API.

---

## 1. Vor dem Start: Entscheidungen von Otto

| # | Frage | Empfehlung | Warum |
|---|---|---|---|
| E1 | Name des Wurzelpakets der Zielarchitektur (offen laut Log, `adr/0002` §4) | `earthx`, neu neben `app` unter `backend/` | Strangler-Muster (`architekturplan.md` 13): Neues entsteht neben dem Prototyp, `app` bleibt lauffähig, bis es entfernt wird |
| E2 | Wo werden die Konsequenzen aus `adr/0001` umgesetzt? | **Nur im neuen Pfad.** Der Prototyp wird nicht umgebaut, sondern später als Ganzes entfernt | Der Prototyp lässt sich in CI und Cloud nicht testen (BIOMASS, Token). Umbau am toten Pfad kostet und beweist nichts |
| E3 | Kacheln schon in M1? | **Nein.** Kachel-Pfad, TiTiler-Spike und Z4 (Streckbereich in der URL) kommen in M2 | Entspricht `projektplan.md` M2; ein eigener Kachel-Endpunkt jetzt würde nach dem Spike vermutlich ersetzt |
| E4 | Anwendungs-Cache (`adr/0001` §9.1) | Postgres | läuft für pgstac ohnehin; `architekturplan.md` 15.3: Redis erst bei messbarem Bedarf |
| E5 | Zwischenzustand in M1 (`adr/0001` §9.3) | Regel (a) gilt: ein Fehlschlag eines Zwischenspeichers macht nur langsamer, nie 404 | im neuen Pfad gibt es in M1 nur den Such-Cache; die Regel wird dort getestet |
| E6 | Ablauffrist im Objektspeicher (`adr/0001` §9.2) | vertagen auf M4 | in M1 schreibt nichts in den Objektspeicher; die Frist hängt am Rezept |
| E7 | Objektspeicher in Tests (offen laut Log) | `moto` für Unit-Tests, MinIO als Service-Container nur in CI | M1 braucht ihn nur für den compose-Start |
| E8 | Status der ADRs | `adr/0001` und `adr/0002` auf „angenommen“ mit E2 bis E7 | beide sind im Log noch „Vorschlag“ |

Zusätzlich vor dem Start, von Otto auszuführen:

- Setup-Skript `scripts/setup-cloud-session.sh` in der Cloud-Umgebung eintragen (im Log „Vorschlag“). Ohne es fehlt neuen Sitzungen Postgres.
- Im Ruleset für `main` „Require status checks to pass“ mit dem CI-Job aktivieren. Das ist Teil der M0-Abnahme (`projektplan.md` M0).

---

## 2. Abgrenzung

**In M1:** Paketgerüst mit scharfen Importregeln, Fetch-Gateway, Datensatz-Registry und
Katalogmodell, Sentinel-2-Collection in pgstac, Earth-Search-Adapter mit föderierter
Item-Suche, STAC-API nach außen, compose-Topologie mit vier Prozessen, strukturierte Logs,
Coverage-ADR (nur Recherche).

**Nicht in M1:** Kacheln, Quicklooks, Zuschnitt und Stitching (M2); Zarr und EOPF (M2);
Frontend-Generalisierung (M2); Coverage-Heatmap bauen (nach dem ADR, M2); Ergebnisse im
Objektspeicher und Rezept (M4); Umbau oder Entfernen des Prototyps (Otto, Stufe B, erst
wenn seine Funktionen token-frei laufen).

**Folge für die Onboarding-Checkliste:** Sentinel-2 ist nach M1 im Katalog, aber noch nicht
vollständig aufgenommen. Coverage Map, Standard-Visualisierung im Viewer und End-to-End-Test
folgen in M2.

---

## 3. Übersicht und Reihenfolge

| ID | Aufgabe | Stufe | Modell | hängt ab von |
|---|---|---|---|---|
| M1-00 | Doku nachziehen: Entscheidungen E1–E8 ins Log, veraltete Zeilen, Befehle in `CLAUDE.md` | A | Sonnet | Ottos Antworten zu Abschnitt 1 |
| M1-01 | Strukturierte Logs | A | Sonnet | M1-00 |
| M1-02 | Paketgerüst `earthx` und Importregeln scharf | A | Sonnet | M1-00 |
| M1-03 | Fetch-Gateway | B | Plan Opus, Umsetzung Sonnet | M1-02 |
| M1-04 | Datensatz-Registry, Katalogmodell, pgstac | B | Plan Opus, Umsetzung Sonnet | M1-02 |
| M1-05 | Spike föderierte Item-Suche | C | Opus | M1-00 |
| M1-06 | Earth-Search-Adapter | B | Sonnet | M1-03, M1-04, M1-05 |
| M1-07 | STAC-API nach außen | B | Plan Opus, Umsetzung Sonnet | M1-04, M1-06 |
| M1-08 | compose-Topologie und CI-Job | B | Sonnet | M1-02 |
| M1-09 | Coverage-ADR mit Recherche | C | Opus | — |
| M1-10 | M1-Abnahme und README | A | Sonnet | alle |

**Wellen**, jeweils parallel möglich:

1. M1-00, M1-09
2. M1-01, M1-02, M1-05
3. M1-03, M1-04, M1-08
4. M1-06
5. M1-07
6. M1-10

M1-01 ist bewusst klein und klar. Sie eignet sich als Probelauf für die M0-Abnahme: Otto
legt sie als GitHub-Issue an, eine Sitzung setzt sie um, der PR läuft durch die
Pflicht-CI, Otto sichtet und mergt ohne weiteres Eingreifen.

---

## 4. Die Aufgaben

### M1-00 — Doku nachziehen

**Ziel:** Ottos Entscheidungen aus Abschnitt 1 festhalten und veraltete Stellen berichtigen.
**Umfang:**
- Pro Entscheidung E1–E8 eine Zeile in `docs/ENTSCHEIDUNGSLOG.md`, mit Ottos tatsächlicher Antwort (liegt der Aufgabe bei). `adr/0001` und `adr/0002` im Kopf auf den entschiedenen Status setzen.
- Log-Zeilen berichtigen, die den Stand vor der Annahme von `adr/0003` beschreiben: die offene Zeile „Lizenzprüfung nach B11 … blockiert“ und den Satz „ADR bleibt ‚Vorschlag‘“. Nicht löschen, sondern Status ändern und auf die erledigende Zeile verweisen.
- Abschnitt „Befehle“ in `CLAUDE.md` mit den Befehlen aus `adr/0002` §6 füllen (ausdrücklich erlaubt).
- Diese Datei nach `docs/plans/m1-fundament.md` legen und Abschnitt 1 mit den Antworten ergänzen.

**Nicht anfassen:** Code, `.github/`.
**Abnahme:** Log enthält E1–E8; keine Zeile widerspricht `adr/0003` „angenommen“; `CLAUDE.md` nennt die Befehle, die CI ausführt.

### M1-01 — Strukturierte Logs

**Ziel:** Alle neuen Prozesse loggen JSON mit Request-ID; Koordinaten erscheinen nie genau.
**Kontext:** `projektplan.md` 7 Punkt 6 (keine exakten AOIs in Logs), `architekturplan.md` 12.4.
**Umfang:** Logging-Konfiguration im neuen Paket (Ort laut M1-02, bis dahin `backend/earthx/logging.py`); Middleware für Request-ID; Hilfsfunktion, die Geometrien vor dem Loggen auf eine grobe Bounding-Box reduziert oder ganz weglässt.
**Nicht anfassen:** `backend/app/`.
**Abnahme:** Tests belegen JSON-Format, Request-ID pro Anfrage und dass eine übergebene Polygon-Geometrie im Log nicht mit ihren Koordinaten auftaucht; auch fehlerhafte Geometrien führen nicht zu Koordinaten im Log.

### M1-02 — Paketgerüst und Importregeln

**Ziel:** Das Wurzelpaket laut E1 existiert mit allen elf Modulen aus `architekturplan.md` 3.1 als leere Pakete; die Importregeln prüfen jeden PR.
**Umfang:** Pakete anlegen; `.importlinter` vom vorläufigen `app` auf das Wurzelpaket umstellen; im CI-Job `import-boundaries` die Einschränkung auf manuelle Läufe entfernen (ausdrücklich erlaubt); ergänzende Regel: HTTP-Clients (`httpx`, `requests`, `urllib`, `pystac_client`, `aiohttp`) nur in `gateway`.
**Nicht anfassen:** `backend/app/`. Keine Regel lockern.
**Abnahme:** `lint-imports` läuft in jeder PR-CI und ist grün; ein Test mit absichtlich verbotenem Import in einem Hilfsmodul schlägt fehl; der bestehende Deckungstest gegen 3.1 bleibt grün.

### M1-03 — Fetch-Gateway

**Ziel:** Einziger Weg nach außen, laut `architekturplan.md` 6.5 und `KLAERUNGEN.md` B8.
**Stufe B:** zuerst Plan im PR, Umsetzung nach Ottos OK.
**Umfang:**
- HTTP-Client-Kapsel; Allowlist aus der Datensatz-Registry (bis M1-04 steht: aus Konfiguration); nur `https`.
- SSRF-Schutz: DNS-Auflösung prüfen, private, Loopback- und Link-Local-Adressen sperren, Redirects nur innerhalb der Allowlist, Größen- und Zeitlimits.
- Pro Host: Obergrenze paralleler Verbindungen, Backoff; Circuit Breaker darf ein späteres Issue sein, dann im PR begründen.
- Zentrale GDAL-Konfiguration für Fernzugriff (Z8 aus `adr/0001`) und eine Prüffunktion, die jede URL freigibt, bevor sie an GDAL oder rasterio geht (B8).
- Exakte Host-Prüfung: Der `endswith`-Fehler aus dem Prototyp (`xfail` in `backend/tests/test_config.py`) darf im Gateway nicht wiederkehren; Test mit `evil`-Präfix und Subdomain-Varianten.
- Test „kein ausgehender Request außerhalb des Gateways“, der M1-Abnahme ist.

**Nicht anfassen:** `backend/app/` (der Prototyp behält seine Allowlist, der `xfail` bleibt dort).
**Hinweis:** Sicherheitsnahe Arbeit kann Klassifikatoren auslösen und einen Modellwechsel bewirken (`projektplan.md` 8); das ist erwartbar.
**Abnahme:** Tests für jede Sperrregel inklusive Umgehungsversuchen (Redirect aus der Allowlist heraus, DNS auf private Adresse, IP-Literal, Großschreibung, abschließender Punkt im Hostnamen).

### M1-04 — Datensatz-Registry, Katalogmodell, pgstac

**Ziel:** Sentinel-2 L2A ist als Collection mit allen `earthx:`-Feldern im eigenen pgstac.
**Stufe B.**
**Umfang:**
- `DatasetConfig` als Dataclass (B13, Stufe M1–M4) mit `format`, allen Capability-Flags ausdrücklich gesetzt (B10), Quad-Pol `false`.
- Eintrag Sentinel-2 L2A laut `adr/0003`: Quelle Earth Search v1, Collection `sentinel-2-c1-l2a`, B11-Stufe Processing, Attributionstext und Haftungssatz aus `adr/0003` §11.2.
- `catalog`: Modelle für die Felder aus `architekturplan.md` 5.1; Laden der Collection nach pgstac; Migrationen versioniert.
- Integrationstests T-C gegen Postgres (Cloud-Sitzung und CI).

**Nicht anfassen:** Lizenz-Einstufung selbst (ist entschieden, nur übernehmen).
**Abnahme:** Collection im pgstac mit korrekten Flags; Test, dass ein Eintrag ohne ausdrücklich gesetzte Capability abgelehnt wird; Laden ist idempotent.

### M1-05 — Spike: föderierte Item-Suche

**Ziel:** Entscheidungsvorlage, wie Items von Earth Search durch die eigene STAC-API gereicht werden (`architekturplan.md` 5.2, 15.2).
**Stufe C:** Bericht als ADR-Entwurf unter `docs/adr/`, keine Produktivcode-Änderung.
**Fragen:** Kann `stac-fastapi-pgstac` die Item-Suche für eine Collection an einen Adapter delegieren, oder braucht es eine eigene Route davor? Latenz und Limits von Earth Search (einige Messungen, Metadaten-Anfragen nur); vertretbarer Cache-TTL; Paging und Such-ID; wie `pystac_client` oder ein eigener Client über `gateway` läuft. Ratengrenzen von Earth Search (offen laut Log).
**Abnahme:** ADR-Entwurf mit Optionen, Messwerten, Empfehlung und Quellen.

### M1-06 — Earth-Search-Adapter

**Ziel:** Suche und Zugriffsauflösung für Sentinel-2 L2A, Vorlage `stac.py` (`architekturplan.md` 13).
**Stufe B.** Vorgehen laut angenommenem Spike M1-05.
**Umfang:** Adapter in `adapters`, alle Aufrufe über `gateway`; Such-Cache im Anwendungs-Cache (E4) mit Ablauf; kein Endpunkt setzt eine vorherige Suche voraus (Z1).
**Fixtures:** synthetisch, nach dem Muster echter Antworten. Aufgezeichnete Antworten nur, wenn die Lizenz der Earth-Search-Metadaten geklärt ist; das im PR benennen und nicht selbst entscheiden.
**Live-Smoke:** ein zeitgesteuerter T-D-Test in GitHub Actions (`adr/0002`), nie in PR-Läufen.
**Abnahme:** Tests für leere Treffer, Upstream-Fehler, Zeitüberschreitung, fehlerhafte AOI, Paging; ein Test, dass ein geleerter Cache nur langsamer macht (E5); ein Test, dass ein Neustart zwischen Suche und Item-Abruf nichts ändert (`adr/0001` §8).

### M1-07 — STAC-API nach außen

**Ziel:** Der eigene Katalog ist als STAC-API lesbar: Collections aus pgstac, Items föderiert.
**Stufe B.** Aufbau laut Spike M1-05.
**Umfang:** Einbindung im `api`-Prozess unter einem eigenen Präfix, das mit keiner Route des Prototyps kollidiert; Konformitätsklassen korrekt ausweisen.
**Abnahme:** automatischer Konformitätstest gegen die laufende API in CI (Werkzeug im PR begründen); Anleitung im PR, wie Otto lokal einen STAC-Browser auf die API richtet (M1-Abnahme).

### M1-08 — compose-Topologie

**Ziel:** `docker compose up` startet `api`, `tiler`, `worker`, `harvester`, Postgres mit pgstac und MinIO; ein Image, vier Startbefehle (`architekturplan.md` 3.2, 12.1).
**Stufe B.**
**Umfang:** Dockerfile, `docker-compose.yml`, Konfiguration nur über Umgebungsvariablen, Health-Endpunkte. `tiler`, `worker` und `harvester` sind in M1 Hüllen, die starten, gesund melden und nichts tun. CI-Job, der die Topologie hochfährt und die Health-Endpunkte prüft (ausdrücklich erlaubt).
**Wichtig:** In der Cloud-Sitzung laufen keine Docker-Images (`adr/0002` §1). Die Sitzung schreibt die Dateien und prüft sie ausschließlich über die CI. Die Allowlist der Umgebung nicht erweitern.
**Keine Secrets:** MinIO- und Postgres-Zugangsdaten nur als Platzhalter in einer `.env.example`; CI setzt eigene Wegwerfwerte.
**Abnahme:** CI-Job grün; Neustart eines einzelnen Dienstes lässt die anderen gesund.

### M1-09 — Coverage-ADR

**Ziel:** Entscheidungsvorlage, wie die gefilterte Coverage-Heatmap technisch umgesetzt wird (`ENTSCHEIDUNGEN` §2, offene Log-Zeile).
**Stufe C**, Subagent `architect` mit `researcher`; Stand der Technik mit Quellen.
**Fragen:** Aggregation pro Anfrage in PostGIS gegenüber vorberechneten Zeitscheiben gegenüber Vektorkacheln oder anderem; wie das bei föderierten Items geht, die nicht im eigenen pgstac liegen; Kosten bei großen Katalogen; wie die Kennzeichnung „Stichprobe“ aussieht, wenn nicht alle Footprints verfügbar sind; Ergänzungen laut §2 (Footprints ab Zoomstufe, Ausdehnung bei Einmal-Produkten, Zeit-Histogramm).
**Abnahme:** ADR-Entwurf unter der nächsten freien Nummer, mit Optionen, Kriterien, Empfehlung und Quellen.

### M1-10 — M1-Abnahme und README

**Ziel:** Die Abnahmekriterien aus Abschnitt 5 sind belegt; die README beschreibt EarthX statt `biomass-viewer`.
**Umfang:** Abnahme-Bericht im PR mit Belegen je Kriterium. README neu: Zweck, Stand, Start der neuen Topologie, Verweis auf `docs/`; der Prototyp als Abschnitt „Referenz, lokal mit eigenem Token“. Attribution für Sentinel-2 laut `adr/0003`.
**Abnahme:** Otto kann M1 anhand des PR abnehmen, ohne Code zu lesen.

---

## 5. Abnahme von M1

Aus `projektplan.md` M1 und `adr/0001` §8:

1. Ein STAC-Browser kann den eigenen Katalog lesen (Otto prüft lokal; zusätzlich Konformitätstest in CI).
2. Test belegt: kein ausgehender Request außerhalb von `gateway`.
3. Importregeln sind scharf und in jeder PR-CI grün.
4. Neustart zwischen Suche und Abruf ändert nichts; ein geleerter Cache macht nur langsamer.
5. `docker compose up` ist in CI grün.
6. Keine Secrets, keine exakten AOIs in Logs (Tests aus M1-01).

---

## 6. Risiken

| Risiko | Umgang |
|---|---|
| Kein Docker in der Cloud-Sitzung | compose nur in CI prüfen (M1-08); Sitzung verzichtet auf lokale Container |
| Ratengrenzen von Earth Search unbekannt | Spike M1-05 misst vorsichtig; Gateway-Limits konservativ; Live-Tests nur zeitgesteuert |
| Lizenz der Earth-Search-Metadaten für Fixtures ungeklärt | synthetische Fixtures; Aufzeichnungen erst nach Klärung durch Otto |
| `stac-fastapi-pgstac` passt nicht zur Föderation | genau dafür steht der Spike vor M1-07 |
| PRs über dem Richtwert von 400 Zeilen | M1-03, M1-04 und M1-06 im Plan-Schritt weiter teilen, falls nötig |
| Review-Stau bei Otto | höchstens zwei Sitzungen gleichzeitig; Stufe-A-Aufgaben zuerst sichten |
