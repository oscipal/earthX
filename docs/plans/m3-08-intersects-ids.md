# M3-08 — `intersects` und `ids` durchreichen: Plan-Schritt

**Status:** Plan vom 23.09.2026, wartet auf Ottos Freigabe. Nichts umgesetzt.
**Aufgabe:** M3-08 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4
(P6, D31). **Stufe B.**
**Grundlagen:** `adr/0005` Regeln I, III, V, VI, §3.5, K8; `adr/0004` §3.4;
`plans/m2-format-und-viewer.md` D21, D31, M2-17; `projektplan.md` 7 Punkt 6
(keine exakte AOI in Logs); `KLAERUNGEN.md` B8.

Belegstufen wie in `adr/0005`: **M** gemessen in dieser Sitzung, **P** am
Quelltext gelesen, **A** eigene Ableitung.

---

## 1. Ziel

Polygon- und Punkt-AOIs suchen genau statt über ihre Bounding Box, und `ids`
filtert, statt mit `400` abgewiesen zu werden. Beides gilt für
`GET` und `POST /stac/search` auf föderierten Collections (Earth Search,
EOPF).

---

## 2. Befund

### 2.1 Was die Quellen können — **[M]**

Gemessen am 23.09.2026 mit `POST /search` gegen beide Quellen. Suchfenster:
Earth Search Juni 2024, EOPF ohne Zeitraum (der Bestand ist rund zwei Monate
alt). Nur Metadaten, rund 80 Anfragen. Die Testgeometrien sind synthetisch
(Dreieck, Kreis, Streifen über Mitteleuropa), keine Nutzer-AOI.

| Fall | Earth Search | EOPF |
|---|---|---|
| `intersects` Polygon | `200`, 159 statt 273 Treffer der bbox | `200` |
| `intersects` Point | `200`, 12 Treffer, 0,33 s | `200`, 15 Treffer, 1,25 s |
| `intersects` MultiPolygon | `200` | `200` |
| `bbox` und `intersects` zusammen | `400` „Expected bbox OR intersects“ | `400` (pydantic) |
| `GET /search?intersects=…` | `200` | `200` |
| `ids`: eine bekannte | `200`, 1 Treffer | `200`, 1 Treffer |
| `ids`: unbekannte | `200`, 0 Treffer | `200`, 0 Treffer |
| `ids` zusammen mit weit entfernter `bbox` oder `intersects` | `200`, 0 Treffer: **UND-verknüpft** | ebenso |
| `ids`: 10 000 Kennungen | `200`, 0,66 s | `200`, 1,04 s |
| `ids: []` | `200`, 0 Treffer | `200`, 0 Treffer |
| `ids: "abc"` (kein Array) | **`200`, 0 Treffer** | `400` |

**Genauigkeit.** Ein schmaler Diagonalstreifen, dessen bbox `[8, 47, 12, 51]`
ist: per bbox 273 (Earth Search) bzw. 317 (EOPF) Treffer, davon berühren 97 bzw.
115 den Streifen wirklich. Per `intersects` kommen genau diese 97 bzw. 115,
**keiner** davon außerhalb (mit shapely an jedem Footprint nachgeprüft). Beide
Quellen filtern also geometrisch genau, nicht über die bbox.

**Größe.** Kreispolygone mit wachsender Stützpunktzahl, `limit=100`:

| Stützpunkte | Rumpf | Earth Search | EOPF |
|---|---|---|---|
| 200 | 5 kB | 0,65 s | 2,30 s |
| 1 000 | 23 kB | 0,98 s | 2,63 s |
| 5 000 | 114 kB | 1,02 s | 2,76 s |
| 20 000 | 454 kB | 1,48 s | 3,78 s |

Keine der Quellen setzt eine Grenze; die Obergrenze muss bei uns stehen, wie
schon bei `limit` (`adr/0005` §3.2).

### 2.2 Was die Quellen still annehmen — **[M]**

Dasselbe Muster wie die bbox außerhalb ±90 (`adr/0005` §3.5), nur schärfer:

| Eingabe | Earth Search | EOPF |
|---|---|---|
| Polygon mit Länge 999 | **`200`, 30 Treffer** | `200`, 0 Treffer |
| Polygon mit Breite 888 | **`200`, 42 Treffer** | `200`, 0 Treffer |
| Punkt mit Breite 95 | `400` mit Elasticsearch-Innenleben im Text | `200`, 0 Treffer |
| Selbstschneidendes Polygon (Schleife) | `200`, 229 Treffer | `200` |
| Ring nicht geschlossen / nur 2 Punkte | `400` mit Java-Text | `400` (pydantic) |
| `Polygon` mit `coordinates: []` | `400` | **`200`, 0 Treffer** |
| LineString, GeometryCollection | `200` | `200` |

Eine Quelle liefert für ungültige Koordinaten plausibel aussehende Treffer,
die andere eine leere Liste; beide Fehlertexte enthalten Innenleben der
Quelle. Die Prüfung gehört deshalb zu uns, vor dem Versand (`adr/0005` Regel
III: kein Fremdtext in unserer Antwort).

### 2.3 Im eigenen Code — **[P]**

- `api/federating_client.py` weist `ids` und `intersects` seit M2-17 ab
  (`_UNSUPPORTED_SEARCH_KEYS`). `SearchParams`, `search_fingerprint` und beide
  `_search_body` kennen nur `bbox`, Zeitfenster, `limit` und Seitenmarke.
- **K8 ist heute verletzt.** Die Landing Page weist
  `https://api.stacspec.org/v1.0.0/item-search` aus (Grundmenge von
  `stac-fastapi`), und zu dieser Klasse gehören `ids` und `intersects`. Mit
  M3-08 stimmt das Versprechen wieder.
- **POST ist der Weg für Geometrien.** Beide Adapter fragen upstream schon per
  `POST /search` (`gateway.post_json`); die URL-Grenze von rund 8 kB
  (`adr/0004` §3.4, D21) trifft die Suche upstream also nicht. Sie gilt weiter
  für jeden `GET`, auch für einen `GET /stac/search` mit `intersects` von
  außen, und für die Coverage-Route, die hier nicht angefasst wird.
- **Der Zugriffslog von Uvicorn schreibt die Abfragezeichenfolge mit**
  (`uvicorn/protocols/http/h11_impl.py`, `get_path_with_query_string`). Ein
  `GET /stac/search?intersects=…` landet damit samt Koordinaten im Log des
  `api`. Dasselbe gilt **schon heute** für die `bbox`, die das Frontend per
  `GET` sendet, und für `GET /coverage/…?intersects=…`.
- **`stac-fastapi` loggt Ausnahmen, die es selbst auf Statuscodes abbildet**
  (`errors.py`, `logger.error(exc, exc_info=True)`). Eigene Ablehnungen laufen
  deshalb weiter als `HTTPException`, deren Text keine Koordinate nennt.
- **Der `next`-Link einer `POST`-Suche wiederholt den ganzen Rumpf**
  (`PagingLinks.link_next`), also auch die Geometrie; die Marke steht in
  `body.token`, nicht im `href`. Das Frontend liest sie heute aus dem `href`.
- **Die Punkt-AOI ist im Frontend ein Quadrat.** `bufferPointToPolygon` macht
  aus einem Klick ein Quadrat von ±0,05°; der Punkt selbst ist danach weg.

---

## 3. Fragen an Otto

Kurz beantwortbar, etwa „alle Empfehlungen“ oder „1a, 2a, 3b …“.

**F1 — Deckel für die Stützpunktzahl von `intersects`.**
a) **1 000 Positionen** über alle Ringe (rund 23 kB JSON). Deckt jede
gezeichnete AOI und die meisten Uploads; Latenz gemessen wie bei 200 Punkten.
**Empfehlung.**
b) 5 000 Positionen (rund 114 kB); großzügiger für Uploads, dafür wiederholt
jede Antwort den Rumpf im `next`-Link.
c) 200 wie in der Coverage (`MAX_AOI_POINTS`).

**F2 — Was über dem Deckel passiert.**
a) **Das Backend weist mit `400` ab und nennt den Deckel. Das Frontend sucht
dann über die bbox der AOI und sagt es in der Meldung** („Area has more than
1000 points; searched its bounding box instead.“). Die bbox ist eine
Obermenge, es fällt also keine Szene weg. **Empfehlung.**
b) Das Backend verdünnt wie die Coverage. In einer STAC-Antwort gibt es aber
kein Feld, das die Vereinfachung ausweist; das wäre wieder „still“.
c) Das Frontend verdünnt. Dabei kann eine Szene am Rand wegfallen.

**F3 — Deckel für `ids`.**
a) **100 Kennungen, gleich `MAX_LIMIT`**, also passen alle Treffer auf eine
Seite. Jede Kennung muss auf `ITEM_ID` passen. Eine leere Liste ergibt `400`:
Beide Quellen beantworten sie mit einer leeren Seite, und die sieht aus wie
„nichts gefunden“, obwohl nichts gefragt war. **Empfehlung.**
b) 1 000 Kennungen, sonst wie a.
c) Kein eigener Deckel.

**F4 — Wenn eine Quelle `intersects` oder `ids` nicht kann** (heute keine,
denkbar bei der dritten Quelle, M3-11).
a) **Jedes Adaptermodul erklärt, welche der beiden es kann; die Dispatch in
`adapters/__init__.py` weist eine nicht unterstützte Anfrage mit `400` ab und
nennt Parameter und Collection. Ein Test prüft, dass die Landing Page
`item-search` nur ausweist, solange jeder Adapter beides kann** (K8). Kommt
eine Quelle ohne, schlägt der Test an und erzwingt eine Entscheidung.
**Empfehlung.**
b) Rückfall auf die bbox und genaues Nachfiltern im Adapter. Dann stimmen
`numberMatched` und die Seitengrößen nicht mehr.
c) Ein Registry-Feld je Datensatz. Die Fähigkeit hängt aber an der Quelle,
nicht am Datensatz.

**F5 — Was die Punkt-AOI sendet.**
a) **Den Punkt als `intersects: Point`.** Treffer sind dann genau die Szenen,
die den geklickten Punkt enthalten. Das Quadrat bleibt, was die Karte zeigt
und was der Download zuschneidet. **Empfehlung.**
b) Das Quadrat als Polygon. Ergibt dieselben Treffer wie heute per bbox und
wäre damit nur ein anderer Weg zum gleichen Ergebnis.

**F6 — Welche Geometrien angenommen werden.**
a) **Alle GeoJSON-Geometrietypen**, wie `item-search` es verlangt (K8), mit
eigener Prüfung: Zahlen endlich, Länge in ±180, Breite in ±90, Ringe
geschlossen mit mindestens vier Positionen, Polygone gültig (kein
Selbstschnitt, geprüft mit shapely, das schon Abhängigkeit ist),
GeometryCollection nicht verschachtelt. **Empfehlung.**
b) Nur Point, Polygon und MultiPolygon, also was der Viewer sendet und die
Coverage schon kennt. Einfacher, aber die Landing Page verspräche dann mehr,
als die API hält.

**F7 — Koordinaten im Zugriffslog** (§2.3).
a) **Das Frontend sucht immer per `POST`, und ein Log-Filter in `api` schwärzt
die Werte von `bbox` und `intersects` im Zugriffslog von Uvicorn.** Deckt auch
API-Nutzer per `GET` und nebenbei die Coverage-Route. Rund 30 Zeilen in
`earthx/logging.py` plus Test. **Empfehlung.**
b) Nur das Frontend auf `POST` umstellen; der Befund für `GET` kommt als
offene Zeile ins Log.
c) Zugriffslog von `api` abschalten (`--no-access-log` in
`docker-compose.yml`). Damit fehlen auch Status und Pfad, die für Betrieb und
Bug-Reports nützlich sind.

---

## 4. Umsetzung nach Empfehlung

Die Reihenfolge entspricht den Commits.

**Backend**

1. **`adapters/federated_search.py`:** `SearchParams` bekommt `intersects`
   (GeoJSON-Mapping) und `ids` (Tupel). `__post_init__` prüft: nicht `bbox`
   und `intersects` zugleich; die Geometrie nach F6 und F1; `ids` nach F3.
   Jeder Fehlertext nennt die verletzte Regel, keine Koordinate.
   `search_fingerprint` nimmt `intersects` (kanonisches JSON, Zahlen als
   `float`) und `ids` (sortiert, ohne Dubletten) **nur auf, wenn gesetzt**.
   Damit bleiben die Fingerabdrücke aller bisherigen Suchen gleich: kein
   Wechsel von `TOKEN_VERSION`, gültige Seitenmarken und Cache-Zeilen bleiben
   gültig. Der Schlüssel bleibt ein SHA-256; die Geometrie steht weder im
   Schlüssel noch in einer eigenen Spalte von `earthx_search_cache`.
2. **`earth_search.py`, `eopf_stac.py`:** `_search_body` sendet `intersects`
   und `ids`. Jedes Modul erklärt seine Fähigkeiten (F4), hier beide.
3. **`adapters/__init__.py`:** Die Dispatch prüft die Fähigkeiten vor dem
   Aufruf; neue Ausnahme `UnsupportedFilter` → `400`.
4. **`api/federating_client.py`:** `_UNSUPPORTED_SEARCH_KEYS` fällt für
   `/search` weg. `post_search` reicht `search_request.intersects`
   (geojson-pydantic, als Dict) und `ids` durch; `get_search` nimmt beide aus
   `kwargs` und liest `intersects` per `json.loads`, sodass kaputtes JSON `400`
   ergibt. **`/collections/{id}/items` weist beide weiter ab**, denn der
   Items-Endpunkt von OGC API Features kennt sie nicht. Die Meldung verweist
   dann auf `/search`.
5. **`earthx/logging.py` und `api/main.py`** (F7a): Filter auf
   `uvicorn.access`, der die Werte von `bbox` und `intersects` in der
   Abfragezeichenfolge durch `…` ersetzt.

**Frontend**

6. **`api.ts`:** `searchItems` sendet `POST /stac/search` mit JSON-Rumpf
   (`collections`, `bbox` oder `intersects`, `datetime`, `limit`, `token`).
   `nextTokenFrom` liest die Marke aus `body.token` des `next`-Links.
   `SearchQuery` bekommt `intersects?: GeoJSON.Geometry`.
7. **`geoUtils.ts`:** reine Funktion `searchArea(aoi, point)`. Ein Rechteck,
   das seiner bbox entspricht, → `bbox`. Ein Punkt → `intersects: Point`
   (F5). Andere Polygone und MultiPolygone → `intersects`, über dem Deckel →
   `bbox` mit Hinweis (F2).
8. **`store.ts`, `MapView.tsx`, `ControlPanel.tsx`:** Das Punktwerkzeug merkt
   sich den Punkt neben dem Quadrat (`aoiPoint`); jede andere AOI löscht ihn.
   `runSearch` und der Datums-Fallback suchen mit `searchArea`. Die
   Footprint-Abfrage der Coverage bleibt bei der bbox.

**Nicht angefasst:** Coverage-Route und ihre Verdünnung; `eopf_sample_coverage`
reduziert `intersects` weiter auf die bbox (Nachziehen ist klein, aber eigene
Sache); gemischte Suche über mehrere Collections (M3-13); `findSceneByName`
bleibt beim Einzelabruf; `gateway`; `decomp.py`; `.github/`, `.claude/`.

---

## 5. Tests (Abnahme)

Backend, Einheit (`tests/earthx/adapters/test_search_params.py` und
Umgebung):

- Polygon, MultiPolygon, Punkt: gehen in den Rumpf beider Quellen; die
  Fingerabdrücke unterscheiden sich von der bbox-Suche.
- **Zu große Geometrie:** 1 001 Positionen → `InvalidQuery`, der Text nennt
  den Deckel.
- **Ungültige Geometrie:** Länge 999, Breite 888, Punkt mit Breite 95, offener
  Ring, Ring mit zwei Punkten, leere Koordinaten, Schleife, unbekannter Typ,
  `NaN`, verschachtelte GeometryCollection → je `InvalidQuery`, nichts geht
  upstream.
- `bbox` und `intersects` zusammen → `InvalidQuery`.
- **`ids`:** bekannte Kennung (Treffer), unbekannte (leere Seite, `200`),
  101 Kennungen → `InvalidQuery`, leere Liste → `InvalidQuery`, Kennung mit
  `/` oder Zeilenumbruch → `InvalidQuery`; Reihenfolge und Dubletten ändern
  den Fingerabdruck nicht.
- Fingerabdruck einer Suche ohne `ids`/`intersects` ist gleich dem bisherigen
  (fester Erwartungswert), eine alte Seitenmarke gilt weiter.
- Seitenmarke aus einer Polygon-Suche gilt nicht für die bbox-Suche und
  umgekehrt.
- Dispatch mit einem Test-Adapter ohne `intersects` → `UnsupportedFilter`.

Backend, Integration (`tests/integration/test_api_federating.py`, pgstac echt,
Quelle gemockt): Die beiden `400`-Tests aus M2-17 werden zu Durchreich-Tests
für `GET` und `POST`; der Rumpf upstream enthält `intersects` bzw. `ids`.
Dazu: kaputtes JSON in `GET intersects` → `400`; `/collections/{id}/items`
mit `intersects` → weiter `400`; die Landing Page weist `item-search` aus und
jeder Adapter kann beides (F4).

**Keine Koordinaten im Log:** Ein Test fährt gültige, ungültige und zu große
Geometrien per `GET` und `POST` durch die App, fängt alle Log-Zeilen (auch
`uvicorn.access` über den Filter) und prüft, dass keine der synthetischen
Koordinaten darin vorkommt. Dafür werden die Zahlen so gewählt, dass sie
sonst nirgends auftauchen (etwa `7.123456`).

Frontend (Vitest): `searchArea` für Rechteck, Punkt, Polygon, MultiPolygon und
über dem Deckel; `searchItems` sendet `POST` mit dem richtigen Rumpf;
`nextTokenFrom` liest `body.token`; `runSearch` mit Punkt-AOI sendet den
Punkt und mit großem Upload die bbox samt Hinweis.

Vor dem Fertigmelden: `ruff check backend`, `pytest`,
`lint-imports --config .importlinter`, `npm run lint`, `npx tsc -b`, Vitest.

---

## 6. Umfang und Risiken

- **Schätzung:** rund 250 Zeilen Code und 300 Zeilen Tests, also über dem
  Richtwert von 400. Der M3-Plan sieht genau einen PR vor; wenn Otto teilen
  will, wäre der Frontend-Teil (Schritte 6–8) der natürliche zweite PR.
- **Kanonisierung:** Dieselbe Fläche mit anderem Startpunkt des Rings ergibt
  einen anderen Cache-Schlüssel, also einen Cache-Fehlgriff, keine falsche
  Antwort. Nicht behandelt.
- **Antimeridian:** Polygone über ±180 werden nicht umgebaut; GeoJSON
  (RFC 7946) verlangt dafür ohnehin eine MultiPolygon-Teilung beim Absender.
- **EOPF ist langsam** (1,2–3,8 s je Seite, §2.1); daran ändert `intersects`
  nichts Messbares.

---

## 7. Messanhang

Ein Skript im Scratchpad der Sitzung, nicht im Repo. Die Anfragen haben diese
Form (Earth Search; EOPF mit `https://stac.core.eopf.eodc.eu` und
`sentinel-2-l2a-zarr3`, ohne `datetime`):

```bash
curl -sS -X POST https://earth-search.aws.element84.com/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"collections":["sentinel-2-c1-l2a"],"limit":100,
       "datetime":"2024-06-01T00:00:00Z/2024-06-30T23:59:59Z",
       "intersects":{"type":"Polygon","coordinates":[[[8,47],[12,47],[8,51],[8,47]]]}}'
```

Für `ids` dieselbe Form mit `"ids":[…]`. Die Genauigkeitsprobe hat für beide
Wege bis zu fünf Seiten geholt und jeden Footprint mit shapely gegen den
Streifen geprüft.
