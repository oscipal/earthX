# M5 — Discovery und Suche

**Stand:** 11.11.2026, **Fassung 3.1** (Nachführung). Fassung 3 (angenommen von Otto am 06.11.2026, §8: F1 und F2 jeweils Option 1) schnitt den Rest der Umsetzung und legte die Abnahme fest. Fassung 3.1 trifft keine neue Entscheidung: Sie trägt den Stand nach (§6.1), die seither entstandenen Aufgaben M5-28 bis M5-30, UI-06, F11, F12 und die Vorarbeiten V1–V9 aus `adr/0031` (§6.2), die Vorgaben Ottos seit dem 07.11. (§2 Punkt 9) und die neue Reihenfolge (§6.3). Die Entscheidungen dazu stehen bereits im Entscheidungslog.
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
2. **Datentypen:** zunächst nur Raster.
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

### 6.2 Offen

Stufe A: ohne Plan-Datei, direkt umsetzen. Stufe B: Plan unter `docs/plans/m5/` (UI unter `docs/plans/vp3/`) mit Fragen im Draft-PR, Umsetzung nach Ottos Antworten im selben PR. Stufe C: nur Entwurf (ADR, Bericht).

**In Arbeit (11.11.2026):**

| Aufgabe | Inhalt | Stand |
|---|---|---|
| **M5-30b** | Teil 3a/3b (Frontend, mit #335 zusammen mergen), Teil 7 (Ersatz GLO-30, Plan §4.8), Teile 8 und 9 (Pyramide GLO-30 und WorldCover), Teil 10 (Nachträge) | läuft |
| **M5-22 Teil c** | Collection Search mit `q`, Zahl am Namen (A18 nach Ottos Antwort), Negativfrage Q51 | #337 |
| **F11** | Quicklook für Sentinel-1 über Kacheln statt PNG (`adr/0018` §4.2), Regel an `georeferencing: gcp_tps`, nur Frontend | läuft, Merge nach #339 |

**Noch nicht gestartet:**

| Aufgabe | Inhalt | Stufe | Modell, Effort | Hängt ab von |
|---|---|---|---|---|
| **F12** | Hinweis an den Originalen (Befund F12 aus #319), Text-Auftrag | A | Sonnet, mittel | — |
| **M5-10** | Geländeoperator mit Capability `terrain` und Operator-Art `focal` (`adr/0030` F3) | B | Opus, hoch | — |
| **M5-09** | BEV ALS-DGM 1 m über ATOM, EPSG:3035; Ersatz GLO-30 unter `min_zoom` wie swissALTI3D | B | Opus, mittel | M5-30b Teil 7 gemergt |
| **M5-17** | Stufe „gelistet“ (`adr/0025` §6.1a, Schnitt 2) und erste Katalogeinträge mit Link: CORINE (`free_account`), Landsat (`requester_pays`) (`adr/0027` W0) | B | Opus, mittel | — |
| **M5-19** | Harvest-Kern (`adr/0025` Schnitt 4): Tabellen, Fetch und Extract für STAC-API und CKAN, Lauf-Befehl | B | Opus, hoch | — |
| **M5-14** | Preset-Felder `composite_presets` und `step_presets` (`adr/0030` F7), Anzeige in „Quick processing“ | B | Opus, mittel | — |
| **M5-11** | Erste Meteorologie-Quelle MeteoSchweiz nach `adr/0029` (zwei PRs: Verweise und Lesen; Datensatz); Wiedervorlage `float64` (§2 Punkt 9) | B | Opus, hoch | — |
| **M5-20** | Verify, Enrich, Dedupe, Kandidaten, `discovery propose`, Lizenzregeln, Skript und Anleitung für Ottos lokalen Lauf (`adr/0025` Schnitt 5, §6.7) | B | Opus, hoch | M5-19, M5-17 gemergt |
| **V1–V9** | Vorarbeiten für das automatische Onboarding (`adr/0031`), danach richtet Claude im Planungs-Chat die geplante Aufgabe ein | B | laut `adr/0031` | laut `adr/0031` (in der Liste nach M5-20) |
| **M5-16** | WorldCover: Klassenanteile in der AOI aus der Ergebnis-Statistik (`adr/0030` F9) | B | Opus, mittel | — |
| **M5-23** | Suche Teil 2 (`adr/0026` §6 Schritte 3 und 4): Vektorarm, Modellwahl am Set, eigene Dockerfile-Stufe, RRF; Suchfeld und AOI-Schalter im Data catalogue; schließt die Lücke Deutsch (Recall@5/MRR@10 nach Teil c: 0,727) | B | Opus, hoch | M5-22 Teil c gemergt |
| **DS-05a** | `sar_db` mit Wertetabelle, `sar_backscatter`, Schritt-Presets „VV dB“/„VH dB“ | B | Opus, hoch | M5-14 gemergt |
| **DS-05c** | Komposit „Dual-pol RGB“ | A | Sonnet, mittel | DS-05a gemergt |
| **M5-21** | Extraktoren GeoSphere, INSPIRE-ATOM, STAC Index als Register (`adr/0025` Schnitt 6) | B | Opus, mittel | M5-20 gemergt |
| **M5-24** | Prozess `harvester` als Takt, Health-Checks, „Last checked“ (`adr/0025` Schnitt 7, §6.6) | B | Opus, mittel | M5-20 gemergt |
| **DS-05b** | Speckle-Filter Boxcar und Lee auf `focal` | B | Opus, hoch | M5-10, DS-05a gemergt |
| **DS-05d** | σ⁰-Kalibrierung, danach RVI | B | Opus, hoch | DS-05a gemergt |
| **M5-25** | JSON-LD und Sitemap für die Datensätze | B | Opus, mittel | M5-22 Teil c gemergt |
| **M5-26** | ADR: Operatoren über mehrere Eingaben oder Zeitschritte (`adr/0030` F10) | C | Opus, hoch | M5-11 gemergt |
| **M5-27** | Abnahmebericht M5 (§7) | C | Opus, hoch | alle übrigen |

**Vorgemerkt, ohne Nummer und ohne Termin:** Tests aufräumen (pytest-Temp-Verzeichnisse, eindeutige Namen der Worker-DBs, Verursacher der verstellten Logger); TPS-Cache, falls Sentinel-1 träge ist (M5-30b F7); Gitterdatei für LV95; ältere Stände von swissALTI3D; BSH; W3 nach M6; Runner-Image 0.5.1 bei Gelegenheit; schlankere PR-Läufe (Vorschlag in #338); Browser-Skripte reparieren (Befund #299).

### 6.3 Reihenfolge

- Höchstens **zwei Sessions der Stufe B** und höchstens **zwei mit Frontend** gleichzeitig; Stufe A und C zählen nicht mit.
- Ist ein Platz frei, startet die nächste Aufgabe dieser Liste, deren Abhängigkeiten erfüllt sind:
  1. F12 · 2. M5-10 · 3. M5-09 · 4. M5-17 · 5. M5-19 · 6. M5-14 · 7. M5-11 · 8. M5-20 · 9. V1–V9 · 10. M5-16 · 11. M5-23 · 12. DS-05a · 13. M5-21 · 14. M5-24 · 15. DS-05b · 16. DS-05d · 17. M5-25 · 18. M5-27.
- Stufe A (DS-05c) und C (M5-26) laufen daneben, sobald ihre Abhängigkeit erfüllt ist.
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

1. Laufend zu Ende bringen: M5-30b (3b mit #335, dann Teile 7–10), M5-22 Teil c (#337), F11 (nach #339).
2. Nächster freier Platz nach §6.3; Plätze mit Frontend sind belegt, solange M5-30b Teil 3b und F11 laufen.
3. Dieser Doku-PR ist zugleich der Nachweis für den Doku-Pfad der neuen CI (#338): Der Pflicht-Check „Backend — lint and tests“ muss mit übersprungenen Teilen grün werden.

## 10. Grenzen (gelten für alle M5-Aufgaben)

- Modulgrenzen laut `architekturplan.md` 3.1 (Import-Linter); ausgehende Requests nur über `gateway`; Worker-Kern zustandslos; `decomp.py` nie generalisieren.
- Keine Secrets im Repo (öffentlich, AGPL-3.0-or-later); Prototyp-Quellen nur nach `adr/0024`; Zugangsdaten nur nach `adr/0027` (Regel R-Z).
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Lizenz-Einstufung und Freigabe jedes Datensatzes immer durch Otto.
- Bilder der Browserprüfung nicht ins Repo; Nachträge heißen nach der Aufgabe.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` nur mit ausdrücklicher Erlaubnis.
