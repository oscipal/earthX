# M5-62 — Klassenlegende

**Stand:** 20.11.2026, Plan **angenommen** (Otto, 20.11.2026: F1 = 1, F2 = 3, F3 = 1, F4 = 1, F5–F7 ja, F8 „Classes“, A1–A5; Grundsatz zu den Farben, §9). PR 1 (Backend) in diesem Draft-PR (§10); PR 2 (Frontend) in einer neuen Session nach dem Merge.
**Stufe B.** Höchstens zwei PRs (M5-Plan §2 Punkt 11).
**Aufgabe (Otto, 19.11.2026; Grundlage M5-Plan §2 Punkt 9):**

> Bei Datensätzen mit Klassenwerten (zuerst WorldCover 2020/2021, später z. B. CORINE) sollen die Klassen sichtbar sein, aus der Registry, für alle solchen Datensätze:
> 1. Registry: Feld je Klassenband mit Wert, Name (Englisch) und Farbe; befüllt für WorldCover 2020 und 2021 nach der Produktdokumentation von ESA.
> 2. Data catalogue: Tabelle Value | Class | Colour beim Band.
> 3. Legende der Ebene: Klassennamen mit Farben statt Farbskala.
> 4. Export: Farbtabelle und Klassennamen in der GeoTIFF, so dass GDAL und QGIS sie lesen (z. B. Category Names bzw. RAT); dazu die Klassen (Wert, Name, Farbe) in der vorhandenen Bands.txt im ZIP, keine eigene Legendendatei.
> 5. Nur solange die Werte unverändert sind: nach Band math oder anderem Processing, das Werte ändert, keine Klassen.
>
> Oberflächentexte nur Englisch, keine zusätzlichen Hinweise im Frontend; Panel scrollt nie (`docs/ui/leitfaden.md`).

**Grundlagen:** M5-Plan §2 Punkte 7 und 9, `projektuebersicht.md` §5 (Onboarding, Punkt 12 aus M5-59), `KLAERUNGEN.md` B10 und B13, M5-07-Plan F4 (Klassen in den Farben der Quelle, kein Stretch), `adr/0014` F6 (Klassen nur mit `nearest`), M5-28 (`x-earthx-passes-values`), M5-59 (`band_descriptions`, `earthx:bands`), `docs/ui/leitfaden.md`.

Belegstufen: **M** in dieser Session gemessen, **P** am Quelltext gelesen (Stand `main` nach #389), **A** eigene Ableitung.

---

## 1. Ziel

Ein Band, dessen Werte Klassen sind, trägt in der Registry seine Klassen (Wert, Name, Farbe). Daraus, ohne zweite Liste:

1. der Data catalogue (Tabelle Value | Class | Colour beim Band),
2. die Legende der Ebene auf der Karte (Klassennamen mit Farben),
3. die Farben der Kacheln (heute eine eigene JSON-Datei, §2),
4. der Export (Farbtabelle und Klassennamen für GDAL/QGIS, Klassen in `BANDS.txt`),

alles nur, solange die Werte des Bands unverändert sind.

**Nicht Teil:** Klassenanteile in der AOI (M5-16), CORINE befüllen (gelistet, wird erst mit M5-44 ff. voll), WorldCover als Maske für andere Datensätze (M5-53), eine Legende für Ebenen ohne Klassen (Farbskala von Messwerten).

---

## 2. Ausgangslage [P]

| Stelle | Heute |
|---|---|
| `backend/catalog/datasets/esa-worldcover-20{20,21}.yaml`, `mask.classes` | Wert und Name der 11 Klassen („the legend in the head of every map file“), ohne Farbe. Zweck: der Operator `mask` und das Panel „Mask“. |
| `backend/catalog/datasets/sentinel-2-c1-l2a.yaml`, `mask.classes` | 12 Klassen der SCL (Namen nach SentiWiki, Tabelle 3), ohne Farbe. |
| `backend/earthx/access/colormap_data/esa-worldcover.json` | Farben der 11 Klassen plus 0 transparent, aus der Farbtabelle der Datei gelesen (06.11.2026). `access/colormaps.py::CLASS_TABLES` registriert sie als `colormap_name` für die Kacheln. Zweite Wahrheit neben der Registry. |
| `default_render.colormap_name: esa-worldcover` | Kacheln in den Farben der Quelle; `frontend/src/datasets.ts::drawsClasses` erkennt daran eine Klassenebene. |
| Data catalogue (`frontend/src/catalogue.ts::bandLinesOf`) | Tabelle Band \| Description \| Unit; WorldCover `map` mit Unit „class code“. Keine Klassen. |
| Legende der Ebene | **Gibt es heute nicht.** Die Einstellungsleiste (`ViewerControls.tsx`) zeigt bei einer Klassenebene im Feld „Colormap“ fest „Classes“ (Tooltip „Each class in the colour of the source …“); Ebenen mit Farbskala haben ebenfalls keine sichtbare Skala, nur das Feld „Colormap“. Die einzige Legende ist die der Coverage Map (`ControlPanel.tsx::CoverageLegend`). → F3. |
| Export (`access/band_export.py`) | `BandMeta.categorical` (Maskenband → Resampling `mode`); `apply_band_tags` schreibt Beschreibung, Scale, Offset; `bands_text` schreibt `exports/BANDS.txt` mit einer Zeile je Band. Keine Farbtabelle, keine Namen. Genutzt von `access/download.py` (Download-Dialog) und `processing/export.py` (Export-Job). |
| „Werte unverändert“ | `Operator.passes_values(params)` je Schritt (`mask`, `mask_values`, `select`, `reproject` mit `nearest`/`mode` u. a.); dieselbe Regel entscheidet heute über nodata und Ausgabetypen (`processing/core.py`, `processing/plan.py`), im Frontend `processingOrder.ts::passesRuleOf`. |

**GDAL und GeoTIFF [M, GDAL 3.12.2 aus rasterio 1.5.2, 20.11.2026]:**

- Die **Farbtabelle** liegt in der GeoTIFF selbst, aber nur bei `uint8`/`uint16` und nur bei einem Band je Datei (TIFF-Palette). WorldCover ist `uint8` mit einem Band: passt.
- **Category Names und RAT** schreibt GDAL bei GeoTIFF nicht in die Datei, sondern immer in eine Begleitdatei `<datei>.tif.aux.xml` (PAM), auch bei `uint8`. Gemessen: `GDALSetRasterCategoryNames` auf eine frische GTiff legt `c_uint8.tif.aux.xml` mit `<CategoryNames>` an. GDAL und QGIS lesen sie, wenn sie neben der Datei liegt. → F4.

**Produktdokumentation:** Die Product User Manuals von ESA (PUM v1 für 2020, v2.0 für 2021) sind aus der Session nicht erreichbar (`esa-worldcover.org`, `worldcover2020.esa.int`, `worldcover2021.esa.int` nicht freigegeben; der Bucket ist Datenquelle, kein Abruf aus der Session nach `adr/0002`). Heute bekannt sind die Namen der Legende im Kopf der Dateien und die Farbtabelle der Dateien (beide gemessen in M5-07). → F2.

---

## 3. Registry: Feld `band_classes`

### 3.1 Form

*Form und Farbregel ersetzt durch §9.2 (Otto, 20.11.2026).*

Neues Pflichtfeld je Eintrag (B10: kein Standard, `{}` wo keine Klassen), Schlüssel wie `band_units`:

```yaml
band_classes:
  map:
  - {value: 10, name: Tree cover, colour: '#006400'}
  - {value: 20, name: Shrubland, colour: '#ffbb22'}
  # … 11 Klassen
```

Prüfungen beim Laden (der Eintrag lädt sonst nicht, wie bei `band_descriptions`):

- Schlüssel ist ein Band aus `band_units`, kein Hilfs-Asset.
- `value` ganze Zahl, eindeutig, aufsteigend; nicht gleich dem nodata der Quelle (WorldCover 0 bleibt draußen und transparent).
- `name` nicht leer, einzeilig, höchstens etwa 40 Zeichen (Englisch prüft der Review, nicht der Code).
- `colour` genau `#rrggbb` (klein), keine Transparenz; zwei Klassen dürfen nicht dieselbe Farbe haben.
- Ein Band mit Klassen hat in `band_units` keine Einheit (`null`).

### 3.2 Eine Wahrheit (F1)

Heute stehen die Namen in `mask.classes` und die Farben in `colormap_data/esa-worldcover.json`. Vorschlag: `band_classes` wird die einzige Liste.

- Die Farbtabelle der Kacheln wird beim Laden aus `band_classes` gebildet (Name wie bisher `esa-worldcover`, bzw. je Eintrag), `colormap_data/esa-worldcover.json` entfällt. Die Kacheln bleiben Pixel für Pixel gleich (Test vergleicht alte und neue Tabelle).
- `mask.classes` behält Wert und Name für den Operator `mask`; eine Ladeprüfung verlangt, dass sie für dasselbe Band mit `band_classes` übereinstimmen (Werte und Namen). Damit kann keine der beiden Listen still abweichen.

### 3.3 Veröffentlichung

Im Collection-JSON je Band in `earthx:bands` (M5-59) zusätzlich die Klassen in der Form der STAC-Erweiterung *classification* (`classification:classes` mit `value`, `name`, `color_hint` als Hex ohne `#`), weil das der verbreitete Standard dafür ist; dazu `stac_extensions` um die Erweiterung ergänzt. Die API liefert damit nichts Eigenes, das ein STAC-Client nicht kennt. Die Collections in Postgres neu schreiben: einmal `catalog-load` (§7). Keine Migration nötig; falls doch, Nummer 035 oder höher (032–034 sind von #388 belegt, Otto 20.11.2026).

### 3.4 Befüllen

*Ersetzt durch §9.3 (Otto, 20.11.2026).*

- **WorldCover 2020 und 2021:** 11 Klassen (10–100), Namen und Farben nach dem PUM (F2). Die Farben der Dateien (heute JSON) und die Namen der Datei-Legende stimmen nach Stand M5-07 mit der Produktbeschreibung überein; Abweichungen in der Schreibweise (z. B. „Bare/sparse vegetation“ gegenüber einer Schreibweise mit Leerzeichen im PUM) werden beim Befüllen geprüft und in `mask.classes` mitgezogen.
- **Sentinel-2 SCL:** F5.
- Andere Einträge: `band_classes: {}`.

### 3.5 Onboarding-Checkliste

`projektuebersicht.md` §5 bekommt Punkt 13: „Jedes Band mit Klassenwerten hat `band_classes` (Wert, Name Englisch, Farbe) nach der Dokumentation der Quelle.“ Dazu eine Zeile im Entscheidungslog. (Auslegung A1.)

---

## 4. Frontend

### 4.1 Data catalogue

Unter der Tabelle Band | Description | Unit je Klassenband eine zweite Tabelle mit den Spalten **Value | Class | Colour**; Colour als Farbfeld (kleines Quadrat) mit dem Hex-Wert daneben (F6). Überschrift der Tabelle ist der Bandname wie in der ersten Tabelle (z. B. „map“), kein weiterer Text. Der Data catalogue ist das große Fenster über der Karte, nicht das Panel; er darf in sich scrollen wie bisher.

Die Farben kommen aus den Daten (Ausnahme „Farben von Daten“ in `docs/ui/leitfaden.md` Farben; eine Zeile mit Grund in `uiRules.test.ts`).

### 4.2 Legende der Ebene (F3)

Heute gibt es keine Legende (§2). Vorschlag (F3 Option 1): Bei einer Klassenebene wird das feste Feld „Colormap: Classes“ der Einstellungsleiste zu einem Knopf **„Classes“**, der ein Popover über der Karte öffnet: je Klasse Farbfeld und Name, eine Zeile je Klasse, in den Farben der Kacheln. Kein Platz im Panel, also kein Scrollen; 11 Zeilen passen bei 360 px Höhe der Karte. Nur Klassen, die die Registry nennt; kein Zusatztext.

Gilt für:

- die Ansicht eines Datensatzes, dessen Standardbild ein Klassenband ist (heute `drawsClasses`), und das einzeln gewählte Klassenband (auch SCL, falls F5 = 1);
- Ergebnis-Ebenen (Zuschnitt, Job), wenn das Band seine Werte behalten hat (§6). Das Backend schreibt die Klassen dann in die Beschreibung des Ergebnisses; das Frontend zeigt, was dort steht, und leitet nichts selbst ab.

### 4.3 Texte

Nur Englisch: „Classes“, Spalten „Value“, „Class“, „Colour“. Britische Schreibweise wie in der Aufgabe und in den vorhandenen Texten („True colour“).

---

## 5. Export

### 5.1 GeoTIFF (F4)

Vorschlag (F4 Option 1), für jede Datei mit Klassenband, dessen Werte unverändert sind:

1. **Farbtabelle** in der Datei, wo GeoTIFF sie erlaubt (ein Band, `uint8`/`uint16`): alle Klassen, nodata transparent. Wird nach `cog_translate` geprüft (bleibt sie erhalten, sonst nach dem Übersetzen gesetzt).
2. **Category Names und RAT** in `<datei>.tif.aux.xml` neben der Datei im ZIP: `CategoryNames` (Index = Wert, leere Namen für Lücken) und eine RAT mit Spalten Value, Class, Red, Green, Blue (Nutzung MinMax, Name, Red, Green, Blue), damit QGIS „Paletted/Unique values“ und „Classify by RAT“ die Namen zeigt. Mehrband-Datei (z. B. SCL neben anderen Bändern in „one multi-band file“): keine Farbtabelle möglich, Namen und RAT je Band in derselben `.aux.xml`.

Die `.aux.xml` ist die Form, in der GDAL die Namen zu einer GeoTIFF ablegt (§2, gemessen); sie ist keine eigene Legendendatei im Sinne der Aufgabe, aber eine zusätzliche Datei im ZIP – deshalb Frage F4.

Ausgabetyp `float32` bei unveränderten Werten (§2 Punkt 9, „Typ der Quelle plus float32“): keine Farbtabelle (GeoTIFF erlaubt sie nicht), Namen und RAT in der `.aux.xml` und die Klassen in `BANDS.txt` bleiben (Auslegung A3).

### 5.2 `BANDS.txt`

Nach der Bandtabelle einer Datei je Klassenband ein Block:

```
Classes of band 1 (map)
Value | Class | Colour
10 | Tree cover | #006400
...
```

Format wie die vorhandene Tabelle (Spalten mit „ | “). Kein Block, wo die Werte nicht mehr die Klassen sind.

---

## 6. Nur bei unveränderten Werten

Ein Band trägt seine Klassen weiter, genau dann wenn:

- es ein Band der Quelle ist (kein neues Band aus Band math, Index, Normalize o. Ä.), **und**
- jeder Schritt des Rezepts `passes_values(params)` erfüllt (dieselbe Regel wie heute für nodata und Ausgabetypen), **und**
- jedes Resampling die Werte behält (`nearest`, `mode`; nie `average`/`bilinear`; heute schon so für `categorical`).

Download-Dialog und Zuschnitt lesen nur und resamplen Klassen mit `mode`/`nearest` → Klassen bleiben. Export-Job und Job-Ergebnis: Regel oben, entschieden im Backend an einer Stelle (`BandMeta` bekommt `classes`, gesetzt nur, wenn die Regel gilt; ein Schritt, der Werte ändert, setzt sie auf `None`). Das Frontend fragt nicht selbst nach.

WorldCover hat `band_math: false`; die Regel gilt trotzdem allgemein (z. B. SCL nach Band math bei Sentinel-2).

---

## 7. Schnitt, Tests, was Otto ausführt

**Schnitt (F7):**

- **PR 1** (dieser Draft-PR): Plan, dann Backend – Registry `band_classes` mit Prüfungen, WorldCover befüllt, Farbtabelle aus der Registry, `earthx:bands` mit `classification:classes`, Regel §6 in `BandMeta`, Export (Farbtabelle, `.aux.xml`, `BANDS.txt`), Onboarding Punkt 13. Geschätzt 300–400 Zeilen ohne YAML-Daten.
- **PR 2** (neue Session nach Merge von PR 1): Frontend – Tabelle im Data catalogue, Popover „Classes“, Klassen bei Ergebnis-Ebenen, Browser-Check. Geschätzt 200–300 Zeilen.

**Tests (ohne Netz, synthetische Fixtures):**

- Registry: fehlendes Feld, Band ohne `band_units`, doppelte/absteigende Werte, Wert = nodata, falsches Farbformat, doppelte Farbe, Einheit gesetzt, Abweichung zu `mask.classes` → Eintrag lädt nicht.
- Kacheln: Farbtabelle aus der Registry gleich der bisherigen JSON (Wert für Wert).
- Collection: `classification:classes` und Erweiterung im JSON; leer bei Einträgen ohne Klassen.
- Export: synthetische `uint8`-Klassenkachel → Farbtabelle in der Datei (rasterio liest sie), `.aux.xml` mit Category Names und RAT (GDAL liest sie zurück), `BANDS.txt` mit Block; `float32` ohne Farbtabelle; Mehrband-Datei; Job mit Band math bzw. `average` → keine Klassen, kein Block, keine `.aux.xml`.
- Frontend (PR 2): Tabelle mit Farbfeld, Popover mit allen Klassen, keine Klassen bei verändertem Ergebnis, `uiRules.test.ts` (Farben von Daten), Browser-Check: Panel scrollt nicht, Popover bei 360 px.

Laufen lassen: Tests der geänderten Module (`backend/tests/earthx/catalog`, `.../access`, `.../processing`, betroffene API-Tests), `ruff check backend`, `lint-imports`; in PR 2 `npm run lint`, `npx tsc -b`, Vitest der geänderten Dateien, betroffene Browser-Checks. Nie zwei Läufe gleichzeitig.

**Otto lokal nach dem Merge von PR 1:** einmal `catalog-load` (Collections mit `earthx:bands` neu), Export eines WorldCover-Zuschnitts in QGIS öffnen (Farben und Namen sichtbar).

---

## 8. Fragen an Otto

**F1 — Eine Liste für Namen und Farben**
1. `band_classes` ist die einzige Liste für Namen und Farben; die Farbtabelle der Kacheln wird daraus gebildet, die JSON-Datei entfällt; `mask.classes` bleibt für den Operator und muss übereinstimmen (Ladeprüfung). **(Empfehlung)**
2. Wie 1, zusätzlich entfällt `mask.classes`; der Operator `mask` liest die Klassen aus `band_classes` (größerer Umbau, berührt Panel „Mask“ und SCL).
3. Farben bleiben in der JSON-Datei, `band_classes` nur für Catalogue, Legende und Export (zwei Wahrheiten).

**F2 — Produktdokumentation von ESA**
Das PUM ist aus der Session nicht erreichbar (§2).
1. Du gibst die Hosts der Dokumentation (`esa-worldcover.org`, `worldcover2020.esa.int`, `worldcover2021.esa.int`) für die Session frei; ich lese die Legende aus PUM v1 und v2.0 und übernehme Namen und Farben wörtlich, Abweichungen zur Datei-Legende nenne ich im PR. **(Empfehlung)**
2. Ich befülle aus Datei-Legende und Farbtabelle der Dateien (in M5-07 gemessen) und du prüfst gegen das PUM im PR.
3. Du schickst die Tabelle aus dem PUM (Wert, Name, Farbe).

**F3 — Wo die Legende der Ebene steht**
Heute zeigt keine Ebene eine Farbskala (§2).
1. Feld „Colormap“ der Einstellungsleiste wird bei Klassen zum Knopf „Classes“ mit Popover über der Karte (Farbfeld + Name je Klasse). **(Empfehlung)**
2. Aufklappbare Liste in der Zeile der Ebene im Layer-Manager (braucht Höhe im Panel; bei 11 Klassen Gefahr des Scrollens).
3. Eigene Legenden-Box auf der Karte (wie die der Coverage Map), sichtbar solange die Ebene sichtbar ist.

**F4 — Klassennamen in der GeoTIFF**
GDAL legt Category Names und RAT bei GeoTIFF nur in `<datei>.tif.aux.xml` ab (gemessen); die Farbtabelle geht in die Datei.
1. Farbtabelle in der Datei, Namen und RAT in der `.aux.xml` daneben im ZIP; GDAL und QGIS lesen beides automatisch. **(Empfehlung)**
2. Nur Farbtabelle in der Datei; Namen nur in `BANDS.txt` (QGIS zeigt Farben, aber Werte statt Namen).
3. Wie 1, zusätzlich die Namen als Metadaten-Tags in der Datei selbst (`GDAL_METADATA`); QGIS nutzt sie nicht für die Legende, aber sie gehen nicht verloren, wenn jemand nur die TIFF weitergibt.

**F5 — Sentinel-2 SCL**
Die SCL ist ebenfalls ein Klassenband (12 Klassen in `mask.classes`).
1. Jetzt mit befüllen, Farben nach derselben SentiWiki-Tabelle wie die Namen (Quelle muss lesbar sein, wie F2). **(Empfehlung)**
2. Nicht jetzt; `band_classes: {}` und eigene kleine Aufgabe.

**F6 — Spalte „Colour“ im Data catalogue**
1. Farbfeld und Hex-Wert (`#006400`). **(Empfehlung)**
2. Nur Farbfeld.

**F7 — Schnitt**
1. Zwei PRs: Backend (dieser), Frontend (neue Session). **(Empfehlung)**
2. Ein PR mit allem (voraussichtlich über 600 Zeilen).

**F8 — Name des Popover-Knopfs bzw. Felds**
1. „Classes“. **(Empfehlung)**
2. „Legend“.

### 8.1 Auslegungen (gelten, wenn du nicht widersprichst)

- **A1:** Onboarding-Checkliste Punkt 13 (§3.5) mit Zeile im Entscheidungslog.
- **A2:** Wert 0 (nodata bei WorldCover) ist keine Klasse; er erscheint weder im Catalogue noch in der Legende, im Export ist er transparent und ohne Namen.
- **A3:** `float32`-Ausgabe mit unveränderten Werten behält Namen, RAT und `BANDS.txt`, nur ohne Farbtabelle (GeoTIFF erlaubt sie dort nicht).
- **A4:** Die Klassen werden in der STAC-Form `classification:classes` veröffentlicht (§3.3); Registry-Feld heißt `band_classes`, Farbe in der Registry mit `#`.
- **A5:** Der Name der Farbtabelle für die Kacheln bleibt `esa-worldcover`, damit gespeicherte Arbeitszustände und Rezepte weiter gelten.

---

## 9. Antworten von Otto (20.11.2026)

### 9.1 Wortlaut

> F1 = 1, F2 = 3, F3 = 1, F4 = 1, F5 = ja, F6 = ja, F7 = ja (Backend hier, Frontend in einer neuen Session nach Merge), F8 = „Classes“. A1–A5 angenommen.
>
> Grundsatz: Farben werden nie von Hand gepflegt. band_classes braucht je Klasse nur Wert und Name; die Farbe ist optional und wird so bestimmt:
> 1. aus der Quelle: eingebaute Farbtabelle der Datei, bei STAC classification:classes (Name und color_hint) – beim Onboarding (adr/0031) automatisch übernehmen, wo vorhanden, auch die Namen;
> 2. sonst eine feste Standardpalette, gut unterscheidbar, nach Reihenfolge der Klassen.
>
> Eine Farbe von Hand nur als Ausnahme. Bei WorldCover die Farben aus der Datei nehmen, nicht aus einer Tabelle von mir.
>
> F2 – Namen (Quelle: Earth-Engine-Katalog ESA/WorldCover v100/v200, gleichlautend bei Planet; die ESA-Seiten sind aus der Sitzung nicht erreichbar): WorldCover 2020 und 2021: 10 Tree cover, 20 Shrubland, 30 Grassland, 40 Cropland, 50 Built-up, 60 Bare / sparse vegetation, 70 Snow and ice, 80 Permanent water bodies, 90 Herbaceous wetland, 95 Mangroves, 100 Moss and lichen. Mit mask.classes abgleichen, Abweichungen im PR melden.
> Sentinel-2 SCL: 0 No data (keine Klasse, A1), 1 Saturated or defective, 2 Topographic shadows (vor Baseline 04.00, 25.01.2022: Dark features / shadows), 3 Cloud shadows, 4 Vegetation, 5 Not vegetated, 6 Water, 7 Unclassified, 8 Cloud medium probability, 9 Cloud high probability, 10 Thin cirrus, 11 Snow or ice. Farben nach Regel 1, sonst Regel 2.
>
> F4: Farbtabelle in der GeoTIFF, Klassennamen und RAT in der .aux.xml daneben im ZIP, dazu die Klassen in BANDS.txt. F3: Das Popover darf das Panel nicht scrollen lassen und keine zusätzlichen Hinweistexte bringen (docs/ui/leitfaden.md).

### 9.2 Form von `band_classes` (ersetzt §3.1)

```yaml
band_classes:
  map:
    colours: file        # file | stac | palette: woher die Farben kommen
    classes:
    - {value: 10, name: Tree cover, colour: '#006400'}
    # …
```

- Je Klasse Pflicht nur `value` und `name`; `colour` ist optional.
- `colours` sagt je Band, woher die Farben kommen:
  - `file`: aus der eingebauten Farbtabelle der Datei; jede Klasse trägt die Farbe, wie das Onboarding sie aus der Datei gelesen hat.
  - `stac`: aus `classification:classes` der Quelle (`color_hint`); ebenso jede Klasse mit Farbe.
  - `palette`: die Quelle hat keine Farben; die Farben kommen beim Laden aus der festen Standardpalette nach der Reihenfolge der Klassen. Eine Klasse darf hier eine `colour` tragen: das ist die Ausnahme von Hand.
- **Auslegung A6:** Farben aus der Quelle liegen in der YAML, weil das Onboarding nach `adr/0031` §7 je Eintrag eine YAML aus einer Probe der Quelle schreibt; „nie von Hand gepflegt“ heißt: Sie werden aus der Quelle übernommen und nicht verändert, eine Hand-Farbe gibt es nur bei `palette` als Ausnahme. Ein Lesen der Farben zur Laufzeit aus der Datei scheidet aus, weil Data catalogue und Legende sonst eine Quelle abrufen müssten.
- **Standardpalette (A7):** die 20 Farben von „tab20“ (matplotlib, Reihenfolge der Kategorien: erst die zehn dunklen von tab10, dann die zehn hellen), gut unterscheidbar und verbreitet; ab der 21. Klasse wiederholt sie sich nicht still, der Eintrag lädt dann nicht (eine Hand-Farbe oder eine Farbe der Quelle ist nötig).
- Der Rest der Prüfungen aus §3.1 bleibt; „zwei Klassen dürfen nicht dieselbe Farbe haben“ gilt für die aufgelösten Farben.

### 9.3 Befüllen (ersetzt §3.4)

- **WorldCover 2020 und 2021:** `colours: file`; Farben aus der Farbtabelle der Datei, wie sie in M5-07 am 06.11.2026 gelesen wurde (bisher `access/colormap_data/esa-worldcover.json`, die Datei entfällt); Namen nach Ottos Liste. Abweichung zu `mask.classes`: nur 60, dort „Bare/sparse vegetation“, neu „Bare / sparse vegetation“ (in `mask.classes` mitgezogen, die Ladeprüfung verlangt Gleichheit).
- **Sentinel-2 SCL:** Namen nach Ottos Liste (Abweichungen zu `mask.classes` meldet §10). Farben: Earth Search führt nach dem Stand im Repo keine `classification:classes` mit `color_hint` für `scl`, und die SCL-Dateien haben keine bekannte Farbtabelle; prüfen kann die Session beides nicht (keine Abrufe der Quelle). Deshalb `colours: palette` (Regel 2). Findet Otto lokal eine Farbtabelle oder `color_hint`, wird der Eintrag auf `file` bzw. `stac` umgestellt.
- Der Name „Topographic shadows“ gilt ab Baseline 04.00; ältere Szenen (vor 25.01.2022) nennen Klasse 2 „Dark features / shadows“. Ein Name je Wert ist die Form des Felds; der heutige Name steht in der Registry, der ältere im YAML-Kommentar (Auslegung A8).
- **Onboarding (A1, Punkt 13):** Klassenbänder bekommen `band_classes`; Namen und Farben übernimmt das Onboarding aus der Quelle (Farbtabelle der Datei, STAC `classification:classes`), sonst `palette`.
