# M5 — Discovery und Suche

**Stand:** 06.11.2026, **Fassung 2**, angenommen von Otto am 06.11.2026 (§7: F1–F3 jeweils Option 1; Zusatz §2 Punkt 8). Fassung 1.1 vom 31.10.2026 enthielt Rahmen, Vorgaben, Antworten und die Aufgaben für die Entscheidungsvorlagen. Fassung 2 schneidet den ersten Teil der Umsetzung: Quellen von Hand, Leseweg Meteorologie, Gelände, Sentinel-1, Operatoren je Datensatz, Datenkatalog in der Oberfläche. Pipeline, Suche und Health-Checks schneidet **Fassung 3**, sobald `adr/0025` und `adr/0026` angenommen sind.
**Grundlage:** `projektplan.md` §4 M5, `architekturplan.md` Abschnitte 4 (Discovery) und 5 (Katalog), `projektuebersicht.md` §5, `KLAERUNGEN.md` B10–B13, `adr/0018` (Sentinel-1), `adr/0021` (Suchfilter), `adr/0022` (Datennähe), `adr/0023` (Quellenkatalog, angenommen 06.11.2026), `adr/0024` (Prototyp-Quellen, angenommen 06.11.2026), `adr/0027` (Quellen mit Konto, angenommen 06.11.2026), Backlog `docs/plans/nach-m4-backlog.md`.
**Rangfolge:** ENTSCHEIDUNGEN_2026-09-18.md > KLAERUNGEN.md > dieser Plan > CLAUDE.md.

## 1. Ziel (Projektplan)

Der eigentliche „Datacrawler“: Datensätze finden, prüfen, freigeben und auffindbar machen.

- **Inhalt:** Trichter Stufen 0 und 1 (STAC Index/Atlas, STAC-Collection-Suche, CKAN, DCAT-AP, OAI-PMH nach Bedarf); Pipeline mit Zustandsautomat, Rohspeicherung, Inhalts-Hash; Verify; Dedupe mit Distributionen; Git-basierter Review; Health-Checks; Hybrid-Suche mit pgvector, Volltext und RRF; Bewertungs-Set für Suchqualität.
- **Funktionen:** AOI-zuerst-Suche; Verfügbarkeits-Zeitleiste; Eignungskarte pro Datensatz; „zuletzt erfolgreich geprüft“ sichtbar; Datensatz-Wünsche und Fehlermeldungen; JSON-LD und Sitemap für eigene Auffindbarkeit.
- **Abnahme (Entwurf aus dem Projektplan):** Ein Harvest-Lauf erzeugt Review-Vorschläge als PRs; ein erneuter Lauf ohne Quelländerung kostet nur bedingte Requests; Bewertungs-Set besteht. Die endgültige Abnahme legt Fassung 3 fest.

## 2. Vorgaben von Otto (31.10.2026)

Wörtlich:

> ich will mich bei den datenquellen auf den DACH raum vorerst fokussieren, also so ESA bzw satellitendaten sowieso immer (auch von JAXA oder NASA usw) aber ich will auch daten von den nationalen behörden der Dach länder (also metereologie usw.)) Ich will eigentlich nur frei verfügbare quellen haben die ohne key funktionieren und rechtlich abgesichert sind. ABer ich will (nur für mich jetzt im prototypen, in de released version sollen die wieder verschwinden) auch daten haben die rechtlich fraglich sind ob sie verwendet werden dürfen. und wegen anonymen api keys haben wir eh schon mal gesprochen.

Daraus:

1. **Satellitendaten immer:** ESA/Copernicus, dazu JAXA, NASA, USGS und andere Raumfahrtagenturen, soweit frei.
2. **DACH-Behörden zuerst:** nationale Stellen in Deutschland, Österreich, Schweiz (und Liechtenstein), z. B. Wetterdienste, Vermessung/Geodaten, Umwelt, Hydrologie.
3. **Nur frei und ohne Schlüssel:** kein Konto, kein eigener API-Key. Ein **anonymes Token**, das die Quelle ohne Anmeldung ausgibt (wie beim Planetary Computer, `adr/0018` §11 C), gilt als „ohne Schlüssel“.
4. **Rechtlich abgesichert:** Lizenz geprüft und nach B11 eingestuft (Katalogeintrag / Anzeige / Processing); Lizenz-Freigabe immer durch Otto.
5. **Prototyp-Quellen:** Für Ottos eigene Erprobung im Prototyp auch Quellen mit **unklarer Rechtslage**. Sie verschwinden in der veröffentlichten Version. Geregelt in `adr/0024` (angenommen).
6. **Kostenlose Konten:** zählen vorerst **nicht** als „ohne Schlüssel“. Der Weg dahin ist in `adr/0027` (angenommen) geregelt; in M5 nur Katalogeinträge mit Link und `access.account`.
7. **Jeder Datensatz hat Eigenheiten (Otto, 31.10.2026):** beim Processing (Fähigkeiten, eigene Operatoren), bei der erweiterten Suche (Filter, DS-02) und bei Schnellrechnungen (Index-Knöpfe, NM4-14). Das Onboarding jedes Datensatzes legt diese drei Teile ausdrücklich fest; sie stehen in der Registry, nicht im Code des Frontends.
8. **Zusatz Otto (06.11.2026):**
   - **Operatoren je Datensatz:** Für jeden Datensatz durchgehen, welche Processing-Operatoren und welche Quick processings sinnvoll wären (Beispiel Otto: Sentinel-1 mit Radar-Processing wie Interferometrie, Quick processing wie Pauli-Zerlegung). → M5-12.
   - **Control Panel:** nicht mehr alle Datensätze, sondern höchstens sechs auf einer Seite, so viele wie ohne Scrollen Platz haben; Blättern durch die hinzugefügten Datensätze (z. B. „‹ 1/6 ›“).
   - **„Advanced search“** ist immer sichtbar.
   - **Kein zusätzlicher Text** im Panel (z. B. bei der AOI-Suche, oder beim DEM „No time axis – acquired Dec 2010 to Jan 2015“).
   - **Datum** generell auf den verfügbaren Zeitraum des Datensatzes begrenzt (auch Sentinel-2).
   - **Data catalogue:** Knopf im linken Panel; alle verfügbaren Datensätze durchsehen (gruppiert), zum Control Panel hinzufügen; je Datensatz mehr Angaben (wie STAC, dazu die Quelle). → UI-05.

## 3. Was mit M5 zusätzlich ansteht

- **DS-04** Sentinel-1 anbinden (`adr/0018` Fassung 2), **DS-05** SAR-Operatoren — Schnitt in §6.
- **`data_region`** als Registry-Feld mit Startcheck (`adr/0022` F3, Form nach `adr/0023` F7) — kommt mit M5-07.
- **Datensatz-Browser** (vorgemerkt seit M3, Log 30.09.2026) — als „Data catalogue“ in UI-05 (§6); die Hybrid-Suche darin folgt mit Fassung 3.
- **Health-Checks** je Quelle (Architekturplan 4.5), „zuletzt erfolgreich geprüft“ sichtbar (B12, Checkliste Punkt 10) — Fassung 3, nach `adr/0025`.
- **Earth Search v2** (Backlog 36): laut `adr/0023` §6.2 weiter Beta ohne öffentlichen Endpunkt; keine Aufgabe in M5, solange das so bleibt.
- Bestehender Dienst `harvester` im Compose-Stack: Stand prüft `adr/0025` (M5-03).
- Mosaik-Zoom bei groben Rastern (Backlog 29, Vermerk): Prüfpunkt beim Onboarding der ersten Meteorologie-Quelle (M5-11).

## 4. Entscheidungsvorlagen

| | Thema | ADR | Stand (06.11.2026) |
|---|---|---|---|
| **A** | Quellenkatalog DACH und Satellit | `adr/0023` | **angenommen** (M5-01, M5-01b, PR #262, #295) |
| **B** | Harvest-Pipeline | `adr/0025` | M5-03 läuft |
| **C** | Hybrid-Suche und Bewertungs-Set | `adr/0026` | M5-04 läuft |
| **D** | Prototyp-Quellen | `adr/0024` | **angenommen** (M5-02, PR #260) |
| **E** | Quellen mit kostenlosem Konto | `adr/0027` | **angenommen** (M5-05, PR #261) |

Kernpunkte der angenommenen ADRs für die Umsetzung:

- **`adr/0023`:** erste Quellen von Hand: ESA WorldCover, swissALTI3D, BEV ALS-DGM 1 m (alle gemessen: anonym, COG mit Overviews, Range, bedingte Anfragen). WorldCover als **zwei Datensätze** (2020, 2021; F6 = 2). Lizenzvorschläge angenommen, Wortlaute prüft Otto vor dem Eintrag (F2). Leseweg NetCDF als eigene Recherche (F3). Geländeoperator mit Capability `terrain` (F5). `data_region` als `<betreiber>:<ort>` bzw. `unknown` (F7). **Offen:** Datensätze mit mehreren Ständen je Kachel (swissALTI3D je Kachel mehrere Jahre, BEV sechs Stichtage).
- **`adr/0024`:** Feld `legal_status` und Präfix `proto-`, Einträge als YAML außerhalb des Pakets, Laden nur mit `EARTHX_PROTOTYPE_SOURCES` und `EARTHX_PROFILE=local`; Umsetzung **nach dem YAML-Lader aus M5-03**. Bis dahin keine Prototyp-Quelle.
- **`adr/0027`:** Konto-Quellen in M5 nur als Katalogeintrag mit Link; Feld `access.account` (`none`, `anonymous_token`, `free_account`, `requester_pays`); Regel R-Z für Zugangsdaten. Anonyme Kopien (u. a. ARCO-ERA5) als Eingabe an M5-06.

## 5. Antworten Otto (31.10.2026)

1. **Reihenfolge:** ja – zuerst ADR A und zwei bis drei Quellen von Hand, dann die Pipeline (ADR B). Jeder Datensatz hat Eigenheiten bei Processing, erweiterter Suche und Schnellrechnungen (§2 Punkt 7).
2. **Datentypen:** zunächst nur Raster.
3. **Prototyp-Quellen:** dürfen ins öffentliche Repo, aber **markiert** (umgesetzt in `adr/0024`).
4. **Anonyme Tokens** zählen als „ohne Schlüssel“, kostenlose Konten nicht – mit dem Ziel, Konten später zu ermöglichen (`adr/0027`).
5. **Discovery-Umfang:** feste Liste bekannter Quellen plus STAC Index, dazu CKAN/DCAT-AP für GovData, data.gv.at und opendata.swiss; offene Suche in Paket 7b.
6. **Bewertungs-Set:** Session entwirft 30–50 Testfragen, Otto ergänzt und gibt frei.

## 5a. Aufgaben für die Entscheidungsvorlagen

Feste ADR-Nummern, damit parallele Sessions nicht kollidieren. Alle Stufe C (nur ADR-Entwurf, Messskripte unter `scripts/` ohne eigene HTTP-Aufrufe außerhalb von `gateway`, Netzschritte als Einmal-Schritt), Opus, Effort hoch. Abnahme je ADR: Entwurf mit Quellen und Belegstufe, Optionen, Empfehlung, Fragen F1 … Fn; Log-Zeile mit PR-Nummer, Status „offen“; Backlog nicht ändern; vor „fertig“ main holen.

| Aufgabe | ADR | Thema | Stand |
|---|---|---|---|
| **M5-01** | `adr/0023-quellenkatalog-dach.md` | Quellenkatalog DACH und Satellit | **erledigt** (#262; Antworten M5-01b, #295) |
| **M5-02** | `adr/0024-prototyp-quellen.md` | Prototyp-Quellen | **erledigt** (#260) |
| **M5-03** | `adr/0025-harvest-pipeline.md` | Harvest-Pipeline; Stand des vorhandenen `harvester` | läuft |
| **M5-04** | `adr/0026-hybrid-suche.md` | Hybrid-Suche und Bewertungs-Set | läuft |
| **M5-05** | `adr/0027-quellen-mit-konto.md` | Quellen mit kostenlosem Konto | **erledigt** (#261) |

Startsatz je Aufgabe: „Führe Aufgabe M5-0x aus `docs/plans/m5/m5-discovery-und-suche.md` (§5a) aus.“

## 6. Schnitt der Umsetzung, Teil 1 (Fassung 2)

### 6.1 Aufgaben

Stufe B heißt wie bisher: Die Session legt zuerst ihren Plan unter `docs/plans/m5/` mit Fragen F1 … Fn im Draft-PR vor, setzt nach Ottos Antworten im selben PR um. Stufe A: ohne Plan-Datei, direkt umsetzen.

| Aufgabe | Inhalt | Stufe | Modell, Effort | Hängt ab von |
|---|---|---|---|---|
| **M5-06** | Leseweg NetCDF/HDF5 für die Meteorologie (`adr/0023` F3): ADR `adr/0029-leseweg-netcdf.md` mit Messung | C | Opus, hoch | — |
| **M5-12** | Operatoren und Quick processings je Datensatz: ADR `adr/0030-operatoren-je-datensatz.md` | C | Opus, hoch | — |
| **UI-05** | Data catalogue im linken Panel; Control Panel mit höchstens sechs Datensätzen und Blättern; Datum auf den verfügbaren Zeitraum begrenzt; kein Zusatztext | B | Opus, hoch | — |
| **M5-07** | ESA WorldCover 2020 und 2021 anbinden; Registry-Feld `data_region` mit Startcheck für alle Datensätze | B | Opus, mittel | — |
| **M5-08** | Allgemeiner STAC-Adapter (aus `earth-search-v1`) und swissALTI3D; Regel für mehrere Stände je Kachel | B | Opus, hoch | M5-07 gemergt |
| **M5-09** | BEV ALS-DGM 1 m über ATOM, EPSG:3035 | B | Opus, mittel | M5-08 gemergt |
| **M5-10** | Geländeoperator (Hangneigung, Exposition, Schummerung) mit Capability `terrain` | B | Opus, hoch | M5-08 gemergt |
| **M5-11** | Erste Meteorologie-Quelle (Kandidat MeteoSchweiz `ogd-surface-derived-grid`) | B | Opus, hoch | M5-06 angenommen, M5-08 gemergt |
| **DS-04** | Sentinel-1 GRD anbinden (`plans/ds/ds-04-…`, `adr/0018` Teil A) | A | Opus, hoch | M5-07 gemergt |
| **DS-05** | SAR-Operatoren (`plans/ds/ds-05-…`), angepasst an `adr/0030` | B | Opus, hoch | DS-04 gemergt, M5-12 angenommen |

ADR-Nummern: 0029 und 0030 sind für M5-06 und M5-12 vergeben. Ist eine davon beim Start schon belegt, nimmt die Session die nächste freie und nennt sie im PR.

**M5-06 — Leseweg NetCDF/HDF5 (Stufe C).**
- **Optionen** aus `adr/0023` §7.1: (a) virtueller Zarr-Speicher (Kerchunk/VirtualiZarr, `architekturplan.md` 6.2), (b) GDAL-Treiber über `/vsicurl/`, (c) flüchtiger COG-Cache mit Ablaufdatum.
- **Messfälle:** MeteoSchweiz-Klimagitter (FSDI), DWD HYRAS; Vergleichsfall ARCO-ERA5 (Zarr v2, ohne CRS, Zeitachse; `adr/0009` §4, `adr/0027` §6.5).
- **Pflichtpunkte:** Prinzip 1 (keine dauerhaften Rohdaten); alle Lesezugriffe über `gateway` (Hinweis `adr/0014` F10: `fsspec`-Wege umgehen `gateway`); Zahl und Größe der Lesezugriffe je Kachel und je AOI; Reprojektion aus LV95 und EPSG:3034/3035; Zeitachse in Registry und Ansicht.
- Stand der Technik mit Quellen (rechenrelevant).

**M5-07 — ESA WorldCover (Stufe B).**
- Zwei Datensätze `esa-worldcover-2020` und `esa-worldcover-2021`, je statisch; Hinweis auf eingeschränkte Vergleichbarkeit in der Beschreibung.
- Weg des DEM (`adr/0009`): Items aus dem Kachelraster im Bucket per Einmal-Befehl in `discovery`, Coverage `LOCAL_SQL`.
- Eigenheiten nach `adr/0023` §8.3: Maske über die elf Klassen, `value_masking`, kein `band_math`, Reprojektion nur `nearest`, Farbtabelle aus der Datei, `search_filters` und `index_presets` leer.
- `data_region` als Pflichtfeld für **alle** Datensätze (bestehende eingeschlossen), Werte nach `adr/0023` §7.3, Startcheck gegen `asset_hosts` bei AWS-Hosts.
- Onboarding-Checkliste `projektuebersicht.md` §5 vollständig, inklusive Punkt 10 und Live-Smoke.
- **Vor dem Merge:** Otto bestätigt den Wortlaut der Lizenz und der Attribution (`adr/0023` F2).

**M5-08 — STAC-Adapter und swissALTI3D (Stufe B).**
- Der Adapter `earth-search-v1` wird zu einem allgemeinen STAC-Adapter; Earth Search bleibt bitgleich (bestehende Tests, Live-Smoke).
- swissALTI3D: LV95, Asset 0,5 m bzw. 2 m (`adr/0023` §8.3), Coverage `LOCAL_SQL` aus materialisierten Items, keine Filter an der Quelle (FSDI ohne Query/CQL2).
- **Mehrere Stände je Kachel:** Der Plan legt eine allgemeine Regel als Registry-Eigenschaft vor (z. B. „je Ort der neueste Stand, ältere wählbar“), die BEV übernimmt. Optionen mit Empfehlung als Frage an Otto.
- Region des FSDI-Buckets ist hinter CloudFront nicht messbar: `data_region` = `unknown`, bis belegt.
- **Vor dem Merge:** Otto bestätigt den Wortlaut der swisstopo-Bedingungen und der Quellenangabe.

**M5-09 — BEV ALS-DGM 1 m (Stufe B).**
- Erste Nicht-STAC-Quelle mit ATOM-Feed (Muster der INSPIRE-Downloaddienste); 55 Kacheln zu 50 km, sechs Stichtage nach der Regel aus M5-08.
- EPSG:3035; Coverage als Fläche; Overviews bis 1:256 belegt (`adr/0023`, M5-01b).
- Betreiber und Ort des Speichers klären, sonst `data_region` = `unknown`.
- **Vor dem Merge:** Otto bestätigt den Wortlaut der BEV-Bedingungen.

**M5-10 — Geländeoperator (Stufe B mit Recherche).**
- Ein generischer Operator, gebunden an die neue Capability `terrain`, die nur Höhenmodelle setzen (B10): Copernicus DEM, swissALTI3D, BEV.
- **Pflichtpunkte:** Nachbarpixel über den Blockrand in der Blockschleife (`adr/0014` F10); Bitgleichheit T2/T2L (`adr/0014` F9); Einheiten bei EPSG:4326 (Grad gegen Meter); Kostenschätzung.
- Schummerung zur Anzeige als Algorithmus im `tiler` mit prüfen (Ergänzung zu NM4-35, das nur bis Zoom 12 reicht).

**M5-11 — Erste Meteorologie-Quelle (Stufe B).**
- Nach dem Leseweg aus M5-06; Kandidat MeteoSchweiz `ogd-surface-derived-grid` (gleicher STAC-Adapter wie M5-08, Lizenz und ETag belegt, kleine Dateien, Jahresarchiv).
- Prüfpunkt Mosaik-Zoom bei 1 km (Backlog 29).

**M5-12 — Operatoren und Quick processings je Datensatz (Stufe C).**
- Je Datensatz (Sentinel-2 L2A, Sentinel-1 GRD nach DS-04, Copernicus DEM, WorldCover, swissALTI3D, BEV, MeteoSchweiz-Klimagitter): welche Processing-Operatoren und welche Quick processings (`index_presets`, UI-03) sinnvoll sind; je Vorschlag Nutzen, Voraussetzungen (Datenlevel, Polarisation, Capability nach B10), Stand der Technik mit Quellen, Rechenkosten, Aufwand, Priorität.
- **Sentinel-1 ausdrücklich:**
  - Interferometrie und Kohärenz brauchen komplexe Daten (SLC). Die Plattform hat bisher nur GRD (`adr/0018`). Zu prüfen: eine SLC-Quelle ohne Konto; sonst nur über den Weg aus `adr/0027`. Fertige Kohärenzprodukte (z. B. Global Coherence, `adr/0023` §6.3) als Alternative bewerten.
  - Pauli-Zerlegung braucht Quad-Pol; Sentinel-1 ist Dual-Pol (`ENTSCHEIDUNGEN` §3). `decomp.py` bleibt ruhend und wird nicht generalisiert. Dual-Pol-Alternativen bewerten (z. B. RGB-Komposit VV/VH/Verhältnis, Radar-Vegetationsindex; H-α für Dual-Pol braucht SLC).
- Abgleich mit dem bestehenden Plan von DS-05; was sich ändert, steht als Folge im ADR.
- Was in der Registry neu wäre (Capabilities, Felder), getrennt ausweisen.

**UI-05 — Data catalogue und Control Panel (Stufe B, Frontend und Registry).**
- Plan unter `docs/plans/vp3/`; Regeln aus `docs/ui/leitfaden.md`; Oberflächentexte englisch.
- **Control Panel:** zeigt nur die hinzugefügten Datensätze, so viele wie ohne Scrollen Platz haben, höchstens sechs je Seite; bei mehr Blättern mit „‹ 1/n ›“. „Advanced search“ immer sichtbar. Kein erklärender Zusatztext im Panel (AOI-Suche, „No time axis …“ beim DEM usw.); Erklärungen hinter (i) bzw. im Tooltip nach Leitfaden.
- **Datum:** Auswahl begrenzt auf den verfügbaren Zeitraum des Datensatzes (zeitliche Ausdehnung der Collection; offenes Ende = heute). Ohne Zeitachse: Feld gesperrt, Grund im Tooltip.
- **Data catalogue:** Knopf im linken Panel. Alle Datensätze, gruppiert; hinzufügen und entfernen. Je Datensatz Angaben wie bei STAC und die Quelle: Beschreibung, Anbieter und Quelle mit Link, Lizenz und Attribution, räumliche und zeitliche Ausdehnung, Auflösung, Bänder mit Einheiten, `data_region`, DOI (`cite-as`), „Last checked“, Processing und Quick processings; Prototyp-Datensätze mit Marke (`adr/0024`); Konto-Quellen als Katalogeintrag mit Link (`adr/0027`).
- **Fragen im Plan:** Gruppierung (z. B. nach Art: optisch, Radar, Gelände, Landbedeckung, Wetter und Klima; oder nach Anbieter/Land) und das Registry-Feld dafür; Vorauswahl beim ersten Besuch; wo die Auswahl gespeichert wird (Browser, Permalink); Platz für die Suche aus `adr/0026` (Fassung 3), ohne sie vorwegzunehmen.

**DS-04, DS-05** laufen nach ihren bestehenden Plänen unter `docs/plans/ds/`. Neu: `data_region` aus M5-07 ist gesetzt; DS-05 übernimmt die Folgen aus `adr/0030`.

### 6.2 Reihenfolge

| Welle | Aufgaben | Bedingung |
|---|---|---|
| 1 (jetzt) | M5-03, M5-04 (laufen); **M5-06**, **M5-12** (C); **M5-07**, **UI-05** (B) | — |
| 2 | **M5-08**, **DS-04** | M5-07 gemergt; M5-08 zusätzlich UI-05 gemergt oder im Plan abgestimmt |
| 3 | **M5-09**, **M5-10** | M5-08 gemergt |
| 4 | **M5-11**, **DS-05** | M5-06 angenommen und M5-08 gemergt bzw. DS-04 gemergt und M5-12 angenommen |

Höchstens zwei Sessions der Stufe B gleichzeitig (Übergabe §3) und höchstens zwei mit Frontend; Stufe C zählt nicht mit. M5-07, M5-08 und M5-09 ändern dieselbe Registry; deshalb nacheinander. UI-05 fügt der Registry nur ein Feld für die Gruppierung hinzu; Überschneidungen mit M5-07 klärt, wer später holt.

### 6.3 Startsätze

- Stufe B und C: „Führe Aufgabe M5-xx aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.1) aus.“
- UI-05: „Führe Aufgabe UI-05 aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.1) aus; Plan unter `docs/plans/vp3/`.“
- DS-04, DS-05: „Führe Aufgabe DS-0x aus `docs/plans/ds/ds-0x-….md` aus. Ergänzung: `data_region` nach M5-07 setzen.“

### 6.4 Was für alle Aufgaben aus §6 gilt

- Onboarding nach `projektuebersicht.md` §5, alle Punkte, inklusive Coverage Map (Punkt 2) und „zuletzt erfolgreich geprüft“ (Punkt 10).
- Eigenheiten (§2 Punkt 7) ausdrücklich in der Registry: Processing, erweiterte Suche, Schnellrechnungen; was nicht geht, erscheint nicht.
- Registry vorerst als Python (B13); der Umzug nach YAML kommt mit der Umsetzung von `adr/0025` und `adr/0024`.
- Feld `access.account` (`adr/0027`) und `legal_status` (`adr/0024`) erst mit dem YAML-Lader; bis dahin gelten alle Datensätze als `none` und `cleared`.
- Lizenz-Einstufung nach `adr/0023` §7.2; den Wortlaut bestätigt Otto im PR vor dem Merge.
- Entscheidungslog nur ergänzen (Regel im Log-Kopf).

## 7. Fragen an Otto (Fassung 2) — beantwortet am 06.11.2026

Otto: „Ja passt alles“, also F1–F3 jeweils Option 1; dazu der Zusatz in §2 Punkt 8 (M5-12, UI-05).

**F1 — Schnitt und Wellen (§6)?**
1. Wie vorgeschlagen **(Empfehlung)**
2. Erst alle drei Quellen, dann Meteorologie und Gelände (M5-06 und M5-10 später)
3. Sentinel-1 (DS-04, DS-05) erst nach den Quellen von Hand

**F2 — Mehrere Stände je Kachel (swissALTI3D, BEV)?**
1. Allgemeine Regel als Registry-Eigenschaft im Plan von M5-08, mit Optionen und Empfehlung **(Empfehlung)**
2. Eigener kleiner ADR (Stufe C) vor M5-08
3. Vorerst nur der neueste Stand je Kachel, ältere nicht wählbar

**F3 — `data_region` für alle Datensätze mit M5-07?**
1. Ja, Pflichtfeld für alle, mit Startcheck bei AWS-Hosts **(Empfehlung)**
2. Nur für neue Datensätze; bestehende später

## 8. Nächste Schritte

1. Welle 1: M5-06, M5-12, M5-07 und UI-05 starten (M5-03 und M5-04 laufen).
2. Fassung 3 nach Annahme von `adr/0025` und `adr/0026`: Pipeline (inklusive YAML-Lader, `legal_status`, `access.account`), Hybrid-Suche im Data catalogue, Bewertungs-Set, Health-Checks, Seed-Liste aus `adr/0023` §7.4, JSON-LD und Sitemap; dazu die endgültige Abnahme von M5.

## 9. Grenzen (gelten für alle M5-Aufgaben)

- Modulgrenzen laut `architekturplan.md` 3.1 (Import-Linter); ausgehende Requests nur über `gateway`; Worker-Kern zustandslos; `decomp.py` nie generalisieren.
- Keine Secrets im Repo (öffentlich, AGPL-3.0-or-later); Prototyp-Quellen nur nach `adr/0024`; Zugangsdaten nur nach `adr/0027` (Regel R-Z).
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Lizenz-Einstufung und Freigabe jedes Datensatzes immer durch Otto.
- Bilder der Browserprüfung nicht ins Repo; Nachträge heißen nach der Aufgabe.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` nur mit ausdrücklicher Erlaubnis.
