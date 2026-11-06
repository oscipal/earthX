# UI-05 — Data catalogue und Control Panel

**Stand:** 06.11.2026, **angenommen** von Otto am 06.11.2026 (§8a: F1–F9 jeweils Option 1, F5 mit Symbol in der Leiste, F3 ergänzt; A1–A9 angenommen). Teil 1 umgesetzt (§9). Beauftragt in `docs/plans/m5/m5-discovery-und-suche.md` §6.1 (UI-05) nach Ottos Zusatz vom 06.11.2026 (§2 Punkt 8 dort).
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

### 3.1 Seiten mit höchstens sechs Datensätzen

- Das Panel zeigt **nur die hinzugefügten Datensätze** (`addedDatasetIds`, Reihenfolge des Hinzufügens), in Seiten zu höchstens sechs Knöpfen (zwei Spalten, höchstens drei Reihen, Knopf wie heute: Titel und Marke).
- **So viele, wie ohne Scrollen Platz haben (Auslegung A1):** Die Zahl der Reihen je Seite ist die größte von 1 bis 3, bei der der scrollende Teil des Panels (`.control-scroll`) nicht scrollen muss; gemessen mit `ResizeObserver` an Fenster und Panel. Mindestens eine Reihe (zwei Knöpfe), auch wenn das Panel dann doch scrollt (sehr niedrige Fenster). Die Seitengröße ändert sich mit der Fensterhöhe; die Seite bleibt die, auf der der zuletzt gewählte Datensatz liegt.
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
- **Ein größeres Fenster über der Karte** (**F5**): links die gruppierte Liste, rechts die Angaben des gewählten Eintrags. Schließen mit dem roten x (Leitfaden §5: Blätter haben das x), Esc schließt nichts, Klick daneben schließt nicht. Unter 900 px über die ganze Breite; die Angaben sind dann eine zweite Stufe mit „Back“ (`arrow-left`).

### 4.2 Liste

- **Gruppen** nach dem neuen Registry-Feld (**F1**), Gruppenköpfe in der Form des Leitfadens (Großbuchstaben per CSS, auf- und zuklappbar mit `chevron-down`/`chevron-right`), in fester Reihenfolge des Feldes; in der Gruppe nach Titel.
- **Zeile:** Titel, Marken (§4.4), rechts ein Knopf **„Add“** (`plus`) bzw. **„Remove“** (`trash-2`), je nachdem, ob der Datensatz im Control Panel ist (Begriffe Leitfaden §2: „Remove“ nimmt aus einer Liste der Oberfläche). Ein nicht anzeigbarer Datensatz (`viewable: false`) ist gesperrt mit Grund, wie im Panel heute. Ein Konto-Datensatz (W0) hat statt „Add“ einen Link zur Quelle (§4.4).
- Klick auf die Zeile zeigt die Angaben; der Knopf wirkt nur auf sich.
- **„Add“** hängt den Datensatz hinten an und blättert das Control Panel auf seine Seite; gewählt wird er nicht (A5). **„Remove“** wählt ihn ab, falls gewählt, und nimmt ihn aus dem Panel; Suchergebnisse, Ansicht und Layer des Datensatzes bleiben (sie sind eigene Dinge) (A6).
- **Platz für die Suche (F6):** Die Kopfzeile des Blatts hat links den Titel „Data catalogue“ und ist so gebaut, dass später ein Suchfeld aus `adr/0026` darunter passt; heute steht dort nichts.

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

- **A1** „So viele wie ohne Scrollen Platz haben“ = gemessene Reihen 1–3, mindestens eine (§3.1).
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
