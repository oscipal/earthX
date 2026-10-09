# M3-06a — AOI-Upload: Backend-Route mit Shapefile: Plan

**Aufgabe:** M3-06a aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B — von Otto am 26.09.2026 freigegeben** mit F1 (1), F2 (1), F3 (1),
F4 (1), F5 (**2**), F6 (1) (§13). F5 (2) heißt: Mehrere Features werden zu
einer `MultiPolygon` vereinigt, wenn alle polygonal sind, statt abgewiesen zu
werden (Empfehlung war 1/Abweisen) — §9 unten ist entsprechend angepasst.
**Nachtrag beim Umsetzen (26.09.2026, zu F3):** Gemessen, dass Starlettes
`max_part_size` (die Grundlage der F3-Empfehlung, Option A) **nur normale
Formularfelder deckelt, keine Datei-Teile** — ein Datei-Teil über der
1-MiB-Spool-Schwelle landet unabhängig von `max_part_size` in einer echten
`SpooledTemporaryFile`-Platte-Datei (nachgeprüft: ein 1 048 577-Byte-Upload
löste einen `rollover()`-Aufruf aus, `max_part_size=1_048_576` gesetzt oder
nicht). Damit hätte Option A ihr eigenes Versprechen nicht eingehalten. §6 ist
entsprechend auf **Option B** (Rohkörper statt `multipart/form-data`)
umgeschrieben — dieselbe Größe (1 MiB), dasselbe Ziel (nachweisbar nie auf
Platte), nur der Übertragungsweg ändert sich. Das ist eine technische
Korrektur der Umsetzung von F3, keine neue Frage: Ziel und Deckelwert aus F3
bleiben, wie von Otto freigegeben.
**Ort im Repo:** `docs/plans/m3-06a-aoi-upload-backend.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` P7, M3-06a;
`architekturplan.md` 0, 3.1, 7.3; `projektuebersicht.md` §2 (Prinzipien 1, 9,
15); `KLAERUNGEN.md` B8, B9; `prototyp-inventar.md` F3 (`frontend/src/aoiFile.ts`,
heutiges Verhalten „erste brauchbare Geometrie gewinnt"); heutiger Code in
`backend/earthx/adapters/federated_search.py` (Geometrie-Prüfung für
`intersects`, M3-08) und `backend/earthx/access/download.py` (Arbeitsspeicher-
statt Platten-Muster, `MemoryFile`/`BytesIO`).

---

## 1. Ziel in einem Satz

Eine Datei — GeoJSON, KML oder ein Shapefile als ZIP — wird über eine Route
angenommen und liefert eine geprüfte, auf EPSG:4326 gebrachte GeoJSON-Geometrie
zurück, ohne dass die Datei oder ihr Inhalt je auf Platte oder ins Log
gelangt.

---

## 2. Heutiger Stand

- **Frontend, `aoiFile.ts` (F3 aus `prototyp-inventar.md`).** GeoJSON
  (`FeatureCollection` → `Feature` → `Geometry`, „erste brauchbare Geometrie
  gewinnt") und ein minimaler KML-Parser über `DOMParser` im Browser, ohne
  Shapefile. Läuft heute clientseitig, ungeprüft (kein Punktanzahl-Deckel,
  keine Validitätsprüfung). M3-06b ersetzt diesen Pfad durch einen Aufruf
  dieser Route.
- **Geometrie-Prüfung existiert schon einmal**, für einen anderen Zweck:
  `federated_search._check_geometry`/`_check_polygon_validity` (M3-08) prüft
  ein GeoJSON `intersects` für die Suche — Positionsformat, Ringschluss,
  Selbstschnitt über `shapely.is_valid`, Punktanzahl-Deckel
  (`MAX_INTERSECTS_POINTS = 1000`). Dieser Code liegt in `earthx.adapters`,
  das laut `.importlinter` nur `gateway` und `catalog` importieren darf und
  selbst nicht von `access` importiert werden darf (die Kontraktliste von
  `access` nennt `adapters` als verbotenes Modul). Eine Wiederverwendung über
  einen Import ist also nicht ohne Weiteres möglich; §5 schlägt vor, die
  gleiche **Technik** (shapely, `is_valid`, ein Punktanzahl-Deckel) unabhängig
  in der neuen Stelle nachzubauen, nicht das Modul zu importieren.
- **Muster „Arbeitsspeicher statt Platte"** ist in `access/download.py` schon
  etabliert: `rasterio.io.MemoryFile`, `io.BytesIO`, nie ein Pfad auf der
  lokalen Platte. §6 übernimmt dasselbe Muster für den Upload.
- **Kein Paket für Shapefile, OGR oder sicheres XML** ist heute installiert
  (geprüft in der Sitzung: `osgeo`, `fiona`, `pyogrio`, `shapefile`,
  `defusedxml`, `geopandas` fehlen alle; `pyproj` ist über `rioxarray`
  transitiv vorhanden, aber nicht direkt in `requirements.txt` gelistet).
  `python-multipart` fehlt ebenfalls — FastAPIs `UploadFile`/`File(...)`
  bricht ohne dieses Paket beim Start mit einem klaren `RuntimeError` ab
  (nachgeprüft in der Sitzung).

---

## 3. Umfang aus dem Aufgabenschnitt

- Route, die eine Datei annimmt und eine geprüfte Geometrie in EPSG:4326
  zurückgibt; nichts wird gespeichert, auch nicht auf Platte.
- Formate: GeoJSON, KML, Shapefile als ZIP. Koordinatensystem aus der `.prj`;
  fehlt sie, wird abgewiesen, nicht geraten.
- Schutz: Größendeckel für Upload und entpackte Größe (ZIP-Bombe),
  Punktanzahl-Deckel, sichere XML-Verarbeitung für KML (keine externen
  Entitäten), ungültige und selbstschneidende Geometrien, Antimeridian.
- Keine Koordinaten und keine Dateiinhalte im Log.

---

## 4. Bibliothekswahl

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **1. Reine Python-Lösung (empfohlen)** | `pyshp` (MIT, reine Python, kein C-Anteil) für `.shp`/`.prj`, `defusedxml` (PSF-artige Lizenz, reine Python) für KML, `shapely` (schon Abhängigkeit) für die Geometrie-Prüfung, `pyproj` (schon transitiv vorhanden über `rioxarray`, jetzt direkt gelistet) für die `.prj`→EPSG:4326-Transformation | Beide neuen Pakete sind klein, reine Python, ohne eigene C-Erweiterung, ohne Netzwerkzugriff, mit permissiver Lizenz (AGPL-Repo, öffentlich, ENTSCHEIDUNGEN §4). `defusedxml` ist genau für die geforderte „sichere XML-Verarbeitung, keine externen Entitäten" gebaut, nicht selbst gebastelt. `pyshp` liest `.shp`/`.dbf`/`.shx` direkt aus datei-ähnlichen Objekten (`BytesIO`), passt also ohne Umweg zum Arbeitsspeicher-Muster von §6 | Zwei zusätzliche, bisher ungenutzte Abhängigkeiten; `pyshp` deckt nur Geometrie/Attribute, keine Reprojektion (die übernimmt `pyproj` ohnehin separat) |
| **2. GDAL/OGR über `osgeo`-Python-Bindings** | `pip install gdal==<Version>` (Python-Bindings zum System-GDAL) für alle drei Formate über einen einzigen Treiber | Ein Treiber für GeoJSON, KML **und** Shapefile statt drei Bibliotheken; OGR ist der De-facto-Standard für Vektorformate | `rasterio` bringt sein GDAL bereits **gebündelt** in seinem eigenen Wheel mit (siehe `rasterio>=1.3`, kein System-GDAL-Zwang bisher); ein zweites, separat zu pinnendes `osgeo`-Paket riskiert eine zweite GDAL-Version im selben Prozess (Versions-Drift, wie das bereits gepinnte `rio-tiler==9.4.6`/`titiler.core==2.3.0` in `requirements.txt` zeigt, dass GDAL-Versionsdrift hier ernst genommen wird). OGRs `VSIZIP`/`VSIMEM`-Handling ist mächtiger, aber auch schwerer nachvollziehbar zu prüfen als ein handgeschriebener Zip-Bomben-Schutz (§7). Kein Formatgewinn: wir brauchen nur Geometrie, keine OGR-Attributabfragen |
| **3. `fiona`/`pyogrio`/`geopandas`** | High-Level-Wrapper um OGR | Komfortabler als OGR direkt | Bringen dieselbe zweite-GDAL-Frage wie Option 2 mit, dazu `numpy`/`pandas`-Gewicht (bei `geopandas`) für eine Aufgabe, die nur eine einzelne Geometrie pro Upload liefert |

**Empfehlung: Option 1.** Kein zweites GDAL im Prozess, kleinstmögliche neue
Abhängigkeiten, `defusedxml` löst die XXE-Anforderung direkt statt über eine
selbst geschriebene Parser-Härtung. → **Frage F1**.

---

## 5. Modul und Prozess

**Modul für die Parsing-/Prüf-Logik.** Kein neues Modul (Vorgabe). Von den elf
Modulen aus `architekturplan.md` 3.1 passt keines wörtlich auf „Datei-Parsing
für eine hochgeladene AOI"; am nächsten ist **`access`** („Tiles, Quicklooks,
Statistik, **Download-Vermittlung**"): `access/download.py` behandelt AOIs
bereits (Zuschnitt, Maske, `adr/0004` §3.4 Verdünnung); die neue Funktion
`access/aoi_upload.py` reiht sich dort ein, statt in `catalog` (STAC-Modell),
`adapters` (Protokolle *externer* Quellen — ein Upload ist keine Quelle) oder
`readers` (Rasterformate, nicht Vektor). `access` importiert laut Vertrag nur
`readers` und `catalog`; die neue Datei braucht keins von beiden (nur
`shapely`, `pyproj`, `pyshp`, `defusedxml`, Stdlib) — der Importvertrag bleibt
unverändert erfüllbar, keine Änderung an `.importlinter` nötig.

**Route und Prozess.** Die Route selbst liegt, wie `api/coverage_route.py`, im
Prozess **`api`** — nicht `tiler`: `access/download.py`s Zuschnitt-Route
(`download_crop`) hängt am `tiler`-Prozess, weil sie `readers`, `gateway`
(GDAL-Umgebung) und echte Datenquellen braucht; diese Route braucht nichts
davon — sie liest nur die hochgeladene Datei, keine Quelle, kein `gateway`.
`api` ist außerdem schon der I/O-lastige, async Prozess für kurze,
zustandslose Anfragen (`architekturplan.md` 3.2). Datei:
`api/aoi_upload_route.py`, in `api/main.py` per `app.include_router(...)`
eingebunden wie `coverage_router` — außerhalb von `/stac` (die Antwort ist
keine STAC-Ressource).

→ **Frage F2** (nur zur Bestätigung, da ohne echte Alternative).

---

## 6. Nur Arbeitsspeicher: das Multipart-Problem — **umgesetzt als Option B**

**Befund (nachgeprüft in der Sitzung, Starlette 1.7.0/FastAPI 0.141.1):**
FastAPIs `UploadFile` läuft über Starlettes `MultiPartParser`, die **jeden**
Datei-Teil in ein `tempfile.SpooledTemporaryFile(max_size=1_048_576)`
schreibt — das ist Pythons Standardverhalten für "spooled": Bis 1 MiB bleibt
der Inhalt im Arbeitsspeicher, **darüber schreibt Python selbst und
automatisch eine echte Datei ins Betriebssystem-Temp-Verzeichnis**, ganz ohne
dass unser Code das anfordert. Das widerspricht der Vorgabe „nichts wird
gespeichert, auch nicht auf Platte" sobald eine Datei diese Schwelle
überschreitet.

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A. `UploadFile`/`multipart/form-data`, Deckel = 1 MiB** | Größendeckel für den gesamten Upload exakt auf Starlettes eigene Spool-Schwelle legen (`Request.form(max_part_size=1_048_576)`, zusätzlich eigene Prüfung der gelesenen Bytes) | Klassisches, standardkonformes Muster (`<input type="file">` + `FormData`) | **Widerlegt beim Umsetzen:** `max_part_size` deckelt in dieser Starlette-Version nur normale Formularfelder (`MultiPartParser.on_part_data`, Zweig `self._current_part.file is None`); für einen Datei-Teil (`file is not None`) gibt es dort **keine** Größenprüfung — die Daten gehen ungeprüft in die `SpooledTemporaryFile`. Nachgemessen mit einer echten `TestClient`-Anfrage: ein Upload von exakt 1 048 576 Byte löste `rollover()` nicht aus, einer von 1 048 577 Byte dagegen schon — unabhängig davon, ob `max_part_size` gesetzt war. Otto freigegebenes F3 (1) wollte genau diese Garantie; Option A liefert sie in dieser Starlette-Version nicht, ohne selbst eine private, kaum wartbare Kopie des Multipart-Parsers zu schreiben |
| **B. Rohkörper ohne Multipart (umgesetzt)** | `POST` mit dem Dateiinhalt direkt als Body, Dateiname über einen Pflicht-Query-Parameter `filename`; `request.stream()` in Häppchen gelesen, mit eigenem, laufend mitgezähltem Deckel — bricht ab, sobald `MAX_UPLOAD_BYTES` überschritten ist, **bevor** ein Byte mehr gelesen wird | Kein `SpooledTemporaryFile`, keine Starlette-Interna zwischen unserem Code und den Bytes; „landet nie auf Platte" ist dadurch eine triviale Tatsache über unseren eigenen Code, keine Annahme über Starlettes; kein `python-multipart` als Abhängigkeit nötig (§4-Pakete reichen) | Untypisch gegenüber einem klassischen `<input type="file">` + `FormData`-Upload; das Frontend (M3-06b) schickt `file` (ein `Blob`) direkt als Body und den Dateinamen als Query-Parameter, nicht als `FormData`-Feld — eine kleine, aber merkliche Abweichung vom Browser-Standardmuster |

**Umgesetzt: Option B**, mit demselben Deckel (1 MiB) und demselben Ziel, das
F3 wollte — nur der Übertragungsweg ist ein anderer als ursprünglich
vorgeschlagen (Nachtrag oben). Ein Test hält die Garantie trotzdem fest,
siehe §11 dritter Punkt.

---

## 7. Format-Parsing im Einzelnen

### 7.1 GeoJSON (`.json`, `.geojson`)

- `json.loads` auf den Rohtext (nach Größendeckel, §8). Erwartet: `Feature`,
  `FeatureCollection` oder eine nackte `Geometry` — wie im heutigen
  `aoiFile.ts`.
- Ein evtl. vorhandenes, veraltetes `crs`-Feld (RFC 7946 verbietet es, ältere
  Exporte tragen es manchmal noch) wird **nicht gelesen**: GeoJSON ist per
  Spezifikation immer EPSG:4326/CRS84. Trägt das Feld einen anderen Wert als
  `urn:ogc:def:crs:OGC::CRS84`/`EPSG:4326`, wird abgewiesen statt geraten
  (dieselbe Haltung wie bei der fehlenden `.prj`) — sonst würde eine
  Alt-Datei mit echtem Fremd-CRS unbemerkt falsch gelesen.
- Geometrietyp- und Positionsprüfung wie in §7.4.

### 7.2 KML (`.kml`)

- `defusedxml.ElementTree.fromstring` statt `xml.etree.ElementTree` — verbietet
  externe Entitäten, DTDs und die „Billion Laughs"-Konstruktion von sich aus
  (das ist der Zweck des Pakets, keine eigene Härtung nötig).
- Gelesen werden `Polygon`, `Point`, `LineString` innerhalb des ersten
  passenden `Placemark` — dieselbe Beschränkung wie im heutigen
  `frontend/src/aoiFile.ts` (bewusst minimal, `prototyp-inventar.md` §F3: „Der
  KML-Pfad ist bewusst minimal; er ignoriert innere …"). Eine dritte
  Koordinate (Höhe) wird verworfen, KML ist sonst immer WGS84 (lon, lat[, alt]
  je Position, per Spezifikation) — keine Transformation nötig.
- Mehrere `Placemark`-Elemente: siehe §9.

### 7.3 Shapefile (`.zip`)

- Der Zip-Inhalt wird **nicht** auf Platte entpackt (§6-Muster: `zipfile.ZipFile`
  über `io.BytesIO`, jedes Element über `ZipFile.open(name)` in Häppchen
  gelesen, in ein weiteres `BytesIO` akkumuliert).
- Erwartete Elemente (Dateiname-Endung, Groß-/Kleinschreibung ignoriert):
  `.shp` und `.prj` **Pflicht**; `.shx`/`.dbf` optional (nachgeprüft beim
  Umsetzen: `shapefile.Reader(shp=..., shx=None, dbf=None)` liest die
  Geometrie unverändert, `pyshp` verlangt keine der beiden für einen reinen
  Shape-Zugriff). Fehlt `.shp` oder `.prj` → `400`, „fehlt", nicht geraten
  (explizit für `.prj` in der Aufgabenstellung gefordert, hier gleich auf
  `.shp` erweitert, weil ohne `.shp` keine Geometrie da ist).
- **Erlaubtes Namensmuster** für Einträge: ein einziger regulärer Ausdruck
  `^[\w.-]+\.(shp|shx|dbf|prj|cpg)$` (ohne Pfadanteil, keine Groß-/
  Kleinschreibungsvorgabe). Alles, was nicht passt, macht den Upload
  ungültig (`400`) — **außer** `__MACOSX/…` und `._*` (macOS-„AppleDouble"-
  Beibehalt beim Zippen im Finder): diese zwei werden übersprungen, nicht als
  Fehler gewertet, weil sie in der Praxis sehr häufig sind und nichts mit dem
  Geometrieinhalt zu tun haben. Diese eine Namensregel schließt nebenbei
  Pfad-Traversal (`../`) und verschachtelte Archive aus, ohne sie einzeln zu
  behandeln.
- `.prj`-Text über `pyproj.CRS.from_user_input(text)`; schlägt das fehl →
  `400`. Ist das Ergebnis nicht bereits EPSG:4326/CRS84, wird jede Position
  über einen `pyproj.Transformer` transformiert, bevor die Punktanzahl- und
  Gültigkeitsprüfung (§7.4) läuft.
- `PointZ`/`PolygonZ`/`PolylineZ` aus `pyshp`: die Z-Komponente wird verworfen,
  wie bei KML.

### 7.4 Gemeinsame Prüfung (alle drei Formate)

Dieselbe Technik wie `federated_search._check_geometry`/
`_check_polygon_validity` (M3-08), unabhängig nachgebaut (siehe §2 zur
Import-Grenze), nicht importiert:

1. Geometrietyp gegen die Erlaubnisliste aus §9 prüfen.
2. Positionen zählen, jede einzeln auf endliche Zahl und `-180..180`/`-90..90`
   prüfen (keine Koordinate wird dabei in eine Fehlermeldung oder ins Log
   geschrieben — nur Zahl der Positionen und Regelname).
3. Punktanzahl gegen den Deckel aus §8 prüfen, **bevor** `shapely` die
   Geometrie aufbaut (billige Prüfung vor teurer).
4. Bei `Polygon`/`MultiPolygon`: Ringe geschlossen (erster = letzter Punkt),
   mindestens vier Positionen je Ring, `shapely.geometry.shape(...).is_valid`
   (verwirft Selbstschnitte, „Bowtie"-Polygone).
5. **Antimeridian:** wird nicht aufgelöst oder zerschnitten (das bliebe eine
   eigene Aufgabe), aber auch nicht verboten — eine Positions-Longitude von
   z. B. `179.9` neben `-179.9` im selben Ring ist für sich genommen gültig
   (beide innerhalb `-180..180`) und wird durchgelassen, exakt wie
   `federated_search` es heute für `intersects` handhabt (Kommentar dort:
   „that is how GeoJSON and STAC write a box that crosses the antimeridian").
   Ob daraus ein sehr breites, „um die halbe Erde" reichendes Polygon
   entsteht, ist Sache der Anzeige/AOI-Verdünnung an der Verbrauchsstelle
   (`adr/0004` §3.4), nicht dieser Route.

---

## 8. Deckelwerte

| Deckel | Wert | Begründung |
|---|---|---|
| `MAX_UPLOAD_BYTES` | 1 MiB (1 048 576) | = Starlettes eigene Spool-Schwelle (§6); macht „nie auf Platte" beweisbar statt plausibel |
| `MAX_ZIP_MEMBERS` | 10 | ein Shapefile-Bündel hat normalerweise 4–6 Dateien (`shp/shx/dbf/prj/cpg`); großzügiger Rand für zusätzliche, ignorierte `__MACOSX`-Einträge |
| `MAX_ZIP_MEMBER_BYTES` (entpackt, pro Element, tatsächlich gelesen, nicht der deklarierte `ZipInfo.file_size`) | 20 MiB | schützt auch dann, wenn `MAX_UPLOAD_BYTES` später einmal angehoben würde; ein Vielfaches über jedem plausiblen Shapefile-Teil, weit unter einer Bombe |
| `MAX_ZIP_TOTAL_BYTES` (entpackt, Summe, ebenfalls laufend mitgezählt) | 20 MiB | dieselbe Überlegung, als Summe statt je Element |
| `MAX_AOI_POINTS` | 20 000 | dieselbe Größenordnung, die M3-08 bereits als von beiden Quellen klaglos angenommen misst (Plan-Kommentar in `federated_search.py`: „measured up to 20 000 points / 454 kB going through both without a word"); **unabhängig** von `MAX_INTERSECTS_POINTS = 1000`, das erst greift, wenn diese AOI später tatsächlich als `intersects` an eine Suche geht (M3-08, unverändert) |

→ **Frage F4** (Deckelwerte insgesamt zur Bestätigung).

---

## 9. Erlaubte Geometrietypen und Verhalten bei mehreren Features

**Geometrietypen:** `Polygon`, `MultiPolygon`, `Point`. Ausgeschlossen:
`LineString`/`MultiLineString` (keine Fläche, kein heutiger Verbraucher),
`MultiPoint`, `GeometryCollection` (M3-08 lässt `GeometryCollection` für
`intersects` zu; für eine AOI-Datei gibt es dafür keinen Anwendungsfall). Ein
Rechteck ist einfach ein `Polygon` mit vier Ecken, kein eigener Typ. Eine Datei
mit einem nicht erlaubten Typ wird mit `400` abgewiesen (das deckt den
Abnahme-Testfall „falscher Typ" zusätzlich zu einer falschen Dateiendung ab).

**Mehrere Features/Datensätze in einer Datei** (GeoJSON-`FeatureCollection`
mit mehr als einem `Feature`, Shapefile mit mehr als einem Datensatz, KML mit
mehr als einem `Placemark`, das eine erlaubte Geometrie trägt):

| Option | Verhalten | Bewertung |
|---|---|---|
| A. Abweisen (Empfehlung war dies) | `400` mit der Anzahl gefundener Geometrien, „export exactly one shape and upload again" | Ehrlich (Prinzip 9), aber verhindert eine absichtlich mehrteilige AOI in einer Datei |
| **B. Vereinigen (Otto, F5 = 2, umgesetzt)** | `shapely.ops.unary_union` zu einer `Polygon`/`MultiPolygon`, **nur wenn alle gefundenen Geometrien polygonal sind** (`Polygon`/`MultiPolygon`); sind mehrere gefunden und mindestens eine ist kein Polygon (z. B. mehrere `Point`, oder ein `Point` neben einem `Polygon`), wird abgewiesen (`400`, nennt die gefundenen Typen) — dafür gibt es keine einfache, nicht-ratende Vereinigung | erlaubt eine absichtlich mehrteilige AOI (z. B. zwei getrennte Untersuchungsgebiete) in einer Datei, ohne bei uneindeutigen Mischungen zu raten |
| C. Erste brauchbare Geometrie, Rest verwerfen | heutiges Verhalten von `aoiFile.ts` (F3) | am wenigsten Überraschung gegenüber heute, aber die stille Flächen-Verkleinerung, die Prinzip 9 vermeiden soll |

**Otto, F5 = 2 (26.09.2026): Option B.** Mehrere polygonale Geometrien
vereinigt die Route selbst zu einer `MultiPolygon` (bzw. `Polygon`, wenn die
Vereinigung zusammenhängend wird); alles andere mit mehr als einer Geometrie
bleibt ein `400`. Die abschließende Punktanzahl- und Gültigkeitsprüfung aus
§7.4 läuft auf dem **vereinigten** Ergebnis.

---

## 10. API-Form

- **Route:** `POST /aoi/upload?filename=<name>`, im Prozess `api`, außerhalb
  `/stac` (analog `/coverage/{dataset_id}`, §5).
- **Anfrage (Option B aus §6, nach dem Nachtrag zu F3):** der Dateiinhalt
  direkt als Anfragekörper (kein `multipart/form-data`, kein `FormData`-Feld);
  der Pflicht-Query-Parameter `filename` liefert die Formaterkennung
  (`.geojson`/`.json` → GeoJSON, `.kml` → KML, `.zip` → Shapefile-Bündel);
  alles andere → `400`. Frontend-seitig (M3-06b) heißt das: den ausgewählten
  `File`/`Blob` direkt als `body` schicken, `file.name` als `filename` in die
  URL.
- **Antwort (`200`):** die geprüfte Geometrie direkt als GeoJSON-Objekt in
  EPSG:4326 (`{"type": "Polygon", "coordinates": [...]}`), ohne Hülle — passt
  unverändert in die Stelle, an der `frontend/src/aoiFile.ts`s
  `parseAoiFile` heute ein `GeoJSON.Geometry` liefert (M3-06b tauscht nur den
  Aufrufer).
- **Fehler:** `400` für jeden inhaltlichen Grund aus §§7–9 (Text nennt die
  verletzte Regel, nie eine Koordinate oder den Dateiinhalt); `413` speziell,
  wenn `MAX_UPLOAD_BYTES` (§8) überschritten ist, bevor überhaupt geparst
  wird.
- **Logging:** eine Zeile pro Anfrage mit Dateiname-Endung (nicht dem vollen
  Namen — der könnte durch den Nutzer frei gewählt sein und ist ebenfalls
  „Dateiinhalt" im weiteren Sinne, deshalb nur die erkannte Endung/Format),
  erkanntem Format, Ergebnis (`ok`/Fehlerklasse) und Dauer — nie Koordinaten,
  nie der Dateiinhalt, nie der volle Dateiname (K-01/K-02, M3-16-Muster).

---

## 11. Tests

Je Format (GeoJSON, KML, Shapefile-ZIP), soweit zutreffend:

1. gültige Datei mit `Polygon` → `200`, erwartete Geometrie (auf EPSG:4326
   umgerechnet, wo die Quelle ein anderes CRS trägt).
2. fehlerhafte/unlesbare Datei (kaputtes JSON, kaputtes ZIP, KML ohne
   erkennbare Geometrie) → `400`.
3. falscher Typ (unbekannte Dateiendung; erlaubter Dateityp, aber nicht
   erlaubter Geometrietyp wie `LineString`) → `400`.
4. Shapefile ohne `.prj` → `400`, nennt das Fehlen, rät kein CRS.
5. zu große Datei (über `MAX_UPLOAD_BYTES`) → `413`.
6. ZIP-Bombe (ein kleines ZIP, das beim Entpacken `MAX_ZIP_TOTAL_BYTES`
   überschreitet) → `400`, ohne dass der Prozess tatsächlich die volle Menge
   entpackt (Test prüft, dass der Abbruch früh genug greift, z. B. über eine
   Obergrenze der gemessenen Laufzeit oder eine Zählung der gelesenen
   Häppchen).
7. KML mit einer externen Entität (`<!ENTITY xxe SYSTEM "file:///etc/passwd">`
   o. Ä.) → `400`, nie aufgelöst.
8. zu viele Punkte (über `MAX_AOI_POINTS`) → `400`.
9. mehrere polygonale Features/Placemarks/Datensätze → `200`, vereinigte
   `MultiPolygon`/`Polygon` (Option B, §9); mehrere Features, darunter
   mindestens ein nicht-polygonales (z. B. zwei `Point` oder ein `Point` und
   ein `Polygon`) → `400` mit den gefundenen Typen.
10. selbstschneidendes („Bowtie") Polygon → `400`.
11. Polygon über den Antimeridian (Longitude-Werte beidseitig `±179.x` im
    selben Ring) → `200`, wird durchgelassen (§7.4 Punkt 5).

Dazu, unabhängig vom Format:

- Test, dass während der gesamten Anfrage kein `open()`/`tempfile`-Aufruf
  eine reale Datei auf Platte erzeugt — am einfachsten durch Patchen von
  `tempfile.SpooledTemporaryFile.rollover` (löst aus, sobald tatsächlich auf
  Platte gespult würde) auf einen fehlschlagenden Aufruf für die Dauer des
  Tests: Für alle Dateien unterhalb der Deckel aus §8 darf `rollover()`
  nie aufgerufen werden.
- `lint-imports --config .importlinter` bleibt grün (keine neue Abhängigkeit
  von `access` auf ein verbotenes Modul; `pyshp`/`defusedxml`/`pyproj` sind
  externe Pakete, keine `earthx.*`-Module).
- Fixtures: ausschließlich synthetisch erzeugt (kleine, von Hand oder per
  Skript gebaute GeoJSON/KML/Shapefile-Dateien unter `backend/tests/fixtures/`
  oder inline im Test), keine echten AOIs, keine echten Flurstücke (B10/D-Teil
  der Öffentlichkeits-Folgen, `ENTSCHEIDUNGEN` §4).

---

## 12. Nicht in dieser Aufgabe

- Frontend-Anbindung (`frontend/src/aoiFile.ts` ersetzen) — M3-06b.
- AOI-Verdünnung für die Suche (`adr/0004` §3.4, `MAX_INTERSECTS_POINTS`) —
  bleibt unverändert an ihrer heutigen Stelle; diese Route liefert nur die
  geprüfte Rohgeometrie.
- Auflösen oder Zerschneiden von Geometrien am Antimeridian.
- Persistenz jeder Art (Worker-Kern-Regel, `KLAERUNGEN.md` B9) — die Geometrie
  lebt nur für die Dauer der Anfrage.

---

## 13. Fragen an Otto — beantwortet 26.09.2026

**F1 — Bibliothek (§4).** (1) reine Python-Lösung: `pyshp` + `defusedxml` +
`pyproj`. (2) OGR über `osgeo`-Bindings. (3) `fiona`/`pyogrio`/`geopandas`.
**Otto: 1.**

**F2 — Modul/Prozess (§5).** Parsing/Prüfung in `access/aoi_upload.py`, Route
in `api/aoi_upload_route.py` im Prozess `api`, wie `coverage_route.py`. (1)
so. (2) anders, bitte benennen. **Otto: 1.**

**F3 — Multipart-Deckel (§6).** (1) `UploadFile`, Deckel 1 MiB = Starlettes
Spool-Schwelle. (2) Rohkörper ohne Multipart, höherer Deckel (z. B. 10 MiB),
Dateiname über Query-Parameter/Header statt `FormData`-Feld. **Otto: 1** —
beim Umsetzen widerlegt (§6-Nachtrag: Starlettes eigener Deckel schützt keine
Datei-Teile) und durch Option 2 (Rohkörper) ersetzt, bei unverändertem Ziel
und Deckelwert (1 MiB).

**F4 — Deckelwerte (§8).** (1) wie in der Tabelle: 1 MiB Upload, 20 MiB
entpackt (Element und Summe), 10 ZIP-Elemente, 20 000 Punkte. (2) andere
Werte, bitte nennen. **Otto: 1.**

**F5 — Mehrere Features (§9).** (1) abweisen, mit Anzahl in der Meldung. (2)
zu einer `MultiPolygon` vereinigen, wenn alle Geometrien polygonal sind. (3)
erste brauchbare Geometrie übernehmen, Rest stillschweigend verwerfen
(heutiges Frontend-Verhalten). **Otto: 2** — abweichend von der Empfehlung;
§9 ist entsprechend umgeschrieben.

**F6 — Erlaubte Geometrietypen (§9).** (1) `Polygon`, `MultiPolygon`, `Point`.
(2) zusätzlich `LineString`/`MultiLineString`. (3) andere Auswahl, bitte
nennen. **Otto: 1.**
