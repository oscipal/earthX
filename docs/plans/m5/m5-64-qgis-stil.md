# M5-64 — QGIS-Stil bei jedem Export

**Stand:** 27.11.2026, Plan mit Fragen an Otto (§8). Umsetzung nach den Empfehlungen in zwei Draft-PRs (§9); wo eine Antwort anders ausfällt, ändert dieselbe Session nach.
**Stufe B.** Höchstens zwei PRs (M5-Plan §2 Punkt 11).
**Grundlagen:** `docs/adr/0028-band-export-formen.md` §6, `docs/plans/m5/m5-60-darstellung-je-band.md` §3.2, §11, §13–§15, `docs/plans/m5/m5-62-klassenlegende.md` §5, `docs/adr/0035-darstellung-am-operator.md`, Entscheidungslog bis 27.11.2026 (Vorgabe Otto 20.11.2026, M5-68 F11–F14 vom 27.11.2026).

Belegstufen: **M** in dieser Session gemessen (QGIS 3.34.4 „Prizren“, LTR, aus Ubuntu 24.04), **P** am Quelltext gelesen (Stand `main` nach #424), **A** eigene Ableitung.

---

## 1. Auftrag (Otto, 20.11.2026, Startsatz 27.11.2026)

Neben jeder Rasterdatei im Export-ZIP liegt eine QGIS-Stildatei `.qml` gleichen Namens. QGIS lädt sie beim Öffnen automatisch, und die Daten sehen aus wie in der App:

- **Ein Band:** dieselbe Farbskala mit demselben Min/Max. Die Werte sind physikalisch und passen bei skalierten Bändern zu den gespeicherten Werten der Datei.
- **RGB:** dieselbe Streckung je Kanal.
- **Klassenband:** Werte, Farben und Namen aus `band_classes` (Renderer „paletted“), passend zur Farbtabelle in der GeoTIFF.

Das gilt für alle Exporte mit Rasterdateien („Download crop“, Export-Job, Processing-Ergebnisse), für „per band“ und für „One multi-band file“.

- **Welche Darstellung:** die, die der Nutzer beim Export gerade eingestellt hat (Look der Ebene), sonst der Look aus der Collection.
- **Farbskalen** werden als Farbrampe mit genügend Stützstellen geschrieben, ohne QGIS-eigene Rampennamen.
- **Worker-Kern bleibt zustandslos:** Der Look kommt mit dem Auftrag.

## 2. Messungen in QGIS [M]

| Frage | Ergebnis |
|---|---|
| Wendet QGIS `scale`/`offset` einer GeoTIFF an? | **Ja.** Ein `uint16`-Wert 1500 mit 0.0001/−0.1 wird als 0,05 abgefragt; der Datentyp erscheint als Float32, die Statistik ist physikalisch. Min/Max im Stil sind deshalb **physikalisch**, genau wie `low`/`high` eines Looks. Eine Umrechnung in gespeicherte Werte wäre falsch. Damit ist die offene Frage aus M5-60 §3.2 beantwortet. |
| Gibt es ein Schema? | **Nein.** QGIS liefert weder DTD noch XSD; `http://mrcc.com/qgis.dtd` im Kopf ist ein historischer Name. Maßstab sind deshalb **Referenzdateien, die QGIS selbst schreibt** (`saveNamedStyle`, Kategorie „Symbology“): `singlebandpseudocolor`, `multibandcolor` und `paletted`. |
| Laden und Zeichnen | Alle drei Referenzstile laden (`loadNamedStyle` ok). Sie zeichnen die erwarteten Farben: Rampe, Streckung je Kanal auf physikalischen Werten, Klassenfarben. Werte ohne Klasse bleiben durchsichtig. |
| nodata bei skalierten Bändern | **Befund:** QGIS vergleicht den rohen nodata-Wert (0) mit dem **skalierten** Wert. Ein Pixel mit dem physikalischen Wert genau 0 wird durchsichtig, bei Sentinel-2 der Rohwert 1000. Das ist QGIS-Verhalten, die App zeichnet es nicht so. Ein Stil kann es nicht ändern, weil der nodata-Wert zur Ebene gehört, nicht zur Symbologie (F6). |

## 3. Ausgangslage [P]

| Export | Wo die Rasterdateien entstehen | Look heute |
|---|---|---|
| „Download crop“ | `access/download.py::build_download_zip`, `exports/…` nach `band_export.plan_files` | nicht im Auftrag (`DownloadRequest`) |
| Export-Job (Angebot nach 413; ganze Szene in „per resolution“/„multi band“) | `processing/export.py::export`; Dateien bitgleich zum Zuschnitt (Test) | nicht im Auftrag; `Attachments` (nicht gehasht) tragen Bänder und Texte |
| Processing-Ergebnis (`result.tif`, `mask.tif`) | Worker schreibt die Rasterdateien. Das ZIP baut `api` beim Herunterladen (`processing_route._job_members`), auch für Bündel. | Ebene in der App: Look aus Collection, Operator oder Preset, im Browser verstellbar |
| Index-Download (Job mit `result.zip`) | wie Processing-Ergebnis | Look des Presets |
| Ganze Szene „per band“ | ZIP im Browser aus den Originaldateien (`originalsZip.ts`) | — |

- Klassen tragen schon Farbtabelle und `.aux.xml` (M5-62).
- Der Look je Band ist in der Registry aufgelöst (`DatasetConfig.look_of`, physikalisch).
- Presets und Operatoren haben eigene Looks (`IndexPreset`, `CompositePreset`, `x-earthx-looks`).

## 4. Was in welche `.qml` kommt

### 4.1 Form der Datei

Wie die Referenz von QGIS mit der Kategorie „Symbology“:
- `<!DOCTYPE qgis …>` und `<qgis styleCategories="Symbology" version="3.34.4-Prizren">`;
- darin `<pipe>` mit `rasterrenderer`, `brightnesscontrast`, `huesaturation` und `rasterresampler`, alle mit den Vorgaben von QGIS;
- `minMaxOrigin` mit `limits=None`, damit QGIS die geschriebenen Zahlen behält und nichts neu berechnet.

Die Datei ist UTF-8, deterministisch und ohne Zeitstempel. So bleiben Zuschnitt und Job bitgleich, und das ETag des Ergebnis-ZIPs bleibt stabil.

### 4.2 Je Datei

| Datei | Stil |
|---|---|
| ein Band mit Klassen (unveränderte Werte, `band_classes` bzw. `classification:classes` eines Ergebnisses) | `paletted`, je Klasse Wert, Farbe, Name; dieselbe Liste wie Farbtabelle und `.aux.xml` (`band_classes`), nodata nicht in der Palette |
| ein Band mit Messwerten | `singlebandpseudocolor`, `colorrampshader` `INTERPOLATED`, `clip="0"` (Werte außerhalb in den Endfarben, wie der Tiler), `minimumValue`/`maximumValue` = Bereich des Looks (physikalisch), Rampe als **256 Stützstellen** (`item`) aus genau der Tabelle, die der Tiler zeichnet (F1), dazu die `colorramp` als Gradient mit denselben Farben |
| ein Asset mit drei Bändern (Echtfarbe `visual`) | `multibandcolor` 1/2/3, je Kanal `StretchToMinimumMaximum` mit dem Bereich des Looks des Assets (Standardbild 0–255) |
| mehrbandige Datei, in der die drei Bänder eines RGB-Looks liegen (Komposit-Preset, Echtfarbe aus Bändern) | `multibandcolor` auf deren Bandnummern, Streckung je Kanal aus dem Look |
| mehrbandige Datei ohne passendes RGB | F2 |
| Maske (`…_mask.tif`, `mask.tif`) | F7 |

### 4.3 Woher der Bereich kommt

1. **Look im Auftrag** (was der Nutzer gerade sieht). Bereiche sind physikalisch (M5-68). Es gibt einen Eintrag je Band oder Asset und höchstens ein RGB.
2. **Sonst** in dieser Reihenfolge:
   - der Look des Operators des letzten Schritts (`x-earthx-looks`, `adr/0035`);
   - bei einem Index-Ergebnis der Look des Index-Presets;
   - bei einem Band mit unveränderten Werten (`earthx:source_values`) bzw. einem Band der Quelle der Look der Collection (`look_of`);
   - sonst `viridis` gemessen.
3. **`fixed`** nimmt `low`/`high`. **`measured`/`percentiles`** brauchen Zahlen (F5):
   - Für Zuschnitt und Export misst der Schreiber die fertige Datei einmal: Perzentile 2/98 bzw. Min/Max der gültigen Pixel, aus einer verkleinerten Lesung (höchstens 1024 px Kante), physikalisch.
   - Beim Ergebnis nimmt er die Statistik in der Maske, die schon in den Eigenschaften steht (M4-32).
   - Beides ist nur eine Rechnung je Datei, nie je Kachel (M5-60 §11).

### 4.4 Wie der Look reist (Worker zustandslos)

| Export | Weg | Hash |
|---|---|---|
| „Download crop“ | neues Feld `look` in `DownloadRequest` | Rezept des Zuschnitts unverändert |
| Export-Job | Seiteneingang `look` neben `recipe` (wie `aoiProvenance`), von `api` in die `Attachments` gelegt; der Kern liest ihn von dort | Rezept und Hash unverändert, `Attachments` sind nicht gehasht |
| Processing-Ergebnis und Index-Download | Parameter `look` beim Herunterladen des ZIPs (`GET …/result.zip?look=…`, Bündel: je Job im Body). Das ZIP baut `api`; der Worker ändert sich nicht. Das ist der Look **beim Export**, also beim Herunterladen (F3). | — |
| ganze Szene „per band“ (Browser) | F4 | — |

Form des Looks (ein JSON-Objekt; im Rezept nie, in keiner URL außer als Darstellungsparameter):

```json
{"bands": {"B04": {"colormap": "viridis", "low": 0.0, "high": 0.3}},
 "rgb": {"bands": ["B12", "B8A", "B04"], "ranges": [[0, 0.4], [0, 0.5], [0, 0.3]]}}
```

- Schlüssel sind Asset-Schlüssel (Zuschnitt, Export) bzw. Bandnamen (Ergebnis).
- `colormap` muss ein Name der Liste des Tilers sein (`GET /colormaps`); unbekannte Namen lehnt `api` ab (422).
- Klassen kommen nie aus dem Auftrag, sondern immer aus `band_classes` bzw. den Klassen des Ergebnisses.

### 4.5 Farbtabellen im Worker-Kern

`access/colormaps.py` lädt titiler und die Registry, beides gehört nicht in den Kern. Die Tabellen der Rampen (rio-tiler, `rocket`/`mako` aus `colormap_data/`, die `_r`-Umkehrungen) wandern in ein schlankes Modul `access/colormap_tables.py`. `colormaps.py` baut darauf auf, und dieselbe Tabelle zeichnet Tiler und `.qml`. Ein Test prüft, dass beide für jeden Namen gleich sind.

## 5. Umfang

**PR 1 (Plan und Backend):**
- `access/colormap_tables.py`;
- `access/qgis_style.py`: die drei Stile, die Wahl je Datei, die Messung einer Datei;
- `.qml` in `build_download_zip`, `export()` (alle Formen, flach, Radar) und im Ergebnis-ZIP und in Bündeln (`api`);
- `look` in `DownloadRequest`, Seiteneingang der Jobs, Parameter des Ergebnis-ZIPs;
- Referenzdateien von QGIS unter `backend/tests/fixtures/qgis/` mit Skript `scripts/write-qgis-reference-styles.py` (läuft nur mit QGIS);
- Tests;
- `adr/0028` §6, Entscheidungslog.

**PR 2 (Frontend):**
- der aktuelle Look geht mit jedem Export mit: „Download crop“ aus Ebene, Ansicht oder Auswahl; Export-Angebot; ganze Szene; Index-Download; Ergebnis-ZIP und Bündel;
- F4 (Stile für das ZIP im Browser);
- Tests, Browser-Check.

## 6. Tests [A]

- **Gegen QGIS-Referenz** (CI, ohne QGIS): Unsere `.qml` hat dieselbe Struktur wie die von QGIS geschriebene Referenz:
  - gleiche Elemente und Attribute, ohne Rücksicht auf die Reihenfolge der Attribute;
  - die Werte (Farben, Min/Max, Bandnummern, Klassen) sind die erwarteten.
- **Mit QGIS** (nur wo `qgis.core` importierbar ist, hier in der Session gelaufen, in der CI übersprungen): QGIS lädt jede erzeugte `.qml`. Geprüft werden Renderer, Min/Max bzw. Streckung, Palette sowie die gezeichnete Farbe an bekannten Pixeln.
- **Exporte:**
  - Zuschnitt und Job bitgleich, auch die `.qml` (bestehender Test um `.qml` erweitert);
  - je Form die richtigen `.qml`-Namen;
  - Klassen passen zur Farbtabelle;
  - ein skaliertes Band hat physikalische Grenzen;
  - unbekannte Colormap → 422;
  - falsche oder zweckfremde Looks (nicht endlich, `low > high`, zu viele Bänder, fremde Felder) → 422;
  - Ergebnis-ZIP mit und ohne `look` (ETag je Look stabil).

## 7. Für Otto in QGIS (nach dem Merge)

1. `catalog-load` ist nicht nötig, es ändert sich keine Collection.
2. **Sentinel-2, ein Band:** Ansicht „Crop to AOI“ öffnen, unter „Band“ z. B. B04 wählen, Farbskala `viridis`, „Apply“. Dann „Download crop“, „One file per band“. ZIP entpacken, `exports/B04_red_10m.tif` in QGIS ziehen.
   - Die Symbologie ist „Singleband pseudocolor“ mit `viridis` und demselben Min/Max wie in der App.
   - „Identify“ zeigt physikalische Werte.
3. **Sentinel-2, RGB:** in derselben Ansicht „Quick processing“ ein Komposit (z. B. „SWIR“) wählen, dann „Download crop“ mit „One multi-band file“.
   - `exports/bands_20m.tif` öffnen: „Multiband color“ mit den drei Bändern auf R/G/B und der Streckung je Kanal wie in der App.
   - Zusätzlich das Standardbild (`visual`, „One file per band“): „Multiband color“ 0–255.
4. **WorldCover:** Zuschnitt herunterladen, `exports/…map….tif` öffnen. „Paletted/Unique values“ zeigt dieselben Farben und Namen wie die Legende der App.
5. **Processing-Ergebnis:** Job mit „Band math“ (z. B. NDVI) laufen lassen und die Ergebnis-Ebene in der App einfärben (z. B. `rdylgn`, −1…1). Dann über ⇩ der Ebene `result.zip` laden und `result.tif` öffnen: Farben und Bereich wie in der App.
6. Gegenprobe: Im Layer-Fenster „Style → Load Style…“ zeigt die geladene `.qml`.

## 8. Fragen an Otto

**F1 – Stützstellen der Farbrampe**
1. 256, genau die Tabelle des Tilers; die Datei wird dadurch etwa 20 KB groß, im ZIP gepackt wenige KB. **Empfehlung.**
2. 32 Stützstellen, linear dazwischen; kleinere Datei, Abweichung höchstens eine Farbstufe.

**F2 – Mehrbandige Datei ohne passenden RGB-Look** (z. B. „One multi-band file“ mit B02, B03, B04 und einem Look für ein einzelnes Band)
1. Liegt das Band des Looks in der Datei: Pseudocolor auf diesem Band mit dem Look. Sonst Echtfarbe aus `true_color`, wenn alle drei Bänder darin liegen (je Kanal 2–98 % gemessen). Sonst Pseudocolor auf Band 1 mit dessen Look. **Empfehlung.**
2. Immer Pseudocolor auf Band 1 mit dessen Look.

**F3 – Look eines Processing-Ergebnisses**
1. Der Look beim Herunterladen des ZIPs, also so, wie die Ebene gerade eingefärbt ist; er geht als Parameter mit (`?look=`). **Empfehlung.**
2. Der Look beim Start des Jobs (müsste am Job gespeichert werden, Migration).

**F4 – Ganze Szene „per band“, ZIP im Browser aus den Originaldateien**
1. Auch dort eine `.qml` je Datei. Der Browser holt sie vom Server (neuer Endpunkt `POST /collections/{dataset}/styles`, Stile aus derselben Funktion); gemessen wird dort nicht, ein Look `measured` ohne Zahlen nimmt den Bereich der Ansicht oder sonst die Messung der ersten Szene (Statistik des Tilers, gecacht). **Empfehlung.**
2. Dort keine `.qml` (es sind unveränderte Originale).

**F5 – Look `measured`/`percentiles` ohne Zahlen im Auftrag** (z. B. „Download crop“ aus der Auswahl ohne offene Ansicht)
1. Der Schreiber misst die fertige Datei einmal (2–98 % bzw. Min/Max der gültigen Pixel, verkleinerte Lesung). **Empfehlung.**
2. Die `.qml` überlässt es QGIS (`minMaxOrigin` „Cumulative count cut 2–98 %“, QGIS rechnet beim Laden selbst; bei großen Dateien geschätzt).

**F6 – Befund nodata in QGIS** (§2: physikalisch genau 0 wird bei skalierten Bändern durchsichtig)
1. Nichts ändern, Befund in `BANDS.txt` nicht erwähnen (keine Hinweistexte). **Empfehlung.**
2. Eine Zeile in `BANDS.txt` je skalierter Datei („QGIS shows a physical value of 0 as no data“).

**F7 – Masken** (`…_mask.tif`, `mask.tif`)
1. Auch eine `.qml`: „paletted“, 1 = „Inside AOI“ weiß, 0 = „Outside AOI“ durchsichtig. **Empfehlung.**
2. Keine `.qml` für Masken.

### 8.1 Auslegungen (gelten, wenn du nicht widersprichst)

- **A1:** Die `.qml` liegt neben der Datei mit demselben Namen (`B04_red_10m.tif` → `B04_red_10m.qml`). Gemessen [M]: Diese Form lädt QGIS beim Öffnen automatisch, `B04_red_10m.tif.qml` nicht.
- **A2:** Ein Look im Auftrag für ein Band, das nicht in der Datei liegt, wird übergangen; ein Look für ein Klassenband ebenso. Klassen kommen immer aus der Registry bzw. dem Ergebnis.
- **A3:** Ein Ergebnis mit `colormap` als Klassentabelle (Ergebnis-Ebene mit Klassen) bekommt „paletted“ aus `classification:classes` des Ergebnisses.
- **A4:** Die Versionskennung in der Datei ist die der Referenz (`3.34.4-Prizren`). QGIS liest Stile älterer und neuerer Versionen.

## 9. Aufteilung

- **PR 1** (Branch `claude/adoring-pasteur-px0etv-qgis`, gegen `main`): Plan, Backend, Doku.
- **PR 2** (Branch `claude/adoring-pasteur-px0etv-qgis-frontend`, auf PR 1 gestapelt): Frontend, Browser-Check.

## 10. Prüfungen

- PR 1: `pytest` der geänderten Module (`tests/earthx/access`, `tests/earthx/api`, `tests/earthx/processing`), der QGIS-Test lokal mit QGIS 3.34, `ruff check backend`, `lint-imports`.
- PR 2: Vitest der geänderten Module, `npx tsc -b`, `npm run lint`, Browser-Check `frontend/e2e/m5-64-qgis-style.cjs` (der Auftrag trägt den Look, das ZIP enthält die `.qml`) bei 1280×800 und 360×740, dazu `band-download.cjs` und `view-index.cjs`.
