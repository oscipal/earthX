# M3-06a — AOI-Upload: Backend-Route mit Shapefile: Plan

**Aufgabe:** M3-06a aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B.** Dieser Plan-Schritt hält an; Umsetzung erst nach Ottos Freigabe
der Fragen in §9, in derselben Session.
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

## 6. Nur Arbeitsspeicher: das Multipart-Problem

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
| **A. `UploadFile`/`multipart/form-data`, Deckel = 1 MiB (empfohlen)** | Größendeckel für den gesamten Upload exakt auf Starlettes eigene Spool-Schwelle legen (`Request.form(max_part_size=1_048_576)`, zusätzlich eigene Prüfung der gelesenen Bytes) | Klassisches, standardkonformes Muster (`<input type="file">` + `FormData`); Starlettes eigener Code garantiert dann, dass der Inhalt nie den Spool-Punkt erreicht — kein eigener Nachweis nötig, dass GDAL/Python nicht doch spult, weil die Schwelle selbst der Deckel ist. Ein AOI-Polygon mit dem in §8 vorgeschlagenen Punktanzahl-Deckel (20 000) passt als Text-GeoJSON oder als Shapefile-ZIP komfortabel unter 1 MiB (grobe Rechnung: 20 000 Stützpunkte × ~16 Byte im `.shp`-Binärformat ≈ 320 KiB, plus `.prj`/`.dbf` im Kilobyte-Bereich) | Deckel wirkt auf den ersten Blick klein/willkürlich; ein sehr detailreiches, aber legitimes Polygon (viele Zehntausend Stützpunkte) würde abgewiesen — dagegen steht, dass genau das auch der Punktanzahl-Deckel in §8 schon tut |
| **B. Rohkörper ohne Multipart** | `POST` mit dem Dateiinhalt direkt als Body (`Content-Type` z. B. `application/zip`), Dateiname über einen Query-Parameter oder Header statt über `FormData`; `await request.body()` bzw. `request.stream()` mit eigenem, höherem Deckel (z. B. 10 MiB), da Starlettes Spool-Mechanik hier nicht greift (reine Body-Lesung, kein `MultiPartParser`) | Erlaubt einen großzügigeren Deckel ohne die 1-MiB-Grenze; einfacher zu prüfen (kein `python-multipart` nötig) | Untypisch für einen Datei-Upload aus dem Browser; das Frontend (M3-06b) müsste den Dateinamen separat mitschicken statt einem gewohnten `FormData`-Feld |

**Empfehlung: Option A.** 1 MiB deckt die in §8 vorgeschlagenen
Deckelwerte komfortabel ab, ist Standard-Idiom, und macht den Beweis
„landet nie auf Platte" trivial (Starlettes eigene Konstante ist der Deckel,
nicht eine Annahme über ihr Verhalten). Ein Test hält das trotzdem fest, siehe
§10 dritter Punkt. → **Frage F3**.

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
  `.shp` und `.prj` **Pflicht**; `.shx`/`.dbf` optional (nur Geometrie wird
  gebraucht, keine Attribute — zu verifizieren beim Umsetzen, ob `pyshp` ganz
  ohne `.shx` einen reinen Shape-Scan erlaubt oder ob ein synthetischer `.shx`
  aus dem `.shp` nachgebaut werden muss). Fehlt `.shp` oder `.prj` → `400`,
  „fehlt", nicht geraten (explizit für `.prj` in der Aufgabenstellung
  gefordert, hier gleich auf `.shp` erweitert, weil ohne `.shp` keine
  Geometrie da ist).
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
| **A. Abweisen (empfohlen)** | `400` mit der Anzahl gefundener Geometrien, „export exactly one shape and upload again" | Ehrlich (Prinzip 9 „Ehrlichkeit in der Anzeige"): ein Nutzer, der aus Versehen mehrere Flächen exportiert, verliert sonst stillschweigend alle bis auf eine (heutiges `aoiFile.ts`-Verhalten, F3) — die Route soll das nicht wiederholen, wenn sie schon ohnehin geprüft wird |
| **B. Vereinigen** (`shapely.union_all`) zu einer `MultiPolygon`, nur wenn alle Geometrien vom selben Grundtyp (polygonal) sind | erlaubt eine absichtlich mehrteilige AOI (z. B. zwei getrennte Untersuchungsgebiete) in einer Datei | verdeckt, ob mehrere Features Absicht oder Versehen waren; bei gemischten Typen (z. B. ein Polygon und ein Punkt) bräuchte es ohnehin eine Sonderregel |
| **C. Erste brauchbare Geometrie, Rest verwerfen** | heutiges Verhalten von `aoiFile.ts` (F3), unverändert übernehmen | am wenigsten Überraschung gegenüber heute, aber genau die stille Flächen-Verkleinerung, die Prinzip 9 vermeiden soll — und M3-06a soll laut Ziel „einheitlich geprüft" liefern, nicht nur „genauso lax wie bisher" |

**Empfehlung: Option A.** → **Frage F5.**

---

## 10. API-Form

- **Route:** `POST /aoi/upload`, im Prozess `api`, außerhalb `/stac` (analog
  `/coverage/{dataset_id}`, §5).
- **Anfrage:** `multipart/form-data`, ein Feld `file` (Option A aus §6);
  Dateiname liefert die Formaterkennung (`.geojson`/`.json` → GeoJSON, `.kml`
  → KML, `.zip` → Shapefile-Bündel); alles andere → `400`.
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
9. mehrere Features/Placemarks/Datensätze → `400` mit Anzahl (Option A, §9).
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

## 13. Fragen an Otto

**F1 — Bibliothek (§4).** (1) reine Python-Lösung: `pyshp` + `defusedxml` +
`pyproj` (**empfohlen**). (2) OGR über `osgeo`-Bindings. (3) `fiona`/
`pyogrio`/`geopandas`.

**F2 — Modul/Prozess (§5).** Parsing/Prüfung in `access/aoi_upload.py`, Route
in `api/aoi_upload_route.py` im Prozess `api`, wie `coverage_route.py` — nur
zur Bestätigung, keine echte Alternative gefunden. (1) so. (2) anders, bitte
benennen.

**F3 — Multipart-Deckel (§6).** (1) `UploadFile`, Deckel 1 MiB = Starlettes
Spool-Schwelle (**empfohlen**). (2) Rohkörper ohne Multipart, höherer Deckel
(z. B. 10 MiB), Dateiname über Query-Parameter/Header statt `FormData`-Feld.

**F4 — Deckelwerte (§8).** (1) wie in der Tabelle: 1 MiB Upload, 20 MiB
entpackt (Element und Summe), 10 ZIP-Elemente, 20 000 Punkte (**empfohlen**).
(2) andere Werte, bitte nennen.

**F5 — Mehrere Features (§9).** (1) abweisen, mit Anzahl in der Meldung
(**empfohlen**). (2) zu einer `MultiPolygon` vereinigen, wenn alle Geometrien
polygonal sind. (3) erste brauchbare Geometrie übernehmen, Rest stillschweigend
verwerfen (heutiges Frontend-Verhalten).

**F6 — Erlaubte Geometrietypen (§9).** (1) `Polygon`, `MultiPolygon`, `Point`
(**empfohlen**). (2) zusätzlich `LineString`/`MultiLineString`. (3) andere
Auswahl, bitte nennen.
