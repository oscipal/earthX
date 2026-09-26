# Funktions- und Design-Inventar des Prototyps

**Aufgabe:** M0 Schritt 3 laut `ENTSCHEIDUNGEN_2026-09-18.md` §6, Grundlage §2.
**Autonomiestufe:** C — nur gelesen und berichtet, kein Produktivcode geändert.
**Stand des untersuchten Codes:** Arbeitskopie im Repo, Branch `main`, Stand 18.09.2026.

## Methode und Grenzen

Das Inventar entstand ausschließlich durch Lesen des Codes in `backend/` und
`frontend/`. Es gab in dieser Sitzung **keinen MAAP-Zugang**; kein externer
Dienst wurde aufgerufen, nichts wurde ausgeführt. Aussagen über Laufzeitverhalten
sind daher aus dem Code abgeleitet, nicht gemessen. Wo der Code eine Annahme über
die Datenquelle trifft, die sich nur an echten Daten prüfen ließe, steht das
ausdrücklich dabei.

Zustand im Prozessspeicher und auf der Platte ist hier nur **vermerkt**. Der
Zustands-Audit ist M0 Schritt 4 (`KLAERUNGEN.md` B1) und bleibt eine eigene
Aufgabe.

Es gibt im Repo **keine Tests** (kein `tests/`-Verzeichnis, keine Testdateien) und
außer `oxlint` im Frontend keine Lint-Konfiguration für das Backend.

## Aufbau des Prototyps in einem Satz

Ein FastAPI-Backend (`backend/app/`) mit neun Routenmodulen unter `/api` spricht den
MAAP-STAC-Katalog an, liest entfernte COGs über HTTP-Range-Requests und rendert
daraus PNG-Kacheln; ein React/MapLibre-Frontend (`frontend/src/`) mit einem einzigen
Zustand-Store (`zustand`) zeichnet AOIs, zeigt Quicklooks und Kacheln als Overlays
und führt durch den Ablauf Suchen → Auswählen → Bestätigen.

### Endpunkte auf einen Blick

| Endpunkt | Modul | Token nötig |
|---|---|---|
| `GET /api/health`, `GET /api/config` | `routes/meta.py` | nein |
| `POST /api/search` | `routes/search.py` | nein (Discovery ist offen) |
| `GET /api/coverage` | `routes/coverage.py` | nein |
| `GET /api/geocode` | `routes/geocode.py` | nein |
| `GET /api/asset` | `routes/assets.py` | **ja** |
| `GET /api/tiles/{item}/{z}/{x}/{y}.png` | `routes/tiles.py` | ja, außer aus lokalem Cache |
| `POST /api/download` | `routes/download.py` | **ja** |
| `POST /api/stitch` | `routes/stitch.py` | **ja** |
| `POST /api/decompose` | `routes/decompose.py` | **ja** |

---

# Teil 1 — Funktionen

## F1 AOI-Auswahl: Punkt, Rechteck, Polygon

**Was und wo.** `frontend/src/components/Toolbar.tsx` bietet drei sich gegenseitig
ausschließende Werkzeuge; `MapView.tsx` betreibt dazu eine `TerraDraw`-Instanz mit
`TerraDrawPointMode`, `TerraDrawRectangleMode`, `TerraDrawPolygonMode` über den
MapLibre-Adapter. Der Store hält `toolMode`, `aoi` und `lastAoi` (`store.ts`).

**Wie gelöst.** Beim `finish`-Ereignis wird die gezeichnete Geometrie übernommen; ein
Punkt wird im Client über `bufferPointToPolygon` (`geoUtils.ts`) zu einem Quadrat mit
Kantenlänge `2 × point_buffer_deg` aufgeweitet — mit demselben Wert, den das Backend in
`geo.py::normalize_aoi` benutzt, damit Anzeige und Suche übereinstimmen. Der Backend-Wert
kommt über `/api/config` ins Frontend. Danach wird die Karte auf die AOI gezoomt, das
Werkzeug zurückgesetzt und das Bedienfeld wieder aufgeklappt. Die AOI wird als GeoJSON-
Quelle `aoi-src` gezeichnet (Füllung 6 % Deckkraft, gestrichelte Linie).

**BIOMASS-spezifisch?** Nein, vollständig übertragbar. Nichts daran kennt den Datensatz.

**Formatgebunden?** Nein. AOI ist GeoJSON in EPSG:4326 und für Zarr identisch nutzbar.

**Token/MAAP?** Nein.

**Zielarchitektur.** Übernehmen. Die doppelte Pufferlogik (Client und Server) ist eine
Dopplung, die man beim Umbau auf eine Stelle ziehen sollte — am sinnvollsten serverseitig,
mit dem Wert aus der Konfiguration, den der Client nur noch spiegelt.

## F2 Ortssuche per Geocoding

**Was und wo.** `frontend/src/components/SearchBox.tsx` (Eingabefeld mit
Vorschlagsliste) gegen `GET /api/geocode` (`routes/geocode.py`).

**Wie gelöst.** Das Backend ist ein dünner Proxy auf einen Nominatim-kompatiblen Dienst
(`geocoder_url`, `geocoder_user_agent` aus `config.py`), weil Nominatim einen eigenen
User-Agent verlangt und der Anbieter so ohne Frontend-Änderung austauschbar bleibt. Die
Antwort wird auf `display_name`, `lat`, `lon`, `bbox`, `type` reduziert; die Nominatim-
Reihenfolge der Bounding-Box (`süd, nord, west, ost`) wird auf `[west, süd, ost, nord]`
umgestellt. Im Client: 350 ms Entprellung, ab drei Zeichen, Enter nimmt den ersten
Treffer, Auswahl setzt die Bounding-Box als AOI-Polygon und fliegt hin. Ein
`suppress`-Ref verhindert, dass das programmatische Ausfüllen des Feldes eine neue Suche
auslöst.

**BIOMASS-spezifisch?** Nein.

**Formatgebunden?** Nein.

**Token/MAAP?** Nein — Nominatim ist token-frei.

**Zielarchitektur.** Übernehmen, aber der ausgehende Request gehört künftig durch
`gateway` (`KLAERUNGEN.md` B8); derzeit ruft `routes/geocode.py` `httpx` direkt auf. Die
Nutzungsbedingungen des öffentlichen Nominatim-Dienstes (Ratenbegrenzung) sind vor einem
Betrieb mit mehreren Nutzern zu klären — offener Punkt, keine Entscheidung in `docs/`.

**Nachtrag M3-07a/b (26.09.2026, umgesetzt):** `POST /geocode` (`earthx/api/geocode_route.py`)
läuft über ein eigenes `gateway`, nur mit dem einen Host aus `EARTHX_GEOCODER_URL`
(ungesetzt = Ortssuche aus). Gecacht in Postgres, mit gemeinsamer Rate über alle
`api`-Prozesse (höchstens 1 Anfrage/s). Anders als der Prototyp: **kein Autocomplete**
(Nominatims Nutzungsbedingung verbietet es), gesucht wird nur auf Enter oder Knopf; die
Auswahl übernimmt den **Umriss** als AOI, wo Nominatim einen liefert, sonst die
Bounding Box (F1, keine Wahl für den Nutzer) — statt wie bisher immer nur die Box. Eine
aus der Ortssuche stammende AOI trägt ihre Herkunft (`source`, `attribution`, `license`)
in ihren GeoJSON-Eigenschaften mit, die unverändert bis in `aoi.geojson` im Download-ZIP
laufen (F3); eine hochgeladene oder gezeichnete AOI trägt das nicht. Attribution
„© OpenStreetMap contributors" kommt aus der Antwort und steht unter der Trefferliste
sowie, solange die AOI noch die aus der Ortssuche ist, unter dem Feld.

## F3 AOI aus Datei und „letzte AOI“ *(steht nicht in §2, ist aber im Code)*

**Was und wo.** `frontend/src/aoiFile.ts`, eingebunden in `ControlPanel.tsx`
(`AoiExtras`). Zwei Schaltflächen: „Upload AOI“ und „Last AOI“.

**Wie gelöst.** Bis M3-06a/b lief das Parsen im Browser (`parseAoiFile`, GeoJSON
oder KML über `DOMParser`, „erste brauchbare Geometrie gewinnt“, ohne Größen-
oder Gültigkeitsprüfung, kein Shapefile). Seit M3-06a/b (26.09.2026) prüft und
parst stattdessen `POST /aoi/upload` im Backend
(`backend/earthx/access/aoi_upload.py`, Plan `plans/m3-06a-aoi-upload-backend.md`):
zusätzlich Shapefile als ZIP, mit Größendeckel (1 MiB), Punktanzahl-Deckel,
Gültigkeitsprüfung und sicherer XML-Verarbeitung. `frontend/src/aoiFile.ts`
(`readAoiFile`) ruft nur noch diese Route auf und bildet ihre Fehlermeldungen ab
(`plans/m3-06b-aoi-upload-frontend.md`). Ein Punkt aus der Datei wird wie in F1
gepuffert. „Last AOI“ stellt die zuletzt gesetzte Geometrie aus `lastAoi` wieder
her — unverändert im Client.

**BIOMASS-spezifisch?** Nein.

**Formatgebunden?** Nein.

**Token/MAAP?** Nein.

**Zielarchitektur.** Übernommen (M3-06a/b). Parsen, Prüfung und Deckelwerte
liegen jetzt im Backend statt im Client; `LineString` wird seither abgewiesen
(kein Verbraucher dafür), mehrere polygonale Features werden vereinigt statt
„erste gewinnt“.

## F4 Szenensuche über STAC und Produktfilter

**Was und wo.** `POST /api/search` (`routes/search.py`) → `stac.py::search`;
im Frontend `store.ts::runSearch` und `products.ts`.

**Wie gelöst.** `pystac_client` öffnet den Katalog aus `stac_catalog_url` und sucht mit
der Bounding-Box der AOI (nicht mit der Geometrie selbst — der Zuschnitt auf das Polygon
passiert erst beim Crop), optionalem STAC-Zeitbereich und einer Collection-Liste,
begrenzt durch `max_search_items` (Vorgabe 300, bewusst hoch, damit eine Gruppe alle
Nachbarkacheln liefert). Jedes Item wird über `serialize_item` auf ein schlankes Objekt
reduziert; dabei wählen zwei Heuristiken die anzuzeigenden Assets:

- `_pick_quicklook`: konfigurierter Schlüssel, sonst ein Asset mit „quicklook“ im Namen
  und `image/*`-Typ, sonst bekannte Namen, sonst Rolle `thumbnail`/`overview`.
- `_pick_cog`: konfigurierter Schlüssel, sonst das erste TIFF, dessen Name keinen der
  Marker `quality`, `probability`, `uncertain`, `cfm`, `mask`, `_ql`, `ql_`, `overview`,
  `thumb` enthält.

Ergebnisse werden nach Datum absteigend sortiert und in die Item-Registry geschrieben
(siehe F13), weil `/tiles` und `/download` später nur eine `item_id` bekommen. Im
Frontend filtert `runSearch` zusätzlich über `ProductDef.match` — reguläre Ausdrücke auf
der Item-ID wie `/BIO_FP_GN/`, `/S[123]_SCS/` — und verlangt für SCS zusätzlich die
Assets `enclosure_i_abs_tiff` und `enclosure_i_phase_tiff`.

**BIOMASS-spezifisch?** **Teilweise.** Das Suchmuster ist übertragbar, die
Produktdefinitionen in `products.ts` (GN, DGM, FH, FD, SCS mit ihren Collections,
Regex-Mustern und Bandzuordnungen) sind reine BIOMASS-Kenntnis. Auch die Asset-Auswahl-
Heuristiken sind auf die MAAP-Namensgebung geeicht (`enclosure_i_abs_tiff` als
Vorgabewert in `config.py`).

**Formatgebunden?** An die STAC-Struktur, ja: die Antwort setzt `item.assets`,
`item.geometry`, `item.bbox` und Properties wie `product:type`, `sat:orbit_state` voraus.
Sie ist **nicht** an COG gebunden — das Format entscheidet erst der Reader. Für Zarr
müssten `_pick_cog` und `_pick_quicklook` durch eine datensatzgetriebene Zuordnung
ersetzt werden (welches Asset ist die Hauptvariable, welcher Pfad in der Zarr-Gruppe),
statt über Dateiendungen und Namensteile zu raten.

**Token/MAAP?** Nein — die MAAP-Discovery ist offen; nur die Pixel sind geschützt
(`stac.py`-Docstring). Das ist der Grund, warum eine tokenlose Sitzung immerhin suchen
kann.

**Zielarchitektur.** Anpassen. `stac.py` ist laut `architekturplan.md` §13 die Vorlage
für den ersten Adapter (Fähigkeiten Suche + Zugriffsauflösung), neu gegen eine
token-freie Quelle. Die Produktliste wandert in die Datensatz-Registry
(`KLAERUNGEN.md` B13), die Regex-Filter entfallen zugunsten echter Collection- bzw.
Property-Filter in der Suche. Der Katalogzugriff gehört über `gateway`, das laut B8 auch
die `pystac_client`-Sitzungsparameter setzt.

## F5 Gruppierung zu Mosaik-/Zeitschritten *(steht nicht in §2, trägt aber F7)*

**Was und wo.** `frontend/src/grouping.ts`.

**Wie gelöst.** Items werden zu Gruppen zusammengefasst mit dem Schlüssel
`Produkttyp | Datum | Orbitrichtung | Track`. Der Track kommt aus der Item-ID über
`/_T(\d{3})_F\d{3}_/`. Eine Gruppe ist damit „ein Überflug“ und genau die Menge
benachbarter Kacheln, die zusammen eine AOI abdecken und die man stitchen darf;
auf- und absteigende Bahnen über derselben Region bleiben getrennt. Sortierung:
neuestes Datum zuerst, innerhalb eines Datums nach `typeRank` — Forest Height, AGB, GN
vor dem Rest, Forest Disturbance ganz zuletzt, weil dessen Quicklooks fast schwarz sind
und sonst die aktive Gruppe mit einem leeren Bild belegen würden.

**BIOMASS-spezifisch?** **Ja, in der Umsetzung**, übertragbar im Prinzip. ID-Muster,
`typeRank` und die Annahme „ein Orbit-Track = eine Akquisition“ sind BIOMASS-Wissen.

**Formatgebunden?** Nein, nur an STAC-Properties.

**Token/MAAP?** Nein.

**Zielarchitektur.** Anpassen. Das Konzept „Zeitschritt = Menge von Szenen, die
gemeinsam angezeigt und gemosaikt werden“ ist wertvoll und gehört generisch gefasst:
die Gruppierungsschlüssel und die Rangfolge kommen aus dem Datensatzeintrag, nicht aus
Regex auf IDs.

## F6 Quicklook-Overlays

**Was und wo.** `frontend/src/mapLayers.ts` (`addQuicklook`, `loadTransparent`,
`keyBlackToTransparent`, `placeImage`), Geometrie in `geoUtils.ts`
(`quicklookCoords`, `footprintCorners`, `rotate180`), Bildbeschaffung über
`GET /api/asset` (F15).

**Wie gelöst.** Für jede Szene der aktiven Gruppe wird ein MapLibre
`image`-Source mit vier Eckkoordinaten gesetzt. Drei nicht offensichtliche Kniffe:

1. **Nodata-Keying.** Der Quicklook wird in ein Canvas gezeichnet und jedes Pixel mit
   allen drei Kanälen ≤ 16 auf Alpha 0 gesetzt, damit der schwarze Rand der Szene nicht
   die Karte zudeckt. Das geht nur, weil das Bild über den eigenen Proxy und damit
   „same-origin“ kommt — sonst wäre das Canvas gesperrt. Ergebnis wird als Data-URL
   im Modul-`Map` `qlDataUrlCache` gehalten.
2. **Eckenzuordnung.** `footprintCorners` sortiert die vier Footprint-Ecken über eine
   Nord-oben-Heuristik in die von MapLibre erwartete Reihenfolge, damit ein rechteckiger
   Quicklook auf ein gedrehtes Viereck verzerrt wird und Nachbarkacheln kantengenau
   aneinanderstoßen.
3. **Geometrie-Sonderfall.** Für IDs, die auf `/S[123]_SCS|DGM/` passen, wird das
   Viereck zusätzlich um 180° gedreht, weil diese L1-Quicklooks in Radargeometrie
   vorliegen.

Ein Generationszähler (`syncGen`) verwirft Bilder, deren Laden eine neuere Synchronisation
überholt hat; `clearDynamicMosaic` räumt über den gesamten Indexbereich auf, damit kein
verwaistes Overlay stehen bleibt. Obergrenze: 40 gleichzeitige Overlays.

**BIOMASS-spezifisch?** **Teilweise.** Punkt 1 und 2 sind übertragbar, Punkt 3 ist ein
hart kodierter BIOMASS-Sonderfall. Der Schwellwert 16 für „schwarz ist Nodata“ ist eine
Annahme über die MAAP-Quicklooks und bei anderen Datensätzen falsch (dunkles Wasser wird
mit entfernt).

**Formatgebunden?** An PNG/JPEG-Quicklooks als eigenes Asset. Zarr-Datensätze wie die
EOPF-Samples liefern nicht zwingend ein vorgerendertes Quicklook-Bild. Für Zarr wäre
entweder ein serverseitig gerendertes Übersichtsbild aus einer groben Auflösungsstufe
nötig (der Zarr-Reader kann das aus der Pyramide liefern) oder die erste Stufe der
zweistufigen Anzeige entfällt und man beginnt direkt mit Kacheln (siehe F10).

**Token/MAAP?** **Ja, mittelbar** — die Bilder kommen über `/api/asset`, das einen Token
braucht. Ohne Token bleibt die Karte trotz gefundener Szenen leer; das Frontend weist
beim Start darauf hin (`store.ts::loadConfig`).

**Zielarchitektur.** Übernehmen, mit zwei Anpassungen: Nodata-Schwelle und
Geometrie-Sonderfall gehören als Felder an den Datensatz statt in den Code; der
Proxy-Zwang entfällt, sobald die Quelle token-frei ist — dann kann das Bild direkt
geladen werden, braucht aber weiterhin CORS-Freigabe für das Canvas-Keying.

## F7 Zeitleiste am unteren Bildschirmrand

**Was und wo.** `frontend/src/components/TimeSlider.tsx`, angeordnet über
`App.tsx` im Bereich `.overlay.bottom`.

**Wie gelöst.** Ein `input[type=range]` über die Gruppen aus F5. Die Gruppen sind
neueste-zuerst sortiert, der Schieberegler stellt sie invertiert dar, damit links alt und
rechts neu ist. Links eine Play-Schaltfläche, die per `setInterval` alle 1400 ms zur
nächsten Gruppe springt und am Ende umläuft; darunter eine Zeile mit der Anzahl der
Bilder der aktuellen Gruppe, „select all frames“ und „add to layers“. Rechts der Zähler
`n/m`. Das Umschalten der Gruppe wechselt über `syncMosaic` die Overlays.

**BIOMASS-spezifisch?** Nein — sie hängt nur an F5.

**Formatgebunden?** Nein.

**Token/MAAP?** Nein selbst; die angezeigten Bilder schon (F6).

**Zielarchitektur.** Übernehmen. Das Intervall und die Sortierrichtung sind
Kandidaten für Einstellungen. Mit vielen Zeitschritten wird der Regler unlesbar; eine
Verdichtung (Histogramm der Aufnahmen über die Zeit) ist die naheliegende Erweiterung,
die es im Prototyp nicht gibt.

## F8 Ablauf „anklicken, auswählen, bestätigen“

**Was und wo.** Verteilt: Kartenklick in `MapView.tsx`, Zeilen in `ResultsPanel.tsx`,
Bestätigung in `DownloadBar.tsx`, Ausführung in `store.ts::runDownload`.

**Wie gelöst.** Der Ablauf ist eine Zustandsmaschine über wenige Store-Felder:

1. AOI setzen (F1–F3) → „Search scenes“ ist erst dann aktiv.
2. Suche klappt das linke Bedienfeld automatisch ein (`panelCollapsed: true`), damit die
   Karte frei wird; bei einem Fehler klappt es wieder auf, damit man die Eingaben
   korrigieren kann.
3. **Anklicken:** Ein Klick auf die Karte sucht mit einem Punkt-in-Polygon-Test
   (`pointInFootprint`, Ray-Casting mit Bounding-Box-Rückfall) die Szene der aktiven
   Gruppe unter dem Cursor und schaltet deren Auswahl um — aber nur, wenn gerade kein
   Zeichenwerkzeug aktiv ist und die Szene ein COG-Asset hat. Alternativ Auswahl per
   Zeile oder Kontrollkästchen in der Ergebnisliste.
4. Die Auswahl wird auf der Karte als gelbe Umrandung (`mosaicsel-line`) hervorgehoben;
   die `DownloadBar` erscheint nur bei nicht leerer Auswahl.
5. **Bestätigen:** eine Schaltfläche „Confirm download (full resolution)“. Eine Szene →
   `POST /api/download`, mehrere → `POST /api/stitch` (F11), Produkt SCS →
   `POST /api/decompose` (F17).
6. Erfolg schaltet in den `focusMode`: Ergebnisliste und Zeitleiste verschwinden, die
   `ViewerControls` erscheinen, die Auswahl wird geleert.

Nicht ladbare Szenen sind durchgehend als solche erkennbar: Zeile abgeblendet,
Kontrollkästchen gesperrt, Abzeichen „PREVIEW“, und der Kartenklick übergeht sie.

**BIOMASS-spezifisch?** Nein. Der Ablauf ist die wertvollste übertragbare
Designentscheidung des Prototyps.

**Formatgebunden?** Mittelbar: „auswählbar“ heißt im Code „hat `cog_key`“
(`ResultsPanel.tsx`, `MapView.tsx`, `store.ts::selectAllInActiveGroup`). Für Zarr ist das
durch eine formatunabhängige Eigenschaft zu ersetzen, etwa „der Datensatz kann
zugeschnitten werden“ als Capability-Flag (`KLAERUNGEN.md` B10).

**Token/MAAP?** Der Ablauf nicht, die Bestätigungsschritte ja (F9, F11, F17).

**Zielarchitektur.** Übernehmen. Das Wort „Download“ ist dabei zu prüfen: Der Prototyp
lädt nichts zum Nutzer herunter, sondern erzeugt einen serverseitigen Zuschnitt und zeigt
ihn an. Die Zielarchitektur trennt das ausdrücklich (`architekturplan.md` §6.4:
Rohdaten per Weiterleitung zur Quelle, Ergebnisse über signierte URLs mit Ablaufdatum).
Der Begriff sollte in der Oberfläche entsprechend geradegezogen werden.

## F9 AOI-Zuschnitt über partielle COG-Reads

**Was und wo.** `backend/app/cog.py::crop_to_aoi`, aufgerufen von
`routes/download.py`.

**Wie gelöst.** Kern der Sache ist `_gdal_env`: GDAL wird so konfiguriert, dass es den
entfernten COG über `/vsicurl` mit Range-Requests liest — kein Verzeichnis-Listing beim
Öffnen, erlaubte Endungen auf TIFF begrenzt, Mehrfach-Ranges und Zusammenfassen
benachbarter Ranges an, HTTP/2, 64 MiB VSI-Cache; der Bearer-Token wird über
`GDAL_HTTP_HEADERS` injiziert. `rio_tiler.io.Reader.part()` liest das AOI-Fenster und
reprojiziert die WGS84-Bounding-Box intern in das CRS des COG, Ausgabe begrenzt auf
4096 px Kantenlänge. Die Maske wird in echtes Nodata übersetzt (NaN bei Float, 0 bei
Ganzzahl), und das Ergebnis wird über `rio_cogeo.cog_translate` als deflate-komprimierter
COG mit 256er-Blöcken und Übersichtsstufen in den Cache geschrieben. Ist der Zuschnitt
schon da, wird er nur „berührt“ (LRU, F13) und zurückgemeldet.

Szenen ohne COG-Asset lösen `NoCogAssetError` aus; die Meldung erklärt ausdrücklich, dass
BIOMASS-L1-SCS-Produkte ihre Daten nur als Zip-Archiv liefern und deshalb nur die Vorschau
funktioniert. Der Fehler wird pro Item gesammelt, nicht als Gesamtabbruch.

**BIOMASS-spezifisch?** Nein im Verfahren; ja im Text der Fehlermeldung und in der
Vorgabe `default_cog_asset`.

**Formatgebunden?** **Ja, vollständig an COG.** Für Zarr braucht es einen eigenen
Reader (`architekturplan.md` §6.2 Rang 1): xarray/zarr statt rasterio, Auswahl über
Dimensionen und Variablennamen statt Bandindizes, Chunk-Grenzen statt GDAL-Blöcken. Die
Schnittstelle „gib mir das AOI-Fenster als Array plus Maske und Transform“ bleibt gleich
und ist die richtige Naht. Auch das Ergebnisformat ist zu entscheiden: der Prototyp
schreibt immer einen COG; ein Zarr-Eingang könnte sinnvoller als Zarr oder NetCDF
herausfallen.

**Token/MAAP?** **Ja.** `crop_to_aoi` ruft `auth.get_access_token()` unbedingt auf, bevor
gelesen wird — auch dann, wenn die Quelle gar keinen Token bräuchte. Das ist eine der
Stellen, die beim Umbau fallen (`ENTSCHEIDUNGEN` §3).

**Zielarchitektur.** Übernehmen als Reader `readers/cog.py`, ohne Token, mit der
GDAL-Konfiguration zentral in `gateway` (B8, `architekturplan.md` §6.3 letzter Punkt).
Das Schreiben in einen Platten-Cache entfällt (siehe F13).

## F10 Zweistufige Anzeige: PNG-Overlay, dann XYZ-Kacheln

**Was und wo.** Stufe 1: F6. Stufe 2: `GET /api/tiles/...` (`routes/tiles.py`) →
`cog.py::render_tile`, im Frontend `mapLayers.ts::placeRaster` und `buildTileUrl`.
Die Umschaltung macht `syncMosaic` anhand von `focusMode`.

**Wie gelöst.** Im Browse-Zustand liegt pro Szene ein statisches, georeferenziertes
Quicklook-Bild auf der Karte — sofort da, grob. Nach dem Bestätigen wechselt die Ansicht
auf eine MapLibre-`raster`-Quelle mit einer Kachelvorlage
`/api/tiles/{item}/{z}/{x}/{y}.png?aoi=<hash>&…`, begrenzt auf die `bounds` des
Zuschnitts. Die Kacheln entstehen dynamisch aus den Übersichtsstufen des zwischengelegten
COG, also erst beim Hineinzoomen in voller Auflösung.

`render_tile` unterscheidet: ein Band → Graustufe durch eine Colormap; mehrere Bänder →
direkt als RGB. Bandwahl über `indexes`, alternativ `expression` (rio-tiler-Bandmathematik).
Ohne explizites `rescale` wird ein 2–98-%-Perzentilstreck pro Band **einmal** berechnet und
im Prozessspeicher unter `item|bandauswahl` behalten, damit alle Kacheln denselben
Streckbereich benutzen und keine Nähte entstehen (F14). Kacheln außerhalb des Footprints
liefern ein 1×1-Pixel-transparentes PNG statt eines Fehlers. Antworten tragen
`Cache-Control: public, max-age=86400`.

**BIOMASS-spezifisch?** Nein. Das Muster „grobe Sofortanzeige, dann dynamische Kacheln“
ist datensatzunabhängig und einer der stärksten Punkte des Prototyps.

**Formatgebunden?** Stufe 2 an COG-Übersichtsstufen (über rio-tiler). Zarr bringt mit
Multiskalen-Gruppen (GeoZarr) das Äquivalent mit; der Ersatz ist ein Zarr-Kachelpfad,
wofür `architekturplan.md` §6.2 ausdrücklich titiler-xarray bzw. TiTiler-EOPF als
Bausteine zu prüfen nennt. Stufe 1 siehe F6.

**Token/MAAP?** Stufe 2 nur, wenn direkt aus der Ferne gelesen wird; aus einem lokalen
Zuschnitt heraus wird bewusst **kein** Token gesetzt (`_resolve_source` liefert
`is_local`, `_gdal_env(None)`).

**Zielarchitektur.** Übernehmen, Umsetzung ersetzen: Kachel-Endpunkte auf den
TiTiler-Fabriken statt selbst gebaut (`architekturplan.md` §6.3), Kachel-URLs vollständig
parametrisiert und damit CDN-fähig — das erfüllt der Prototyp bereits, weil alle
Renderparameter in der URL stehen (`buildTileUrl`).

## F11 Stitching mehrerer Szenen über eine AOI

**Was und wo.** `backend/app/cog.py::stitch_to_aoi`, `routes/stitch.py`,
ausgelöst in `store.ts::runDownload` bei mehr als einer ausgewählten Szene.

**Wie gelöst.** Aus der AOI-Bounding-Box wird ein gemeinsames Zielgitter berechnet: die
längere Seite bekommt `max_size` (4096) Pixel, die kürzere entsprechend dem
Seitenverhältnis. Jede Szene wird mit genau diesen `width`/`height` in dieselbe
Bounding-Box gelesen, sodass alle Ergebnisse pixelgleich übereinanderliegen; gültige
Pixel werden nach der Regel „erster gültiger Wert gewinnt“ eingesetzt
(`fill = valid & ~cmask`). Szenen, die die AOI nicht schneiden, werden übersprungen.
Danach ein einziger COG wie in F9, unter einer synthetischen ID
`stitch_<md5 der sortierten ID-Liste>`, sodass dieselbe Szenenmenge denselben Cache-
Eintrag trifft.

**BIOMASS-spezifisch?** Nein.

**Formatgebunden?** An COG als Ein- und Ausgabe, mit denselben Überlegungen wie F9.
Das Verfahren selbst (gemeinsames Zielgitter, Erst-gültig-gewinnt) ist formatneutral.

**Token/MAAP?** Ja, wie F9.

**Zielarchitektur.** Übernehmen als Operator, aber neu einordnen. In der
Zielarchitektur ist ein Mosaik kein einmalig geschriebener COG, sondern ein
Mosaik-Backend über eine Item-Suche, deren Ergebnis unter einer Such-ID kurz gehalten
wird, damit Kachel-URLs stabil bleiben (`architekturplan.md` §6.3). Zwei sachliche
Schwächen, die dabei zu beheben sind: „erster gültiger Wert gewinnt“ ignoriert
Aufnahmequalität und Zeit, und die feste Kantenlänge 4096 bedeutet bei großen AOIs
stillschweigenden Auflösungsverlust ohne Hinweis an den Nutzer.

## F12 Coverage Map pro Datensatz

**Was und wo.** `GET /api/coverage` (`routes/coverage.py`), Datenerzeugung in
`stac.py::coverage_features` und im Skript `backend/build_coverage.py`; Darstellung in
`mapLayers.ts` (Ebene `coverage-heat`), Schalter in `ControlPanel.tsx`.

**Wie gelöst.** Zwei Wege, die auf dieselbe Datei zeigen:

- **Zur Laufzeit:** `coverage_features` sucht ohne Bounding-Box über eine ganze
  Collection (Obergrenze 1500) und gibt nur Geometrien zurück. Der Docstring vermerkt
  ~20 s Laufzeit; das Ergebnis wird als `data/coverage/<collection>.geojson` abgelegt und
  danach sofort ausgeliefert. `?refresh=true` baut neu.
- **Vorab per Skript:** `build_coverage.py` holt eine größere Stichprobe (Vorgabe 5000)
  und rastert die Footprints in ein grobes Lon/Lat-Gitter (Vorgabe 1°), zählt pro Zelle
  die überlappenden Aufnahmen und schreibt **Gitterzellen mit `count`** statt Footprints.
  Begründung im Docstring: der Katalog enthält Hunderttausende Aufnahmen, die Ausgabegröße
  soll durch das Gitter begrenzt bleiben.

Das Frontend zeichnet eine Choropleth-Fläche, die über `count` (1 → 4 → 8 → 13 → 20) von
Blau nach Rot interpoliert, bei 50 % Deckkraft. Der Store hält das Ergebnis pro Produkt
zwischen und verwirft es beim Produktwechsel.

**BIOMASS-spezifisch?** Nein im Verfahren. Die Collection-Liste in `build_coverage.py`
ist BIOMASS; die Schwellwerte der Farbskala sind auf die BIOMASS-Aufnahmedichte geeicht.

**Formatgebunden?** Nein — es werden nur Metadaten verarbeitet, keine Pixel. Für Zarr
identisch nutzbar und deshalb der am leichtesten zu übertragende Punkt der Liste.

**Token/MAAP?** Nein.

**Zielarchitektur.** Übernehmen und ausbauen: Die Coverage Map ist Pflichtpunkt der
Onboarding-Checkliste (`ENTSCHEIDUNGEN` §5, `KLAERUNGEN.md` B12). Zwei Punkte sind zu
klären:

1. **Stichprobe oder Wahrheit.** Beide Wege zeigen eine *Stichprobe*, nicht die
   vollständige Abdeckung; die Zahl steht zwar als `sample` in der Datei, aber nicht in der
   Oberfläche. Für eine Pflichtangabe pro Datensatz ist das zu wenig — entweder vollständig
   aus pgstac aggregieren oder die Stichprobe sichtbar ausweisen.
2. **Widerspruch zur Beschreibung.** §2 nennt „Coverage Map (Footprints) pro Datensatz“.
   Der ausgelieferte Inhalt ist je nach Erzeugungsweg einmal Footprints und einmal ein
   Dichtegitter; das Frontend stylt nur das Dichtegitter korrekt (es liest `count`). Das
   ist eine echte Unstimmigkeit im Bestand, keine Auslegungsfrage.

## F13 Platten-Cache mit LRU und Item-Registry *(Zustand — nur vermerkt)*

**Was und wo.** `backend/app/store.py`; Cache-Pfade aus `config.py`
(`cache_dir`, `cache_max_bytes` = 5 GiB).

**Wie gelöst.** Zwei Dinge in einem Modul:

- **Item-Registry.** Ein Modul-Dictionary `_registry`, gefüllt von jeder Suche, das zu
  einer `item_id` die Asset-Hrefs und die gewählten Quicklook-/COG-Schlüssel merkt, weil
  `/tiles`, `/download` und `/asset` nur die ID bekommen. Es wird als
  `cache/registry.json` gespiegelt, damit es einen Neustart überlebt. Zugriff über ein
  `threading.RLock`.
- **Zuschnitt-Cache.** Dateiname `<item>__<aoi-hash>__<asset>.tif`, wobei der AOI-Hash die
  ersten 12 Zeichen eines SHA-1 über die kanonisierte Geometrie ist. `touch()` schreibt den
  Zugriffszeitpunkt in `cache/cache_index.json`; `evict_if_needed()` summiert alle `*.tif`
  im Verzeichnis und löscht, beginnend beim ältesten Zugriff, bis die Obergrenze wieder
  eingehalten ist. Aufgerufen wird es jeweils vor und nach dem Schreiben.

**BIOMASS-spezifisch?** Nein.

**Formatgebunden?** Der Cache speichert COGs, die Verdrängung zählt `*.tif` — Ergebnisse
in einem anderen Format würden bei der Größenberechnung schlicht übersehen.

**Token/MAAP?** Nein.

**Zielarchitektur.** **Ersetzen.** Beides widerspricht der Zielarchitektur unmittelbar:

- Der Worker-Kern ist zustandslos und ohne Plattformdienste (`KLAERUNGEN.md` B9),
  `tiler` und `api` haben laut `architekturplan.md` §3.2 ausdrücklich „keinen Zustand“.
  Ein lokaler Platten-Cache mit LRU macht jede Instanz einzigartig: hinter zwei Instanzen
  trifft dieselbe Kachel-URL mal einen Treffer und mal nicht, und die Verdrängung
  schreibt aus einem Request heraus in ein gemeinsames Verzeichnis.
- Die Item-Registry ist noch heikler: Sie ist **Voraussetzung dafür, dass `/tiles` und
  `/download` überhaupt funktionieren** („Item unknown — run a search first“), also kein
  Beschleuniger, sondern verdeckter Sitzungszustand im Prozess. Zwei Nutzer teilen sich
  denselben globalen Namensraum.

Der Ersatz laut `architekturplan.md` §12.3: Kacheln über HTTP/CDN, Suchergebnisse und
COG-Header in Redis oder Postgres, Job-Ergebnisse im Objektspeicher mit Ablaufdatum. Die
Auflösung `item_id → Adresse` gehört in den Katalog, nicht in ein Prozess-Dictionary.
`architekturplan.md` §13 führt `store.py` bereits als „Kandidat für Ersatz“.

Nebenbefunde für den Zustands-Audit (M0 Schritt 4): `_load_index()`/`_save_index()`
lesen und schreiben die ganze Indexdatei bei **jedem** `touch()`; `evict_if_needed()`
statet bei jedem Schreiben alle Dateien im Verzeichnis; die Schreibvorgänge sind nicht
atomar (kein Schreiben in eine Temporärdatei mit anschließendem Umbenennen), ein Abbruch
kann `registry.json` unbrauchbar machen — der Lesepfad fängt das ab, indem er still einen
leeren Zustand annimmt, was den Fehler unsichtbar macht.

## F14 Streckbereichs-Cache im Prozessspeicher *(Zustand — nur vermerkt, nicht in §2)*

**Was und wo.** `cog.py::_RESCALE_CACHE`, ein Modul-Dictionary ohne Sperre und ohne
Obergrenze, zusätzlich `store.set_item_rescale` (in der Registry vorgesehen, im
gelesenen Code nirgends aufgerufen).

**Wie gelöst.** Siehe F10. Zweck ist Nahtfreiheit, nicht nur Geschwindigkeit: alle
Kacheln einer Ansicht müssen denselben Streckbereich benutzen.

**Zielarchitektur.** Anpassen. Der Zweck bleibt gültig und ist wichtig, der Ort nicht:
Ein unbegrenztes Prozess-Dictionary wächst unbeschränkt und liefert hinter mehreren
Instanzen unterschiedliche Bilder für dieselbe URL. Die Statistik gehört in den
Anwendungs-Cache (Redis/Postgres) oder — besser — als Teil der Kachel-URL bzw. der
Rezept-ID, damit die Antwort vollständig durch die URL bestimmt ist.

## F15 Asset-Proxy mit Token-Injektion und Host-Allowlist *(nicht in §2)*

**Was und wo.** `GET /api/asset` (`routes/assets.py`), `config.py::host_allowed`.

**Wie gelöst.** Der Browser darf den MAAP-Token nie sehen. Der Endpunkt löst die
Adresse über die Registry auf, prüft den Host gegen `asset_host_allowlist`
(Suffix-Vergleich), holt die Bytes serverseitig mit dem Bearer-Token und reicht sie mit
`Cache-Control: public, max-age=3600` durch. 401/403 vom Upstream werden in eine
verständliche Meldung übersetzt. Der Allowlist-Vergleich ist bewusst gegen offene
Weiterleitung gerichtet.

**BIOMASS-spezifisch?** Ja im Zweck (es gibt ihn nur, weil die Assets token-geschützt
sind).

**Formatgebunden?** Nein.

**Token/MAAP?** **Ja, vollständig.**

**Zielarchitektur.** **Ersetzen.** Mit token-freien Datensätzen entfällt der Grund: Die
Zielarchitektur schickt Rohdaten per Link oder Weiterleitung direkt zur Quelle, es läuft
kein Byte durch das eigene Backend (`architekturplan.md` §6.4). Was bleibt und gerettet
werden muss, ist der Allowlist-Gedanke — er ist der Keim des Fetch-Gateways
(§6.5, B8). Anmerkung zum Vergleich selbst: `host_allowed` akzeptiert neben `host == h`
und `host.endswith("." + h)` auch ein blankes `host.endswith(h)`, womit ein Host wie
`bösemaap.eo.esa.int` durchginge. Im Gateway ist das als reiner Label-Grenzen-Vergleich
zu implementieren.

## F16 MAAP-Anmeldung und Token-Austausch

**Was und wo.** `backend/app/auth.py`, Konfiguration in `config.py`, Status über
`/api/config`.

**Wie gelöst.** Der aus dem MAAP-Portal erzeugte Token ist meist ein Offline-Token
(Keycloak-Refresh-Token). `auth.py` dekodiert die JWT-Nutzlast ohne Signaturprüfung, um
`typ` zu lesen, tauscht ihn bei Bedarf am OIDC-Endpunkt gegen einen Access-Token und
hält ihn in Modulvariablen bis 30 s vor Ablauf. `token_status()` meldet dem Frontend nur
`configured` und `kind`, nie den Wert.

**BIOMASS-spezifisch?** **Ja, vollständig** — MAAP-Keycloak-Realm, MAAP-Client.

**Formatgebunden?** Nein.

**Token/MAAP?** Ist die Token-Abhängigkeit.

**Zielarchitektur.** **Ersetzen durch nichts.** `ENTSCHEIDUNGEN` §1 und §3 sind
eindeutig: kein Token in der Zielarchitektur, `auth.py` wird nicht übernommen und nicht
generalisiert; Token pro Connector ist ein fernes Zukunftsthema
(`architekturplan.md` §6.1). Der Modulzustand (drei globale Variablen unter einem Lock)
ist für den Zustands-Audit zu vermerken, erledigt sich aber mit dem Modul.

> **Hinweis, kein Vorschlag, sondern eine Frage an Otto (siehe unten, Offene Punkte):**
> `config.py` enthält neben der OIDC-Endpunkt-URL und der Client-ID auch einen
> vorbelegten Client-Secret-Wert als Literal im Quelltext. Er ist im Kommentar als von
> MAAP dokumentierter öffentlicher Wert für den Offline-Token-Austausch bezeichnet.
> Im **öffentlichen** Repo ist das trotzdem ein Literal in einem Feld namens
> „Secret“ und kollidiert mit der Regel aus §4 („keine Secrets im Repo“). Der Wert wird
> hier bewusst nicht wiedergegeben. Er betrifft auch die History-Prüfung aus M0 Schritt 1.

## F17 Polarimetrische Dekomposition

**Was und wo.** `backend/app/decomp.py`, `routes/decompose.py`; Oberfläche in
`DownloadBar.tsx` und `ViewerControls.tsx` (`DECOMPS` aus `products.ts`).

**Wie gelöst.** Das BIOMASS-L1A-SCS-Produkt liefert die komplexen Quad-Pol-Daten als
zwei vierbandige GeoTIFFs — Betrag (`enclosure_i_abs_tiff`) und Phase
(`enclosure_i_phase_tiff`) — in Schrägsicht-Geometrie, georeferenziert nur über GCPs.
`_warp_complex` entwirft daraus ein geografisches Zielgitter (`calculate_default_transform`
über die GCPs), schneidet es auf die Schnittmenge mit der AOI, begrenzt es auf 2048 px und
warpt beide Dateien bandweise mit **Nächster-Nachbar**-Interpolation — ausdrücklich, damit
Betrag und Phase je Pixel zusammengehörig bleiben und ein gültiger Single-Look-Complex-Wert
rekonstruierbar ist. Dann `s = a · e^{iφ}` je Kanal (Reihenfolge HH, HV, VH, VV) und:

- **Pauli:** R = |HH−VV|/√2, G = √2·|HV|, B = |HH+VV|/√2 — kohärent, nutzt die Phase.
- **Freeman–Durden:** modellbasiert, mit Mehrfachsichtung über einen eigenen
  numpy-Boxcar-Mittelwert auf Integralbildbasis (`_boxcar`, `_boxcar_c`, Fenster 5),
  Kovarianzelemente C11/C33/C13, Fallunterscheidung Oberflächen- gegen
  Doppelreflexion, Leistungen auf ≥ 0 begrenzt; R = Doppelreflexion, G = Volumen,
  B = Oberfläche.

Das Ergebnis ist ein dreibandiger Float32-COG mit NaN außerhalb des Streifens, der unter
dem Asset-Schlüssel `decomp_<methode>` im selben Cache liegt und über den normalen
Kachelpfad ausgeliefert wird (`cog.py::_resolve_source` erkennt das Präfix). Die
Oberfläche kündigt 1–2 Minuten pro Szene an.

Davon zu unterscheiden ist das **Pseudo-Pauli** in `products.ts::computeRender`: für die
detektierten Produkte (GN, DGM) wird ohne Phase nur ein Bandmathematik-Ausdruck
`abs(bHH-bVV);bCross;abs(bHH+bVV)` an rio-tiler übergeben. Die Oberfläche benennt das
korrekt als „Pseudo-Pauli“ und die Modusliste weist „Decomposition“ auf
Nicht-SCS-Produkten als nicht verfügbar aus.

**BIOMASS-spezifisch?** **Ja** — und das ist bereits entschieden. Die Mathematik gilt nur
für komplexe Quad-Pol-Daten; `decomp.py` wird laut `ENTSCHEIDUNGEN` §3 als Operator mit
Quad-Pol-Capability übernommen und **nie generalisiert**. Zusätzlich hart kodiert sind die
beiden Asset-Namen und die Annahme über die Bandreihenfolge HH/HV/VH/VV, die aus dem Code
allein nicht überprüfbar ist.

**Formatgebunden?** An zwei getrennte, GCP-georeferenzierte GeoTIFFs. Eine Zarr-Quelle
für komplexe Daten würde Real- und Imaginärteil oder Betrag/Phase als Variablen in einer
Gruppe führen; der Rechenkern (ab `s = a·e^{iφ}`) wäre unverändert nutzbar, das Einlesen
und Warpen nicht.

**Token/MAAP?** **Ja** — und mehr als das: Es ist unklar, ob es überhaupt eine
token-freie Quelle für komplexe Quad-Pol-Daten gibt (Sentinel-1 ist Dual-Pol).
`ENTSCHEIDUNGEN` §3 hält deshalb fest: Der Operator ruht mit synthetischen Tests.

**Zielarchitektur.** Übernehmen als isolierter Datensatz-Operator unter
`datasets/<id>`, an eine Capability gebunden (`KLAERUNGEN.md` B10), mit synthetischen
Mini-Fixtures (B2). Die Trennung „echte Dekomposition nur bei komplexen Daten,
Pseudo-Pauli als Anzeigeoption“ ist gut gelöst und sollte erhalten bleiben — sie ist das
Muster für „häufigste Analysemethoden pro Datensatz“.

## F18 Darstellungssteuerung: Colormap, Streckung, Polarisationsmodi *(nicht in §2)*

**Was und wo.** `ViewerControls.tsx`, `products.ts::computeRender`,
`mapLayers.ts::buildTileUrl`, Auswertung in `routes/tiles.py` und `cog.py`.

**Wie gelöst.** Im `focusMode` erscheint eine Leiste mit: Polarisationsmodus
(Single-pol / Intensity RGB / Pseudo-Pauli / Decomposition), Bandwahl, 13 Colormaps,
`vmin`/`vmax` mit Rückfall auf „auto“ (das serverseitige 2–98-%-Perzentil) und einer
ausdrücklichen Schaltfläche **„Apply“**. Erst „Apply“ schreibt `appliedRender`; die
Kachel-URL ändert sich also nur auf Bestätigung und nicht bei jedem Tastendruck. Die
Modusliste blendet sich nach Produkteigenschaften ein (`pols.length`, `complex`).

**BIOMASS-spezifisch?** Teilweise — die Zuordnung Polarisation → Bandindex steht pro
Produkt in `products.ts` (laut Kommentar „an den echten COGs verifiziert“).

**Formatgebunden?** Bandindizes sind ein COG-Begriff; bei Zarr träte die Auswahl über
Variablen- und Dimensionsnamen an ihre Stelle.

**Token/MAAP?** Nein.

**Zielarchitektur.** Anpassen. `architekturplan.md` §13 sieht vor, dass der
Processing-Teil der Oberfläche später aus Operator-Schemas erzeugt wird; genau dafür ist
diese Leiste die Vorlage. Die „Apply“-Semantik und die Aufteilung
Sofort-Anzeigeparameter (T1) gegen Rechenauftrag (T2, Dekomposition) entsprechen den
Ausführungsstufen aus §7.3 und sollten übernommen werden.

## F19 Layer-Manager *(nicht in §2, aber eine tragende Funktion)*

**Was und wo.** `frontend/src/layers.ts`, `components/LayerManager.tsx`,
`mapLayers.ts::syncLayers`, Store-Aktionen `addCurrentToLayers`, `selectLayer` u. a.

**Wie gelöst.** „Add to layers“ friert ein, was gerade auf der Karte liegt — entweder die
Kachel-Overlays der geladenen Zuschnitte oder die Quicklooks der aktiven Auswahl — als
`MapLayer` mit Namen, Sichtbarkeit, Deckkraft und einer Liste von Overlays. Zusätzlich
speichert jede Ebene unter `restore` so viel Arbeitszustand (`focusMode`, `downloaded`,
`appliedRender`, `activeGroupIndex`, `selectedIds`, `aoi`), dass ein Klick auf den Namen
die Ansicht wiederherstellt und man weiterarbeiten kann. Die Liste wird von unten nach
oben gezeichnet (oberster Eintrag zuletzt), mit Obergrenze 200 Overlays und demselben
Generationszähler-Schutz wie in F6. Der Name entsteht aus `describeView` und benennt die
Ansicht fachlich, etwa „GN · stitched“ oder „SCS · pauli decomp“.

**BIOMASS-spezifisch?** Nein, bis auf die Produktkürzel im Namen.

**Formatgebunden?** Nein.

**Token/MAAP?** Nur mittelbar über die referenzierten Bilder.

**Zielarchitektur.** Übernehmen. Das ist mehr als ein Ebenenschalter: Der
`restore`-Block ist faktisch ein gespeicherter Ansichtszustand und damit der Keim von
teilbaren Ansichten bzw. Rezepten. Zu beachten: Die Ebenen liegen nur im
Browserspeicher und sind nach einem Neuladen weg; ein Ergebnis, das über eine Sitzung
hinaus Bestand hat, ist in der Zielarchitektur ein Objekt mit Adresse, nicht ein
React-Zustand.

## F20 Weitere Bedienfunktionen *(nicht in §2)*

| Funktion | Ort | Übertragbar |
|---|---|---|
| Verschiebbare Bedienfelder mit Greifpille, ohne Steuerelemente zu kapern | `components/Draggable.tsx` | ja, unverändert |
| Ein-/ausklappbares linkes Bedienfeld mit Reiter, klappt bei Zeichenwerkzeug und Suche automatisch zu | `App.tsx`, `store.ts::setToolMode`, `.panel-dock` in `index.css` | ja |
| „Zoom to selection“ mit Rangfolge Zuschnitt → Auswahl → Gruppe → AOI | `store.ts::zoomToView` | ja |
| „Clear all“ setzt Suche, Auswahl und geladene Bilder zurück | `store.ts::clearAll` | ja |
| Statuszeile mit drei Meldungsarten: Fortschritt, Fehler (bleibt stehen), Hinweis (blendet nach 5 s aus) | `components/StatusBar.tsx` | ja |
| Hinweis beim Start, wenn kein Token konfiguriert ist | `store.ts::loadConfig` | entfällt mit dem Token |
| `GET /api/health`, `GET /api/config` als einzige Quelle für Frontend-Vorgaben | `routes/meta.py` | ja, Muster übernehmen |
| Sichtbarkeitsschalter für das geladene Bild („Hide image“) zum Vergleich mit dem Basiskartenbild | `ViewerControls.tsx` | ja |

## F21 Fehlerbehandlung als durchgehendes Muster *(nicht in §2)*

Erwähnenswert, weil es eine bewusste Designentscheidung ist und nicht zufällig entsteht:
Alle Mehrfachoperationen (`/download`, `/decompose`) brechen **nicht** beim ersten Fehler
ab, sondern sammeln pro Item ein Ergebnisobjekt mit `status`, `code` und Klartextfehler;
das Frontend zeigt Teilerfolge an und listet die gescheiterten Items einzeln. Fehlerklassen
sind sauber getrennt (`TokenError` → 401, `NoCogAssetError` → 422 mit `preview_only`,
unbekanntes Item → 404). Die Fehlertexte sind an Nutzer gerichtet und nennen den nächsten
Schritt. Das ist übertragbar und sollte als Konvention für die öffentliche API erhalten
bleiben.

---

# Teil 2 — In §2 genannt, im Code nicht oder anders vorgefunden

## N1 Theme-Umschalter — **nicht vorhanden**

`index.css` definiert vollständig **zwei** Token-Sätze, `[data-theme='tech']` (dunkel)
und `[data-theme='normal']` (hell), inklusive Sonderregeln für die primäre Schaltfläche
und die MapLibre-Attribution. Der Kopfkommentar der Datei spricht von „toggled via
[data-theme]“, und `MapView.tsx` enthält einen Kommentar, der einen Themenwechsel als
Grund nennt, alle Ebenen neu aufzubauen. **Es gibt aber keine Umschaltmöglichkeit:**
`App.tsx` setzt `data-theme="tech"` fest, und kein Code schreibt das Attribut je um.
Das helle Thema ist also vorbereitet, aber nicht erreichbar und im Betrieb nie erprobt.

## N2 „Dunkles Kartendesign“ — **anders gelöst als die Formulierung nahelegt**

Es gibt keinen dunklen Kartenstil im Sinne eines dunklen Vektor-Basiskartenbildes.
`mapStyles.ts` enthält genau einen, handgeschriebenen Stil: ein einzelner Raster-Layer
mit Esri-„World Imagery“-Satellitenkacheln über einem fast schwarzen Hintergrund
(`#04070a`), der nur beim Laden sichtbar ist. Dunkel ist die **Oberfläche** — die
halbtransparenten HUD-Bedienfelder darüber. Für die Übertragung ist das wichtig: „dunkles
Kartendesign“ ist im Bestand eine Eigenschaft der Bedienoberfläche, nicht der Karte.
Ein heller Modus bräuchte zusätzlich ein passendes Basiskartenbild, das es noch nicht
gibt. Nebenbefund: Die Esri-Kachel-URL ist fest verdrahtet und wird vom Browser direkt
geladen; Nutzungsbedingungen und die spätere Einordnung unter `gateway` sind offen.

## N3 Coverage Map als Footprints — **teilweise abweichend**

Siehe F12: Ausgeliefert wird je nach Erzeugungsweg ein Dichtegitter oder Footprints; das
Frontend stylt nur das Dichtegitter. Beides ist außerdem eine Stichprobe.

## N4 „Download“ — **Begriff trifft nicht das Verhalten**

Siehe F8: Der Ablauf erzeugt einen serverseitigen Zuschnitt und zeigt ihn an. Eine
Funktion, mit der ein Nutzer eine Datei erhält, existiert im Prototyp nicht.

## N5 Nicht gefunden, weil nicht vorhanden

Keine Tests, keine Fixtures, kein `tests/`-Verzeichnis; keine CI-Konfiguration; keine
`.env.example` im Repo, obwohl README und `config.py` darauf verweisen (sie ist über
`.gitignore` ausgeschlossen); kein Linting für das Backend. `frontend/src/App.css` und
`src/assets/` sind unbenutzte Reste der Vite-Vorlage (`main.tsx` bindet nur `index.css`
ein). Toter Code außerdem: `grouping.ts::isGnItem` und `store.py::set_item_rescale`
werden nirgends aufgerufen.

---

# Teil 3 — Design

Ziel dieses Abschnitts: so beschrieben, dass man es ohne den Prototyp nachbauen kann.

## Grundhaltung

Ein „HUD über der Karte“. Die Karte füllt das gesamte Fenster
(`position: absolute; inset: 0`); alles andere schwebt als halbtransparente, unscharf
hinterlegte Tafeln darüber. Die Overlay-Behälter sind
`pointer-events: none`, ihre direkten Kinder `pointer-events: auto` — die Karte bleibt
also überall dort bedienbar, wo keine Tafel liegt. Die Schriftart ist durchgehend
**monospace**, auch in Fließtexten; Beschriftungen sind klein, großgeschrieben und
gesperrt. Der Eindruck ist bewusst technisch, nicht produktverspielt.

## Farben (Token aus `index.css`)

**Dunkel (`data-theme='tech'`, der einzige aktive Modus):**

| Token | Wert | Verwendung |
|---|---|---|
| `--panel-bg` | `rgba(6, 12, 16, 0.82)` | Tafelhintergrund |
| `--panel-border` | `rgba(120, 220, 255, 0.32)` | Rahmen, Trennlinien, Greifpille |
| `--accent` | `#19e0ff` (Cyan) | aktive Zustände, Links, primäre Schaltfläche, AOI |
| `--accent-2` | `#ffd166` (Bernstein) | **Auswahl** — Umrandung auf der Karte, Zeilenhinterlegung, Abzeichen |
| `--text` | `#d7f2ff` | Text |
| `--muted` | `#7fa8b8` | Beschriftungen, Nebeninformation, inaktiv |
| `--input-bg` | `rgba(10, 20, 26, 0.9)` | Eingabefelder, Werkzeugtasten |
| `--glow` | `0 0 18px rgba(25, 224, 255, 0.18)` | Schein an Tafeln und aktiven Elementen |
| `--row-hover` | `rgba(25, 224, 255, 0.08)` | Zeilen unter dem Zeiger |
| Fehler | `#ff5a6e` Rahmen, `#ff9aa7` Text | Fehlermeldung, „danger“-Schaltflächen |

**Hell (`data-theme='normal'`, vorbereitet, nicht erreichbar):** `--panel-bg`
`rgba(255,255,255,0.94)`, `--accent` `#0a7ea4`, `--accent-2` `#c76b00`, `--text`
`#10222c`, `--muted` `#5a6b74`, `--glow` als weicher Schlagschatten statt Schein.

**Die Farblogik in einem Satz:** Cyan heißt „aktiv / anklickbar / System“, Bernstein
heißt „von dir ausgewählt“, Rot heißt „Fehler oder zerstörend“. Diese Trennung wird
konsequent durchgehalten und ist der Grund, warum die Oberfläche trotz vieler Elemente
lesbar bleibt.

**Kartenfarben (nicht aus den Token, sondern in `mapLayers.ts`):** AOI `#19e0ff`,
Füllung 6 % Deckkraft, Linie 1,6 px gestrichelt `[3, 2]`. Auswahl-Umrandung `#ffd166`,
3 px, 1 px Unschärfe, 95 % Deckkraft. Coverage-Choropleth interpoliert linear über
`count`: `1 → #2c7bb6`, `4 → #00a6ca`, `8 → #a6d96a`, `13 → #fdae61`, `20 → #d7191c`,
bei 50 % Deckkraft und ohne Umrandung.

## Kartenstil

Esri „World Imagery“ als einzige Raster-Quelle, 256 px Kacheln, `maxzoom` 19,
darunter ein Hintergrund `#04070a`. Startansicht `center: [10, 20]`, `zoom: 1.6` — also
global, was zur „erst Coverage ansehen, dann AOI wählen“-Reihenfolge passt.
Navigationssteuerung unten rechts, **ohne Kompass**. Attribution kompakt und im dunklen
Thema zusätzlich abgedunkelt. Bewegungen zu einem Ziel immer als `fitBounds` mit
80 px Rand, 900 ms Dauer und `maxZoom: 14`, damit ein Punktziel nicht bis zur
Unkenntlichkeit hineinzoomt.

Reihenfolge der Ebenen von unten nach oben: Satellitenbild → angeheftete Ebenen des
Layer-Managers → aktive Overlays (Quicklooks oder Kacheln) → AOI-Füllung und -Linie →
Auswahl-Umrandung. Technisch durchgesetzt über `beforeAoi()`, das jedes neue Overlay
unter `aoi-fill` einfügt, damit die AOI nie verdeckt wird.

## Layout

Fünf feste Ankerzonen, alle mit 16 px Abstand zum Rand:

| Zone | Inhalt | Position |
|---|---|---|
| oben links | Bedienfeld, max. 340 px breit, mit Reiter zum Einklappen | `top: 16px; left: 16px` |
| oben rechts | „Zoom to selection“, „Layers (n)“ | `top: 16px; right: 16px` |
| oben mitte | Statusmeldungen, `min(560px, 90vw)` | mittig, `top: 16px` |
| rechts | Ergebnisliste, 300 px, `top: 96px; bottom: 120px` | rechts, zwischen den anderen Zonen |
| unten mitte | Auswahl-Leiste und Zeitleiste, bzw. im Fokus die Ansichtssteuerung | `min(760px, 92vw)`, gestapelt mit 10 px Abstand |

Der Layer-Manager startet bei `top: 96px; left: 420px`, also neben dem Bedienfeld, und
ist wie die unteren Tafeln frei verschiebbar.

Tafelgestalt einheitlich: 10 px Eckenradius, 1 px Rahmen, `backdrop-filter: blur(10px)`,
Schein nach `--glow`. Eingabefelder und Schaltflächen 6 px Radius. Typografische Stufen:
Titel 15 px / 2 px Sperrung, Abschnittsbeschriftung 10 px großgeschrieben / 1,5 px
Sperrung, Fließtext 11–12 px, Item-IDs 9 px in `--muted` mit Auslassungszeichen,
Abzeichen 8 px.

## Bedienmuster

Diese acht Muster tragen die Oberfläche und sind der eigentliche übertragbare Gehalt:

1. **Die Karte ist der Arbeitsplatz, Tafeln weichen aus.** Ein Zeichenwerkzeug oder eine
   startende Suche klappt das linke Bedienfeld automatisch weg (0,32 s Übergang); Abschluss
   des Zeichnens oder ein Suchfehler holt es zurück. Der Nutzer muss nichts aufräumen.
2. **Zwei Ansichtszustände statt vieler Fenster.** *Browsen*: Ergebnisliste rechts,
   Zeitleiste unten, Quicklooks auf der Karte. *Fokus*: beide verschwinden, es erscheint
   eine einzige Leiste unten mit den Darstellungsoptionen für das geladene Bild. Der
   Rückweg heißt ausdrücklich „‹ Choose a different image“.
3. **Auswahl ist überall dasselbe.** Kartenklick, Zeilenklick und Kontrollkästchen
   schalten denselben Zustand um; die Rückmeldung erfolgt gleichzeitig in Liste und Karte.
4. **Nicht Verfügbares wird gezeigt, nicht versteckt.** Szenen ohne ladbares Asset
   bleiben sichtbar, abgeblendet, mit Abzeichen „PREVIEW“ und erklärendem Hinweistext;
   geladene tragen „HI-RES“.
5. **Bestätigen ist ein eigener Schritt.** Die Auswahl-Leiste erscheint erst bei einer
   Auswahl und nennt im Text, was passieren wird („Crop each scene to the AOI and mosaic
   them into one image“). Ebenso schreibt „Apply“ erst auf Klick neue Kachelparameter —
   nichts rechnet ungefragt los, und teure Vorgänge kündigen ihre Dauer an
   („takes ~1–2 min per scene“).
6. **Alles Schwebende ist verschiebbar.** `Draggable` versetzt eine Tafel relativ zu ihrem
   Anker, sodass das Layout responsiv bleibt; Steuerelemente werden über eine
   `closest()`-Prüfung vom Ziehen ausgenommen, eine Greifpille zeigt die Möglichkeit an.
7. **Rückmeldung in drei Schärfegraden.** Fortschritt (mit Spinner, verschwindet von
   selbst), Hinweis (blendet nach 5 s aus), Fehler (bleibt bis zum Wegklicken). Fehler
   nennen die Ursache und den nächsten Schritt.
8. **Kleine Hilfen an den richtigen Stellen.** „Last AOI“, „select all frames“, „auto“ zum
   Zurücksetzen der Streckung, „Zoom to selection“ mit sinnvoller Rangfolge, `title`-Texte
   an praktisch jedem Bedienelement, durchgehend `aria-label`/`aria-pressed` an
   Umschaltern.

## Was beim Nachbau zu beachten ist

- Die Oberfläche setzt `overflow: hidden` auf `body` und arbeitet mit `100vw/100vh`. Es
  gibt **keine** Anpassung an kleine Bildschirme: keine Media Queries, feste Tafelbreiten
  von 300–340 px, Ankerzonen mit festen Abständen. Auf einem Telefon ist das unbenutzbar.
  Für die Zielplattform ist das entweder zu ergänzen oder als Entscheidung festzuhalten.
- Kontrast: `--muted` `#7fa8b8` auf `--panel-bg` bei 9–10 px Schriftgröße liegt unter den
  üblichen Schwellen; die Farbkodierung Cyan/Bernstein ist zudem die einzige
  Unterscheidung zwischen „aktiv“ und „ausgewählt“. Für eine öffentliche Plattform ist
  ein Zugänglichkeitsdurchgang nötig.
- Die verwendeten Schriften (`JetBrains Mono`, `Inter`) werden nirgends geladen; es
  greift der jeweilige System-Rückfall. Beim Nachbau bewusst entscheiden.

---

# Teil 4 — Übersicht

„Aufwand grob“ schätzt die Übertragung auf einen token-freien Datensatz in der
Zielarchitektur, nicht die Neuentwicklung von Grund auf: **S** = im Wesentlichen
umziehen, **M** = umbauen mit klarem Bild, **L** = neu entwerfen oder erst noch zu
klären.

| Funktion | übertragbar | formatgebunden | Token | Zielarchitektur | Aufwand |
|---|---|---|---|---|---|
| F1 AOI Punkt/Rechteck/Polygon | ja | nein | nein | übernehmen | S |
| F2 Ortssuche (Geocoding) | ja | nein | nein | übernehmen, über `gateway` | S |
| F3 AOI aus KML/GeoJSON, „letzte AOI“ | ja | nein | nein | übernehmen | S |
| F4 STAC-Suche + Produktfilter | teilweise | STAC-Struktur | nein | anpassen (erster Adapter) | M |
| F5 Gruppierung zu Zeitschritten | teilweise | nein | nein | anpassen (Regeln aus der Registry) | M |
| F6 Quicklook-Overlays | teilweise | PNG-Quicklook-Asset | ja (mittelbar) | übernehmen, Parameter an den Datensatz | M |
| F7 Zeitleiste mit Abspielen | ja | nein | nein | übernehmen | S |
| F8 Anklicken → Auswählen → Bestätigen | ja | nein | nein | übernehmen (Begriff „Download“ klären) | S |
| F9 AOI-Zuschnitt, partielle Reads | ja | **COG** | ja | übernehmen als Reader, ohne Token | M |
| F10 Zweistufige Anzeige (PNG → XYZ) | ja | COG-Overviews (Zarr: Multiskalen) | teilweise | übernehmen, Umsetzung auf TiTiler | M |
| F11 Stitching über eine AOI | ja | COG | ja | übernehmen, als Mosaik-Backend neu einordnen | M |
| F12 Coverage Map | ja | nein | nein | übernehmen und ausbauen (Pflichtpunkt) | S–M |
| F13 Platten-Cache LRU + Item-Registry | **nein** | `*.tif` | nein | **ersetzen** (widerspricht B9 / §3.2) | L |
| F14 Streckbereichs-Cache im Prozess | teilweise | nein | nein | anpassen (Zweck ja, Ort nein) | M |
| F15 Asset-Proxy mit Token + Allowlist | teilweise | nein | **ja** | **ersetzen**; Allowlist → `gateway` | M |
| F16 MAAP-Token / OIDC | **nein** | nein | **ja** | **ersatzlos streichen** (§1, §3) | — |
| F17 Polarimetrische Dekomposition | nein, bewusst | zwei GCP-GeoTIFFs | ja | Operator mit Quad-Pol-Capability, ruht | L |
| F18 Darstellungssteuerung | teilweise | Bandindizes | nein | anpassen, später aus Operator-Schemas | M |
| F19 Layer-Manager | ja | nein | nein | übernehmen, Zustand verorten | M |
| F20 Bedienfunktionen (Sammelposten) | ja | nein | nein | übernehmen | S |
| F21 Fehlerbehandlung pro Item | ja | nein | nein | übernehmen als API-Konvention | S |
| N1 Theme-Umschalter | — | — | — | **fehlt im Code**, neu zu bauen | S |
| N2 Dunkles Kartendesign | teilweise | — | nein | HUD übernehmen; dunkle Basiskarte fehlt | M |

---

# Teil 5 — Offene Punkte

Das Inventar hält sich an die Regel, nicht zu raten. Folgende Punkte sind in `docs/`
nicht entschieden und werden hier nur benannt:

1. **Client-Secret-Literal in `config.py`** (siehe F16). Es steht im öffentlichen Repo
   und in der History. Optionen:
   (a) *Empfehlung:* zusammen mit `auth.py` beim Umbau ersatzlos entfernen und den Punkt
   in die History-Prüfung aus M0 Schritt 1 aufnehmen;
   (b) sofort aus dem Code lösen und nur noch über eine Umgebungsvariable versorgen,
   solange der Prototyp lokal weiterläuft;
   (c) als dokumentierten öffentlichen Wert bewusst stehen lassen und im Entscheidungslog
   festhalten, dass §4 hier nicht greift.
2. **Coverage Map: Footprints oder Dichtegitter, Stichprobe oder vollständig?** (F12/N3).
   (a) *Empfehlung:* Dichtegitter aus pgstac vollständig aggregiert, mit ausgewiesenem
   Stand;
   (b) Footprints direkt, mit Obergrenze und sichtbarem Hinweis „Stichprobe“.
3. **Dunkles Kartendesign und Theme-Umschalter** (N1/N2): Was genau soll übertragen
   werden?
   (a) *Empfehlung:* dunkle HUD-Oberfläche übernehmen und dazu eine dunkle Vektor-
   Basiskarte ergänzen, Umschalter auf hell neu bauen;
   (b) nur die HUD-Oberfläche übernehmen, Umschalter zurückstellen;
   (c) Satellitenbild als einzige Basiskarte beibehalten.
4. **Nutzungsbedingungen der fest verdrahteten Fremddienste**: Esri World Imagery als
   Basiskarte (N2) und der öffentliche Nominatim-Dienst (F2). Beides ist für einen
   Prototyp unkritisch und für eine öffentliche Plattform zu klären — vermutlich als
   eigener Punkt neben der Lizenzeinstufung der Datensätze.
