# M3-13 — Gemischte Suche und CQL2: Plan-Schritt

**Status (26.09.2026):** Plan-Schritt, wartet auf Ottos Freigabe. Kein
Produktivcode geändert.
**Aufgabe:** M3-13 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4 (P6),
mit dem Nachtrag vom 26.09.2026 (M3-11b F11): **ein Zeitraum, mehrere
Datensätze zugleich; der Viewer nutzt die gemischte Suche.** **Stufe B.**
Hängt an M3-11b (gemergt). Plan-Schritt mit Opus (hoch), weil Paging über
mehrere Quellen heikel ist.
**Grundlagen:** `adr/0005` Regeln I, III, V, VI, K1, K3, K5, K8, §3.3, §8.4;
`architekturplan.md` 5.2, 5.3, 16 („Föderierte Suche ist so langsam wie die
langsamste Quelle“); `plans/m1-07-stac-api.md` §6, §7; `plans/m2-format-und-viewer.md`
D8; `plans/m3-08-intersects-ids.md` §2.1; `plans/m3-12-frontend-sonderfaelle.md`
§4.2; `ENTSCHEIDUNGSLOG.md`, Zeilen vom 20.09.2026 (D8) und 26.09.2026
(Richtung Viewer).

Belegstufen wie in `adr/0005`: **M** gemessen in dieser Sitzung, **P** am
Quelltext gelesen (Stand `main` 067322b), **A** eigene Ableitung.

---

## 1. Ziel

`POST`/`GET /stac/search` über mehrere Collections — eigene (pgstac) und
föderierte gemischt — liefert eine einheitliche STAC-Antwort statt `400`. Die
Seitenmarke trägt über alle beteiligten Quellen, bleibt zustandslos (K3) und
unsere eigene (Regel III). Fällt eine Quelle aus oder antwortet zu spät, kommen
die übrigen trotzdem, und die Antwort sagt, welche fehlt. Die Landing Page
verspricht nur, was jede beteiligte Quelle tatsächlich einlöst (K8). Die Frage
nach CQL2 ist neu entschieden (Regel VI).

Für den Viewer heißt das: Eine Suche über „ein Zeitraum, mehrere Datensätze“
ist ein einziger Aufruf. Die Mehrfachauswahl selbst baut M3-10.

---

## 2. Befund

### 2.1 Im eigenen Code — **[P]**

- `FederatingCoreCrudClient._dispatch_search` (`api/federating_client.py`)
  teilt die Ziel-Collections in föderierte und eigene (pgstac, auch
  materialisierte seit M3-11a). Drei Fälle: nur eigene → `super()`; genau
  eine föderierte → Adapter; alles andere → `400` „a search spanning more than
  one source is not supported yet“. Eine Suche **ohne** `collections` zielt auf
  alle Collections und ist damit heute immer `400` (gemessen, §2.2).
- Mehrere **eigene** Collections beantwortet pgstac schon heute in einem
  Aufruf, mit eigener Seitenmarke `coll:item-id` (Keyset, §2.2).
- Die Seitenmarke der föderierten Adapter (`adapters/federated_search.py`)
  bindet an `search_fingerprint`, und der enthält `limit`. Eine Marke, die mit
  `limit=34` ausgegeben wurde, weist derselbe Adapter bei `limit=50` als „page
  token belongs to a different search“ ab. Der Such-Cache-Schlüssel braucht
  `limit` (die gespeicherte Seite hängt davon ab), die Marke selbst nicht
  (§2.2).
- `_apply_time_axis` (M3-12) verwirft `datetime` nur, wenn **alle** Ziel-
  Collections keine Zeitachse haben. Der Docstring hält fest, dass die
  gemischte Lage (eine mit, eine ohne Zeitachse) erst mit M3-13 entschieden
  wird.
- `api/main.py` schaltet die Extensions `query`, `fields`, `pagination` ein;
  `filter` und `sort` bleiben hart aus (Regel VI, m1-07 F2). `filter`,
  `filter-lang` und `sortby` werden mit `400` abgewiesen statt verworfen.
- Frontend: `api.ts::buildSearchBody` schickt immer genau eine Collection;
  `searchAllPages` blättert bis `MAX_SEARCH_ITEMS = 300` (`store.ts`) und
  verlässt sich nicht auf eine Sortierung (D8). Der Viewer nutzt weder
  `query` noch `fields`.

### 2.2 Gemessen gegen die eigene API — **[M]**

Lokales pgstac aus dem Setup-Hook, die App über `httpx.ASGITransport`,
Earth Search per `MockTransport` (keine Anfrage nach außen), eine synthetische
materialisierte Collection mit fünf Items.

| Anfrage | Ergebnis |
|---|---|
| Landing Page, `conformsTo` | `item-search`, `item-search#query`, `item-search#fields`, `ogcapi-features#query`, `ogcapi-features#fields`; kein `filter`, kein `sort` |
| Suche ohne `collections` | `400` „a search spanning more than one source …“ |
| unbekannte Collection | `404` (pgstac, Regel I) |
| materialisiert, `limit=2`, dann mit Marke weiter | Keyset-Marke `next:<coll>:<item-id>`, Seite 2 lückenlos; kein `numberMatched` (Context-Extension aus) |
| zwei eigene Collections zusammen | ein pgstac-Aufruf, eine Marke, funktioniert |
| materialisiert mit `query` | wirkt (pgstac filtert) |
| **föderiert mit `query`** | **`200`, der Filter fehlt im Rumpf an die Quelle** — still verworfen |
| **föderiert mit `fields`** | **`200`, ebenso still verworfen**; der föderierte Weg projiziert auch selbst nicht (`_federated_page`, **[P]**) |

Die letzten beiden Zeilen sind ein **Befund außerhalb der Aufgabe, aber in
ihrem Kern (K8):** Die Landing Page verspricht seit M1-07 `#query` und
`#fields`, und auf jeder föderierten Collection fallen beide stillschweigend
weg. Das ist dasselbe Muster, das Regel VI für `filter` ausschließt.

### 2.3 Gemessen an den Quellen — **[M]**

14 Anfragen, je mindestens 1,2 s Abstand, nur Metadaten, AOI synthetisch
(`bbox` 8–12° O, 47–51° N).

**Konformität** (je eine Anfrage an die Landing Page):

| | `filter` (CQL2) | `query` | `fields` | `sort` |
|---|---|---|---|---|
| Earth Search v1 | **nein** | ja | ja | ja |
| EOPF STAC | ja (`features-filter`, `item-search#filter` rc.2) | ja | ja | ja |
| eigenes pgstac | kann es, ist aus | an | an | aus |

**Seitenmarke unabhängig von `limit`?** Je Quelle: Referenzseite `limit=6`;
dann `limit=2` und mit der Marke weiter bei `limit=4`. Beide Male ergeben die
zwei Seiten zusammen genau die Referenzseite:

| Quelle | Marke | lückenlos bei wechselndem `limit` |
|---|---|---|
| Earth Search | `body.next` = `datetime,id` des letzten Items | ja |
| EOPF | `body.token` = `next:<coll>:<item-id>` | ja |
| pgstac (eigene, §2.2) | `next:<coll>:<item-id>` | ja (Keyset) |

Alle drei Marken sind Keyset-Marken: Sie zeigen auf das letzte gelieferte Item,
nicht auf einen Versatz. Die Seitengröße darf sich also von Seite zu Seite
ändern — **nur unsere eigene Marke** verbietet das heute (§2.1).

Latenzen aus `plans/m3-08-intersects-ids.md` §2.1: Earth Search 0,3–1,5 s,
EOPF 1,2–3,8 s, auch mit Polygonen bis 20 000 Stützpunkten. Das Gateway
wartet höchstens 5 s auf die Verbindung und 15 s auf die Antwort; `POST` wird
nicht wiederholt.

---

## 3. Paging über mehrere Quellen: Optionen (→ F1)

„Quelle“ heißt hier: **eine föderierte Collection** oder **eine Gruppe
eigener Collections**, die pgstac in einem Aufruf beantwortet (§2.1). Eine
Suche über den DEM und die beiden Sentinel-2-Datensätze hat also drei Quellen.

**Option 1 — Auffächern mit Anteilen, die jede Seite neu verteilt.** Jede
Seite fragt alle noch offenen Quellen **parallel**, jede mit einem Anteil am
`limit` (100 bei drei Quellen: 34/33/33). Ist eine Quelle erschöpft, teilen
die übrigen ab der nächsten Seite ihren Anteil unter sich auf. Die Marke hält
je offener Quelle deren innere Marke. Voraussetzung: Adapter-Marken binden
nicht mehr an `limit` (§2.1; §2.3 zeigt, dass die Quellen das tragen).
*Für:* Jeder Datensatz kommt ab der ersten Seite vor — wichtig für den Viewer,
der bei 300 Items aufhört; Latenz einer Seite = langsamste Quelle, nicht die
Summe; keine Seite größer als `limit` (Regel V); zustandslos (K3).
*Gegen:* kleine Änderung an der Marke der Adapter (neue `TOKEN_VERSION`;
Marken, die vor dem Deployment ausgegeben wurden, werden mit `400`
abgewiesen — sie leben nur für die Dauer eines Blätterns).

**Option 2 — Auffächern mit festen Anteilen.** Wie 1, aber jede Quelle behält
ihren Anteil der ersten Seite bis zum Ende. Keine Änderung an den Adaptern.
*Gegen:* Seiten schrumpfen, sobald Quellen leer sind. Beispiel DEM + Sentinel-2
über eine AOI: Der DEM ist nach Seite 1 erschöpft, Sentinel-2 liefert danach
50 statt 100 je Seite; der Viewer braucht für 300 Items sechs statt drei
Seiten, jede 0,5–1 s.

**Option 3 — Nacheinander.** Erst Quelle A bis zum Ende, dann B. Eine Seite an
der Grenze füllt sich aus B auf.
*Gegen:* Mit dem Deckel von 300 Items im Viewer sieht ein später Datensatz
nichts, sobald der erste mehr als 300 Treffer hat; an der Grenze addieren sich
die Latenzen.

**Option 4 — Nach Datum zusammengemischt (k-Wege-Merge).** Global sortiert.
*Gegen:* Eine Quelle, von deren Seite nur ein Teil ausgegeben wurde, braucht
eine Marke mitten in der Seite. Die müssten wir aus Item-Feldern selbst
nachbauen, in den Formaten der Quellen, die nirgends dokumentiert sind
(`adr/0005` §8 Punkt 5). Jede Seite fragt jede Quelle mit vollem `limit` (K5).
Verworfen.

**Empfehlung: Option 1.** In keiner Option gibt es eine Sortierung über
Quellen hinweg. Die API sortiert ohnehin nicht (D8, m1-07 §6), und der Viewer
blättert bereits alle Seiten durch.

---

## 4. Vorgeschlagene Umsetzung

### 4.1 Wann die gemischte Suche greift

Unverändert bleiben: nur eigene Collections, auch mehrere (pgstac allein, wie
heute), und genau eine föderierte Collection (Adapter allein, wie heute). Die
gemischte Suche greift, sobald **zwei oder mehr Quellen** beteiligt sind, auch
bei einer Suche ohne `collections`. Damit ändert sich für jeden Aufruf, der
heute funktioniert, nichts; nur die heutigen `400` werden zu Antworten.

### 4.2 Eine Seite

1. Alle Ziel-Collections auflösen (`404` bei unbekannter, Regel I, vor jeder
   Anfrage nach außen). `SearchParams` einmal prüfen (`400` bei ungültiger
   Eingabe, für alle Quellen gleich). Fähigkeiten je föderierter Collection
   prüfen (`UnsupportedFilter` → `400`, bevor irgendeine Quelle gefragt wird).
2. Quellen bilden: eigene Collections, gruppiert nach dem Zeitfilter, der für
   sie gilt (§4.5), je Gruppe eine pgstac-Quelle; jede föderierte Collection
   eine Quelle. Feste Reihenfolge: pgstac-Gruppen zuerst, dann föderierte nach
   Collection-ID.
3. Offene Quellen aus der Marke (erste Seite: alle). Anteile verteilen:
   `limit // k`, der Rest einzeln an die ersten Quellen. Bei `limit < k`
   bekommen die hinteren Quellen auf dieser Seite nichts und bleiben offen.
4. Alle Quellen mit Anteil > 0 **parallel** fragen, jede mit eigenem Zeitlimit
   (§4.4). Föderierte über `adapters.search_items` wie heute (Cache, Gateway,
   Normalisierung unverändert); pgstac-Gruppen über `super().post_search` mit
   einer Kopie des Suchmodells (eigene `collections`, `limit`, `token`,
   `datetime`); auch eine `GET`-Suche geht intern diesen Weg.
5. Items in Quellen-Reihenfolge aneinanderhängen; Links je Item für seine
   eigene Collection umschreiben (wie `_to_item_collection` heute).
6. Neue Marke: je Quelle, die noch weitere Seiten hat, ihre innere Marke;
   erschöpfte fallen weg. Keine offene Quelle mehr → kein `next`-Link.

`numberMatched` fehlt in der gemischten Antwort immer. Eine Summe wäre nur
richtig, wenn jede Quelle eine Zahl liefert; pgstac (Context aus) und EOPF
liefern nie eine (§2.2, `eopf_stac.py`). Weglassen statt raten, wie bei
`_to_item_collection` heute.

### 4.3 Die Seitenmarke

- **Gemischte Marke:** eigenes, versioniertes Format, Base64url über JSON wie
  die Adapter-Marke (Regel III): `{"v": 1, "k": "mixed", "h": <Fingerprint der
  ganzen Suche>, "s": {<Quelle>: <innere Marke>}, "f": {<Collection>: <Grund>}}`.
  Der Fingerprint deckt die sortierte Collection-Liste, `bbox`/`intersects`,
  `ids` und `datetime` ab, **nicht** `limit`. `f` hält ausgefallene Quellen
  fest (§4.4). Lebt in einem neuen Modul `api/mixed_search.py`;
  `federating_client.py` hat schon 570 Zeilen.
- **Adapter-Marke** (`adapters/federated_search.py`): bindet künftig an den
  Fingerprint **ohne** `limit`; der Cache-Schlüssel behält `limit`.
  `TOKEN_VERSION` 1 → 2. Einzelsuchen verhalten sich sonst unverändert.
- **Prüfungen:** Marke einer anderen Suche, Marke einer Einzelsuche in einer
  gemischten (und umgekehrt), eine Quelle in `s`, die zu dieser Suche nicht
  gehört, eine pgstac-Marke, deren Collection nicht in ihrer Gruppe liegt,
  `prev:` → jeweils `400` mit eigenem Text, nie der Text einer Quelle. Eine
  gemischte Marke, die an eine reine pgstac-Suche geht, wird erkannt und
  abgewiesen, statt sie pgstac vorzulegen.
- Länge: drei innere Marken ergeben rund 600 Zeichen, weit unter der
  URL-Grenze des Gateways (8 kB) und für den `next`-Link einer `GET`-Suche
  unkritisch.

### 4.4 Ausfall und Zeitablauf einer Quelle (→ F2)

- Jede föderierte Quelle bekommt in der gemischten Suche ein **Zeitbudget von
  10 s** je Seite (`asyncio.wait_for`), unter dem Lese-Zeitlimit des Gateways
  (15 s), mit Abstand über der langsamsten gemessenen Antwort (3,8 s, §2.3).
  Einzelsuchen behalten ihr heutiges Verhalten.
- Scheitert eine Quelle (Zeitablauf, nicht erreichbar, Fehlerstatus der
  Quelle, unlesbare Antwort), kommen die Items der übrigen mit `200`; die
  Antwort trägt
  `"incomplete_collections": [{"collection": "…", "reason": "timeout"}]`,
  Gründe `timeout`, `unreachable`, `upstream_error`, `unrecognised_answer`.
  Die ausgefallene Quelle fällt für den Rest des Blätterns heraus und steht in
  `f` der Marke, sodass **jede** folgende Seite den Vermerk wiederholt — auch
  die letzte.
- Antwortet auf einer Seite **keine** Quelle, gilt wie heute bei der
  Einzelsuche: `504`, wenn alle in den Zeitablauf liefen, sonst `502`. Die
  Marke bleibt dieselbe; ein erneuter Versuch ist möglich.
- Ein Fehler der eigenen Datenbank ist kein Teilergebnis, sondern wie heute
  ein Fehler der ganzen Anfrage.
- Log: eine Zeile je ausgefallener Quelle mit Collection und Grund, ohne
  Koordinaten (M3-16).

### 4.5 Zeitachse in der gemischten Suche (→ F4)

`datetime` gilt je Quelle: Eine Collection ohne Zeitachse
(`time_range=False`, der DEM) wird nie nach Datum gefiltert (Nachtrag 2 zu
M3-12, Punkt 2), die übrigen schon. `ignored_filters` bleibt eine Liste und
heißt künftig ausdrücklich „für mindestens eine gesuchte Collection nicht
angewandt“; so beschreibt es der Kommentar in `api.ts` bereits. Welche das
ist, liest ein Client an `earthx:capabilities.time_range` der Collection ab;
der Viewer hat das als `hasTimeAxis` schon.

Folge für mehrere eigene Collections mit und ohne Zeitachse: Heute gilt
`datetime` dort für alle (auch den DEM); künftig bilden sie zwei pgstac-Gruppen
(§4.2 Schritt 2). Mit dem DEM als einziger eigener Collection kommt der Fall
heute nicht vor.

### 4.6 CQL2 (`filter`) neu geprüft (→ F3)

Regel VI hat CQL2 in M1 abgeschaltet, weil es keine eigenen Items gab. Jetzt
gibt es eine eigene Collection, den DEM. Seine Items tragen außer dem
Aufnahmezeitraum und `gsd` keine Eigenschaft, nach der man filtern würde
(`adapters/cop_dem_bucket.py`); was bleibt, decken `bbox`/`intersects` und
`datetime` schon ab. Earth Search kann kein CQL2 (§2.3), EOPF schon.

Wie ein Client erkennen könnte, wo CQL2 wirkt: Standard nach OGC API Features
Teil 3 ist die Konformitätsklasse auf der Landing Page, dazu je Collection ein
Link `rel=…/queryables`. Die Konformitätsklasse gilt aber für die ganze API;
sie auszuweisen, solange Earth Search mitsucht, bricht K8.

**Empfehlung:** CQL2 bleibt aus. Landing Page ohne `filter`, `filter` weiter
`400`. Neu zu prüfen, sobald eine eigene Collection Eigenschaften trägt, nach
denen sich filtern lässt (frühestens mit dem Harvester in M5). Dann über
`queryables` je Collection, und `filter` auf einer Suche, die eine Collection
ohne Unterstützung berührt, bleibt `400`.

### 4.7 `query` und `fields` (Befund §2.2, → F5)

**Empfehlung:** Beide Extensions abschalten (`_ENABLED_EXTENSIONS =
["pagination"]`), `query` und `fields` wie `filter` mit `400` abweisen, auch
an `GET /collections/{id}/items`. Die Landing Page verspricht dann nur noch,
was jede Quelle einlöst (K8). Beide Quellen könnten beides (§2.3); das
Durchreichen ist eine spätere Aufgabe, sobald jemand es braucht. Der Viewer
nutzt keine der beiden.

### 4.8 Frontend (→ F6)

- `api.ts`: `SearchQuery.collection` wird `collections: string[]`;
  `ItemPage` und `searchAllPages` tragen `incompleteCollections` (über alle
  Seiten gesammelt, nicht nur von der ersten wie heute `ignoredFilters`).
- `store.ts`: Alle Suchen schicken `[dataset.id]`. Der Viewer läuft damit
  schon über denselben Weg, den M3-10 dann auf mehrere Datensätze erweitert.
- **Für M3-10 festgehalten, hier nicht gebaut:** Mehrfachauswahl; Trefferliste
  und Gruppen über mehrere Datensätze; der Deckel von 300 Items gilt je Suche,
  nicht je Datensatz (mit Option 1 bekommt jeder Datensatz ab der ersten Seite
  seinen Anteil); der ±90-Tage-Fallback je Datensatz mit Zeitachse; Anzeige
  von `incomplete_collections`.

### 4.9 Nicht anfassen

`readers`, `access`, Tiler- und Coverage-Route, Registry (keine neuen Felder:
Budget und Anteile sind Plattformkonstanten, keine Eigenschaft eines
Datensatzes), `item_collection` für föderierte Collections (bleibt eine
Collection), `get_item`.

---

## 5. Tests (Abnahme)

Integration (echtes pgstac, Quellen per `MockTransport`, synthetische Items):

- **Gemischt eigen + föderiert:** synthetische materialisierte Collection +
  Earth Search; Items beider in einer Antwort, Links je eigener Collection,
  kein `numberMatched`; `GET` und `POST`; auch ohne `collections`.
- **Paging über die Grenze:** alle Seiten durchblättern → Vereinigung gleich
  der Vereinigung der Einzelsuchen, keine Dublette, keine Lücke; keine Seite
  größer als `limit`; eine Quelle erschöpft sich, die andere bekommt ab der
  nächsten Seite den ganzen Anteil; `limit=1` bei drei Quellen.
- **Ausfall einer Quelle:** `503`, nicht erreichbar, unlesbare Antwort,
  Zeitablauf (Budget im Test herabgesetzt) → `200` mit den übrigen und
  `incomplete_collections`; die Folgeseiten wiederholen den Vermerk und
  fragen die Quelle nicht mehr; alle Quellen fallen aus → `502` bzw. `504`.
- **Unbekannte Collection** in einer gemischten Liste → `404`, keine Anfrage
  nach außen.
- **`filter`** (und nach F5 `query`, `fields`) auf einer gemischten Suche und
  auf einer Collection ohne Unterstützung → `400`, keine Anfrage nach außen;
  Landing Page ohne `filter` (und nach F5 ohne `#query`/`#fields`).
- **Marken:** fremde Suche, geänderte Collection-Liste, Einzel- statt
  gemischte Marke und umgekehrt, manipulierte Quelle in `s`, kaputtes
  Base64, `prev:` → `400` ohne Text einer Quelle; eine Marke bleibt nach
  „Neustart“ (neuer App-Lebenszyklus) gültig (K3).
- **Zeitachse:** DEM-artige Collection ohne Zeitachse + Sentinel-2 mit
  `datetime` → DEM ungefiltert, Sentinel-2 gefiltert, `ignored_filters =
  ["datetime"]`.
- **`intersects` und `ids`** über eine gemischte Suche: an jede Quelle
  weitergereicht.
- **Einzelsuchen unverändert:** die bestehenden Tests bleiben grün; zusätzlich
  eine Adapter-Marke über zwei Seiten mit verschiedenem `limit`.
- **Log:** kein Koordinatenwert im Log einer gemischten Suche mit Ausfall.

Einheitstests: Anteile (Summe = `limit`, Rest, `limit < k`), Marke hin und
zurück, Fingerprint unabhängig von `limit` und Reihenfolge der Collections.

Vitest: `buildSearchBody` mit mehreren Collections, `searchAllPages` sammelt
`incompleteCollections` über alle Seiten.

Vor „fertig“: `ruff check backend`, `pytest`, `lint-imports --config
.importlinter`, `npm run lint`, `npx tsc -b --pretty false`, Vitest.

---

## 6. Umfang und Schnitt (→ F7)

Schätzung: Backend rund 300 Zeilen (neues Modul `api/mixed_search.py`,
Umbau `_dispatch_search`, Marke der Adapter, Extensions), Frontend rund 40,
Tests rund 450, Doku rund 60. Zusammen über dem Richtwert von 400 Zeilen,
davon mehr als die Hälfte Tests.

---

## 7. Risiken

| Risiko | Gegenmittel |
|---|---|
| Neue `TOKEN_VERSION` bricht Marken, die während des Deployments ausgegeben wurden | nur laufendes Blättern betroffen; `400` mit eigenem Text; der Viewer startet eine neue Suche |
| Parallele Anfragen belasten die Quellen stärker (K5) | je Seite genau eine Anfrage je Quelle, mit ihrem Anteil statt vollem `limit`; Gateway-Grenze von 6 Verbindungen je Host gilt weiter |
| Eine langsame Quelle bremst jede Seite | Budget 10 s je Quelle, danach Teilergebnis (§4.4) |
| `super().post_search` mit einer Kopie des Suchmodells hängt an der Form des pgstac-Modells | derselbe öffentliche Weg, den `post_search` heute für `datetime` schon nutzt (`model_copy`); Test gegen echtes pgstac |
| Abschalten von `query`/`fields` trifft einen externen Client | es gibt noch kein öffentliches Deployment; die Landing Page sagt es |

---

## 8. Doku und Log (bei der Umsetzung)

- `adr/0005`: Nachtrag zu Regel I (gemischte Suche umgesetzt, Verfahren nach
  F1), Regel III (gemischte Marke; Adapter-Marke ohne `limit`) und Regel VI
  (Ergebnis von F3); Originaltext bleibt stehen.
- `architekturplan.md` 5.2/5.3: gemischte Suche und Konformitätsklassen;
  16: Gegenmittel „Teilergebnisse mit Kennzeichnung“ als umgesetzt.
- `plans/m3-dritte-quelle-und-interface.md`: Stand von M3-13; Hinweise aus
  §4.8 an M3-10.
- `ENTSCHEIDUNGSLOG.md`: je eine Zeile für den Plan-Schritt (dieser PR) und
  für Ottos Antworten.

---

## 9. Fragen an Otto

**F1 — Paging-Verfahren (§3)**
1. Auffächern, Anteile je Seite neu verteilt; Adapter-Marke bindet nicht mehr
   an `limit`. **(Empfehlung)**
2. Auffächern mit festen Anteilen, Adapter unverändert; Seiten schrumpfen,
   wenn Quellen leer sind.
3. Nacheinander, eine Quelle nach der anderen.

**F2 — Ausfall einer Quelle (§4.4)**
1. Teilergebnis mit `200` und `incomplete_collections`; ausgefallene Quelle
   für den Rest des Blätterns heraus, Vermerk auf jeder Folgeseite; Budget
   10 s je Quelle. **(Empfehlung)**
2. Wie 1, aber die ausgefallene Quelle wird auf der nächsten Seite erneut
   gefragt.
3. Kein Teilergebnis: Fällt eine Quelle aus, scheitert die ganze Anfrage.

**F3 — CQL2 (§4.6)**
1. Bleibt aus; neu prüfen, sobald eine eigene Collection filterbare
   Eigenschaften hat. **(Empfehlung)**
2. Jetzt für eigene Collections einschalten, `queryables` je Collection,
   `filter` auf föderierten `400`. Landing Page weist dann `filter` aus,
   obwohl Earth Search es nicht kann (bricht K8 in der heutigen Lesart).

**F4 — `ignored_filters` in der gemischten Suche (§4.5)**
1. Bleibt eine Liste, „für mindestens eine Collection“; welche, steht an der
   Collection. **(Empfehlung)**
2. Zusätzlich je Collection: `{"cop-dem-glo-30": ["datetime"]}`.

**F5 — `query` und `fields` (Befund §2.2, §4.7)**
1. Beide abschalten und mit `400` abweisen. **(Empfehlung)**
2. An die föderierten Quellen durchreichen (beide können es).
3. Nicht in M3-13; eigene Aufgabe.

**F6 — Frontend in M3-13 (§4.8)**
1. `api.ts` mit Collection-Liste und `incompleteCollections`, der Viewer
   schickt `[dataset.id]`; alles Weitere in M3-10. **(Empfehlung)**
2. Kein Frontend in M3-13; M3-10 macht alles.

**F7 — Schnitt (§6)**
1. Ein PR mit getrennten Commits, rund 850 Zeilen, davon rund 450 Tests.
   **(Empfehlung)**
2. Zwei PRs: M3-13a gemischte Suche und Marke, M3-13b Extensions (F3/F5) und
   Frontend.
