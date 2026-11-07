# M5 — Discovery und Suche

**Stand:** 06.11.2026, **Fassung 3**, angenommen von Otto am 06.11.2026 (§8: F1 und F2 jeweils Option 1). Fassung 2 (angenommen 06.11.2026) schnitt den ersten Teil der Umsetzung. Fassung 3 schneidet den Rest, nachdem alle Entscheidungsvorlagen angenommen sind (`adr/0023` bis `adr/0027`, `adr/0029`, `adr/0030`), und legt die Abnahme von M5 fest.
**Grundlage:** `projektplan.md` §4 M5, `architekturplan.md` Abschnitte 4 (Discovery) und 5 (Katalog), `projektuebersicht.md` §5, `KLAERUNGEN.md` B10–B13, `adr/0018` (Sentinel-1), `adr/0021` (Suchfilter), `adr/0022` (Datennähe), `adr/0023` (Quellenkatalog), `adr/0024` (Prototyp-Quellen), `adr/0025` (Harvest-Pipeline), `adr/0026` (Hybrid-Suche), `adr/0027` (Quellen mit Konto), `adr/0029` (Leseweg NetCDF), `adr/0030` (Operatoren je Datensatz), Backlog `docs/plans/nach-m4-backlog.md`.
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
   - **Control Panel:** je Seite so viele Datensätze, wie ohne Scrollen passen, ohne Obergrenze (Otto, 07.11.2026; bis dahin höchstens sechs); Seitenpfeile klein oben neben „Datasets“ (Otto, 06.11.2026 abends). Die Vorauswahl beim ersten Besuch bleibt bei höchstens sechs.
   - **„Advanced search“** immer sichtbar.
   - **Kein zusätzlicher Text** im Panel.
   - **Datum:** begrenzt auf den verfügbaren Zeitraum und am Anfang mit frühestem und spätestem Aufnahmedatum des Datensatzes vorausgefüllt (Otto, 06.11.2026 abends).
   - **Data catalogue:** größeres Fenster über der Karte, geöffnet über ein Symbol in der linken Leiste (UI-05 F5); gruppiert, mit Angaben wie bei STAC und der Quelle; darin später die Suche (`adr/0026` §7).

## 3. Was mit M5 zusätzlich ansteht

- **DS-04** Sentinel-1 anbinden (`adr/0018` Fassung 2), **DS-05** SAR-Operatoren, aufgeteilt nach `adr/0030` §9 in DS-05a bis DS-05d.
- **`data_region`**: erledigt mit M5-07 (#298).
- **Datensatz-Browser**: als „Data catalogue“ in UI-05; Suche darin mit M5-23.
- **Health-Checks** je Quelle, „zuletzt erfolgreich geprüft“ sichtbar: M5-24.
- **Earth Search v2** (Backlog 36): weiter Beta ohne öffentlichen Endpunkt; keine Aufgabe in M5, solange das so bleibt.
- **`harvester`**: heute eine leere Hülle (`adr/0025` §2); wird mit M5-24 zum Takt der Pipeline.
- **Mosaik-Zoom bei groben Rastern** (Backlog 29): Prüfpunkt in M5-11.

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

Kernpunkte für die Umsetzung:

- **`adr/0023`:** Quellen von Hand: WorldCover (zwei Datensätze), swissALTI3D, BEV ALS-DGM 1 m; Lizenzvorschläge angenommen, Wortlaute bestätigt Otto im PR; `data_region` als `<betreiber>:<ort>` bzw. `unknown`. Offen bis M5-08: mehrere Stände je Kachel.
- **`adr/0024`:** `legal_status` (`cleared`/`unclear`), Präfix `proto-`, YAML außerhalb des Images, Laden nur mit `EARTHX_PROTOTYPE_SOURCES` und `EARTHX_PROFILE=local`, nie in CI und Runner; Ergebnisse erben den Status (F11).
- **`adr/0025`:** Befehle in `discovery`, Zustand in Postgres, Kandidaten in Git, PR durch Otto (P1); Harvest in M5 nur lokal bei Otto; Stufe „gelistet“ (B11 Stufe 1); Kandidatendateien; höchstens 20 Kandidaten je PR; CKAN mit Herausgeberliste; Lizenzregeln „Herausgeber + Lizenz-URI → Stufe“; `User-Agent` Pflicht in `gateway`; YAML unter `backend/catalog/`; Schnitt in sieben Schritte (§8 dort).
- **`adr/0026`:** Volltext (`simple`, `german`, `english`, `unaccent`, Trigramme, Glossar) und Vektor (multilingual-e5-small/-base, int8, im Prozess `api`, nicht im Runner-Image), **ohne pgvector** (Vektor als Spalte, Vergleich in `api`); RRF k = 60; harte Filter vor der Fusion; Collection Search mit `q`, Fläche nur per `POST`; Index in `catalog-load`; Bewertungs-Set mit 50 Fragen, Grenze Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8 je Sprache.
- **`adr/0027`:** Konto-Quellen nur als Katalogeintrag mit Link; `access.account` (`none`, `anonymous_token`, `free_account`, `requester_pays`); Regel R-Z.
- **`adr/0029`:** eigene virtuelle Verweise (h5py nur in `discovery`), ein Item je Zeitschritt, Verweise im Item, ETag-Prüfung beim Lesen, Fehlerart `source_changed`; zuerst nur abgeschlossene Jahresdateien; ARCO-ERA5 nicht in M5.
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
| M5-07 | ESA WorldCover 2020/2021, `data_region` für alle Datensätze | #298 |
| UI-05 Teil 1 | Control Panel mit Seiten, „Advanced search“ immer sichtbar, Datum begrenzt, kein Zusatztext | #299 |
| — | CI: Doku-PRs schnell (`scripts/ci-scope.sh`) | #304 |

### 6.2 Offen

Stufe A: ohne Plan-Datei, direkt umsetzen. Stufe B: Plan unter `docs/plans/m5/` (UI unter `docs/plans/vp3/`) mit Fragen im Draft-PR, Umsetzung nach Ottos Antworten im selben PR. Stufe C: nur Entwurf (ADR, Bericht).

| Aufgabe | Inhalt | Stufe | Modell, Effort | Hängt ab von |
|---|---|---|---|---|
| **UI-05b** | UI-05 Teil 2: Data catalogue als Fenster, Registry-Felder für Gruppe, `providers`, `gsd`, Auswahl im Browser, Vorauswahl | B (Plan fertig) | Opus, hoch | — |
| **M5-18** | `gateway`: `User-Agent` Pflicht, Abstand je Host, `robots.txt` (`adr/0025` Schnitt 3) | B | Opus, mittel | — |
| **M5-13** | YAML-Lader (`adr/0025` §7, Schnitt 1): Umzug aller Einträge bitgleich, `legal_status`, `proto-`, Startprüfung (`adr/0024` R5), `access.account` (`adr/0027` §6.1), `EARTHX_PROFILE`, Dockerfile | B | Opus, hoch | UI-05b gemergt |
| **M5-08** | Allgemeiner STAC-Adapter und swissALTI3D; Regel für mehrere Stände je Kachel | B | Opus, hoch | M5-13 gemergt |
| **DS-04** | Sentinel-1 GRD anbinden (`adr/0018` Teil A); Plan neu schreiben (der alte enthält den Text von DS-00) | B | Opus, hoch | Plan sofort; Umsetzung nach M5-13 |
| **M5-22** | Suche Teil 1 (`adr/0026` §6 Schritte 1, 2 und API): Bewertungs-Set als Fixture und Test, Suchtext, lexikalischer Arm mit Glossar, Collection Search mit `q` | B | Opus, hoch | M5-13 gemergt |
| **M5-10** | Geländeoperator mit Capability `terrain` und Operator-Art `focal` (`adr/0030` F3) | B | Opus, hoch | M5-08 gemergt |
| **M5-09** | BEV ALS-DGM 1 m über ATOM, EPSG:3035 | B | Opus, mittel | M5-08 gemergt |
| **M5-15** | Sentinel-2-Presets NDMI, MNDWI, NDREI, SAVI (`adr/0030` F8) | A | Sonnet, mittel | M5-13 gemergt |
| **M5-17** | Stufe „gelistet“ (`adr/0025` §6.1a, Schnitt 2) und erste Katalogeinträge mit Link: CORINE (`free_account`), Landsat (`requester_pays`) (`adr/0027` W0) | B | Opus, mittel | M5-13 gemergt |
| **M5-19** | Harvest-Kern (`adr/0025` Schnitt 4): Tabellen, Fetch und Extract für STAC-API und CKAN, Lauf-Befehl | B | Opus, hoch | M5-13, M5-18 gemergt |
| **M5-14** | Preset-Felder `composite_presets` und `step_presets` (`adr/0030` F7), Anzeige in „Quick processing“ | B | Opus, mittel | M5-13 gemergt |
| **M5-11** | Erste Meteorologie-Quelle MeteoSchweiz nach `adr/0029` (zwei PRs: Verweise und Lesen; Datensatz) | B | Opus, hoch | M5-08 gemergt |
| **M5-20** | Verify, Enrich, Dedupe, Kandidaten, `discovery propose`, Lizenzregeln, Skript und Anleitung für Ottos lokalen Lauf (`adr/0025` Schnitt 5, §6.7) | B | Opus, hoch | M5-19, M5-17 gemergt |
| **M5-16** | WorldCover: Klassenanteile in der AOI aus der Ergebnis-Statistik (`adr/0030` F9) | B | Opus, mittel | — |
| **M5-23** | Suche Teil 2 (`adr/0026` §6 Schritte 3 und 4): Vektorarm, Modellwahl am Set, eigene Dockerfile-Stufe, RRF; Suchfeld und AOI-Schalter im Data catalogue | B | Opus, hoch | M5-22, UI-05b gemergt |
| **DS-05a** | `sar_db` mit Wertetabelle, `sar_backscatter`, Schritt-Presets „VV dB“/„VH dB“ | B | Opus, hoch | DS-04, M5-14 gemergt |
| **DS-05c** | Komposit „Dual-pol RGB“ | A | Sonnet, mittel | DS-05a gemergt |
| **M5-21** | Extraktoren GeoSphere, INSPIRE-ATOM, STAC Index als Register (`adr/0025` Schnitt 6) | B | Opus, mittel | M5-20 gemergt |
| **M5-24** | Prozess `harvester` als Takt, Health-Checks, „Last checked“ (`adr/0025` Schnitt 7, §6.6) | B | Opus, mittel | M5-20 gemergt |
| **DS-05b** | Speckle-Filter Boxcar und Lee auf `focal` | B | Opus, hoch | M5-10, DS-05a gemergt |
| **DS-05d** | σ⁰-Kalibrierung, danach RVI | B | Opus, hoch | DS-05a gemergt |
| **M5-25** | JSON-LD und Sitemap für die Datensätze | B | Opus, mittel | M5-22 gemergt |
| **M5-26** | ADR: Operatoren über mehrere Eingaben oder Zeitschritte (`adr/0030` F10) | C | Opus, hoch | M5-11 gemergt |
| **M5-27** | Abnahmebericht M5 (§7) | C | Opus, hoch | alle übrigen |

**Text-Aufträge ohne Nummer** (bei Bedarf): Browser-Skripte reparieren (sieben scheitern auf `main`, Befund #299); Nachtrag UI-05 Teil 1 (Seitenpfeile oben, Datum vorausgefüllt), falls nicht in #299.

### 6.3 Reihenfolge

- Höchstens **zwei Sessions der Stufe B** und höchstens **zwei mit Frontend** gleichzeitig (Übergabe §3); Stufe A und C zählen nicht mit.
- Ist ein Platz frei, startet die nächste Aufgabe dieser Liste, deren Abhängigkeiten erfüllt sind:
  1. UI-05b · 2. M5-18 · 3. M5-13 · 4. M5-08 · 5. DS-04 · 6. M5-22 · 7. M5-10 · 8. M5-09 · 9. M5-17 · 10. M5-19 · 11. M5-14 · 12. M5-11 · 13. M5-20 · 14. M5-16 · 15. M5-23 · 16. DS-05a · 17. M5-21 · 18. M5-24 · 19. DS-05b · 20. DS-05d · 21. M5-25 · 22. M5-27.
- Stufe A (M5-15, DS-05c) und C (M5-26) laufen daneben, sobald ihre Abhängigkeit erfüllt ist.
- **Registry:** UI-05b, M5-13 und M5-08 ändern dieselben Dateien und laufen deshalb nacheinander. Nach M5-13 stehen alle Einträge als YAML; jede spätere Aufgabe schreibt YAML.
- Der Plan von DS-04 darf sofort entstehen (Stufe B, nur Doku), die Umsetzung erst nach M5-13.

### 6.4 Startsätze

- Stufe A, B, C: „Führe Aufgabe M5-xx aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.2) aus.“
- UI-05b: „Führe UI-05 Teil 2 aus `docs/plans/vp3/ui-05-data-catalogue.md` aus (Antworten §8a).“
- DS-04, DS-05x: „Führe Aufgabe DS-0x aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.2) aus; Grundlage `adr/0018` und `adr/0030` §9.“

### 6.5 Was für alle Aufgaben aus §6 gilt

- Onboarding nach `projektuebersicht.md` §5, alle Punkte, inklusive Coverage Map (Punkt 2), „zuletzt erfolgreich geprüft“ (Punkt 10) und Schlagworte deutsch und englisch (`adr/0026` F7).
- Eigenheiten (§2 Punkt 7) ausdrücklich in der Registry; was nicht geht, erscheint nicht.
- Lizenz-Einstufung nach `adr/0023` §7.2; Wortlaut der Attribution bestätigt Otto im PR vor dem Merge.
- Live-Abrufe gegen Quellen laufen nicht aus Cloud-Sessions über `gateway` (`adr/0002`); Laden von Items und Harvest-Läufe macht Otto lokal, die Session nennt die Befehle.
- Entscheidungslog nur ergänzen (Regel im Log-Kopf).

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

1. Starten: UI-05b und M5-18 (Stufe B), dazu der Plan von DS-04, sobald ein Platz der Stufe B frei ist.
2. Otto lokal: WorldCover-Items laden (`python -m earthx.discovery.materialize esa-worldcover-2020` bzw. `-2021`), `live-smoke` einmal von Hand.

## 10. Grenzen (gelten für alle M5-Aufgaben)

- Modulgrenzen laut `architekturplan.md` 3.1 (Import-Linter); ausgehende Requests nur über `gateway`; Worker-Kern zustandslos; `decomp.py` nie generalisieren.
- Keine Secrets im Repo (öffentlich, AGPL-3.0-or-later); Prototyp-Quellen nur nach `adr/0024`; Zugangsdaten nur nach `adr/0027` (Regel R-Z).
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Lizenz-Einstufung und Freigabe jedes Datensatzes immer durch Otto.
- Bilder der Browserprüfung nicht ins Repo; Nachträge heißen nach der Aufgabe.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` nur mit ausdrücklicher Erlaubnis.
