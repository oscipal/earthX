# M5 — Discovery und Suche

**Stand:** 13.11.2026, **Fassung 3.2 (laufend, noch nicht im Repo)**. Der Planungs-Chat trägt Wichtiges laufend in die Projektkopie ein; die nächste Doku-Runde bringt es ins Repo. Fassung 3.1 (11.11.2026, Nachführung): Fassung 3 (angenommen von Otto am 06.11.2026, §8: F1 und F2 jeweils Option 1) schnitt den Rest der Umsetzung und legte die Abnahme fest. Fassung 3.1 trifft keine neue Entscheidung: Sie trägt den Stand nach (§6.1), die seither entstandenen Aufgaben M5-28 bis M5-30, UI-06, F11, F12 und die Vorarbeiten V1–V9 aus `adr/0031` (§6.2), die Vorgaben Ottos seit dem 07.11. (§2 Punkt 9) und die neue Reihenfolge (§6.3). Die Entscheidungen dazu stehen bereits im Entscheidungslog.
**Grundlage:** `projektplan.md` §4 M5, `architekturplan.md` Abschnitte 4 (Discovery) und 5 (Katalog), `projektuebersicht.md` §5, `KLAERUNGEN.md` B10–B13, `adr/0018` (Sentinel-1), `adr/0021` (Suchfilter), `adr/0022` (Datennähe), `adr/0023` (Quellenkatalog), `adr/0024` (Prototyp-Quellen), `adr/0025` (Harvest-Pipeline), `adr/0026` (Hybrid-Suche), `adr/0027` (Quellen mit Konto), `adr/0029` (Leseweg NetCDF), `adr/0030` (Operatoren je Datensatz), `adr/0031` (automatisches Onboarding), `adr/0032` (Übersicht und Mosaik bei kleinem Zoom), Backlog `docs/plans/nach-m4-backlog.md`.
**Rangfolge:** ENTSCHEIDUNGEN_2026-09-18.md > KLAERUNGEN.md > dieser Plan > CLAUDE.md.

## 1. Ziel (Projektplan)

Der eigentliche „Datacrawler“: Datensätze finden, prüfen, freigeben und auffindbar machen.

- **Inhalt:** Trichter Stufen 0 und 1 (STAC Index/Atlas, STAC-Collection-Suche, CKAN, DCAT-AP, OAI-PMH nach Bedarf); Pipeline mit Zustandsautomat, Rohspeicherung, Inhalts-Hash; Verify; Dedupe mit Distributionen; Git-basierter Review; Health-Checks; Hybrid-Suche mit Volltext, Vektor und RRF; Bewertungs-Set für Suchqualität.
- **Funktionen:** AOI-zuerst-Suche; Verfügbarkeits-Zeitleiste; Eignungskarte pro Datensatz; „zuletzt erfolgreich geprüft“ sichtbar; Datensatz-Wünsche und Fehlermeldungen; JSON-LD und Sitemap für eigene Auffindbarkeit.
- **Abnahme:** §7 (Fassung 3; ersetzt den Entwurf aus dem Projektplan, `adr/0025` F7).

## 2. Vorgaben von Otto (31.10.2026)

Wörtlich:

> ich will mich bei den datenquellen auf den DACH raum vorerst fokussieren, also so ESA bzw satellitendaten sowieso immer (auch von JAXA oder NASA usw) aber ich will auch daten von den nationalen behörden der Dach länder (also metereologie usw.)) Ich will eigentlich nur frei verfügbare quellen haben die ohne key funktionieren und rechtlich abgesichert sind. ABer ich will (nur für mich jetzt im prototypen, in de released version sollen die wieder verschwinden) auch daten haben die rechtlich fraglich sind ob sie verwendet werden dürfen. und wegen anonymen api keys haben wir eh schon mal gesprochen.

Daraus:

1. **Satellitendaten immer:** ESA/Copernicus, dazu JAXA, NASA, USGS und andere Raumfahrtagenturen, soweit frei.
2. **DACH-Behörden zuerst:** nationale Stellen in Deutschland, Österreich, Schweiz (und Liechtenstein), z. B. Wetterdienste, Vermessung/Geodaten, Umwelt, Hydrologie.
3. **Nur frei und ohne Schlüssel:** kein Konto, kein eigener API-Key. Ein **anonymes Token**, das die Quelle ohne Anmeldung ausgibt (wie beim Planetary Computer, `adr/0018` §11 C), gilt als „ohne Schlüssel“.
4. **Rechtlich abgesichert:** Lizenz geprüft und nach B11 eingestuft (Katalogeintrag / Anzeige / Processing); Lizenz-Freigabe immer durch Otto, auch über Lizenzregeln (`adr/0025` §6.7).
5. **Prototyp-Quellen:** Für Ottos eigene Erprobung im Prototyp auch Quellen mit **unklarer Rechtslage**. Sie verschwinden in der veröffentlichten Version. Geregelt in `adr/0024`.
6. **Kostenlose Konten:** zählen vorerst **nicht** als „ohne Schlüssel“. In M5 nur Katalogeinträge mit Link und `access.account` (`adr/0027`).
7. **Jeder Datensatz hat Eigenheiten (Otto, 31.10.2026):** beim Processing (Fähigkeiten, eigene Operatoren), bei der erweiterten Suche (Filter, DS-02) und bei Schnellrechnungen (Index-Knöpfe, NM4-14). Das Onboarding jedes Datensatzes legt diese drei Teile ausdrücklich fest; sie stehen in der Registry, nicht im Code des Frontends. Was je Datensatz sinnvoll ist, legt `adr/0030` fest.
8. **Zusatz Otto (06.11.2026):**
   - **Operatoren je Datensatz:** → `adr/0030` (M5-12, erledigt).
   - **Control Panel:** je Seite so viele Datensätze, wie ohne Scrollen passen, ohne Obergrenze (Otto, 07.11.2026; Vorauswahl beim ersten Besuch höchstens sechs); Seitenpfeile klein oben neben „Datasets“ (Otto, 06.11.2026 abends).
   - **„Advanced search“** immer sichtbar.
   - **Kein zusätzlicher Text** im Panel.
   - **Datum:** begrenzt auf den verfügbaren Zeitraum und am Anfang mit frühestem und spätestem Aufnahmedatum des Datensatzes vorausgefüllt (Otto, 06.11.2026 abends).
   - **Data catalogue:** größeres Fenster über der Karte, geöffnet über ein Symbol in der linken Leiste (UI-05 F5); gruppiert, mit Angaben wie bei STAC und der Quelle; darin später die Suche (`adr/0026` §7).
9. **Zusätze Otto (07.–11.11.2026)**, gelten für alle Aufgaben mit Frontend:
   - **Keine Hinweise, Marken oder Zusatztexte** im Frontend; nötige Erklärungen höchstens im Tooltip. Lizenzpflichtige Nennungen (z. B. Copernicus beim Ersatz-Datensatz) stehen in der Quellenzeile der Karte, nicht als Hinweis.
   - **Das Panel scrollt nie.**
   - **Nie verschwindet ein Bild beim Herauszoomen** (`adr/0032`): unter `min_zoom` eine Übersicht oder ein Ersatz-Datensatz, nie eine leere Karte.
   - **Kompass immer sichtbar** wie bei Google Maps, 3D-Knopf unter den Zoom-Knöpfen (UI-06).
   - **Ausgabetypen nur, wo sie Sinn machen** (#333): Werte unverändert → Typ der Quelle plus `float32`; neu gerechnet → nur `float32`, bei Quelle `float64` dann `float64` (Vorgabe) und `float32`; Angabe `x-earthx-passes-values` aus der Operator-Registry. Wiedervorlage `float64` bei M5-11.
   - ~~**Keine Marke „Overview“** an Pyramiden-Layern (Korrektur zu `adr/0032` F12, 11.11.2026), höchstens Tooltip.~~ Ersetzt (Otto, 16.11.2026, UI-08): eine Marke „Overview“ überall, wo die Karte eine vergröberte Ansicht zeigt (Job-Ergebnisse, Pyramiden, Ersatz), gleicher Platz und Tooltip.
   - **Ladesymbol** (13.11.2026): Dauert das Laden einer Kartenebene länger, erscheint ein Ladesymbol (Leitfaden, kein Text); allgemein, umgesetzt mit M5-30b in #345.
   - **Nie verschwindet ein Bild, auch nicht zwischen zwei Teilen einer Aufgabe** (13.11.2026, Browserprüfung #345).
   - **Ladeanzeige auf der Karte** (14.11.2026): wie beim Laden der Suchergebnisse, dasselbe Bauteil, Text „Loading data“ (ersetzt „kein Text“); Symbol in der Zeile der Ebene bleibt.
   - **Einheiten im Band-Menü** (14.11.2026): nur physikalische Einheiten (z. B. „m“); DN und einheitslose Werte dort ohne Einheit. Im Data catalogue steht je Band immer die Einheit bzw. Art der Werte (auch „DN, uncalibrated digital numbers“). Umsetzung in #343.
   - **Statusbox oben** (14.11.2026): immer mittig im freien Kartenbereich zwischen offenem Panel links und rechts, bei Bedarf schmaler, nie überdeckt; nur der Data catalogue darf sie überdecken. In #345, falls dieselbe Box wie „Loading data“, sonst eigene kleine Aufgabe.
10. **Zusätze Otto (11.11.2026 abends)**, noch ohne ADR:
   - **Keys der Nutzer erlaubt** (ändert Punkt 6 und `adr/0027`): Quellen mit Key oder kostenlosem Konto (z. B. Copernicus Data Space) dürfen angebunden werden. Der Nutzer hinterlegt seinen Key selbst beim Datensatz im Data catalogue; ein Key schaltet alle Datensätze desselben Anbieters frei; solche Datensätze tragen ein **kleines Schloss** (ausdrückliche Ausnahme von „keine Marken“) und lassen sich freischalten; der Key wird laufend auf Gültigkeit geprüft. Kein Key der Plattform, keine Secrets im Repo. → M5-32.
   - **Processing-Panel mit Reitern** (General, Optical, Radar …), je Reiter die häufig gebrauchten Verarbeitungen. Gemeint ist das Panel, in dem man einen Auftrag zusammenstellt, nicht die Job-Liste. → UI-07.
   - **Radar: Standard-Verarbeitung, kein InSAR** (`adr/0030` bleibt): Orbit, thermisches Rauschen und Randrauschen, Kalibrierung σ⁰/γ⁰, Speckle, Terrain Flattening, Geländekorrektur GTC/RTC, dB, Verhältnisse. Vollständige GRD-Produkte mit Annotation gibt es über Copernicus Data Space mit Key; im AWS-Bucket fehlt die Annotation (`adr/0018` §3.1), die Verweise der Items zeigen zudem auf die RFI-Annotation (Befund #343). → M5-31.
   - **Zwei Bilder gleichzeitig verarbeiten und vergleichen** → M5-26, vorgezogen und erweitert.
   - **Sentinel-1 nur in Radargeometrie**, solange es keine richtige Bearbeitung gibt → DS-04d.
11. **Arbeitsweise (13.11.2026):** eine Aufgabe, ein PR, höchstens zwei. Jeder weitere Teil bekommt eine eigene Nummer und eine neue Session. Grund: M5-30b mit zehn Teilen führte zu gestapelten PRs, Konflikten zwischen den Teilen und halbfertigen Zwischenständen.
12. **Alle Geodaten auffindbar (Otto, 14.11.2026):** Ziel ist, alle Geodaten der Anbieter über die Seite erreichbar zu machen, auch Tabellen (Excel, CSV), Vektordaten, Dokumente und Dienste.
   - **In M5:** Stufe „gelistet“ für alle Datentypen: Eintrag im Data catalogue mit Titel, Anbieter, Lizenz, Format, Beschreibung, räumlicher und zeitlicher Ausdehnung und Link zur Quelle; die Datei holt der Browser direkt beim Anbieter. Der Crawler (M5-19 bis M5-21) verwirft Nicht-Raster nicht mehr, sondern listet sie. Karte und Processing bleiben vorerst Raster.
   - **Auch ohne direkten Download (Otto, 14.11.2026):** Daten, die die Plattform nicht selbst anbieten kann (Bestellung, Anmeldung, Konto, kostenpflichtig, nur auf Anfrage, Portal ohne Datei-Link), werden ebenfalls gelistet, mit Link auf die Seite des Anbieters, über die man sie bekommt, und der Art des Zugangs (`access.account` bzw. neue Angabe). Das ändert `adr/0031` §8 und §9 Fall 5 (Konto-Quellen: bisher Stopp mit Notiz, gelistet nur mit `way: listed`) zu „gelistet als Vorgabe“. Lizenz-Einstufung und Freigabe im PR bleiben bei Otto.
   - **Filter im Data catalogue:** nach Region und Zeit, auch über die AOI aus „Search and area“; gilt für alle Einträge, auch gelistete. Dafür muss der Harvest Ausdehnung und Zeitraum je Eintrag erfassen; offen, wie Einträge ohne bekannte Ausdehnung im Filter behandelt werden (Frage in M5-20).
   - **Später (eigene Vorlage, M6 oder danach):** Vorschau von Tabellen auf der Seite; Tabellen mit Koordinaten (z. B. Messstationen) als Punkte auf der Karte; Vektordaten (GeoJSON, Shapefile, WFS) auf der Karte.
   - Log-Zeile dazu fehlt noch im Repo; nimmt die nächste Session mit, die den Crawler oder den Data catalogue anfasst (M5-17 oder M5-20).

## 3. Was mit M5 zusätzlich ansteht

- **DS-04** Sentinel-1 anbinden (`adr/0018` Fassung 2), **DS-05** SAR-Operatoren, aufgeteilt nach `adr/0030` §9 in DS-05a bis DS-05d.
- **`data_region`**: erledigt mit M5-07 (#298).
- **Datensatz-Browser**: als „Data catalogue“ in UI-05; Suche darin mit M5-23.
- **Health-Checks** je Quelle, „zuletzt erfolgreich geprüft“ sichtbar: M5-24.
- **Earth Search v2** (Backlog 36): weiter Beta ohne öffentlichen Endpunkt; keine Aufgabe in M5, solange das so bleibt.
- **`harvester`**: heute eine leere Hülle (`adr/0025` §2); wird mit M5-24 zum Takt der Pipeline.
- **Mosaik-Zoom bei groben Rastern** (Backlog 29): durch `adr/0032` geregelt (M5-30); Prüfpunkt bleibt in M5-11 für das erste NetCDF-Raster.

## 4. Entscheidungsvorlagen (alle angenommen)

| | Thema | ADR | PR |
|---|---|---|---|
| A | Quellenkatalog DACH und Satellit | `adr/0023` | #262, #295 |
| B | Harvest-Pipeline | `adr/0025` | #300 |
| C | Hybrid-Suche und Bewertungs-Set | `adr/0026` | #301 |
| D | Prototyp-Quellen | `adr/0024` | #260 |
| E | Quellen mit kostenlosem Konto | `adr/0027` | #261 |
| — | Leseweg NetCDF/HDF5 | `adr/0029` | #303 |
| — | Operatoren und Quick processings je Datensatz | `adr/0030` | #302 |
| — | Automatisches Onboarding (M5-29) | `adr/0031` | siehe Log |
| — | Übersicht und Mosaik bei kleinem Zoom (M5-30) | `adr/0032` | siehe Log |

Kernpunkte für die Umsetzung:

- **`adr/0023`:** Quellen von Hand: WorldCover (zwei Datensätze), swissALTI3D, BEV ALS-DGM 1 m; Lizenzvorschläge angenommen, Wortlaute bestätigt Otto im PR; `data_region` als `<betreiber>:<ort>` bzw. `unknown`. Offen bis M5-08: mehrere Stände je Kachel.
- **`adr/0024`:** `legal_status` (`cleared`/`unclear`), Präfix `proto-`, YAML außerhalb des Images, Laden nur mit `EARTHX_PROTOTYPE_SOURCES` und `EARTHX_PROFILE=local`, nie in CI und Runner; Ergebnisse erben den Status (F11).
- **`adr/0025`:** Befehle in `discovery`, Zustand in Postgres, Kandidaten in Git, PR durch Otto (P1); Harvest in M5 nur lokal bei Otto; Stufe „gelistet“ (B11 Stufe 1); Kandidatendateien; höchstens 20 Kandidaten je PR; CKAN mit Herausgeberliste; Lizenzregeln „Herausgeber + Lizenz-URI → Stufe“; `User-Agent` Pflicht in `gateway`; YAML unter `backend/catalog/`; Schnitt in sieben Schritte (§8 dort).
- **`adr/0026`:** Volltext (`simple`, `german`, `english`, `unaccent`, Trigramme, Glossar) und Vektor (multilingual-e5-small/-base, int8, im Prozess `api`, nicht im Runner-Image), **ohne pgvector** (Vektor als Spalte, Vergleich in `api`); RRF k = 60; harte Filter vor der Fusion; Collection Search mit `q`, Fläche nur per `POST`; Index in `catalog-load`; Bewertungs-Set mit 50 Fragen, Grenze Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8 je Sprache.
- **`adr/0027`:** Konto-Quellen nur als Katalogeintrag mit Link; `access.account` (`none`, `anonymous_token`, `free_account`, `requester_pays`); Regel R-Z.
- **`adr/0029`:** eigene virtuelle Verweise (h5py nur in `discovery`), ein Item je Zeitschritt, Verweise im Item, ETag-Prüfung beim Lesen, Fehlerart `source_changed`; zuerst nur abgeschlossene Jahresdateien; ARCO-ERA5 nicht in M5.
- **`adr/0031`:** geplante Aufgabe, ein Sammel-PR je Tag mit neuen Datensätzen, Profile je Quellenart, Prüflauf in GitHub Actions; vorher die Vorarbeiten V1–V9 (§6.2); Lizenz-Einstufung bleibt bei Otto.
- **`adr/0032`:** Übersicht bei kleinem Zoom; Budget je Kachel 32 Dateien und 4 s, `MOSAIC_THREADS` 4; Teilkacheln mit Kopf `X-EarthX-Partial`, `no-store`, ohne Marke; Mosaik-ID aus dem Hash der Item-Liste (bis 2000 Items); Kostenschätzung statt 25er-Grenze; Pyramide nur für GLO-30 und WorldCover (Bau gleich nach `materialize`, 0,25 s Abstand, Ablauf 30 Tage mit Verlängerung nach bedingter Prüfung); unter `min_zoom` von swissALTI3D und BEV zeigt GLO-30 als Ersatz (F7 = 1), Copernicus in der Quellenzeile.
- **`adr/0030`:** Operator-Art `focal` (in M5-10), `sar_db` mit Wertetabelle, Speckle-Filter Boxcar/Lee, σ⁰-Kalibrierung, Felder `composite_presets` und `step_presets`, vier Sentinel-2-Presets, Klassenanteile WorldCover; keine eigene InSAR, kein Pauli; Quick processings auf S1 als Nachtrag M5-12 zu `adr/0018` F3.

## 5. Antworten Otto (31.10.2026)

1. **Reihenfolge:** zuerst ADR A und zwei bis drei Quellen von Hand, dann die Pipeline (ADR B).
2. **Datentypen:** zunächst nur Raster. **Geändert (Otto, 14.11.2026, §2 Punkt 12):** gelistet werden alle Datentypen; Karte und Processing vorerst nur Raster.
3. **Prototyp-Quellen:** dürfen ins öffentliche Repo, aber markiert (`adr/0024`).
4. **Anonyme Tokens** zählen als „ohne Schlüssel“, kostenlose Konten nicht (`adr/0027`).
5. **Discovery-Umfang:** feste Liste bekannter Quellen plus STAC Index, dazu CKAN/DCAT-AP für GovData, data.gv.at und opendata.swiss; offene Suche in Paket 7b.
6. **Bewertungs-Set:** Session entwirft 30–50 Testfragen, Otto ergänzt und gibt frei (in `adr/0026` F4 freigegeben).

## 6. Schnitt der Umsetzung (Fassung 3)

### 6.1 Erledigt

| Aufgabe | Inhalt | PR |
|---|---|---|
| M5-01 bis M5-06, M5-12 | Entscheidungsvorlagen (§4) | #260–#262, #295, #300–#303 |
| M5-29, M5-30 (ADR) | `adr/0031`, `adr/0032` | siehe Log |
| M5-07 | ESA WorldCover 2020/2021, `data_region` für alle Datensätze | #298 |
| UI-05 Teil 1 | Control Panel mit Seiten, „Advanced search“ immer sichtbar, Datum begrenzt, kein Zusatztext | #299 |
| UI-05 Teil 2 (UI-05b) | Data catalogue als Fenster, Registry-Felder für Gruppe, `providers`, `gsd` | siehe Log |
| UI-06 | 3D-Ansicht, Kompass immer sichtbar | siehe Log |
| M5-13 | YAML-Lader, alle Einträge unter `backend/catalog/datasets/` | siehe Log |
| M5-18 | `gateway`: `User-Agent`, Abstand je Host, `robots.txt` | siehe Log |
| M5-08 a–c | Allgemeiner STAC-Adapter, swissALTI3D, mehrere Stände je Kachel | siehe Log |
| DS-04 a–c | Sentinel-1 GRD (TPS, Fassung über CRC64NVME mit Rückfall auf ETag) | siehe Log, #327 |
| M5-15 | Sentinel-2-Presets NDMI, MNDWI, NDREI, SAVI | siehe Log |
| M5-22 Teile 1 und b | Bewertungs-Set, Suchtext, lexikalischer Arm mit Glossar | siehe Log |
| M5-28 | nodata-Regeln (float → NaN; Ganzzahl: Randwert, Verschieben bei Kollision, Klemmen), Runner 0.5.1 | siehe Log |
| M5-30b Teile 1, 2, 5, 6 | Übersicht und Mosaik bei kleinem Zoom, Messung, Budgets | #329–#332, #339 |
| — | Ausgabetypen nur, wo sinnvoll (§2 Punkt 9) | #333 |
| — | CI: Doku-PRs schnell; Pin `ubuntu-24.04`; Logger-Fix im Test; Backend in vier parallelen Teilen (6 statt 15 min) | #304, #322, #336, #338 |
| — | Weitere Nachträge | #316, #328 |
| M5-22 Teil c | Collection Search mit `q`, Zahl am Namen, Q51 | #337 |
| F11 | Quicklook für Sentinel-1 über Kacheln (`gcp_tps`) statt PNG | #340 |
| M5-30b Teil 7 | GLO-30 als Ersatz unter `min_zoom` von swissALTI3D (F7 = 1) | #341 |
| M5-35 | Prüfung Skalierbarkeit (`docs/plans/m5/m5-35-skalierbarkeit.md`), F1–F7 = 1, F4 mit Bedingung; Folgeaufgaben M5-36 bis M5-42 | #351 |
| M5-41 | Nachtrag `adr/0026` F3: pgvector ≥ 0.8.4, HNSW auf `halfvec`, gefiltert exakt bis 5·10⁴ Zeilen; Messung mit echten Embeddings in M5-23 | #354 |
| M5-40 | Gelistete Einträge in Postgres (Migration 021, `categories.yaml`, `keywords`, `blocked.yaml`, Grabstein 410, Blättern), Data catalogue mit Gruppen je `category`, Nachladen, Filter-Popup mit × je Feld, „Filter by search panel“, Suchfeld (`q`), „Add dataset“ im Search panel | #356, #358 |
| M5-10 | Geländeoperator `terrain` (Neigung, Exposition, Schummerung) mit Operator-Art `focal`, bitgleich auf jeder CPU; Schritt „Terrain“ im Panel; gerechnete Bilder in allen Ansichten bis z0 (auf Pyramide bzw. Ersatz). Nahtlinie an Dateigrenzen in Kacheln akzeptiert (Otto 16.11.). GLO-30 unter z7 nach lokalem Bau 17.11. kontrollieren | #350, #357 |
| M5-38 | Pyramiden: `extend` und `sweep` unter Sperre (Lease-Zeile, Migration 019 `earthx_overview_upkeep`) | #353 |
| M5-39 | `adr/0033` Freigabe gelisteter Einträge (drei Ebenen, Warteliste, Sperrliste mit Grabstein, neue Felder) | #352 |
| DS-04d | Sentinel-1 in Radargeometrie (ohne CRS/Geotransform, GCPs bleiben, `mask.tif` wie M3-18, Mosaik je Durchgang mit `line_times`, eigene Fehlerarten, `reprojection: false`, Ergebnis-Layer pixelgenau je Slice, Einheit „DN“ nur im Data catalogue, Runner 0.5.2) | #343 |
| F12 (DS-04) | Originale von Sentinel-1: dritter Satz in `limitations`, `limitations` als Abschnitt in `ATTRIBUTION.txt`, keine Beschriftung im Frontend | #344 |
| — | Doku-Runde Fassung 3.1, zugleich Nachweis des Doku-Pfads der CI | Doku-PR 11.11. |

### 6.2 Offen

Stufe A: ohne Plan-Datei, direkt umsetzen. Stufe B: Plan unter `docs/plans/m5/` (UI unter `docs/plans/vp3/`) mit Fragen im Draft-PR, Umsetzung nach Ottos Antworten im selben PR. Stufe C: nur Entwurf (ADR, Bericht).

**In Arbeit (13.11.2026):**

| Aufgabe | Inhalt | Stand |
|---|---|---|
| **M5-30b** | Umsetzung `adr/0032` – abgeschlossen mit #355 (15.11.); GLO-30-Pyramide lokal im Bau | erledigt |
| **M5-36** | Grenzen je Host für alle Instanzen: `backend/catalog/hosts.yaml` (Pflicht je Host), ein Zähler je Host und Prozess für GDAL, HTTP und Zarr, Teilung durch `EARTHX_SOURCE_INSTANCES` für `api` und `tiler` zusammen, nur Warten statt Verweigern | Plan in #360, G1–G6 = 1 (Otto 16.11.: FSDI 6 Verbindungen und 1 s Abstand für `materialize`, Earth Search 6, S3-Buckets je 32; Kacheln und Suche ohne Abstand; ≤ 5 % langsamer; zwei PRs); PR 1 #360 gemergt; PR 2 in #365 (Teilbudget, alle Lesestellen des `tiler`, Messung; H1 = 1, hinnehmen) |
| **UI-08** (ohne schmale Fenster) | Kästchen schalten nur an Kästchen und Text; Layer erholt sich nach einem Neustart der Dienste selbst (gescheiterte Kacheln erneut laden); Statusbox über den Panels unter 240 px frei; Marke „Overview“ einheitlich für Job-Ergebnisse, Pyramiden und Ersatz (Otto, 16.11.) | Draft-PR #363 |

**M5-30b im Einzelnen** (Merge jeweils mit Merge-Commit):

| Teil | Inhalt | PR | Stand |
|---|---|---|---|
| 1, 2, 5, 6 | Messskript, Budget je Kachel, Vorarbeiten | #329–#332 (über #339) | gemergt |
| 7 | GLO-30 als Ersatz unter `min_zoom` | #341 | gemergt |
| 3a | Auswahl-ID (Backend), Migration 017 | #335 | gemergt 14.11. |
| 3b | Auswahl-ID im Frontend, 64 fällt, Rückfall 40 nach Lage; Ersatz in der Ansicht (Fehler behoben), Umrisse aller ausgewählten Szenen (Schnitt bei 40 entfernt), Ladesymbol auf der Karte über dem Kompass nach 0,6 s und in der Zeile, höchstens 2 gleichzeitige Mosaik-Kacheln je Prozess | #345 (Basis 3a) | gemergt 14.11. (mit Ladeanzeige „Loading data“ und Statusbox zwischen den Panels) |
| 8a | Lesen mit 0,25 s je Host, Kern der Pyramide | #346 | gemergt 14.11. |
| 8b-1 | Tabellen (Migration 018), Bauwunsch aus `materialize`, Präfix `overviews/` mit 31 Tagen | #347 (Basis #346) | gemergt 14.11.; lokal einmal `objectstore-init` |
| 8b-2 | Bau im eigenen Faden, zwei Kindprozesse, Upload; band-select auf „uint16“ | #348 (Basis #347) | gemergt 14.11.; `--force` bestätigt nicht, ein PR |
| 8b-3 | Pflege: Bestätigung durch unveränderten `materialize`-Lauf, Verlängerung bis 31 Tage − 12 h, Neubau abgelaufener, Aufräumen `proto-*` | #349 (Basis #348) | gemergt 14.11.; Auslegungen §8.10 bestätigt; lokale Prüfung (GLO-30, ~3,6 h) offen |
| 9 (+4, 10) | Kachelroute aus der Pyramide (GLO-30 unter z7, WorldCover unter z5, swissALTI3D unter z7 aus der GLO-30-Pyramide nur über der Schweiz), `min_zoom` DEM 7 und WorldCover 5, Regel „Pyramide verlangt `min_zoom` ≥ 1“, Thread-Pool (Warten außerhalb des Pools, eigenes Tor für Pyramidenkacheln), Browser-Test #319 F13, Nachträge | #355 | gemergt 15.11. (inkl. Footprint-Auswahl für Suchergebnisse und Szenenansicht, Robustheit des Baus, Migration 020) |

Reihenfolge: alle Teile gemergt; M5-30b abgeschlossen 15.11.
**Stand lokaler Bau (15.11.):** `objectstore-init` erledigt. Erste Bauten auf pr-355 scheiterten alle mitten im Lesen ohne Logzeile (GLO-30 bei 8 %, WorldCover 2020 bei 9 %, WorldCover 2021 bei 51 %, `failure_kind = unknown`); während der Läufe lief bei Otto ein schwerer anderer Prozess → Speichermangel wahrscheinlich. Stand #355 (15.11. nachm.): Netzfehler werden als `source_unreachable` erkannt, bis 4 Versuche mit Backoff und Retry-After (≥ 0,25 s je Host), unlesbare Basiskachel ausgelassen (Tabelle `earthx_overview_omitted`, Migration 020), stündlicher Nachbau über die Sperre aus #353; Ausfall ab > 5 % und > 3 fehlenden Basiskacheln; `source_unreachable` nach 1 h bis 3-mal automatisch wiederholt; gleiche `version` bei WorldCover 2020/2021 gewollt (ETag des gemeinsamen Gitters); GLO-30 dauert eher 6–7 h. Vorfall: ein Subagent baute WorldCover 2020 am `gateway` vorbei gegen die echte Quelle – nicht erlaubt, im Log festzuhalten. #355 fertig gemeldet 15.11. (Nachbau-Tests rot gegengeprüft; Host-Sperre `earthx_overview_host` in Migration 020, Lease nur für den Nachbau, Bau hält Hosts über seine Zeile – ok Otto; Vorfall im Log, Arbeitsdateien gelöscht). Lokal 15.11. abends: WorldCover-Pyramiden ohne Last durchgelaufen. Browserprüfung: Crop and merge bis z0 ok, Suchergebnisse und Szenenansicht verschwinden unter `min_zoom` → in #355 neue Footprint-Auswahl (Hash der Treffer, 1–N) für diese beiden Ansichten (Otto 1.1); Vorschau und Index-Darstellungen unter `min_zoom` (auch in Crop and merge und angehefteter Ebene) schließt M5-10 PR B (2.1, 3.1). Merge nach kurzem Blick auf `earthx_overview_omitted` und Browserprüfung WorldCover unter z5; danach Bescheid an M5-40 (main holen, Konflikte) und M5-10 (PR 2). GLO-30 (6–7 h) lokal erst Dienstag 17.11. abends; danach GLO-30 unter z7 (auch Neigung aus M5-10) im Browser ansehen; scheitert der Bau, kleine Folgeaufgabe. Nächster Schritt Otto ohne Last: `git pull origin pull/355/head`, `docker compose build`, `up -d`, `materialize esa-worldcover-2021` und `-2020`, `docker stats`, SQL-Abfragen (`earthx_overview`, `earthx_overview_omitted`); danach GLO-30 über Nacht. Session baut in #355: Fehler des Kindprozesses mit Art, Grund, Basiskachel und Exit-Signal ins Log; Wiederholen mit Backoff (429/503, Retry-After); unlesbare Basiskachel auslassen und stündlich nachbauen; gleiche `version` bei WorldCover 2020/2021 klären. Migration: 019 ist von M5-38 (#353, gemergt 15.11.) belegt → #355 holt main, nimmt 020 und nutzt die Sperre aus #353.
**Für Otto nach dem Merge von #346–#349 (vor dem Merge von Teil 9):**
1. Einmal `objectstore-init` (vermutlich `docker compose run --rm objectstore-init`; Befehl in README bzw. M5-30-Plan §8.10 prüfen). Ohne die neue Regel für `overviews/` startet der Worker nicht.
2. Lokale Prüfung über Nacht: `docker compose up`, dann `docker compose run --rm materialize cop-dem-glo-30` (Bau ~3,6 h, ~1 GB). Morgens im Worker-Log „overview build ended“ ohne Fehler; Abfrage `SELECT dataset_id, status, progress, attempts, failure_kind FROM earthx_overview;`; Objekte unter `overviews/cop-dem-glo-30/…`; `materialize` unverändert wiederholen → nach der stündlichen Runde „overview pyramids extended“. Genaue PowerShell-Befehle in M5-30-Plan §8.10. Befunde gehen in Teil 9.
Antworten zu 8b-2 (an die Session geschickt 13.11., Umsetzung nach #345/#335): alle vier Option 1; der regelmäßige Lauf von `materialize` kommt später vom Prozess `harvester` (M5-24), bis dahin von Hand. Auslegungen #341: Ausdehnung = gewählter Datensatz und „ohne schreibbare Quellenangabe kein Ersatz“ bestätigen; „höchstens 500 Items je Ersatzkachel“ klären lassen (Budget 32 Dateien und 4 s gilt auch dort).

**Noch nicht gestartet:**

| Aufgabe | Inhalt | Stufe | Modell, Effort | Hängt ab von |
|---|---|---|---|---|
| **M5-32** | ADR: Keys der Nutzer (§2 Punkt 10): Ablage vor dem Login (Browser oder Server), Weg durch api, gateway und Runner ohne Zustand im Worker-Kern, nie in Logs/URLs/Rezepten/Hashes; Art der Keys je Anbieter (zuerst Copernicus Data Space), Prüfung und Ablauf; Cache von Ergebnissen aus Key-Daten; Registry (`access.account` mit Anbieter, Schloss); Sicherheit im öffentlichen Repo | C | Opus, hoch | — |
| **M5-31** | ADR: Radar-Verarbeitung (§2 Punkt 10) mit Stand der Technik: GRD-Kette selbst rechnen (sarsen, pyroSAR/SNAP, ISCE3) vs. fertige RTC-Produkte (Planetary Computer `sentinel-1-rtc`, ASF/OPERA); vollständige GRD über Copernicus mit Key; Inhalt des Reiters „Radar“; kein InSAR | C | Opus, hoch | — |
| **M5-26** | ADR: mehrere Eingaben, vorgezogen und erweitert: zwei Bilder verarbeiten und vergleichen (zwei Zeitpunkte, zwei Datensätze; Differenz, Verhältnis, Veränderung; Angleichen der Raster; Anzeige nebeneinander/Swipe; Zeitschritte M5-11) | C | Opus, hoch | — |
| **UI-07** | Reiter im Processing-Panel (`docs/plans/vp3/ui-07-processing-reiter.md`) | B | Opus, hoch | M5-31, M5-26, M5-32 entschieden |
| **UI-08** | Rest (Otto, 16.11.): schmale Fenster gesammelt (Statusbox überdeckt bei 360 px den Kompass); der übrige Teil ist in #363 | B | Opus, mittel | M5-30b abgeschlossen |
| **M5-37** | Zeiger und Unterbrecher je Host in Postgres (Muster der Ortssuche) für Harvester, `materialize` und Pyramidenbau (M5-35 F1) | B | Opus, hoch | M5-36; vor M5-19 und M5-24 |
| **M5-43** | Postgres-Image `postgis/postgis:16-3.7` plus pgvector ≥ 0.8.4 (eigenes Dockerfile) für Compose, CI und Cloud-Umgebung; ersetzt das nicht mehr gebaute `16-3.4`; CI baut das Dockerfile im Job mit Layer-Cache, Bauzeit messen; Cloud-Setup baut pgvector (gilt erst für neue Sessions). **Erlaubnis Otto für `.github/` und Setup der Cloud-Umgebung nötig** | B | Opus, mittel | M5-41 gemergt; vor M5-23 |
| **M5-42** | Lexikalische Suche indexfähig (M5-35 Befund B7) | B | Opus, mittel | M5-41 |
| **M5-34** | Normalize im Processing (Otto, 14.11.): Bereich „From“ aus den Daten wählen – Min/Max, Perzentile (z. B. 2–98 %, 1–99 %, eigene), dazu das Histogramm der Verteilung zum Wählen; Fragen im Plan: Werte aus der Vorschau-Statistik (schnell, näherungsweise, als Zahlen ins Rezept) oder exakt im Job (wie NM4-71); Bedienung wie „Scale“ (absolute/percentile) in der Seitenleiste. Dazu (Otto, 14.11.): „Bands to process“ heißt „Bands in output“; Normalize erzeugt wie Band math ein neues Band mit vorbelegtem, änderbarem Namen (z. B. `VV_norm`), das sich zu „Bands in output“ hinzufügen lässt, das Original bleibt wählbar; gilt für alle bandverändernden Schritte (Otto, 14.11.; Bezug `adr/0020`, `adr/0028`). Befund: Vorgabe „From“ −1000..1000 passt nicht zu DN von Sentinel-1 | B | Opus, mittel | M5-30b abgeschlossen |
| **M5-33** | swissALTI3D genau verorten (Otto, 13.11.): offizielle Korrekturdatei von swisstopo (CHENyx06) statt Näherung, damit die Lage nicht ~1 m abweicht; Lizenz der Datei klären, Datei im Image (PROJ ohne Netz zur Laufzeit, B8), gilt für Karte, Zuschnitt und Jobs; `limitations` neu: Satz zur Ungenauigkeit entfällt, neu „When zoomed out, the map shows Copernicus DEM GLO-30 instead.“ Gilt auch für BEV (EPSG:3035/MGI) prüfen. Dazu: Download und Zuschnitt im Originalformat (LV95) prüfen bzw. sicherstellen; Quellenzeile zeigt „©swisstopo“ und „©swisstopo (modified)“ gleichzeitig – nur eine Angabe, passend zum Gezeigten | B | Opus, mittel | M5-30b abgeschlossen |
| **M5-09** | BEV ALS-DGM 1 m über ATOM, EPSG:3035; Ersatz GLO-30 unter `min_zoom` wie swissALTI3D | B | Opus, mittel | Fix zum Herauszoomen aus #345 gemergt |
| **M5-17** | Stufe „gelistet“ (`adr/0025` §6.1a, Schnitt 2) für alle Datentypen (§2 Punkt 12, mit Log-Zeile) und erste Katalogeinträge mit Link: CORINE (`free_account`), Landsat (`requester_pays`) (`adr/0027` W0) | B | Opus, mittel | M5-40 gemergt |
| **M5-19** | Harvest-Kern (`adr/0025` Schnitt 4): Tabellen, Fetch und Extract für STAC-API und CKAN, Lauf-Befehl | B | Opus, hoch | M5-37 gemergt |
| **M5-14** | Preset-Felder `composite_presets` und `step_presets` (`adr/0030` F7), Anzeige in „Quick processing“ | B | Opus, mittel | — |
| **M5-11** | Erste Meteorologie-Quelle MeteoSchweiz nach `adr/0029` (zwei PRs: Verweise und Lesen; Datensatz); Wiedervorlage `float64` (§2 Punkt 9) | B | Opus, hoch | — |
| **M5-20** | Verify, Enrich (inkl. räumlicher und zeitlicher Ausdehnung, alle Datentypen, §2 Punkt 12), Dedupe, Kandidaten, `discovery propose`, Lizenzregeln, Skript und Anleitung für Ottos lokalen Lauf (`adr/0025` Schnitt 5, §6.7) | B | Opus, hoch | M5-19, M5-17 gemergt |
| **V1–V9** | Vorarbeiten für das automatische Onboarding (`adr/0031`), danach richtet Claude im Planungs-Chat die geplante Aufgabe ein | B | laut `adr/0031` | laut `adr/0031` (in der Liste nach M5-20) |
| **M5-16** | WorldCover: Klassenanteile in der AOI aus der Ergebnis-Statistik (`adr/0030` F9) | B | Opus, mittel | — |
| **M5-23** | Suche Teil 2 (`adr/0026` §6 Schritte 3 und 4): Vektorarm, Modellwahl am Set, eigene Dockerfile-Stufe, RRF; Entscheidung pgvector ja/nein neu nach M5-35 (viele gelistete Einträge); Suchfeld und Filter kommen schon mit M5-40 PR 2, M5-23 bringt den Vektorarm dahinter; Messung mit echten Embeddings (Skript aus M5-41); schließt die Lücke Deutsch (Recall@5/MRR@10 nach Teil c: 0,727) | B | Opus, hoch | M5-43 gemergt |
| **DS-05a** | `sar_db` mit Wertetabelle, `sar_backscatter`, Schritt-Presets „VV dB“/„VH dB“ | B | Opus, hoch | M5-14 gemergt |
| **DS-05c** | Komposit „Dual-pol RGB“ | A | Sonnet, mittel | DS-05a gemergt |
| **M5-21** | Extraktoren GeoSphere, INSPIRE-ATOM, STAC Index als Register (`adr/0025` Schnitt 6) | B | Opus, mittel | M5-20 gemergt |
| **M5-24** | Prozess `harvester` als Takt, Health-Checks, „Last checked“ (`adr/0025` Schnitt 7, §6.6) | B | Opus, mittel | M5-20, M5-37 gemergt |
| **DS-05b** | Speckle-Filter Boxcar und Lee auf `focal` | B | Opus, hoch | M5-10, DS-05a gemergt |
| **DS-05d** | σ⁰-Kalibrierung, danach RVI | B | Opus, hoch | DS-05a gemergt |
| **M5-25** | JSON-LD und Sitemap für die Datensätze | B | Opus, mittel | — |
| **M5-27** | Abnahmebericht M5 (§7) | C | Opus, hoch | alle übrigen |

**Vorgemerkt, ohne Nummer und ohne Termin:** Für M6 (aus M5-35): `host_cap` je Host und `global_cap` je Pool in der Job-Queue; Egress-Proxy mit Grenzen je Ziel, Verbindungs-Pooler für Postgres, CDN, Lasttest mit N Instanzen je Prozesstyp (`architekturplan.md` 12.4); Sentinel-1 2019: Datatakes mit zwei Fassungen derselben Strecke (NRT-3h und Fast-24h) erscheinen in der Zeitleiste als ein Durchgang (Befund #343 §12.8); Thread-Pool: wartende Mosaik-Kacheln belegen Threads des gemeinsamen Pools (M5-30 Plan §8.7, Lösung mit Teil 9); Browser-Check band-select auf „uint16“ (mit 8b-2); `scripts/tile-bench` fängt die ID-Suche beim Anlegen einer Auswahl nicht ab; Browser-Check many-scenes wartet seit dem Ladesymbol länger (Ursache im Software-Rendering vermutet, mit GPU nicht geprüft); Tests aufräumen (pytest-Temp-Verzeichnisse, eindeutige Namen der Worker-DBs, Verursacher der verstellten Logger, gemeinsame Test-Datenbank startet mitten im Lauf neu bzw. hat Migrationskonflikte zwischen Checkouts, Teardown-Fehler in `test_worker.py` nur im gemeinsamen Lauf); TPS-Cache, falls Sentinel-1 träge ist (M5-30b F7); ältere Stände von swissALTI3D; BSH; W3 nach M6; Runner-Image 0.5.1 bei Gelegenheit; schlankere PR-Läufe (Vorschlag in #338); Browser-Skripte reparieren (Befund #299).

### 6.3 Reihenfolge

- Höchstens **zwei Sessions der Stufe B** und höchstens **zwei mit Frontend** gleichzeitig; Stufe A und C zählen nicht mit.
- Ist ein Platz frei, startet die nächste Aufgabe dieser Liste, deren Abhängigkeiten erfüllt sind:
  1. M5-10 · 2. M5-36 · 3. M5-09 · 4. M5-37 · 5. M5-40 · 6. M5-17 · 7. M5-19 · 8. M5-14 · 9. M5-11 · 10. M5-20 · 11. V1–V9 · 12. M5-16 · 13. M5-43 · 14. M5-42 · 15. M5-23 · 16. DS-05a · 17. M5-21 · 18. M5-24 · 19. DS-05b · 20. DS-05d · 21. M5-25 · 22. UI-07 · 23. M5-27. Nach M5-30b außerdem UI-08, M5-33, M5-34 an passender Stelle.
- Stufe A (DS-05c, M5-38) und C (M5-39, M5-41, M5-32, M5-31, M5-26, in dieser Reihenfolge) laufen daneben, sobald ihre Abhängigkeit erfüllt ist.
- Eine Aufgabe, höchstens zwei PRs (§2 Punkt 11).
- Gestapelte PRs: nach dem Merge der Basis zeigt GitHub die Folge-PRs auf `main` (Einstellung „Automatically delete head branches“ ist seit 11.11. an). Gestapelte PRs und Onboarding-PRs mit Merge-Commit, Squash nur bei Merge- oder WIP-Commits.

### 6.4 Startsätze

- Stufe A, B, C: „Führe Aufgabe M5-xx aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.2) aus.“
- DS-05x: „Führe Aufgabe DS-05x aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.2) aus; Grundlage `adr/0018` und `adr/0030` §9.“
- V1–V9: „Führe die Vorarbeiten V1–V9 aus `adr/0031` aus; Rahmen `docs/plans/m5/m5-discovery-und-suche.md` §6.2.“
- Zu jedem Startsatz nennt der Planungs-Chat Modell und Effort.

### 6.5 Was für alle Aufgaben aus §6 gilt

- Onboarding nach `projektuebersicht.md` §5, alle Punkte, inklusive Coverage Map (Punkt 2), „zuletzt erfolgreich geprüft“ (Punkt 10) und Schlagworte deutsch und englisch (`adr/0026` F7).
- Eigenheiten (§2 Punkt 7) ausdrücklich in der Registry; was nicht geht, erscheint nicht.
- Lizenz-Einstufung nach `adr/0023` §7.2; Wortlaut der Attribution bestätigt Otto im PR vor dem Merge.
- Live-Abrufe gegen Quellen laufen nicht aus Cloud-Sessions über `gateway` (`adr/0002`); Laden von Items und Harvest-Läufe macht Otto lokal, die Session nennt die Befehle.
- Entscheidungslog nur ergänzen (Regel im Log-Kopf; `merge=union` löst gleichzeitige Zeilen).
- Frontend nach §2 Punkte 8 und 9 und `docs/ui/leitfaden.md`.

## 7. Abnahme M5

M5 ist abgenommen, wenn der Abnahmebericht (M5-27) für jeden Punkt einen Beleg nennt:

1. **Quellen von Hand:** WorldCover 2020/2021, swissALTI3D, BEV ALS-DGM 1 m und eine Meteorologie-Quelle sind angebunden, jeweils mit vollständiger Onboarding-Checkliste und den Eigenheiten aus `adr/0030`.
2. **Harvest:** Ein Lauf (lokal bei Otto) über die Seed-Liste erzeugt Kandidaten und mit `discovery propose` einen Branch für einen Draft-PR mit höchstens 20 Kandidaten je Quelle.
3. **Zweiter Lauf** ohne Quelländerung: bedingte Anfragen, wo die Quelle `ETag` oder `Last-Modified` liefert; sonst ein Abruf der Liste ohne Folgearbeit, entschieden über den Inhalts-Hash; je Quelle im Lauf-Bericht ausgewiesen; kein neuer Branch (`adr/0025` F7).
4. **Suche:** Das Bewertungs-Set besteht nach `adr/0026` F5 (Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8 je Sprache, alle Filterfragen, drei von vier Negativfragen) in der CI ohne Netz.
5. **Data catalogue:** Fenster mit allen Datensätzen, gruppiert, mit Suche und AOI-Schalter; gelistete Einträge mit Link und Marke für Konto-Quellen.
6. **Health:** „Last checked“ ist je Datensatz sichtbar und stammt aus einem echten Lauf.
7. **Prototyp-Quellen:** Die Startprüfung aus `adr/0024` ist durch Tests belegt; ein Prototyp-Eintrag lädt nur lokal mit Schalter.
8. **Auffindbarkeit:** JSON-LD je Datensatz und eine Sitemap werden ausgeliefert.
9. **Sentinel-1:** DS-04 und DS-05a sind gemergt; DS-05b bis DS-05d dürfen nach M5 folgen.
10. **Skalierbarkeit (Otto, 14.11.2026):** Die Prüfung M5-35 liegt vor; jede ihrer Befunde ist behoben oder mit Ottos Entscheidung zurückgestellt. Alle M5-Bausteine laufen mit mehreren Instanzen je Prozesstyp, ohne die Last auf eine Quelle zu vervielfachen.

Der Projektplan §4 M5 bekommt mit dem Abnahmebericht einen Nachtrag mit dieser Fassung.

## 8. Fragen an Otto (Fassung 3) — beantwortet am 06.11.2026

Otto: F1 und F2 jeweils Option 1.

**F1 — Schnitt und Reihenfolge (§6.2, §6.3)?**
1. Wie vorgeschlagen **(Empfehlung)**
2. Suche (M5-22, M5-23) vor dem Harvest (M5-19 bis M5-21)
3. Harvest vor Sentinel-1 (DS-04, DS-05)

**F2 — Abnahme (§7)?**
1. Wie vorgeschlagen; DS-05b bis DS-05d dürfen nach M5 folgen **(Empfehlung)**
2. Ganz DS-05 gehört zur Abnahme
3. Sentinel-1 gehört nicht zur Abnahme von M5

## 9. Nächste Schritte

1. M5-30b geordnet abschließen (Reihenfolge in §6.2).
3. Stufe C nach Ottos Freigabe: M5-32, M5-31, M5-26.

## 10. Grenzen (gelten für alle M5-Aufgaben)

- Modulgrenzen laut `architekturplan.md` 3.1 (Import-Linter); ausgehende Requests nur über `gateway`; Worker-Kern zustandslos; `decomp.py` nie generalisieren.
- Keine Secrets im Repo (öffentlich, AGPL-3.0-or-later); Prototyp-Quellen nur nach `adr/0024`; Zugangsdaten nur nach `adr/0027` (Regel R-Z).
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Lizenz-Einstufung und Freigabe jedes Datensatzes immer durch Otto.
- Bilder der Browserprüfung nicht ins Repo; Nachträge heißen nach der Aufgabe.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` nur mit ausdrücklicher Erlaubnis.
