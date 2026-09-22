# M2-09b — Zweiter Datensatz im Katalog: Umsetzungsplan

**Status:** **Entwurf, wartet auf Ottos Freigabe.** Stufe B laut `projektplan.md`
1.2: zuerst dieser Plan als Draft-PR, Umsetzung erst nach dem OK. Die Fragen
stehen gesammelt in §10; ohne ihre Antworten wird kein Produktivcode
geschrieben.
**Aufgabe:** M2-09b aus `docs/plans/m2-format-und-viewer.md`.
**Grundlage:** `adr/0007` §6, §7 und besonders §12 (Nachmessung), mit den
fünfzehn Umsetzungspunkten in §12.11; `adr/0004` §5 (Anbieter-Begriff, Regel V,
Option 6); `adr/0005` Regel I–VI (Katalog entscheidet, eigene Seitenmarke,
eigener Deckel); `adr/0006` §3.3 und §5 (`asset_hosts`, Standard-Visualisierung);
`architekturplan.md` 3.1 (Modulgrenzen), 5.1 (die `earthx:`-Felder), 5.2
(zweistufiger Katalog), 6.1 (Adapter-Fähigkeiten); `KLAERUNGEN.md` B8, B10, B11,
B12, B13; `projektuebersicht.md` §5 (Onboarding-Checkliste);
`ENTSCHEIDUNGSLOG.md` 2026-09-20 (Umsetzungsauflagen M2-09b) und 2026-09-22
(M2-09a umgesetzt, vier Sitzungssetzungen).
**Voraussetzungen:** erfüllt. M2-03b (Nachmessung, `adr/0007` §12), M2-04
(`asset_hosts` fließt in die Allowlist, `earthx:viewer`, Kachelroute), M2-09a
(`readers/zarr_reader.py`, Dispatch über `format` in `api/tiler.py`).

---

## 1. Ziel in einem Satz

`sentinel-2-l2a-zarr3` steht als zweiter Datensatz in Registry und Katalog, ist
über die föderierte Suche erreichbar, und Kachel, Statistik und Zuschnitt lesen
ihn über denselben Zarr-Lesepfad, den M2-09a gegen das synthetische Mini-Zarr
gebaut hat.

---

## 2. Ausgangslage: was schon steht und was fehlt

| Baustein | Stand |
|---|---|
| `DataFormat.ZARR`, `CoverageProvider.SAMPLE` | vorhanden (M1-04) |
| `SourceInfo.asset_hosts` → Gateway-Allowlist | vorhanden (M2-04, `api/dependencies.py::policy_from_registry`) |
| Zarr-Lesepfad (`GatewayStore` → `zarr` → `xarray` → `XarrayReader`) | vorhanden (M2-09a) |
| Dispatch Kachel/Statistik/Zuschnitt über `format` | vorhanden (`api/tiler.py::_resolve_asset_path`) |
| Registry-Eintrag für `…-zarr3` | **fehlt** |
| Adapter für die EOPF-STAC-API | **fehlt** — `AdapterKind` kennt nur `EARTH_SEARCH_V1` |
| Normalisierung STAC 1.1 → 1.0 | **fehlt** |
| Stufenwahl aus `multiscales` im Store | **fehlt** — der Reader öffnet die Gruppe, die das Asset nennt |
| Bandwahl innerhalb einer Auflösungsgruppe | **fehlt** — siehe §4.2, das ist der schärfste Befund dieses Plans |
| Ausgewiesene Stichprobe als Coverage-Anbieter | **fehlt** — `api/coverage_route.py` antwortet für `SAMPLE` heute `501` und verweist wörtlich auf M2-09b |
| Feld für den Status „staging" | **fehlt** (`adr/0007` §12.11 Punkt 14) |

---

## 3. Was in dieser Sitzung gegen die echte Quelle nachgesehen wurde

Nur lesend, über `curl` und `python3` im Kratzverzeichnis, ohne Produktivcode und
ohne eine Abhängigkeit zu ändern. Rund zehn Anfragen, davon eine über 0,5 MB (die
konsolidierte Wurzel eines Stores). Kein Produkt heruntergeladen. Zweck: prüfen,
ob die Messung aus `adr/0007` §12 zwei Tage später noch trägt, und die zwei
Stellen schließen, die §12 offengelassen hat (Asset-Adressierung, Bandbestand je
Stufe).

### 3.1 Die Quelle lebt, und §12 trägt unverändert — **[M]**

| Befund | Messung (22.09.2026) | gegen `adr/0007` §12 |
|---|---|---|
| `stac.core.eopf.eodc.eu`, `data.eodc.eu` | beide `200` | unverändert |
| Titel der Collection | „Sentinel-2 Level-2A (Zarr3 **staging**)" | unverändert (§12.6) |
| `stac_version` der Collection | `1.1.0` bei `license: proprietary` | unverändert (§12.6) |
| `extent.spatial` | −33,00 … 179,58 / **34,21 … 72,10** | unverändert |
| `extent.temporal` | 2026-07-16T10:06:01Z bis 2026-09-20T13:48:41Z | Ende wandert mit, Anfang fest |
| Assets je Item | dieselben zehn, `zipped_product` auf `data.eodc.eu` | unverändert (§12.1) |
| Rollen | `data`, `reflectance`, `atmosphere`, `mask`, `metadata`, `archive` | **kein** `thumbnail`/`preview`/`visual` (§12.7) |
| `multiscales` an `measurements/reflectance` | sechs Stufen `r10m`…`r720m`, je mit `spatial:shape` und `spatial:transform` | unverändert (§12.3) |
| Sharding | `chunk_shape` 11264², Innenchunk 1024², `blosc`/`zstd` | unverändert (§12.3) |
| CRS im Store | `spatial_ref` mit `crs_wkt` je Stufe, `grid_mapping` an jedem Band | unverändert (§12.3) |

### 3.2 Neu: das Asset zeigt auf eine **Gruppe**, nicht auf eine Variable — **[M]**

Gemessen an `S2A_MSIL2A_20260921T141821_N0513_R096_T26WME_20260921T222815`:

```
SR_10m  href  …/<produkt>.zarr/measurements/reflectance/r10m
        zarr:node_type = "group",  gsd 10,  proj:shape [10980, 10980],
        bands = [b02, b03, b04, b08]
SR_20m  href  …/<produkt>.zarr/measurements/reflectance/r20m   bands: 10 Stück
product href  …/<produkt>.zarr                                  (zarr:consolidated)
zipped_product  href  …/<produkt>.zarr.zip
```

**Das bricht die Adressregel aus M2-09a.** `split_asset_href` liest das letzte
Pfadsegment als Variable; hier ist das letzte Segment `r10m` und damit die
Auflösungsgruppe. Der Reader würde nach einer Variablen `r10m` in der Gruppe
`measurements/reflectance` suchen und mit `UnknownVariable` abbrechen. Die Regel
war für den EOPF-**v2**-Bestand richtig (`…/quality/l2a_quicklook/r10m/tci`, ein
Array am Ende) und ist für die v3-Collection falsch. Das ist genau das
Registry-Feld, das `adr/0007` §7 Punkt 7 in Aussicht gestellt und der
Entscheidungslog vom 22.09.2026 offengelassen hat („M2-09b kann die Regel dadurch
ersetzen, muss es aber nicht") — es **muss** jetzt. Fragen dazu: §10 F2.

`zipped_product` scheitert an derselben Regel von selbst (kein Segment auf
`.zarr`, das letzte heißt `.zarr.zip`) — das ersetzt die Auflage aus §12.11
Punkt 10 aber nicht: das Asset bleibt aus dem Registry-Eintrag heraus.

### 3.3 Neu: der Bandbestand hängt an der Auflösungsstufe — **[M]**

| Stufe | Variablen (ohne `x`, `y`, `spatial_ref`) |
|---|---|
| `r10m` | b02, b03, b04, b08 |
| `r20m` | b01, b02, b03, b04, b05, b06, b07, b08, b8a, b11, b12 |
| `r60m` … `r720m` | alle zwölf |

Für die Echtfarb-Darstellung (b04, b03, b02) ist das folgenlos — die drei liegen
auf **jeder** Stufe. Für die Stufenwahl heißt es: die gröberen Stufen sind
band-reicher, nicht band-ärmer; ein Wechsel nach oben verliert nie das Band.

### 3.4 Neu: die Bänder sind skaliert — **[M]**

`b04` trägt `scale_factor = 0.0001`, `add_offset = -0.1`, `_FillValue = 0`,
`dtype <u2`, `valid_min 1`, `valid_max 65535`. `xarray.open_zarr` wendet beides
standardmäßig an (`mask_and_scale`), der Reader liefert also **Reflexionsgrad als
Fließkommazahl**, nicht rohe Zähler. Der Streckbereich der Standard-Visualisierung
ist damit ein anderer als bei Sentinel-2 über Earth Search, wo `visual` bereits
8-Bit-RGB ist. Vorschlag in §4.5, Frage in §10 F6.

---

## 4. Was neu entsteht, Modul für Modul

Die Modulgrenzen aus `architekturplan.md` 3.1 bleiben unangetastet: Protokollwissen
über die Quelle nach `adapters`, Registry und Nahtstellen nach `catalog`, der
Lesepfad nach `readers`, der Prozess-Einstieg nach `api`. Nichts davon lockert eine
Importregel.

### 4.1 `catalog` — Registry-Eintrag und zwei neue Felder

**Der Eintrag** `SENTINEL_2_L2A_ZARR3` in `catalog/datasets.py`, mit allen
Capability-Flags (B10), Lizenzfeldern wie beim ersten Datensatz (D18 — dieselbe
Sentinel Data Legal Notice, gemessen als `cite-as`- und `license`-Link der
Collection), `asset_hosts = ("data.eodc.eu",)` (§12.11 Punkt 5),
`AccessInfo.cors = True` (§12.11 Punkt 4), `format = DataFormat.ZARR`,
`coverage.provider = CoverageProvider.SAMPLE` (§12.11 Punkt 13), Extents aus der
Collection (§3.1), `viewer = ViewerInfo(group_by=("datetime", "grid:code"))` —
`grid:code` steht am Item als `MGRS-26WME` (§3.2), der Schlüssel ist also derselbe
wie beim ersten Datensatz und `group_key` bleibt unverändert.

**Neu: `maturity`.** Der Status „staging" ist eine Auflage (§12.11 Punkt 14) und
hat heute kein Feld. Vorschlag: ein Enum `Maturity` (`STABLE`, `STAGING`,
`EXPERIMENTAL`) ohne Vorgabewert an `DatasetConfig`, gespiegelt in
`collection.to_stac_collection`. Wohin es in `architekturplan.md` 5.1 gehört,
ist eine Architekturfrage — §10 F4.

**Neu: `ZarrInfo`.** Was der Reader über den Aufbau dieses Stores wissen muss und
heute als Regel in `readers/zarr_reader.py` steht: wie eine Variable adressiert
wird, wo `multiscales` hängt, dass die Konvention eine v0.1-Pilotfassung ist
(§12.11 Punkt 2 verlangt den Vermerk ausdrücklich). Form: §10 F2.

**Zu prüfen ist der Eintrag, nicht nur zu schreiben.** `tests/catalog/test_registry.py`
führt eine Klasse, die **jeden** Eintrag der Registry durchgeht; sie greift für den
neuen automatisch. Dazu ein Test wie `test_sentinel_2_l2a.py` für den neuen Eintrag.

### 4.2 `adapters` — ein zweiter Adapter, und die Normalisierung

Die EOPF-STAC-API ist nicht Earth Search: andere Seitenmarke, kein
`numberMatched`, keine Aggregation, STAC 1.1. `AdapterKind` bekommt
`EOPF_STAC_V1`, und `adapters/eopf_stac.py` bekommt `search_items` und `get_item`
mit **derselben** Signatur wie `earth_search.py` — die föderierte Suche ruft
danach über eine kleine Dispatch-Tabelle statt direkt (`adapters/__init__.py`
exportiert heute `earth_search.search_items` unter dem generischen Namen; das ist
die eine Stelle, die sich ändert).

**Was der Adapter mitbringt, und was er von Earth Search erbt:** Die Regeln aus
`adr/0005` sind quellenunabhängig formuliert und gelten weiter — Regel I (unser
Katalog entscheidet über die Existenz), Regel III (unsere eigene Seitenmarke, die
fremde verlässt das Modul nie), Regel V (eigener `limit`-Deckel). Die
Eingabeprüfungen (`SearchParams`) und die Seitenmarken-Kodierung sind bereits
quellenunabhängig und werden geteilt, nicht kopiert. Quellenspezifisch sind nur:
der Aufbau des Suchkörpers, das Lesen der `next`-Marke und die Normalisierung.

**Die Normalisierung** setzt `adr/0007` §6 Punkt 4 Wort für Wort um, ergänzt um
§12.11 Punkt 11, als reine Funktion über ein Item-Dict:

| Feld | Quelle (1.1) | wir (1.0) |
|---|---|---|
| `stac_version` | `1.1.0` | `1.0.0` |
| `stac_extensions` | `eo` v2.0.0, `projection` v2.0.0, `raster` v2.0.0 | die 1.0-tauglichen Fassungen v1.1.0 |
| Asset-`bands` | `bands: [{name, eo:common_name, …}]` | `eo:bands: [{name, common_name, …}]`, `eo:`-Präfixe **innerhalb** der Bandobjekte fallen weg |
| `proj:code` | `"EPSG:32626"` | `proj:epsg: 32626`, nur bei `EPSG:`-Präfix |
| Asset-`nodata`, `data_type`, `raster:spatial_resolution` | direkt am Asset | als `raster:bands`-Eintrag |
| `proj:bbox` | hier in Metern und korrekt (§12.11 Punkt 11) | **geprüft**, nicht umbenannt: passt sie nicht zur CRS, wird sie verworfen |

Alles Übrige bleibt stehen, statt still verfälscht zu werden — die
`zarr`-Extension v1.1.0 hat keine 1.0-Entsprechung und bleibt unverändert.

**Die ausgewiesene Stichprobe** (`adr/0004` Option 6, §12.11 Punkt 13) ist die
vierte Adapter-Fähigkeit neben Suche, Zugriffsauflösung und Aggregation
(`architekturplan.md` 6.1). Sie erfüllt dasselbe `CoverageSource`-Protokoll wie
`aggregate_coverage`: sie zieht Seiten von Footprints bis zu einem Deckel,
rastert selbst auf Geotile-Stufe (dieselbe Zentroid-Regel wie `adr/0004` §5),
baut das Monatshistogramm und liefert `completeness = SAMPLE` mit
`total_count = None`. Dass `total_count is None` die Dichteanzeige stehen lässt
und Footprints **nicht** automatisch einschaltet, ist in
`CoverageResult.footprints_advised` bereits so gebaut (M2-05) — die Ersatzregel
aus M2-07c ist damit serverseitig schon erfüllt und braucht nichts Neues.
Der Deckel: §10 F5.

### 4.3 `readers` — Stufenwahl und Bandadressierung

Zwei Ergänzungen an `readers/zarr_reader.py`, beide klein und beide durch den
synthetischen Test aus M2-09a abgesichert, bevor sie die echte Quelle sehen:

1. **Stufenwahl aus `multiscales`** (F10, `adr/0007` §12.11 Punkt 2). Das
   `layout` nennt je Stufe `asset` (den Gruppennamen), `spatial:shape` und
   `spatial:transform`; die Bodenauflösung steht als erstes Glied der Affinen
   (gemessen: 10, 20, 60, 120, 360, 720). Gewählt wird die **gröbste** Stufe, die
   noch mindestens so fein ist wie die angefragte Kachel — gerechnet, nicht
   nachgeschlagen (§12.10, F9). Fehlt `multiscales`, bleibt es bei der Gruppe, die
   das Asset nennt; das ist der Rückfall, den F10 a verlangt, und zugleich der
   Fall des synthetischen Mini-Zarr.
2. **Bandadressierung**: die Variable kommt nicht mehr allein aus dem letzten
   Pfadsegment. Form: §10 F2.

**Was sich *nicht* ändert:** `GatewayStore` samt Byte-Ranges (§12.11 Punkt 1),
`zarr_format=3` (Punkt 6), kein `to_dataarray`/`to_array` (Punkt 7), keine
Listung, die CRS-Reihenfolge Store vor Item (Punkt 3). Alles steht seit M2-09a
und ist getestet.

### 4.4 `api` — Route, Coverage-Anbieter, und ein Fall, den es bisher nie gab

`coverage_route.py` verzweigt heute auf `UPSTREAM_AGGREGATION` und antwortet sonst
`501` mit Verweis auf M2-09b; hier wird der zweite Zweig gefüllt.

**Und ein Befund, der nicht in `docs/` steht.** `api/federating_client.py::_dispatch_search`
weist eine Suche über **mehr als eine** föderierte Collection mit `400` ab —
bewusst so gebaut, „nicht reachable at all with today's registry (one dataset)".
Mit dem zweiten Datensatz ist dieser Fall erstmals erreichbar, und er trifft nicht
nur die ausdrückliche Mehrfach-Suche, sondern **jedes `GET /search` und
`POST /search` ohne `collections`**: `_dispatch_search` setzt dann alle
Collections als Ziel ein. Das Frontend sucht je Datensatz (D8) und nennt die
Collection, ist also nicht betroffen — die API aber schon, und für einen
STAC-Client ist eine Suche ohne `collections` der Normalfall. §10 F3.

### 4.5 Standard-Visualisierung

Echtfarbe aus `b04`, `b03`, `b02` — ein fertiges Bild gibt es nicht (§3.1, §12.7).
Wegen der Skalierung (§3.4) liefert der Reader Reflexionsgrad, kein 8-Bit-RGB; der
Startwert des Streckbereichs ist damit nicht die Identität wie beim ersten
Datensatz. Vorschlag als Startwert, ausdrücklich Setzung und keine Messung:
`rescale = ((0.0, 0.30), (0.0, 0.30), (0.0, 0.30))`. Das ist nur das Bild, bevor
jemand einen Regler anfasst — der szenenspezifische Streckbereich kommt aus
`/statistics` (Z4, F18), und `adr/0007` §12.11 Punkt 8 legt fest, dass die
Statistik auf `r720m`/`r360m` gerechnet wird. §10 F6.

**Quicklook-Ersatz** (M2-09b-Umfang laut Plan): eine Vorschau aus der gröbsten
Stufe über denselben Kachelpfad, gemessen 38 kB und 0,6 s (§12.4). Sie braucht
keinen eigenen Endpunkt — es ist eine Kachel-URL auf `r720m`. Die Anzeige ist
Sache von M2-10.

---

## 5. Tests

Fixtures ausschließlich synthetisch (`ENTSCHEIDUNGEN` §4, `KLAERUNGEN` B2): die
aufgezeichneten Antworten sind gekürzte, bereinigte STAC-Dokumente der
token-freien Quelle, die Pixel kommen aus dem Mini-Zarr von M2-09a.

| Was | Wo | Fehlerfälle, die dazugehören |
|---|---|---|
| Registry-Eintrag vollständig | `tests/catalog/test_sentinel_2_l2a_zarr3.py` | fehlendes Flag, `staging` ohne Feld, `zipped_product` im Eintrag |
| Normalisierung 1.1 → 1.0 | `tests/earthx/adapters/test_eopf_normalise.py` | `proj:code` ohne `EPSG:`-Präfix bleibt stehen; `proj:bbox` in Grad bei UTM-CRS wird verworfen; ein Feld ohne 1.0-Entsprechung bleibt unverändert |
| Suche und Seitenmarke | `tests/earthx/adapters/test_eopf_stac.py` | fremde Marke verlässt das Modul nicht; `limit` über dem Deckel; Antwort ohne `features` |
| Stichprobe als Coverage | `tests/earthx/adapters/test_eopf_sample_coverage.py` | Deckel erreicht → `completeness = SAMPLE`, `total_count = None`, `footprints_advised = False`; Item ohne Geometrie; leere Antwort |
| Stufenwahl | `tests/earthx/readers/test_zarr_levels.py` | `multiscales` fehlt → Rückfall auf die Asset-Gruppe; kaputtes `layout` → definierter Fehler, kein Raten; Überzoom wählt die feinste Stufe |
| Bandadressierung | `tests/earthx/readers/test_zarr_reader.py` (erweitert) | Asset zeigt auf eine Gruppe ohne benannte Variable; unbekanntes Band; `zipped_product`-Adresse wird abgewiesen |
| Kein Request außerhalb `gateway` | `tests/earthx/test_no_outbound_outside_gateway.py` | greift automatisch, zusätzlich `lint-imports` |

**Was hier bewusst *nicht* steht:** ein Test gegen die echte Quelle. `adr/0002`
T-D hält fest, dass ein Live-Smoke aus einer Cloud-Sitzung nicht nachfahrbar ist —
`gateway` verbindet zur geprüften Adresse, und der Sitzungs-Proxy weist `CONNECT`
auf eine IP mit `403` ab. Die Hosts sind aus dieser Sitzung über `curl`
erreichbar (§3.1), über unseren eigenen Stapel voraussichtlich nicht. §10 F7.

---

## 6. Was nicht angefasst wird

- **`gateway`.** Die Adress-Bindung ist eine Sicherheitseigenschaft aus M1-03.
  Der neue Host kommt allein über den Registry-Eintrag in die Allowlist — genau
  der Weg, den D12 beschreibt, und er steht seit M2-04.
- **`sentinel-2-l2a`** (die v2-Collection) wird nicht aufgenommen: dieselben
  Item-IDs wie `…-zarr3`, das verletzte die ID-Eindeutigkeit der föderierten
  Suche (§12.11 Punkt 12).
- **`zipped_product`** kommt nicht in den Eintrag (Punkt 10).
- **Das Frontend.** Der zweite Datensatz im Viewer ist M2-10. Dass er nach diesem
  PR in der Datensatzliste des Viewers auftaucht, ist eine Folge des
  Registry-Eintrags und beabsichtigt; die sichtbare Auszeichnung von „staging"
  ist Sache von M2-10 (§12.11 Punkt 14 sagt das ausdrücklich).
- **`level_for_viewport`** und die Coverage-Gitterstufen (zurückgestellt, D26).
- **Die Abnahmetexte in `plans/m2-format-und-viewer.md` §5.** Sie gegen Punkt 15
  zu prüfen ist eine Planänderung und gehört zu M2-12 (offene Log-Zeile).

---

## 7. Reihenfolge der Umsetzung

Der Umfang liegt deutlich über dem Richtwert von etwa 400 geänderten Zeilen.
Vorschlag, drei PRs statt eines — jeder für sich abnehmbar, jeder mit Tests:

1. **M2-09b-1 — Katalog und Suche.** `AdapterKind.EOPF_STAC_V1`,
   `adapters/eopf_stac.py` mit Suche, Item-Abruf und Normalisierung, Dispatch in
   `adapters/__init__.py` und `federating_client.py`, Registry-Eintrag samt
   `maturity` und `ZarrInfo`, Collection-Abbildung. Danach ist der Datensatz
   suchbar.
2. **M2-09b-2 — Lesepfad.** Stufenwahl aus `multiscales`, Bandadressierung,
   Standard-Visualisierung. Danach sind Kachel, Statistik und Zuschnitt da.
3. **M2-09b-3 — Stichprobe.** Der Coverage-Anbieter und der zweite Zweig der
   Coverage-Route.

§10 F1 fragt, ob der Schnitt so recht ist.

---

## 8. Risiken

| Risiko | Umgang |
|---|---|
| Die Quelle heißt „staging" und kann verschwinden | Bekannt und eingepreist (§12.11 Punkt 15): die M2-Abnahme hängt daran nicht. Fällt sie weg, fällt dieser PR, nicht M2 |
| `multiscales` v0.1 bricht | Dann bricht nur die Stufenwahl, nicht der Lesepfad (Punkt 2): Rückfall ist die Gruppe, die das Asset nennt. Der Vermerk steht im Registry-Eintrag |
| Kachelkosten ab z11 rund 1–4,3 MB | Der HTTP-Cache ist bei diesem Datensatz Voraussetzung, keine Feinarbeit (§12.10); er arbeitet nach Frist, nicht nach Revalidierung (Punkt 9) |
| Zwei föderierte Quellen brechen `GET /search` ohne `collections` | §4.4, §10 F3 — vor der Umsetzung zu entscheiden |

---

## 9. Abnahme dieses Plans

Otto beantwortet §10. Danach wird umgesetzt, in der Reihenfolge aus §7, mit
`ruff check backend`, `pytest`, `lint-imports --config .importlinter` grün und
dem Ergebnis im jeweiligen PR.

---

## 10. Fragen an Otto

**F1 — Schnitt.** M2-09b in einem PR liegt weit über dem Richtwert von 400 Zeilen.

a) **Drei PRs wie in §7** (Katalog/Suche, Lesepfad, Stichprobe). *(Empfehlung)*
b) Zwei PRs: Katalog/Suche/Lesepfad zusammen, Stichprobe getrennt.
c) Einer, Richtwert überschritten.

**F2 — Wie wird ein Band adressiert?** Das Asset zeigt auf eine Gruppe, nicht auf
eine Variable (§3.2); die Regel aus M2-09a trägt hier nicht.

a) **Registry-Feld `ZarrInfo` mit einem Trennzeichen, Asset-Schlüssel in der
   Kachel-URL wird `SR_10m:b04`.** Der Reader nimmt die Gruppe aus dem
   Asset-`href`, die Variable aus dem Suffix. Die URL sagt weiterhin, was sie
   zeigt (Z4), der Registry-Eintrag sagt, wie sie zu lesen ist, und das
   synthetische Mini-Zarr bleibt ohne Trennzeichen gültig. *(Empfehlung)*
b) Zweiter Abfrageparameter `band` an der Kachelroute. Trennt Asset und Band
   sauber, erfindet aber einen Parameter, den TiTiler und der COG-Pfad nicht
   kennen, also eine Sonderbehandlung im Frontend — genau das, was M2-10
   ausschließt.
c) Der Reader liest `zarr:node_type` des Assets und nimmt bei `group` die erste
   Variable. Rät, und sobald zwei Bänder in Frage kommen, rät es falsch.

**F3 — Suche ohne `collections` bei zwei föderierten Quellen** (§4.4).

a) **So lassen, nur die Meldung schärfen** („nenne genau eine Collection"). Der
   Viewer sucht ohnehin je Datensatz (D8), der Aufwand bleibt bei null, der
   Zustand ist ehrlich. *(Empfehlung)*
b) Bei fehlendem `collections` still auf den ersten föderierten Datensatz
   zurückfallen. Bequem, aber die Antwort verschweigt, dass etwas fehlt.
c) Zusammenführung mehrerer Quellen jetzt bauen — eigene Aufgabe, eigener Plan,
   Seitenmarke über zwei Quellen ist nicht klein.

**F4 — Wohin gehört der Status „staging"?** `architekturplan.md` 5.1 führt heute
neun `earthx:`-Felder.

a) **Zehntes Feld `earthx:maturity`** mit `stable`/`staging`/`experimental`, ohne
   Vorgabewert (B10), samt Nachtrag in 5.1. Der Status gehört zur Wahrheit über
   den Datensatz wie Lizenz und Attribution (§12.11 Punkt 14) und ist keine
   Messung wie `health`. *(Empfehlung)*
b) Als zusätzlicher Wert in `earthx:health`. Kein neues Feld, vermischt aber „wie
   vorläufig ist die Quelle" mit „lief der letzte Test durch".
c) Freitext in `description`. Kein Feld, nichts Prüfbares, keine Anzeige in M2-10.

**F5 — Deckel der Stichprobe.** `adr/0004` Option 6 nennt keinen; der Prototyp
brauchte rund 20 s für 1500 Footprints, die Quelle liefert rund 1300 Items je Tag
(§12.6).

a) **Fünf Seiten à 100 Items = 500 Footprints**, entspricht dem
   `FOOTPRINT_THRESHOLD` aus M2-05 und dem `FOOTPRINT_FETCH_LIMIT` des Frontends;
   gemessen rund 2 s für fünf Seiten. *(Empfehlung, Setzung — keine Messung der
   Anzeigequalität)*
b) 20 Seiten = 2000 Footprints. Dichter, aber rund 8 s je Kartenbewegung.
c) Zahl offenlassen und per Messung in M2-10 festlegen.

**F6 — Startwert des Streckbereichs** für die Echtfarbe (§3.4, §4.5).

a) **`(0.0, 0.30)` je Band** auf dem skalierten Reflexionsgrad. Üblicher Wert für
   Sentinel-2-L2A-Echtfarbe; der szenenspezifische Bereich kommt ohnehin aus
   `/statistics`. *(Empfehlung, Setzung)*
b) `mask_and_scale` abschalten und auf rohen Zählern `(0, 3000)` strecken. Näher
   am ersten Datensatz, verschenkt aber `_FillValue` und die Offset-Korrektur.
c) Vor der Umsetzung über fünf Szenen messen, wie es `adr/0006` §5 für den ersten
   Datensatz getan hat — kostet eine eigene Messsitzung.

**F7 — Vorführung gegen die echte Quelle.** Die Abnahme verlangt „Suche, Kachel,
Statistik und Zuschnitt gegen die echte Quelle vorgeführt"; aus einer
Cloud-Sitzung geht das über `gateway` nicht (`adr/0002` T-D, §5).

a) **Otto führt lokal vor**, die Sitzung belegt die Erreichbarkeit mit `curl` und
   die Logik mit synthetischen Fixtures. So ist M2-07c und M2-14 schon
   abgenommen worden. *(Empfehlung)*
b) Die Quelle in `live-smoke.yml` aufnehmen und die Vorführung der CI überlassen —
   wäre belastbarer, macht die Abnahme aber von einer „staging"-Quelle abhängig,
   die jederzeit rot werden kann.
c) Abnahmekriterium für diesen Datensatz entsprechend umformulieren (gehört dann
   zu M2-12).
