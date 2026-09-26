# M3-11b — DEM-Adapter, Einmal-Befehl in `discovery`, Registry-Eintrag: Plan-Schritt

**Status (26.09.2026):** Plan-Schritt, wartet auf Ottos Freigabe (§9).
**Aufgabe:** M3-11b aus `docs/plans/m3-dritte-quelle-und-interface.md` §4
(P24). **Stufe B.** Hängt an M3-11a (gemergt, #95).
**Grundlagen:** `adr/0009` §3.1, §7, §10, §11; `adr/0003` §10.1, §11.1;
`adr/0004` §5; `plans/m3-11a-materialisierte-quellen.md` §3.5, §3.6 (F3);
`architekturplan.md` 3.1, 5.1, 5.2; `KLAERUNGEN.md` B8, B10, B11, B13;
`projektuebersicht.md` §5 (Onboarding-Checkliste).

Belegstufen wie in `adr/0009`: **M** in dieser Sitzung gemessen, **P** am
Primärdokument oder Quelltext gelesen (Stand `main` 1b66759), **S** Suchtreffer,
**A** eigene Ableitung.

---

## 1. Ziel

Copernicus DEM GLO-30 steht als dritter Datensatz in der Registry. Ein
Einmal-Befehl in `discovery` erzeugt über einen neuen Adapter aus
`tileList.txt` die 26 450 Items und schreibt sie über `catalog` nach pgstac.
Ein zweiter Lauf erkennt eine unveränderte Quelle an der ETag. Der Datensatz
besteht die Onboarding-Checkliste.

---

## 2. Messungen an der Quelle (26.09.2026)

Gedrosselt auf höchstens eine Anfrage pro Sekunde, per `curl` und rasterio aus
der Sitzung (nicht über `gateway`, das die Quelle aus einer Sitzung nicht
erreicht, M2-13). **Rund 100 bis 115 Anfragen** an
`copernicus-dem-30m.s3.amazonaws.com`, zusammen rund 15 MB. Die Zahl ist nicht
genau: Ein erster Kachel-Lauf mit abgeschaltetem GDAL-Cache und ein versehentlich
doppelt gestarteter, nach wenigen Sekunden abgebrochener Lauf haben ihre Anfragen
nicht gezählt; beide Läufe sind verworfen. Dazu das Product Handbook
(`dataspace.copernicus.eu`), zwei Webseiten und ein abgewiesener Aufruf an
`doi.org` (nicht freigegeben).

### 2.1 `tileList.txt` und ETag — **[M]**

- `ETag "637fe75ddf7615ba853dd83caf05cd82"`, `Last-Modified` 09.05.2022,
  1 110 900 Byte, wie in `adr/0009` §7.3.
- Ein `GET` mit `If-None-Match: <ETag>` antwortet **`304`**. `gateway` gibt
  einen `304` als Antwort zurück, nicht als Fehler (`gateway/client.py`, nur
  Status ab 400 wird zu `UpstreamError`) **[P]**. Die Prüfung „unverändert“
  kostet damit eine Anfrage ohne Rumpf.
- 26 450 Zeilen, **CRLF**-Zeilenenden, keine Doppel. Jede Zeile passt auf
  `Copernicus_DSM_COG_10_[NS]dd_00_[EW]ddd_00_DEM`. Breiten S90 bis N83, Längen
  W180 bis E179; es gibt `S01`, aber kein `S00`, und kein `W000`.

### 2.2 Abgleich mit dem Bucket-Listing — **[M]**

`ListObjectsV2` mit `delimiter=/` und `max-keys=1000`: **27 Anfragen, 45 s**
(gedrosselt), 26 450 Präfixe. Liste und Listing sind **deckungsgleich** (0 nur in
der Liste, 0 nur im Bucket). Im Wurzelverzeichnis liegen außerdem:

- **`blacklist.txt`** (25 Zeilen): genau die 25 fehlenden Kacheln aus
  `adr/0009` §10.3 (N38–N41, E043–E050). Die Quelle führt die Lücke also selbst.
- **`geometry.txt`**: ein WKT-Polygon, die Erde mit dieser Lücke als Loch.
- `readme.html`, `tileList.txt`.

Die Registry-Seite bei AWS verweist für die Lücke auf eine Liste des
Copernicus-Programms („not yet released to the public“) **[P]**.

Ein Präfix enthält 16 Objekte, darunter den DEM-COG
`<name>/<name>.tif` und eine Metadaten-XML (gemessen an `N46_00_E010_00`). Die
Vorschau liegt als TIFF vor (`PREVIEW/…_DEM_QL.tif`, 1,5 MB), nicht als PNG oder
JPEG.

### 2.3 Kachelgrenzen und Pixel — **[M]/[P]**

Sechs Kacheln geöffnet (Äquator, Himalaya, Totes Meer, Alpen, N80, S90):

- Pixel-is-point (`AREA_OR_POINT=Point`); die Mitte des Eckpixels liegt auf der
  ganzen Gradzahl **[M]**, wie im Handbook §1.2.2 beschrieben **[P]**. Der Name
  nennt die **Südwestecke**; die Datei reicht um ein halbes Pixel nach Westen und
  Norden darüber hinaus (z. B. `N46_00_E010_00`: 9,999861 bis 10,999861 O,
  46,000139 bis 47,000139 N).
- Die Pixelbreite in Länge wächst polwärts: 3600 px bis 50°, bei N80 720 px, bei
  S90 360 px. Die Datei von S90/W180 beginnt deshalb bei −180,0014, also jenseits
  der Datumsgrenze.
- `float32`, EPSG:4326, Overviews 2/4/8, **kein `nodata`** im Header.
  Das Handbook nennt einen NoData-Wert −32 767 für Pixel ohne Höhe **[P]**; in
  den sechs Kacheln kam er nicht vor **[M]**.

### 2.4 Wertebereich — **[M]**

Aus der gröbsten Overview je Kachel (p2 / p98, min / max, in m):

| Kachel | p2 | p98 | min | max |
|---|---|---|---|---|
| N00 E006 (Gabun, Küste) | 0 | 440 | 0 | 1 934 |
| N27 E086 (Himalaya) | 409 | 5 907 | 190 | 8 669 |
| N31 E035 (Totes Meer) | −427 | 1 053 | −427 | 1 291 |
| N46 E010 (Alpen) | 627 | 3 154 | 235 | 3 850 |
| N80 E020 (Svalbard) | 0 | 563 | 0 | 617 |
| S90 W180 (Antarktis) | 2 832 | 2 996 | 2 829 | 3 000 |

Meeresflächen innerhalb von Küstenkacheln haben den Wert 0.

### 2.5 Kachelkosten — **[M]**

rio-tiler, Kachel über `N46_00_E010_00`, GDAL-Standardeinstellungen, kalt:

| Zoom | Dauer | Anfragen | übertragen |
|---|---|---|---|
| z8 | 1,39 s | 1 HEAD + 2 GET | 0,62 MB |
| z12 | 1,34 s | 1 HEAD + 2 GET | 2,49 MB |

Das deckt sich mit `adr/0009` §3.1 (z8 1,05 s, 0,59 MB). Die native Auflösung
von 1″ (rund 30 m) entspricht etwa z12 am Äquator (38 m/px).

### 2.6 Zeitangaben — **[M]/[P]**

Aufnahmezeitraum aus der Metadaten-XML von sechs weiteren Kacheln (dazu die aus
`adr/0009` §10.1):

| Kachel | Beginn | Ende |
|---|---|---|
| N00 E006 (`adr/0009`) | 2011-07-30 | 2013-09-20 |
| N27 E086 | 2011-01-05 | 2014-09-08 |
| N40 W106 | 2011-03-13 | 2014-08-29 |
| N46 E010 | 2011-05-17 | 2014-08-17 |
| N64 W020 | 2011-03-01 | 2012-09-01 |
| S04 W061 | 2011-02-02 | 2013-05-07 |
| S34 E018 | 2011-03-27 | 2014-01-18 |

Das **Product Handbook** (Fassung 5.0, 29.11.2022, S. 30) sagt: „the
TanDEM-X/WorldDEM has been acquired between December 2010 and January 2015“
**[P]**. S. 28 nennt „time frame of data acquisition (2011-2015)“ **[P]**. Die
CDSE-Seite rät, für Füllquellen bis 2001 zurückzusuchen **[P]** — Lücken sind mit
älteren Modellen gefüllt (SRTM, ASTER u. a.). Welchem Release (2019_1 bis
2024_1) der Stand des AWS-Buckets vom 09.05.2022 entspricht, ist **unbelegt**.

### 2.7 DOI — **[P]**

Die CDSE-Seite zu COP-DEM (dieselbe, auf die `adr/0003` §11.1 die Lizenz
zurückführt) nennt als Zitier-DOI `https://doi.org/10.5270/ESA-c5d3d65`, für
das Produkt, nicht für eine Instanz. `doi.org` selbst ist aus der Sitzung
gesperrt; die Auflösung ist nicht geprüft.

---

## 3. Vorgeschlagene Umsetzung

### 3.1 Adapter `adapters/cop_dem_bucket.py`

- Neuer `AdapterKind.COP_DEM_BUCKET = "cop-dem-bucket"`.
- Der Adapter **erzeugt** Items; er sucht nicht. Er steht deshalb **nicht** in
  `adapters._ADAPTERS` (Such- und Abruf-Dispatch), sondern in einer zweiten,
  kleinen Tabelle `_MATERIALIZERS` mit einer Funktion
  `adapters.materialize_items(config, *, gateway, known_version)`. So bleibt
  `test_every_adapter_supports_intersects_and_ids` unberührt, und
  `_adapter_for` weist den DEM weiter mit `UnsupportedSource` ab (M3-11a).
- Ablauf, alles über `gateway`:
  1. `GET tileList.txt` mit `If-None-Match: <known_version>`. Antwort `304` →
     Ergebnis „unverändert“, sonst die Liste und ihre neue ETag.
  2. `GET blacklist.txt`.
  3. Bucket-Listing mit `delimiter=/`, seitenweise (27 Anfragen, §2.2).
  4. Abgleich (§3.2), dann je gültiger Zeile ein Item (§3.3).
- Rückgabe: Items (als Generator), neue ETag und ein Bericht mit Zahlen
  (gelistet, im Bucket, fehlend, zurückgehalten, unbekannt).
- Parser streng: eine Zeile, die nicht auf das Namensschema passt, ist ein
  Fehler des ganzen Laufs, kein stilles Überspringen.

### 3.2 Fehlende Dateien erkennen (→ F2)

Dem Listing nicht blind glauben (`adr/0009` §11), ohne 26 450 Anfragen:

- **Liste gegen Listing der Präfixe** (27 Anfragen). Eine Kachel aus der Liste
  ohne Präfix im Bucket wird **nicht** geladen und im Bericht gezählt.
- **Liste gegen `blacklist.txt`.** Eine zurückgehaltene Kachel, die trotzdem in
  der Liste steht, wird nicht geladen und gezählt.
- Präfixe im Bucket, die nicht in der Liste stehen, werden gezählt, aber nicht
  geladen: Die Liste ist die Freigabe der Quelle.
- **Abbruch ohne Schreiben**, wenn das Listing leer ist oder mehr als 1 % der
  Liste fehlt. Dann stimmt eher der Lauf nicht als die Quelle.

Nicht geprüft wird damit, dass in einem vorhandenen Präfix auch die `.tif`
liegt. Dafür bräuchte es das volle Listing ohne `delimiter` (rund 420 Anfragen,
16 Objekte je Kachel **[A]**). Fehlt die Datei doch, antwortet die Kachelroute für
genau dieses Item mit einem Fehler (wie heute bei einer nicht lesbaren Quelle).

### 3.3 Form der Items (→ F1, F3)

| Feld | Wert | Begründung |
|---|---|---|
| `id` | Kachelname, z. B. `Copernicus_DSM_COG_10_N46_00_E010_00_DEM` | stabil, eindeutig; `upsert` braucht stabile IDs (`adr/0009` §7.3) |
| `collection` | `cop-dem-glo-30` | = `dataset_id` (F4) |
| `geometry`, `bbox` | die **nominelle** 1°-Zelle aus dem Namen (Südwestecke + 1°) | Die Datei reicht ein halbes Pixel darüber hinaus (§2.3). Die Zelle ist unter einem Pixel ungenau, bleibt aber diesseits der Datumsgrenze und fügt sich für die Coverage in M3-11c lückenlos zusammen. Die Reader lesen die echten Grenzen aus der Datei. |
| `properties.datetime` | nach F1 | |
| `properties.start_datetime` / `end_datetime` | nach F1 | |
| `properties.gsd` | `30` | Nennauflösung; die Download-Schätzung (M3-18) braucht einen Wert, sonst greift ihr Worst Case |
| `properties.proj:code` | `EPSG:4326` | gemessen (§2.3) |
| `assets.data` | `href` `https://copernicus-dem-30m.s3.amazonaws.com/<name>/<name>.tif`, Typ COG, Rolle `data` | Host = `asset_hosts` |
| Vorschau-Asset | keins | Die Vorschau der Quelle ist ein TIFF (§2.2), das ein Browser nicht zeigt. Quicklooks für den DEM sind M3-12. |

### 3.4 Einmal-Befehl `python -m earthx.discovery.materialize <dataset_id>`

- Weist einen Datensatz ab, der nicht `materialized` ist.
- Liest die ETag des letzten erfolgreichen Laufs (§3.5) und gibt sie dem Adapter.
- Bei „unverändert“: Lauf als `unchanged` protokollieren, Ausgabe, Ende mit 0.
  `--force` lädt trotzdem.
- Sonst **eine Transaktion**: `catalog.upsert_items` (M3-11a), dann
  `catalog.delete_items_except(conn, config, keep_ids)` (neu, für entfallene
  Kacheln — das „delsert“ aus `adr/0009` §7.3), dann der Protokolleintrag, dann
  `commit`. Bricht etwas ab, bleibt die Datenbank wie vorher.
- Gateway-Policy: Endpunkt-Host plus `asset_hosts`, wie bei den anderen
  Adaptern. Kein Zeitplan, keine Review-Queue (M5).
- Ausgabe: Zahlen und ETag, keine Koordinaten.
- `discovery` importiert `adapters`, `catalog` und `gateway` — erlaubt laut
  `.importlinter`.

### 3.5 Protokoll der Läufe (→ F5)

M3-11a F3 hat das offengelassen (Vorschlag dort: eigene Tabelle).

- Migration `catalog/migrations/004_materialize_runs.sql`:
  `public.earthx_materialize_runs` mit `dataset_id`, `started_at`,
  `finished_at`, `status` (`loaded` | `unchanged`), `source_version` (ETag),
  `items_written`, `items_deleted`, `listed`, `missing`, `withheld`.
- In `catalog/`: `last_source_version(conn, dataset_id)` und
  `record_materialize_run(conn, …)`.
- Fehlgeschlagene Läufe werden nicht eingetragen (die Transaktion rollt zurück);
  sie melden sich mit Exit-Code 1 und einer Zeile auf `stderr`.
- `SourceInfo.harvest_run` bleibt `None`, auch beim DEM. Ob das Feld entfällt,
  klärt M3-14.

### 3.6 Registry-Eintrag `COP_DEM_GLO_30` (→ F1, F4, F6, F7)

| Feld | Vorschlag | Quelle |
|---|---|---|
| `dataset_id` | `cop-dem-glo-30` | gängiger Name (Earth Search, Planetary Computer); keine Kollision, weil nicht föderiert |
| `title` | `Copernicus DEM GLO-30` | |
| `description` | siehe unten | |
| `doi` | `https://doi.org/10.5270/ESA-c5d3d65` | §2.7 |
| `data_class` | `RASTER_STATIC` | P24 |
| `format` | `COG` | §2.3, `adr/0009` §3.1 |
| `spatial_extent` | `(-180, -90, 180, 84)` | aus der Liste (S90 bis N83) |
| `temporal_extent` | nach F1 | |
| `capabilities` | `roi`, `band_math`, `interpolation`, `ml_processing` `True`; `time_range` **`False`** (keine Zeitachse); `quad_pol` `False`; `single_coverage_product` `True` | B10; `adr/0009` §6 |
| `license` | wie `adr/0003` §11.1: kein SPDX, Name „Licence for Copernicus DEM instance COP-DEM-GLO-30-F Global 30m Full, Free & Open“, URL des PDFs, alle Flags `True` außer `share_alike`, Stufe `PROCESSING`; Attribution unverändert „© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved“, bearbeitet mit dem Zusatz „produced using Copernicus WorldDEM-30“ (Art. 6 b); `terms` mit dem Haftungssatz aus Art. 6 c | `adr/0003` §11.1 |
| `access` | geprüft am 26.09.2026, `cors=False` (kein `Access-Control-Allow-Origin`, `adr/0009` §3.1) | |
| `source` | Adapter `cop-dem-bucket`, Endpunkt `https://copernicus-dem-30m.s3.amazonaws.com`, `source_collection_id` `copernicus-dem-30m` (Bucket-Name, weil es keine Collection gibt), `asset_hosts` genau `("copernicus-dem-30m.s3.amazonaws.com",)`, `harvest_run=None`, `item_holding=MATERIALIZED` | `adr/0009` §10.2 |
| `coverage` | `LOCAL_SQL`, `typical_footprint_km=111`, `max_geotile_level=8` (= `max_geotile_level_for(111)`) | M3-11a verlangt `local-sql` für `materialized` |
| `default_render` | nach F6 | |
| `viewer` | nach F7 | |
| `health` | `OK` | |
| `maturity` | `STABLE` | statisches Produkt |
| `zarr` | `None` | |

**Beschreibung (Entwurf, Englisch):**

> Copernicus DEM GLO-30 Public: global 30 m digital surface model from the
> TanDEM-X mission (acquired December 2010 to January 2015), as
> cloud-optimized GeoTIFF in 1° × 1° tiles, read from the AWS Open Data bucket
> (state of 9 May 2022). Oceans have no tiles, and 25 tiles between 38° and
> 42° N and 43° and 51° E are withheld from public release by the Copernicus
> programme.

Den Wortlaut der Lizenz-Hinweise und des Haftungssatzes übernehme ich beim
Umsetzen aus dem PDF (Art. 6 a–c) und prüfe ihn dort am Primärdokument.

### 3.7 Lokaler Start (→ F8)

- Lokal: `python -m earthx.discovery.materialize cop-dem-glo-30` mit den
  `PG*`-Variablen, nach `catalog.load`.
- Compose: ein Dienst `materialize` unter `profiles: ["materialize"]`, gleiche
  Umgebung wie `catalog-load`. `docker compose up` startet ihn **nicht**; Start
  mit `docker compose run --rm materialize cop-dem-glo-30`. So berührt die CI
  (`docker compose up` im Job `compose-topology`) die Quelle nie.
- README: ein Abschnitt dazu.

---

## 4. Onboarding-Checkliste

| Punkt | für den DEM |
|---|---|
| 1 Beschreibung | §3.6 |
| 2 Coverage | `single_coverage_product` → Ausdehnung; zählt in `test_onboarding_checklist.py` ohne Befund. Bis M3-11c antwortet die Route mit der `bbox` der Collection, also global ohne Lücken (§7) |
| 3 DOI | §2.7 |
| 4 Lizenz | wie `adr/0003` §11.1, mit `terms` |
| 5 Format | COG |
| 6 Zugriff | 26.09.2026, `curl` |
| 7 Klasse, Flags | §3.6 |
| 8 Visualisierung | F6 |
| 9 End-to-End | F9 |
| 10 T-D-Smoke | neues `backend/tests_live/test_cop_dem_smoke.py`: bedingter Abruf von `tileList.txt` (ETag unverändert → `304`), eine Seite Listing, ein Range-Read auf eine Kachel; zusammen drei Anfragen. Der Marker reicht der Checkliste; **laufen** würde der Smoke erst mit einem Eintrag in `.github/workflows/live-smoke.yml` (F10) |

---

## 5. Tests

Alle Fixtures synthetisch. Eine synthetische `tileList.txt` (CRLF), eine
`blacklist.txt`, XML-Seiten eines Listings und ein kleiner `float32`-COG in
EPSG:4326 mit Pixel-is-point und ohne `nodata` (neu, `mini_dem.py` neben
`mini_cog.py`), alle über `httpx.MockTransport` bzw. den Speicher-Resolver.

**Einheit (T-A):**
- Namensparser: Südwestecke für alle vier Quadranten, `S90`/`W180`,
  CRLF und Leerzeilen am Ende; falscher Name → Fehler; Breite/Länge außerhalb
  des Bereichs → Fehler.
- Item: Geometrie, `bbox`, `href` auf dem Host aus `asset_hosts`,
  Zeitfelder nach F1, pgstac-taugliche Zeitangabe.
- Abgleich: fehlender Präfix, zurückgehaltene Kachel, überzählige Präfixe;
  leeres Listing und über 1 % fehlend → Abbruch; Seitenwechsel mit
  `NextContinuationToken`.
- `304` → „unverändert“, ohne weitere Anfrage.
- Quelle antwortet `403`/`500` bzw. kaputtes XML → Fehler, nichts geschrieben.
- `_adapter_for` weist den DEM weiter ab; `materialize_items` weist einen
  föderierten Eintrag ab.
- Registry: der Eintrag besteht alle `__post_init__`-Regeln; `asset_hosts` ist
  genau der eine Host (nie `s3.amazonaws.com` oder `amazonaws.com`).
- Kein Request außerhalb von `gateway` (bestehende Syntaxbaum-Prüfung plus
  `lint-imports`).

**Integration (T-C, echtes pgstac):**
- Befehl lädt die synthetischen Kacheln vollständig; zweiter Lauf mit gleicher
  ETag → `unchanged`, keine Schreibvorgänge; `--force` → gleiche Anzahl, keine
  Doppel.
- Entfallene Kachel in einer neuen Liste → aus pgstac gelöscht.
- Abbruch mitten im Schreiben → Datenbank unverändert, kein Protokolleintrag.
- Föderierter Datensatz → abgewiesen.
- `/stac/search` mit `collections=["cop-dem-glo-30"]` und `bbox` findet genau die
  Kacheln der Box; eine Kachel und ein Zuschnitt über die echte Item-Quelle aus
  pgstac (M3-11a).

**Checkliste:** alle bestehenden Checklisten-Tests grün für drei Einträge.

---

## 6. Nicht in dieser Aufgabe

- `readers` (unverändert)
- die Coverage-Route und `local-sql` (M3-11c)
- Frontend (M3-12): Zeitleiste, Gruppierung und Datumsfilter für einen
  Datensatz ohne Zeitachse, Quicklooks
- gemischte Suche (M3-13)
- Zeitplan, Review-Queue, Harvester-Prozess (M5)
- `.github/` ohne Freigabe (F10)

---

## 7. Übergang

- Bestehende Datenbanken brauchen `catalog.load` (neue Collection, Migration
  004) und danach einmal den Befehl.
- Bis M3-11c gemergt ist, zeigt die Coverage des DEM die globale `bbox`, also
  auch Meere und die Lücke als abgedeckt — genau das, was `adr/0009` F5
  ausschließt. M3-11c ersetzt das; die Reihenfolge der Merges regelt F11.
- Solange M3-12 fehlt, sendet der Viewer bei jeder Suche einen Zeitraum mit. Ob
  der DEM dann erscheint, hängt an F1 (§8).

---

## 8. Zur Zeitangabe (F1)

pgstac verlangt einen Zeitraum je Item (`adr/0009` §10.1). Wie ein Datumsfilter
wirkt: pgstac findet ein Item, wenn sich sein Zeitraum mit dem gesuchten
überschneidet **[A]**.

| Option | Items | Folge für eine Suche nach 2024 |
|---|---|---|
| 1 | je Kachel aus ihrer XML | fällt heraus; kostet 26 450 Anfragen (rund 1,2 GB) beim ersten Laden, danach nur bei neuer ETag |
| 2 | `datetime: null`, ein Zeitraum für alle: 2010-12-01 bis 2015-01-31 (Handbook, §2.6) | fällt heraus |
| 3 | ein fester `datetime` für alle | fällt heraus, außer das Datum liegt zufällig im Suchzeitraum |

Keine Option lässt den DEM bei einer Suche nach 2024 erscheinen. Das ist fachlich
richtig (die Daten sind von 2010 bis 2015), für einen Nutzer aber überraschend.
Der saubere Weg liegt im Viewer bzw. in der Suche: Ein Datensatz mit
`capabilities.time_range = False` bekommt keinen Datumsfilter. Das gehört zu
M3-12 bzw. M3-13 und wird hier nur vorgeschlagen, nicht gebaut.

---

## 9. Fragen an Otto

**F1 — Zeitangabe der Items** (§8)
1. `datetime: null`, `start_datetime` 2010-12-01T00:00:00Z, `end_datetime`
   2015-01-31T23:59:59Z für alle Kacheln und die Collection; belegt am Handbook
   (S. 30). Dazu `time_range = False` und als Vorschlag für M3-12/M3-13: kein
   Datumsfilter für Datensätze ohne Zeitachse. **(Empfehlung)**
2. Zeitraum je Kachel aus der XML (genau, 26 450 Anfragen beim ersten Laden).
3. Ein fester `datetime` für alle (einfach, ohne belegte Bedeutung).

**F2 — Fehlende Dateien** (§3.2)
1. Liste gegen Präfix-Listing (27 Anfragen) und gegen `blacklist.txt`;
   Abbruch bei leerem Listing oder über 1 % fehlend. **(Empfehlung)**
2. Volles Objekt-Listing (rund 420 Anfragen), prüft jede `.tif` samt Größe.
3. Wie 1, dazu je Lauf ein Range-Read auf 20 zufällige Kacheln.

**F3 — Geometrie der Items** (§3.3)
1. Nominelle 1°-Zelle aus dem Namen. **(Empfehlung)**
2. Exakte Dateigrenzen mit halbem Pixel Überstand (Breite je Breitenband),
   mit Sonderfall an der Datumsgrenze.

**F4 — `dataset_id`**
1. `cop-dem-glo-30`. **(Empfehlung)**
2. `copernicus-dem-glo-30`

**F5 — Protokoll der Läufe** (§3.5)
1. Eigene Tabelle `public.earthx_materialize_runs` per Migration; ETag des
   letzten erfolgreichen Laufs von dort. **(Empfehlung)**
2. Kein Protokoll; die ETag steht nur in der Ausgabe, jeder Lauf lädt voll.
   (Erfüllt die Aufgabe „erkennt eine unveränderte Quelle“ nicht.)

**F6 — Darstellung** (`default_render`, §2.4)
1. Asset `data`, Colormap `terrain`, `rescale` 0 bis 5 000 m, `nearest`.
   `terrain` färbt 0 m als Wasser (Meer in Küstenkacheln) und oben Weiß (Schnee);
   über 5 000 m sättigt es. Beides ist schon in der Colormap-Liste des Viewers.
   **(Empfehlung)**
2. `gist_earth`, `rescale` −500 bis 9 000 m (ganzer Bereich, dafür flach).
3. Graustufen, `rescale` 0 bis 5 000 m.

Hinweis für M3-12: `/statistics` streckt heute je Item. Nebeneinander liegende
DEM-Kacheln bekämen dann verschiedene Streckungen und sichtbare Kanten.

**F7 — `viewer`**
1. `group_by = ("start_datetime",)`: alle Kacheln bilden eine Gruppe, der
   Zuschnitt über mehrere Kacheln wird eine Datei (P19). `min_zoom = 8` (eine
   Kachel ist rund eine z8-Kachel breit; darunter ist es Sache der Coverage,
   wie bei EOPF), `max_zoom = 15` (drei Stufen über der nativen Auflösung, zum
   Hineinzoomen). **(Empfehlung, bei F1 Option 1)**
2. wie 1, aber `min_zoom = 0` wie Sentinel-2 COG (eine Item-Kachel liest nur
   die gröbste Overview; teuer wird es erst im Viewer, der dann viele Items
   gleichzeitig kachelt).
3. Bei F1 Option 3: `group_by = ("datetime",)`.

**F8 — Start in Compose** (§3.7)
1. Dienst `materialize` unter einem Compose-Profil, Start von Hand mit
   `docker compose run`. **(Empfehlung)**
2. Nur lokal mit `python -m …`, kein Compose-Dienst.
3. Bei jedem `docker compose up` nach `catalog-load` (billig wegen ETag, aber
   die CI würde dann die echte Quelle anfragen).

**F9 — Checklisten-Punkt 9 für eine materialisierte Quelle**
`test_onboarding_endtoend.py` sucht über `adapters.search_items`, das einen
materialisierten Datensatz abweist (M3-11a).
1. Für materialisierte Einträge heißt Glied 1 „Erzeugung“: Items kommen aus dem
   Adapter des Eintrags gegen die synthetische Quelle, Anzeige und Zuschnitt
   bleiben wie heute ohne Datenbank. Die Suche über pgstac prüft der
   T-C-Test aus §5. **(Empfehlung)**
2. Punkt 9 für materialisierte Einträge gegen ein echtes pgstac (die Checkliste
   hinge dann an einer laufenden Datenbank).

**F10 — Live-Smoke in der CI** (`.github/`)
1. In `.github/workflows/live-smoke.yml` einen Schritt für
   `test_cop_dem_smoke.py` ergänzen (drei Anfragen je Lauf). Das braucht deine
   Freigabe, weil `.github/` sonst tabu ist. **(Empfehlung)**
2. Nur den Test anlegen; den Workflow ergänzt du selbst.

**F11 — Schnitt und Reihenfolge**
Geschätzt rund 500 Zeilen Code, Migration, Registry und Doku, rund 550 Zeilen
Tests **[A]**, also weit über dem Richtwert von 400.
1. Ein PR, mit dem Registry-Eintrag; Merge erst nach M3-11c, damit die Coverage
   nie die globale `bbox` zeigt. **(Empfehlung)**
2. Zwei PRs: (a) Adapter, Befehl, `catalog`, Migration, getestet mit einem
   synthetischen Eintrag; (b) Registry-Eintrag, Checkliste, Smoke, README.
3. Ein PR, Merge unabhängig von M3-11c; die globale `bbox` gilt bis dahin.
