# UI-05 — Data catalogue und Control Panel

**Stand:** 06.11.2026, **angenommen** von Otto am 06.11.2026 (§8a: F1–F9 jeweils Option 1, F5 mit Symbol in der Leiste, F3 ergänzt; A1–A9 angenommen). Teil 1 umgesetzt (§9), Teil 2 umgesetzt (§10); dessen Auslegungen (a)–(d) und (h) angenommen von Otto am 06.11.2026. Review von Teil 2 (Otto, 07.11.2026): keine Obergrenze von sechs Datensätzen je Seite mehr (§8a, §3.1). Beauftragt in `docs/plans/m5/m5-discovery-und-suche.md` §6.1 (UI-05) nach Ottos Zusatz vom 06.11.2026 (§2 Punkt 8 dort).
**Stufe B:** Erst dieser Plan mit Fragen F1 … F9, dann setzt dieselbe Session nach Ottos Antworten Teil 1 um (§8a, §9); Teil 2 bekommt eine neue Session und einen eigenen PR.
**Modell:** Opus, Effort hoch.
**Gilt dazu:** `docs/ui/leitfaden.md` (alle Regeln; Oberflächentexte englisch), `adr/0024` R8 (Marke „Prototype“), `adr/0027` W0 (Konto-Quellen als Katalogeintrag mit Link), `KLAERUNGEN` B10 (keine Vorgaben in der Registry), B12 (Punkt 10 „zuletzt erfolgreich geprüft“).
**Startsatz:** „Führe Aufgabe UI-05 aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.1) aus; Plan unter `docs/plans/vp3/`.“

## 1. Wunsch (Otto, 06.11.2026, aus dem M5-Plan §2 Punkt 8)

- **Control Panel:** nicht mehr alle Datensätze, sondern höchstens sechs auf einer Seite, so viele wie ohne Scrollen Platz haben; Blättern durch die hinzugefügten Datensätze (z. B. „‹ 1/6 ›“).
- **„Advanced search“** ist immer sichtbar.
- **Kein zusätzlicher Text** im Panel (z. B. bei der AOI-Suche oder beim DEM „No time axis – acquired Dec 2010 to Jan 2015“).
- **Datum** generell auf den verfügbaren Zeitraum des Datensatzes begrenzt (auch Sentinel-2).
- **Data catalogue:** Knopf im linken Panel; alle verfügbaren Datensätze durchsehen (gruppiert), zum Control Panel hinzufügen; je Datensatz mehr Angaben (wie STAC, dazu die Quelle).

Aus §6.1 des M5-Plans dazu: Erklärungen hinter (i) bzw. im Tooltip; ohne Zeitachse ist das Datumsfeld gesperrt, der Grund steht im Tooltip; offenes Ende = heute; Angaben im Katalog wie bei STAC (Liste in §4.2); Prototyp-Datensätze mit Marke, Konto-Quellen als Katalogeintrag mit Link; die Suche aus `adr/0026` (Fassung 3) bekommt Platz, wird aber nicht vorweggenommen.

## 2. Bestandsaufnahme (Stand `main`, 06.11.2026)

| Stelle | Heute | Befund für UI-05 |
|---|---|---|
| `ControlPanel.tsx` `DatasetPicker` | ein Knopf je Datensatz aus `/stac/collections`, Raster mit zwei Spalten, zwei Zeilen sichtbar (`.dataset-list`, `max-height`), darüber scrollt die Liste | wird zur Seite mit höchstens sechs Knöpfen und Blättern; zeigt nur die hinzugefügten Datensätze |
| `store.ts` `loadDatasets` | `datasets` = alle Collections, `selectedDatasetIds` leer beim Start | neu: die Menge der hinzugefügten Datensätze (`addedDatasetIds`) neben der gewählten |
| `AdvancedSearch.tsx` | `if (offers.length === 0) return null` — ohne gewählten Datensatz verschwindet der Knopf | immer da; ohne Datensatz gesperrt mit Grund im Tooltip |
| `AcquisitionDateFields` | zwei `type="date"` ohne `min`/`max`; gesperrt, wenn kein gewählter Datensatz eine Zeitachse hat; darunter je Datensatz ohne Zeitachse ein Absatz aus `acquisitionNote` | `min`/`max` aus `extent.temporal`; der Absatz wandert in den Tooltip der gesperrten Felder bzw. in ein (i) |
| `PlaceSearchField` | nach der Wahl eines Ortes die Zeile „Bern · © OpenStreetMap contributors“ unter dem Feld | Zusatztext; die Attribution ist aber Pflichtangabe (ODbL) → **F8** |
| `DatasetNotes` | bei `earthx:maturity` ≠ `stable` ein gelber Absatz („staging: the provider may withdraw …“) | der Satz wandert in ein (i) an „Datasets“ und in die Angaben im Katalog; die Marke am Knopf bleibt. Heute ohne Wirkung (beide Datensätze `stable`) |
| `CoverageLegend` | Absatz „Scenes counted by their center point in the cell“ | wird ein (i) an der Legende; die Angabe „sample: n of m scenes“ bleibt sichtbar (Pflicht nach `ENTSCHEIDUNGEN` §2: Stichprobe kenntlich) |
| Kopf `brand` | „EarthX“ und „Geo and satellite data viewer“ | Marke, keine Erklärung: bleibt (Auslegung A9) |
| Registry (`catalog/registry.py`, `collection.py`) | veröffentlicht `title`, `description`, `keywords`, `license`, `extent` (bbox, Intervall), `links` (`license`, `cite-as`), `sci:doi`, `sci:citation`, `earthx:license_flags` (mit Attribution), `earthx:band_units`, `earthx:auxiliary_assets`, `earthx:mask`, `earthx:capabilities`, `earthx:index_presets`, `earthx:source` (Endpunkt, Hosts), `earthx:health.status`, `earthx:maturity` | **fehlt:** Gruppe, Anbieter (STAC `providers`), Auflösung (`gsd`), `data_region` (kommt mit M5-07), Datum „Last checked“ (kommt mit den Health-Checks, Fassung 3), `legal_status` und `access.account` (kommen mit dem YAML-Lader, M5-Plan §6.4) |
| Registry heute | zwei Datensätze: Sentinel-2 L2A (`2015-06-27` – offen), Copernicus DEM GLO-30 (ohne Zeitachse, Dez 2010 – Jan 2015) | Blättern und Gruppen werden erst mit M5-07 ff. sichtbar; Tests decken mehr als sechs Datensätze mit Fixtures ab |
| `preferences.ts` | Einstellungen je Browser in `localStorage` (`earthx.*`), robust bei gesperrtem Speicher | Muster für die Auswahl des Katalogs (**F4**) |
| `permalink.ts` | hält Auftrag und Ansicht (Mitte, Zoom, Bereich, Basemap, Projektion), keine Datensatz-Auswahl | ein Permalink nennt seinen Datensatz im Auftrag (A7) |

## 3. Control Panel

### 3.1 Seiten mit so vielen Datensätzen, wie Platz haben

*Fassung vom 07.11.2026 (Otto, Review von Teil 2): Die Obergrenze von sechs Datensätzen und drei Reihen je Seite entfällt.*

- Das Panel zeigt **nur die hinzugefügten Datensätze** (`addedDatasetIds`, Reihenfolge des Hinzufügens), in Seiten zu zwei Spalten mit so vielen Reihen, wie Platz haben (Knopf wie heute: Titel und Marke); erst der Rest kommt auf die nächste Seite.
- **So viele, wie ohne Scrollen Platz haben (Auslegung A1):** Die Zahl der Reihen je Seite ist die größte, bei der der scrollende Teil des Panels (`.control-scroll`) nicht scrollen muss, ohne Obergrenze; gemessen mit `ResizeObserver` am Panel, neu bei jeder Größenänderung des Fensters oder des Panels. Mindestens eine Reihe (zwei Knöpfe), auch wenn das Panel dann doch scrollt (sehr niedrige Fenster). Die Seitengröße ändert sich mit der Fensterhöhe; die Seite bleibt die, auf der der zuletzt gewählte Datensatz liegt.
- **Blättern:** unter dem Raster eine Zeile „‹ 1 / 3 ›“ mit `chevron-left` / `chevron-right` (Leitfaden §3, „Bild davor / danach“) und dem Zähler in der Schreibweise des Leitfadens (`4 / 7` mit Leerzeichen, §2). Auf der ersten bzw. letzten Seite ist der Pfeil gesperrt mit Grund („Already on the first page“ / „… last page“). Mit nur einer Seite entfällt die Zeile nicht, sondern bleibt mit „1 / 1“ und zwei gesperrten Pfeilen, damit das Panel nicht springt (A2; Leitfaden §1 Punkt 5).
- **Gewählte Datensätze auf anderen Seiten** bleiben gewählt; die Suche läuft über alle gewählten wie heute. Der Zähler zeigt nur die Seite, nicht die Zahl der gewählten (die steht schon in der Suche).
- **„Select multiple datasets“** und „Coverage“ / „Hide coverage“ bleiben unverändert.
- **Leerzustand:** ohne hinzugefügten Datensatz statt des Rasters „No datasets yet — add some from the Data catalogue“ (Leitfaden §4: Leerzustand, der sagt, was zu tun ist); kommt mit Teil 2, in Teil 1 sind immer alle Datensätze hinzugefügt.

### 3.2 „Advanced search“ immer sichtbar

- Der Knopf steht immer im Fuß des Panels über „Search“. Ohne gewählten Datensatz ist er gesperrt (`aria-disabled`, Leitfaden §4) mit Grund „Choose a dataset to see its filters“.
- Ein offenes „Advanced search“ schließt, wenn der letzte gewählte Datensatz abgewählt wird (wie heute).

### 3.3 Datum auf den verfügbaren Zeitraum begrenzt

- **Bereich:** aus `extent.temporal.interval[0]` der gewählten Datensätze **mit** Zeitachse, als Tag in UTC (`formatDay`). Mehrere gewählt: von frühestem Anfang bis spätestem Ende, offenes Ende = heute (UTC) (A3). Die Felder bekommen `min` und `max`; der Kalender bietet nur diese Tage an.
- **Werte außerhalb:** Ein getippter oder stehen gebliebener Wert außerhalb des Bereichs wird beim Verlassen des Feldes und bei einem Wechsel der Wahl auf die Grenze gesetzt (A4). Leitfaden §2 „Was der Nutzer tippt, gilt genau so“ betrifft Zahlen in Feldern; hier ist die Grenze der Daten die Regel des Felds. → Widerspruch möglich, darum als Auslegung.
- **Ohne Zeitachse** (alle gewählten ohne): beide Felder gesperrt, Grund im Tooltip, gebildet aus der Ausdehnung: „No time axis: acquired Dec 2010 – Jan 2015“ (Text aus `acquisitionNote`, Trenner „–“ nach Leitfaden §2). Der Absatz darunter entfällt.
- **Gemischt** (DEM und Sentinel-2 gewählt): Felder frei mit dem Bereich von Sentinel-2; der Hinweis zum DEM steht hinter einem (i) an „Acquisition date“, nicht als Absatz.
- **Nichts gewählt:** Felder frei, ohne Grenzen (wie heute); die Grenze kommt mit dem ersten gewählten Datensatz.
- Coverage, Histogramm und Suche lesen die Felder wie bisher; der Permalink ist nicht berührt.

### 3.4 Kein Zusatztext

| Text heute | Neu |
|---|---|
| Absatz „No time axis – acquired …“ unter dem Datum | Tooltip der gesperrten Felder bzw. (i) an „Acquisition date“ (§3.3) |
| Zeile „Bern · © OpenStreetMap contributors“ unter dem Ortsfeld | **F8** |
| gelber Absatz zu `earthx:maturity` (`DatasetNotes`) | (i) an „Datasets“ (nur wenn ein gewählter Datensatz nicht `stable` ist; `tone="warn"`) und in den Angaben im Katalog |
| „Scenes counted by their center point in the cell“ | (i) an der Legende der Coverage |
| „sample: n of m scenes“ / „showing n of m scenes“ | bleibt sichtbar (Pflicht, `ENTSCHEIDUNGEN` §2) |
| „n scenes found“, „Correct the filters in Advanced search.“ | bleiben (Wert bzw. Fehler mit Handlung, Leitfaden §4) |
| Kopf „Geo and satellite data viewer“ | bleibt (A9) |

Ein Test in `uiRules.test.ts` findet die verschobenen Texte als Absatz wieder (Muster aus UI-04 Teil 6).

## 4. Data catalogue

### 4.1 Ort und Form

- **Symbol „Data catalogue“ in der Leiste links** (Otto, 06.11.2026, F5; Lucide `library`, neu in `icons.ts` und Leitfaden §3). Es öffnet kein Panel im Dock, sondern das Fenster unten; ein zweiter Klick auf das Symbol schließt es wie das rote x. Die Abweichung von `adr/0026` §7 (dort im linken Panel) ist gewollt (Otto); das Suchfeld kommt später oben ins Fenster.
- **Ein größeres Fenster über der Karte** (**F5**; neue Form „Fenster“, Leitfaden §5, §7): links die gruppierte Liste, rechts die Angaben des gewählten Eintrags. Schließen mit dem roten x oder einem zweiten Klick auf das Symbol in der Leiste (wie bei den linken Panels); Esc schließt nichts; ein Klick neben das Fenster schließt es nicht (wie bei Dialogen; Otto, 06.11.2026, aus `adr/0026`, #301). Unter 900 px über die ganze Breite; die Angaben sind dann eine zweite Stufe mit „Back“ (`arrow-left`).

### 4.2 Liste

- **Gruppen** nach dem neuen Registry-Feld (**F1**), Gruppenköpfe in der Form des Leitfadens (Großbuchstaben per CSS, auf- und zuklappbar mit `chevron-down`/`chevron-right`), in fester Reihenfolge des Feldes; in der Gruppe nach Titel.
- **Zeile:** Titel, Marken (§4.4), rechts ein Knopf **„Add“** (`plus`) bzw. **„Remove“** (`trash-2`), je nachdem, ob der Datensatz im Control Panel ist (Begriffe Leitfaden §2: „Remove“ nimmt aus einer Liste der Oberfläche). Ein nicht anzeigbarer Datensatz (`viewable: false`) ist gesperrt mit Grund, wie im Panel heute. Ein Konto-Datensatz (W0) hat statt „Add“ einen Link zur Quelle (§4.4).
- Klick auf die Zeile zeigt die Angaben; der Knopf wirkt nur auf sich.
- **„Add“** hängt den Datensatz hinten an und blättert das Control Panel auf seine Seite; gewählt wird er nicht (A5). **„Remove“** wählt ihn ab, falls gewählt, und nimmt ihn aus dem Panel; Suchergebnisse, Ansicht und Layer des Datensatzes bleiben (sie sind eigene Dinge) (A6).
- **Platz für die Suche (F6, Nachtrag Otto 06.11.2026):** Der obere Bereich des Fensters bleibt frei für das Suchfeld und den AOI-Schalter aus `adr/0026`, **ohne sichtbar leere Fläche**: Heute steht dort nur die Kopfzeile mit dem Titel „Data catalogue“ und dem roten x; die Liste schließt direkt an. Die Kopfzeile ist ein eigener Bereich (`catalogue-head`), in den Suchfeld und Schalter später als zweite Zeile kommen, ohne die Liste umzubauen.

### 4.3 Angaben je Datensatz

Reihenfolge wie bei einem STAC-Browser, Werte aus `/stac/collections`, nichts aus Code je Datensatz (P10). Was die Collection nicht trägt, zeigt „—“ (Leitfaden §2 „— none —“ gilt für Wahlen; hier ein Wert), nie eine Vermutung.

| Zeile | Quelle in der Collection | Stand |
|---|---|---|
| Titel, Marken | `title`, §4.4 | da |
| Description | `description` | da |
| Provider | STAC `providers` (Name mit Link, Rolle) | **neu (F2)** |
| Source | `earthx:source.endpoint` als Host mit Link zur Collection der Quelle (`…/collections/<source_collection_id>`) | da; Link nur bei `https://` (wie `place-attribution`) |
| License | `earthx:license_flags.name` mit Link `url`, Stufe (`tier`: Catalogue / Display / Processing), Bedingungen (`terms_url`) | da |
| Attribution | `attribution_unmodified` / `attribution_modified`, `{year}` als „[year]“ | da |
| Spatial extent | `extent.spatial.bbox`, als „-180° – 180° E · -90° – 84° N“ über `formatNumber` | da |
| Temporal extent | `extent.temporal.interval`, „2015-06-27 – today“ (`formatDay`); ohne Zeitachse dazu „No time axis“ | da |
| Resolution | STAC `summaries.gsd` (Meter, mehrere Werte „10, 20, 60 m“) | **neu (F2)** |
| Bands | Schlüssel von `earthx:band_units` mit Einheit („red · reflectance“), ohne `earthx:auxiliary_assets`; die Maske aus `earthx:mask` als eigene Zeile | da |
| Data region | `earthx:data_region` | kommt mit M5-07; bis dahin „—“ (A8) |
| DOI | Link `cite-as`, dazu `sci:citation` | da |
| Last checked | Datum der Health-Checks | **fehlt (F7)** |
| Maturity | `earthx:maturity` mit dem Satz aus `maturityNote` | da |
| Processing | Operatoren aus `earthx:capabilities` (`band_math`, `masking`, `value_masking`, `normalization`, `reprojection`, `interpolation` …), Namen wie im Processing-Panel | da |
| Quick processing | Titel aus `earthx:index_presets`; „Enhance contrast“ für alle | da |

### 4.4 Marken

- **„Prototype“** (`adr/0024` R8) bei `earthx:legal_status: unclear`, mit `earthx:legal_note` hinter (i); **„Account“** bei `earthx:access.account` ≠ `none` (`adr/0027` W0), dann Link zur Quelle statt „Add“; Maturity wie heute als Marke. Alle als `Badge` (Leitfaden §7).
- Beide Felder gibt es erst mit dem YAML-Lader (M5-Plan §6.4). → **F7**.

### 4.5 Gespeicherte Auswahl und erster Besuch

- **Speicher (F4):** `addedDatasetIds` je Browser in `localStorage` unter `earthx.datasets` (Muster `preferences.ts`): gesperrter oder werfender Speicher ändert nichts am Verhalten, unbekannte und ausgemusterte Kennungen (`RETIRED`) fallen beim Laden weg, die Reihenfolge bleibt.
- **Erster Besuch (F3, Otto 06.11.2026):** Ohne gespeicherte Auswahl sind alle anzeigbaren Datensätze hinzugefügt, solange es höchstens sechs sind. Gibt es mehr, sind es **die ersten sechs in der Reihenfolge der Gruppen** (Reihenfolge von `category`, in der Gruppe nach Titel), also dieselbe Reihenfolge wie die Liste im Katalog.
- **Permalink (A7):** Öffnet ein Permalink einen Auftrag mit einem Datensatz, der nicht hinzugefügt ist, wird er hinzugefügt (und gespeichert), damit Ansicht und Panel zusammenpassen. Der Permalink selbst trägt keine Auswahl.

## 5. Registry

UI-05 fügt laut M5-Plan §6.2 „nur ein Feld für die Gruppierung“ hinzu. Die Angaben in §4.3 brauchen zwei weitere (**F2**). Vorschlag:

| Feld | Form | STAC | Werte heute |
|---|---|---|---|
| `category` (**F1**) | Enum `DatasetCategory` ohne Vorgabe (B10): `optical`, `radar`, `elevation`, `land_cover`, `weather_climate` | `earthx:category` | Sentinel-2 L2A `optical`, Copernicus DEM `elevation` |
| `providers` (**F2**) | Tupel aus `Provider(name, roles, url)`, mindestens einer, Rollen nach STAC (`producer`, `licensor`, `processor`, `host`) | `providers` (STAC-Kern) | aus der Collection der Quelle übernommen und belegt |
| `gsd` (**F2**) | Tupel aus Metern > 0, mindestens einer | `summaries.gsd` | Sentinel-2 10, 20, 60; DEM 30 |

- Prüfung je Eintrag in `__post_init__` wie die übrigen Felder; ein Test über die ganze Registry, dass alle drei gesetzt sind.
- `architekturplan.md` 5.1 bekommt die Zeilen, `ADDING_ESA_DATASETS.md` bleibt (Beschreibung des Stands vom 13.08.2026).
- **Überschneidung mit M5-07** (`data_region`, WorldCover): beide ändern `registry.py`, `datasets.py`, `collection.py`. Wer später holt, gleicht ab (M5-Plan §6.2). WorldCover bekommt `land_cover`; das trage ich nach, falls M5-07 vorher gemergt ist, sonst M5-07.

## 6. Umsetzung, Tests, Abnahme

### 6.1 Schnitt (F9)

Vorschlag: zwei Teile, je ein Draft-PR unter etwa 400 Zeilen ohne Tests.

| Teil | Inhalt | Dateien (Schwerpunkt) |
|---|---|---|
| **1** | §3: Seiten, „Advanced search“ immer, Datum begrenzt, kein Zusatztext; `addedDatasetIds` im Store mit „alle“ als Startwert (bis Teil 2) | `ControlPanel.tsx`, `AdvancedSearch.tsx`, `store.ts`, `datasets.ts`, `index.css`, Leitfaden |
| **2** | §4, §5: Registry-Felder, Data catalogue, Speicher, Vorauswahl, Permalink | `catalog/registry.py`, `datasets.py`, `collection.py`, neu `DataCatalogue.tsx`, `catalogue.ts`, `preferences.ts`, `icons.ts`, Leitfaden |

Teil 1 in diesem PR, Teil 2 in einer neuen Session mit eigenem PR nach dem Merge von Teil 1.

### 6.2 Tests

- **Seiten:** mit sieben bis dreizehn Datensätzen aus Fixtures (synthetisch): Seitengröße bei 1, 2, 3 Reihen; Pfeile an den Rändern gesperrt mit Grund; gewählte Datensätze auf anderen Seiten bleiben gewählt und werden gesucht; Wechsel der Fensterhöhe behält die Seite des gewählten; kein Scrollen in `.control-scroll` bei 1280 × 800 (Browser-Skript `e2e/dataset-pages.cjs`, Hell/Dunkel, 1280 und 360 px).
- **Advanced search:** sichtbar ohne Datensatz, gesperrt mit Grund (Eintrag in `fixtures/lockedControls.ts`).
- **Datum:** `min`/`max` je Fall (ein Datensatz, gemischt, mehrere mit Zeitachse, ohne Zeitachse, nichts gewählt); offenes Ende = heute mit `testClock`; Wert außerhalb wird auf die Grenze gesetzt; fehlerhafte Ausdehnung (Ende vor Anfang, kein Intervall, ungültiges Datum) ergibt keine Grenze statt eines Fehlers.
- **Zusatztext:** die Texte aus §3.4 nicht als Absatz (`uiRules.test.ts`), das (i) mit Text vorhanden.
- **Katalog (Teil 2):** Gruppen in Reihenfolge, Add/Remove, Remove eines gewählten wählt ab, Konto-Datensatz ohne „Add“, Marke „Prototype“ nur bei `unclear`, Links nur `https://`; Speicher gesperrt, werfend, mit unbekannter und ausgemusterter Kennung, mit kaputtem JSON; Registry-Prüfungen für die neuen Felder (fehlend, leer, negative `gsd`, unbekannte Rolle).
- Gegenprobe der neuen Tests gegen `main` im PR.

### 6.3 Abnahme

- Leitfaden §2, §3, §4, §7, §10 nachgezogen („Data catalogue“, „Add“, Seiten, Datum).
- Vor „fertig“: `vitest`, `tsc`, `oxlint`; bei Teil 2 dazu `ruff`, `pytest`, `lint-imports`; Browser-Skripte, die das Panel berühren (`advanced-search`, `evaluate-coverage`, `narrow-windows`, `settings-panel`, `tooltips`, neu `dataset-pages`).
- Zeile im Entscheidungslog je Teil.

## 7. Auslegungen (angenommen von Otto, 06.11.2026)

- **A1** „So viele wie ohne Scrollen Platz haben“ = gemessene Reihen, mindestens eine (§3.1); bis 06.11.2026 höchstens drei, die Obergrenze hat Otto am 07.11.2026 gestrichen.
- **A2** Die Zeile „‹ 1 / 1 ›“ bleibt auch mit einer Seite, Pfeile gesperrt.
- **A3** Mehrere gewählte Datensätze: Bereich von frühestem Anfang bis spätestem Ende der Datensätze mit Zeitachse.
- **A4** Ein Datum außerhalb des Bereichs wird beim Verlassen des Feldes auf die Grenze gesetzt.
- **A5** „Add“ wählt nicht, blättert aber auf die Seite des Datensatzes.
- **A6** „Remove“ wählt ab; Suchergebnisse, Ansicht und Layer bleiben.
- **A7** Ein Permalink fügt seinen Datensatz hinzu; der Permalink trägt keine Auswahl.
- **A8** `data_region` zeigt „—“, bis M5-07 das Feld setzt.
- **A9** „Geo and satellite data viewer“ im Kopf bleibt (Marke, keine Erklärung).

## 8. Fragen an Otto

**F1 — Gruppierung im Data catalogue?**
1. Nach Art: Optical, Radar, Elevation, Land cover, Weather and climate; Registry-Feld `category` **(Empfehlung)**
2. Nach Anbieter bzw. Land (ESA, NASA, swisstopo, BEV, MeteoSchweiz …)
3. Nach Art, umschaltbar auf Anbieter (braucht F2 Option 1)

**F2 — Anbieter und Auflösung: neue Registry-Felder?**
1. Ja: `providers` und `gsd` nach STAC, dazu `category` — drei Felder statt einem **(Empfehlung)**
2. Nur `category`; Anbieter und Auflösung zeigen „—“ bis Fassung 3
3. Nur `category` und `providers`; Auflösung später

**F3 — Vorauswahl beim ersten Besuch?**
1. Alle anzeigbaren Datensätze der Registry, solange es höchstens sechs sind; darüber frage ich neu **(Empfehlung)**
2. Keiner; das Panel zeigt den Leerzustand mit dem Knopf „Data catalogue“
3. Eine Startauswahl als Registry-Feld (`preselected`)

**F4 — Wo wird die Auswahl gespeichert?**
1. Je Browser (`localStorage`), wie die Einstellungen; Permalink fügt seinen Datensatz hinzu (A7) **(Empfehlung)**
2. Je Browser und zusätzlich im Permalink
3. Nur für den Besuch (Neuladen = Vorauswahl)

**F5 — Form des Data catalogue?**
1. Blatt neben dem Dock über der Karte, Liste links, Angaben rechts, rotes x **(Empfehlung)**
2. Eigenes Panel in der Leiste links (340 px), Angaben aufklappbar in der Zeile
3. Ersetzt den Inhalt von „Search and area“, zurück mit `arrow-left`

**F6 — Platz für die Suche aus `adr/0026`?**
1. Heute kein Feld; die Kopfzeile ist so gebaut, dass es später passt **(Empfehlung)**
2. Schon jetzt ein einfacher Filter über Titel, Beschreibung und `keywords`, den Fassung 3 ersetzt

**F7 — Angaben, die es noch nicht gibt (Last checked, Prototype, Account)?**
1. Zeilen und Marken jetzt bauen und aus der Collection lesen, wenn das Feld da ist; „Last checked“ zeigt „—“ mit Tooltip „Not checked yet“; Tests mit Fixtures **(Empfehlung)**
2. Erst bauen, wenn die Felder kommen (Fassung 3, YAML-Lader)

**F8 — Attribution der Ortssuche („© OpenStreetMap contributors“) nach der Wahl?**
1. Die Zeile unter dem Feld entfällt; die Attribution steht in der Ergebnisliste und danach hinter einem (i) am Feld **(Empfehlung)**
2. Bleibt sichtbar als Pflichtangabe (ODbL), nur der Ortsname davor entfällt
3. Entfällt ganz nach der Wahl

**F9 — Schnitt?**
1. Zwei Teile nach §6.1, Teil 1 in diesem PR **(Empfehlung)**
2. Alles in diesem PR (über dem Richtwert von etwa 400 Zeilen)
3. Erst Teil 2 (Katalog), dann Teil 1

## 8a. Antworten Otto (06.11.2026)

- **F1–F9:** jeweils Option 1.
- **F5** ausdrücklich so: ein größeres Fenster über der Karte mit rotem x, geöffnet über ein Symbol „Data catalogue“ in der linken Leiste (§4.1). Die Abweichung von `adr/0026` §7 (dort linkes Panel) ist gewollt; das Suchfeld kommt später oben ins Fenster (F6).
- **F3 ergänzt:** Gibt es mehr als sechs Datensätze, sind beim ersten Besuch die ersten sechs in der Reihenfolge der Gruppen hinzugefügt (§4.5).
- **A1–A9** angenommen.
- Danach: Teil 1 umsetzen (§6.1, §9).
- **Nachtrag (Otto, 06.11.2026, aus `adr/0026`, #301):** Der Data catalogue ist ein Fenster: ein Klick daneben schließt es nicht, ein zweiter Klick auf das Symbol in der Leiste schließt es. Der obere Bereich bleibt frei für Suchfeld und AOI-Schalter, ohne sichtbar leere Fläche (§4.1, §4.2). Die Form „Fenster“ steht im Leitfaden §5 und §7.
- **Review von Teil 2 (Otto, 07.11.2026):** Die Obergrenze von sechs Datensätzen je Seite entfällt. Jede Seite zeigt so viele, wie ohne Scrollen ins Panel passen, neu berechnet bei jeder Größenänderung des Fensters; erst der Rest kommt auf die nächste Seite. Die Vorauswahl beim ersten Besuch bleibt bei höchstens sechs (F3). Umgesetzt in §10.
- **Review von Teil 1 (Otto, 06.11.2026):**
  1. **Seitenpfeile** oben, klein, rechts neben der Überschrift „Datasets“ statt unter der Liste; weiter mit gesperrtem Pfeil und Grund am Rand. Umgesetzt: „‹ 1 / n ›“ steht in der Kopfzeile zwischen „Datasets“ und „Select multiple datasets“, ohne Umbruch (bei 320 px bricht dafür „Select multiple datasets“ in zwei Zeilen).
  2. **Datum vorausgefüllt** mit dem frühesten und spätesten Aufnahmedatum des gewählten Datensatzes (offenes Ende = heute), bei mehreren über alle; bei jeder neuen Datensatz-Wahl neu; was Otto selbst einträgt, bleibt bis dahin. Ersetzt A4 für die neue Wahl (dort wurde nur auf die Grenze geschoben); beim Verlassen eines Feldes gilt A4 weiter. Auslegungen (gelten, bis Otto widerspricht): (a) bei gemischter Wahl zählen nur die Datensätze mit Zeitachse, wie bei den Grenzen (§3.3); (b) nur mit Datensätzen ohne Zeitachse zeigen die gesperrten Felder deren Zeitraum (DEM: 2010-12-01 → 2015-01-31; ESA WorldCover 2020 aus M5-07: 2020-01-01 → 2020-12-31, beide Jahre gewählt 2020-01-01 → 2021-12-31); (c) ohne gewählten Datensatz sind die Felder leer; (d) „neue Wahl“ ist die Wahl im Panel (Klick auf einen Datensatz, Ende der Mehrfachwahl), nicht das Öffnen eines Layers, das seinen Datensatz mit anwählt.
  3. **Folgen:** Die Suche trägt jetzt immer einen Zeitraum. Sie kommt mit den neuesten Treffern zuerst: das Backend schickt jeder Suche `sortby` nach `datetime` absteigend (`adapters/federated_search.py` `SORTBY`, Test `test_every_search_carries_our_own_fixed_sortby`), die Liste gruppiert „newest first“ (`grouping.ts`). „Filter within AOI only“ braucht einen Zeitraum mit beiden Enden und ist mit einer AOI damit immer frei.
  4. **Messung der ersten Suche und der Coverage über das ganze Archiv: in der Cloud-Sitzung nicht möglich.** Das API startete lokal (Platzhalter für den Objektspeicher), Earth Search ist per Name erreichbar, aber `gateway` verbindet sich bewusst mit der aufgelösten IP-Adresse (Name nur per SNI und `Host`, `gateway/client.py` `_once`); über den Proxy der Sitzung scheitert das mit `transport`. Eine Änderung daran wäre eine Lockerung von `gateway` und bleibt bei Otto. Die Messung braucht einen lokalen Lauf bei Otto (Frage im PR).

## 9. Teil 1 umgesetzt (06.11.2026)

Umgesetzt wie §3, mit den Auslegungen A1–A4 und F8:

- **Seiten:** `datasetPages.ts` (Reihen, die passen; Seitenzahl; Seite eines Eintrags), `DatasetPicker` misst mit `ResizeObserver` den freien Platz in `.control-scroll` und hält das Raster auf der Höhe einer vollen Seite (`--dataset-rows`). Ohne Layout (jsdom) bleiben drei Reihen.
- **„Advanced search“:** immer da; ohne gewählten Datensatz „Choose a dataset to see its filters“, mit gewählten ohne Filter „The chosen datasets offer no filters“ (`aria-disabled`).
- **Datum:** `dateBounds.ts`; `min`/`max` an beiden Feldern, Grenze beim Verlassen des Feldes und bei jeder neuen Wahl (`applyDatasetSelection` im Store).
- **Kein Zusatztext:** wie §3.4; `DatasetNotes` ist durch eine Warnung an „Datasets“ ersetzt, die Zeile der Ortssuche durch ein (i) am Feld (F8).
- **Abweichung von §6.1:** `addedDatasetIds` kommt erst mit Teil 2. In Teil 1 sind alle Datensätze der Registry „hinzugefügt“, das Panel blättert über `datasets`; ein Feld im Store, das nichts ändert, wäre bis dahin ein toter Rest.
- **Beobachtung:** Nach dem Klick auf den letzten „Next page“ ist der Pfeil gesperrt, sein Grund erscheint aber erst, wenn der Zeiger den Pfeil verlässt und wieder darüber kommt (`TipLayer` reagiert auf das Hineinfahren, nicht auf eine neue Sperre unter dem Zeiger). Gilt ebenso für andere Knöpfe, die sich durch den eigenen Klick sperren; nicht geändert.

**Geprüft:** `vitest` (alle Dateien), `tsc`, `oxlint`; Gegenprobe der neuen und geänderten Tests gegen die Komponenten von `main` (22 scheitern); Browser-Skript `e2e/dataset-pages.cjs` (Hell/Dunkel; 1280 × 800, 1280 × 560, 360 und 320 px) grün, gegen `main` bricht es ab (kein Zähler). `e2e/focus-and-type.cjs` grün. `advanced-search`, `evaluate-coverage`, `narrow-windows`, `settings-panel`, `tooltips`, `selection-block` und `within-aoi` scheitern auf `main` genauso wie auf dem Branch (gleiche Befunde, gleiche Stellen); `advanced-search.cjs` ist an Teil 1 angepasst (Schritt 1: Knopf beim DEM da und gesperrt), die Schritte davor bestehen.

## 10. Teil 2 umgesetzt (06.11.2026)

Umgesetzt wie §4 und §5 mit F1–F9, A5–A8 und dem Nachtrag zu F5/F6; alle vier Einträge auf `main` haben die neuen Felder, auch ESA WorldCover 2020 und 2021 aus M5-07.

- **Registry:** `category` (`DatasetCategory`), `providers` (`Provider(name, roles, url)`, Rollen `ProviderRole`, `url` nur `https://` oder keine) und `gsd` (Meter > 0, aufsteigend, je Wert einmal), alle ohne Vorgabe (B10), geprüft in `__post_init__`; veröffentlicht als `earthx:category`, `providers` und `summaries.gsd`; `architekturplan.md` 5.1 nachgezogen. Werte:
  - Sentinel-2 L2A: `optical`, `gsd` 10, 20, 60; Anbieter aus der Collection der Quelle (Earth Search, gelesen 06.11.2026). Die Quelle verlinkt AWS nur über `http://`; der Eintrag „AWS“ bleibt darum ohne Link.
  - Copernicus DEM GLO-30: `elevation`, `gsd` 30 (Raster von GLO-30 laut `readme.html` des Buckets; die Collection nennt keine `gsd`); Anbieter aus der eigenen STAC-Collection des Buckets (`copernicus-dem-30m-stac`, `dem_cop_30.json`).
  - ESA WorldCover 2020 und 2021: `land_cover`, `gsd` 10 (`readme.html` des Buckets). Der Bucket hat keine STAC-Collection, und Terrascope und Planetary Computer sind aus der Sitzung nicht erreichbar; die Anbieter stammen darum aus der Collection, die `stactools-packages/esa-worldcover` für das Produkt baut (`PROVIDERS` in `constants.py`), wörtlich übernommen.
- **Frontend:** `catalogue.ts` (Gruppen, Erstbesuch, Angaben je Datensatz nur aus der Collection), `DataCatalogue.tsx` (Fenster), Symbol `library` als zweites in der Leiste, `addedDatasetIds` im Store, Speicher `earthx.datasets` (`preferences.ts`), Permalink fügt die Datensätze seines Auftrags hinzu (A7), Leerzustand im Panel.
- **Auslegungen.** (a)–(d) und (h) sind **fest** (Otto, 06.11.2026; in der Rückmeldung zu #310 als 1–5 nummeriert, nicht zu verwechseln mit A1–A5 aus §7). (e), (f) und (g) gelten, bis Otto widerspricht:
  - (a) *fest:* **Source** verlinkt den Endpunkt der Quelle, nicht `…/collections/<source_collection_id>`: DEM und WorldCover kommen aus Buckets, deren `source_collection_id` keine STAC-Collection ist; der Link dorthin führte ins Leere. Die Kennung steht als Text daneben („earth-search.aws.element84.com · sentinel-2-c1-l2a“).
  - (b) *fest:* **„Remove“** (A6) wählt ab, ohne die Ergebnisse der letzten Suche und den aktiven Datensatz zu verwerfen; der aktive Datensatz darf bis zur nächsten Wahl im Panel ein nicht mehr gewählter sein. Während eine Suche läuft, ist „Remove“ eines gewählten Datensatzes gesperrt („Wait until the search is finished“).
  - (c) *fest:* **Layer:** Wählt ein Layer seinen Datensatz an (wie bisher), kommt dieser zurück ins Panel, falls er entfernt war; sonst gäbe es eine gewählte, aber unsichtbare Auswahl. Gleicher Gedanke wie A7.
  - (d) *fest:* **Erstbesuch** wird nicht gespeichert, bis der Nutzer etwas hinzufügt oder entfernt; bis dahin folgt die Vorauswahl der Registry (ein neuer Datensatz erscheint, solange es höchstens sechs sind).
  - (e) Eine Collection ohne oder mit unbekannter `earthx:category` steht in einer Gruppe „Other“ am Ende, damit die Lücke sichtbar ist.
  - (f) **„Last checked“** zeigt immer „—“ mit „Not checked yet“: Das Feld kommt mit M5-24 unter `earthx:health` (`adr/0025` §6.6, Otto 06.11.2026); bis dahin liest das Frontend keines, M5-24 schließt die Zeile daran an.
  - (g) **Konto-Datensatz:** statt „Add“ ein Link „Source“ auf den Endpunkt; ohne `https`-Endpunkt bleibt „Add“ gesperrt mit Grund.
  - (h) *fest:* **Quick processing** in den Angaben nennt, was die Seitenleiste anbietet: die Indizes und „Enhance contrast“ nur bei einem Datensatz mit Echtfarbenbild (nicht „für alle“ wie in §4.3).
- **Nach dem Review (Subagent `reviewer`):** Ein übernommener Auftrag („Open in panel“, „Process“ eines Ergebnis-Layers, Index, Permalink) bringt seinen Datensatz zurück ins Panel (sonst gewählt, aber unsichtbar); unter 900 px schließt ein Symbol eines Panels der Leiste das Fenster, weil es das Panel ganz verdeckt; das Fenster liegt über Seitenleiste und Processing-Sheet (sonst verdeckten sie das rote x); ein Endpunkt, den `URL` nicht lesen kann, ergibt „—“ statt eines Absturzes; `Provider.url` verlangt einen Host. Offen gelassen: Ein anzeigbarer Datensatz mit Konto (`access.account`) könnte über einen Layer gewählt werden, ohne ins Panel zu kommen; heute nicht erreichbar, weil das Feld erst mit dem YAML-Lader kommt. Ein Datensatz, der beim Laden vorübergehend fehlt, fällt aus der gespeicherten Liste, sobald der Nutzer sie ändert (wie §4.5 „fallen beim Laden weg“).
- **Nach dem Review von Otto (07.11.2026):** `rowsThatFit` kennt keine Obergrenze mehr; drei Reihen sind nur noch der Startwert vor der ersten Messung (und ohne Layout, jsdom). Dabei aufgefallen und behoben: Der Platz wurde an `.control-scroll` gemessen, das nur so hoch ist wie sein Inhalt; die Messung sah darum nur Mangel, nie freien Platz, und ein Fenster, das wieder höher wurde, bekam seine Reihen nicht zurück (schon in Teil 1, dort durch die drei Reihen kaum sichtbar). Gemessen wird jetzt am Panel: seine Höhe ohne den Fuß mit „Search“, beobachtet am Panel selbst. `e2e/dataset-pages.cjs` hat dafür 23 Datensätze und ein hohes Fenster (1280 × 1200), verlangt dort mehr als sechs je Seite und prüft, dass ein niedrigeres Fenster Reihen wegnimmt und das wieder höhere sie zurückgibt.
- **Umfang:** über dem Richtwert von etwa 400 Zeilen ohne Tests (Registry, Store, zwei neue Module und CSS); ein weiterer Schnitt hätte Teile ohne Oberfläche ergeben.

**Geprüft:** `pytest` (Backend), `ruff`, `lint-imports`, `vitest`, `tsc`, `oxlint`; Browser-Skripte `e2e/data-catalogue.cjs` (neu; Hell/Dunkel, 1280 und 360 px, mit erfundenen und mit den echten vier Collections) und `e2e/dataset-pages.cjs` (angepasst: speichert seine neun Datensätze, weil ein Erstbesuch höchstens sechs hinzufügt) grün; `e2e/narrow-windows.cjs` und `e2e/tooltips.cjs` grün, `e2e/settings-panel.cjs` nach Anpassung (sechs Symbole; Panels über ihre Kennung statt über die Position) grün. Gegenprobe: Die Tests zu Permalink, Layer und übernommenem Auftrag scheitern ohne die jeweilige Änderung.
