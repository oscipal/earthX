# M3-11a — Materialisierte Quellen in Registry, Dispatch und Item-Abruf: Plan-Schritt

**Status (26.09.2026):** Plan-Schritt, wartet auf Ottos Freigabe (§7).
**Aufgabe:** M3-11a aus `docs/plans/m3-dritte-quelle-und-interface.md` §4
(P24, K-03, K-05). **Stufe B.**
**Grundlagen:** `adr/0009` §3.5, §7, §11; `adr/0005` Regeln I und VI;
`plans/m3-02-konformitaetsbericht.md` K-03, K-05, K-26 und Antwort 2;
`architekturplan.md` 3.1, 5.1, 5.2; `KLAERUNGEN.md` B10, B11, B13.

Belegstufen wie in `adr/0009`: **M** gemessen in dieser Sitzung, **P** am
Quelltext gelesen (Stand `main` 7e18d8d), **A** eigene Ableitung.

**Reihenfolge:** Laut Wellenplan (Fassung 2, §3) sollte M3-22 vor M3-11a
laufen. M3-22 ist noch offen. M3-11a hängt fachlich nicht daran, und die
Dateien überschneiden sich nur in `api/tiler.py`: M3-22 arbeitet im
Download-Schreibpfad, M3-11a an Item-Abruf und Lizenzprüfung.

---

## 1. Ziel

Die Plattform erkennt eine Collection, deren Items in pgstac liegen, als eigene
Art von Quelle. Sie ist über `/stac/search` findbar und über die Kachel- und
Download-Route lesbar, auch bevor der DEM eingetragen ist. Dazu kommt die
Lizenzprüfung an der Kachelroute (K-03), und `catalog` kann Items schreiben
(für M3-11b).

---

## 2. Befund

### 2.1 Ein Feld trägt zwei Fragen — **[P]**

- `SourceInfo.adapter: AdapterKind` ist Pflicht (`catalog/registry.py`
  Z. 199–214) und kennt nur `earth-search-v1` und `eopf-stac-v1`.
- `api/federating_client.py::_adapter_of` (Z. 316–331) liest
  `earthx:source.adapter` aus dem Collection-Dokument in pgstac. Ist der Wert
  ein bekannter `AdapterKind`, wird föderiert. Fehlt `earthx:source` oder ist
  der Wert unbekannt, gibt die Funktion `None` zurück, und die Anfrage läuft über
  `super()` (pgstac).
- Damit gilt heute eine Collection genau dann als materialisiert, wenn **kein
  bekannter Adapter** eingetragen ist. P24 schließt genau das aus. Ein
  Tippfehler im Adapterwert würde außerdem still zu einer leeren,
  gültig aussehenden Antwort (K-05, gegen `adr/0005` Regel I).
- M3-11b bringt für den DEM einen **neuen `AdapterKind`**, weil die Items von
  einem Adapter erzeugt werden. Ohne neues Feld würde der Föderationscode den
  DEM dann als föderiert behandeln und `adapters.search_items` aufrufen. Dort
  gibt es für ihn keine Suche.

### 2.2 Item-Abruf für Kacheln und Download — **[P]**

- `api/tiler.py::build_item_source` (Z. 705–721) holt jedes Item über
  `adapters.get_item`. Das ist der einzige Weg. Für ein Item in pgstac fehlt ein
  zweiter Weg.
- `_lifespan` (Z. 724–731) baut die Item-Quelle mit dem modulweiten
  `REGISTRY`, nicht mit dem Registry-Objekt, das `build_app(registry)` bekommt.
  Ein Test mit eigener Registry erreicht den echten Item-Abruf deshalb nicht.
  Das ist heute folgenlos, weil jeder Tiler-Test `earthx_item_source` ersetzt.
- pgstac 0.9.12 bringt `pgstac.get_item(_id, _collection)` und
  `pgstac.upsert_items(jsonb)` mit, beide mit `search_path=pgstac, public` **[M]**
  (in der Datenbank der Sitzung abgefragt). `pypgstac.load.Loader` öffnet eine
  eigene Verbindung (`PgstacDB`) **[M]**.

### 2.3 Lizenzstufe an der Kachelroute — **[P]**

- Der Download verlangt `LicenseTier.PROCESSING` (`api/tiler.py`, Z. 487).
- Kachel, `/statistics`, `/info`, `/point` und `/tilejson.json` laufen über
  `dataset_asset_path` bzw. `_viewer_zoom_range` und prüfen die Stufe nicht.
- Otto hat am 23.09.2026 (M3-02, Antwort 2, Option 1) entschieden: Kacheln
  verlangen mindestens „Anzeige“. Dazu kommt eine Registry-Prüfung, dass
  Einträge der Stufe `catalog` kein `viewer` tragen.

### 2.4 Was schon geht — **[P]**

- Suche, Item-Abruf und `item_collection` über `super()` arbeiten für eine
  Collection mit Items in pgstac bereits, mit Paging, `intersects` und `ids`
  (`adr/0009` §3.5).
- `item_collection` prüft `filter`, `sortby`, `ids` und `intersects` nur auf dem
  föderierten Zweig (Z. 212–215). Auf dem pgstac-Zweig würden diese Parameter
  still übergangen, gegen `adr/0005` Regel VI („nicht still verworfen“). Bisher
  gab es dort keine Collection, jetzt schon.

---

## 3. Vorgeschlagene Umsetzung

### 3.1 Registry: neues Feld `SourceInfo.item_holding` (→ F1, F2)

```python
class ItemHolding(Enum):
    """Where the items of a dataset live (architekturplan.md 5.2)."""
    FEDERATED = "federated"        # asked live at the source, through its adapter
    MATERIALIZED = "materialized"  # generated once by its adapter, held in our pgstac
```

- `SourceInfo.item_holding: ItemHolding`, **ohne Vorgabewert** (B10).
- `adapter` bleibt Pflicht und bedeutet künftig „welcher Adapter die Items
  abfragt (föderiert) bzw. erzeugt (materialisiert)“.
- Beide bestehenden Einträge setzen `item_holding=ItemHolding.FEDERATED`. Sonst
  ändert sich an ihnen nichts.
- `collection.to_stac_collection` gibt das Feld als
  `earthx:source.item_holding` aus.
- `architekturplan.md` 5.1, Zeile `earthx:source`: „Adapter-Typ,
  Item-Haltung (föderiert/materialisiert), Quell-ID, Harvest-Lauf“.

**Prüfungen am Eintrag** (`DatasetConfig.__post_init__`, → F4):

| Regel | Warum |
|---|---|
| `materialized` ⇒ `coverage.provider` ist `local-sql` | Ohne Such-API gibt es weder Aggregation noch Stichprobe an der Quelle. Die Coverage kommt aus den eigenen Items (M3-11c). |
| `federated` ⇒ `coverage.provider` ist nicht `local-sql` | Ohne eigene Items zählt `local-sql` nichts. Ergebnis wäre eine leere, gültig aussehende Coverage. |
| `federated` ⇒ `harvest_run is None` | Es gibt keinen Lauf, den das Feld beschreiben könnte. |
| `license.tier` ist `catalog` ⇒ `viewer is None` | K-03, Antwort 2 (entschieden) |

### 3.2 Suche: Dispatch nach `item_holding` (→ F5)

`FederatingCoreCrudClient._adapter_of` wird zu `_holding_of`:

- `federated` → föderiert wie heute (Adapter über `adapters.search_items` bzw.
  `adapters.get_item`)
- `materialized` → `super()` (pgstac)
- `earthx:source` fehlt, oder `item_holding` fehlt bzw. ist unbekannt → Fehler
  statt Rückfall (siehe F5)

Unverändert bleibt: Eine Suche über mehrere Quellen, auch
föderiert + materialisiert, wird wie heute mit `400` abgewiesen. Die gemischte
Suche kommt mit M3-13.

`item_collection` prüft `filter`, `sortby`, `ids` und `intersects` künftig **vor**
der Verzweigung, also auch auf dem pgstac-Zweig (§2.4). Suche und Einzelabruf
tun das schon.

`adapters._adapter_for` weist einen Eintrag mit `materialized` mit
`UnsupportedSource` ab. Ein materialisierter Datensatz hat keinen Such- oder
Abruf-Adapter, und ein solcher Aufruf wäre ein Dispatch-Fehler (heute ebenso für
einen unbekannten `AdapterKind`).

### 3.3 Item-Abruf im `tiler` (→ F6)

- **`catalog/pgstac.py`**, neu: `async def fetch_item(aconn, collection_id,
  item_id) -> dict | None` über `SELECT pgstac.get_item(%s, %s)`. Asynchron,
  weil der `tiler` den `psycopg`-Pool (`dependencies.cache_pool`) schon
  asynchron hält.
- **`api/tiler.py::build_item_source`** verzweigt nach dem Registry-Eintrag:
  `federated` → `adapters.get_item` wie heute, `materialized` →
  `catalog.fetch_item` über den Pool. Kein Item-Cache davor: Die Abfrage ist
  lokal, der Cache war für die Quelle da.
- Fehlerbilder:
  - Item nicht in pgstac → `404` „no item … in …“ (wie beim föderierten `404`)
  - materialisiert, aber kein Pool (Prozess ohne Datenbank) → `503`
    „the catalogue is not available“. Ohne Datenbank gibt es für diese Quelle
    keinen Weg; E5 („langsamer, nie falsch“) greift nur, wo die Quelle selbst
    antwortet.
  - Datenbankfehler → `503`, ohne Text aus der Datenbank
- **Zugriffsauflösung unverändert** (K-04, bis M4 in `api/tiler.py`): Jede
  Asset-`href` eines Items aus pgstac läuft durch dieselbe Policy
  (`asset_hosts`) und `check_url` wie heute.
- **`_lifespan`** baut die Item-Quelle aus `app.state.earthx_registry` statt aus
  dem Modul-`REGISTRY` (§2.2). Eine Zeile, nötig für den Integrationstest.

### 3.4 Lizenzstufe an der Kachelroute (K-03, entschieden)

Neue Funktion `_check_display_allowed(config)` in `api/tiler.py`. Sie wird als
Erstes in `dataset_asset_path` und `_viewer_zoom_range` aufgerufen, also noch
vor der Zoomprüfung und vor dem Item-Abruf, und antwortet bei Stufe `catalog`
mit `403`. Das gilt für Kachel, `/statistics`, `/info`, `/point` und
`/tilejson.json`. Den Download (`processing`) ändert das nicht.

### 3.5 `catalog` schreibt Items (für M3-11b, → F7)

**`catalog/pgstac.py`**, neu:
`upsert_items(conn, config, items: Iterable[dict]) -> int` (synchron, wie
`load_collection`).

- Weist einen Eintrag ab, der nicht `materialized` ist: Items einer föderierten
  Collection in pgstac wären eine zweite Wahrheit, die niemand liest (B13
  Punkt 3).
- Weist ein Item ab, dessen `collection` nicht `config.dataset_id` ist. Es
  überschreibt den Wert nicht.
- Schreibt in Blöcken (1 000 Items) über `SELECT pgstac.upsert_items(%s::jsonb)`
  und gibt die Anzahl zurück.
- Die Transaktion gehört dem Aufrufer, wie bei `load_registry`.
- Wiederholbar ohne Doppel (`upsert`). Entfallene Items löschen (`delsert`),
  ETag und Protokoll gehören zu M3-11b.
- `catalog` importiert dafür keinen Adapter (`.importlinter`).

### 3.6 `harvest_run` (→ F3)

Das Feld bleibt, wie es ist (`None` überall). Ein Registry-Eintrag ist Python-Code
und kann einen Lauf zur Laufzeit nicht festhalten: Der Einmal-Befehl kann nicht
in `datasets.py` schreiben, und was er in das Collection-Dokument in pgstac
schriebe, überschreibt `catalog.load` beim nächsten Start. Wo der Lauf samt ETag
von `tileList.txt` protokolliert wird (`adr/0009` §7.3), entscheidet M3-11b.

---

## 4. Tests

Alle Fixtures sind synthetisch. Die Collection heißt `earthx-test-materialized`,
das Item ist das `mini_cog` aus `tests/earthx/readers`.

**Einheit (T-A):**
- Registry:
  - `item_holding` ist Pflicht (`TypeError` ohne das Feld)
  - jede Regel aus §3.1 mit Positiv- und Negativfall
  - `catalog`-Stufe mit `viewer` → `ConfigError`
- `to_stac_collection` gibt `item_holding` aus.
- `adapters.search_items`/`get_item` mit einem materialisierten Eintrag →
  `UnsupportedSource`.
- Tiler mit synthetischer Registry:
  - Eintrag der Stufe `catalog`: Kachel, `/statistics`, `/info`, `/point` und
    `/tilejson.json` antworten `403`; der Download antwortet `403` wie bisher
    (K-26).
  - Die Abweisung kommt vor jedem Item-Abruf (die Item-Quelle wird nicht
    aufgerufen).
- `build_item_source`:
  - `materialized` ohne Pool → `503`
  - `federated` ruft weiter den Adapter

**Integration (T-C, echtes pgstac):**
- `upsert_items`:
  - schreibt synthetische Items; ein zweiter Lauf ändert die Anzahl nicht
  - föderierter Eintrag → Abweisung
  - fremde `collection` → Abweisung
- STAC-API, mit der synthetischen Collection und ihren Items in pgstac
  (eingetragen und nach dem Test wieder gelöscht, weil der API-Prozess eigene
  Verbindungen hat):
  - `GET`/`POST /stac/search` mit `collections=[…]` findet das Item, auch mit
    `ids` und `intersects`
  - `GET /collections/…/items/…` und `item_collection` liefern es
  - `filter` auf `item_collection` → `400`
  - kein Request an den Gateway-Transport
- Dispatch-Fehler: eine Collection in pgstac ohne `item_holding` → Antwort nach
  F5, **keine** leere Seite
- Tiler mit echtem Pool und echtem `build_item_source`:
  - eine Kachel und ein Zuschnitt des synthetischen Items aus pgstac
  - ein unbekanntes Item → `404`
- Föderiert unverändert: Die bestehenden Tests in `test_api_federating.py`,
  `test_tiler*.py` und `test_download_route.py` bleiben ohne inhaltliche
  Änderung grün.
- Die Onboarding-Checkliste bleibt für beide bestehenden Datensätze grün.
- `lint-imports` grün.

**Umfang geschätzt [A]:** rund 200 Zeilen Code und Doku, rund 350 Zeilen Tests.
Zusammen liegt das über dem Richtwert von 400 Zeilen (→ F8).

---

## 5. Nicht in dieser Aufgabe

- `readers` (unverändert, M3-Abnahme)
- die Coverage-Route und `local-sql` (M3-11c)
- DEM-Adapter, neuer `AdapterKind`, Einmal-Befehl, Registry-Eintrag, ETag,
  `delsert` (M3-11b)
- gemischte Suche (M3-13)
- Frontend: Quicklooks eines `catalog`-Datensatzes, die der Browser direkt von
  der Quelle lädt, bleiben ungeprüft. B11 nennt „Quicklooks über eigene
  Dienste“; das gehört zu M3-12.
- Verlagerung der Zugriffsauflösung (K-04, M4)

---

## 6. Übergang

Nach dem Merge tragen die Collection-Dokumente in einer bestehenden Datenbank
`item_holding` erst, wenn `catalog-load` neu gelaufen ist. `catalog-load` läuft
bei jedem `docker compose up` vor `api` (`docker-compose.yml`, Z. 52–55,
125). Mit F5 Option 1 antwortet eine Suche bis dahin mit `500`, statt still den
falschen Weg zu nehmen. Lokal heißt das: einmal `docker compose up` bzw.
`python -m earthx.catalog.load`.

---

## 7. Fragen an Otto

**F1 — Form des neuen Felds**
1. `SourceInfo.item_holding: ItemHolding` mit den Werten `federated` und
   `materialized`; `adapter` bleibt für beide Arten. **(Empfehlung)**
2. Zwei Typen `FederatedSource` und `MaterializedSource` statt eines
   `SourceInfo`. Das ist strenger typisiert, ändert aber jede Stelle, die
   `config.source` liest.
3. Den Unterschied aus einer Menge „materialisierter“ `AdapterKind`-Werte
   ableiten. Das mischt die beiden Fragen wieder (gegen P24).

**F2 — Name**
1. `item_holding` („Haltung“ wie in `architekturplan.md` 5.2) **(Empfehlung)**
2. `items`
3. `item_store`

**F3 — `harvest_run`**
1. Das Feld bleibt ungenutzt. M3-11b entscheidet, wo der Lauf protokolliert
   wird (Vorschlag dort: eigene Tabelle per Migration). Ob das Feld entfällt,
   klärt M3-14. **(Empfehlung)**
2. Das Feld jetzt entfernen.
3. Der Einmal-Befehl schreibt den Lauf in das Collection-Dokument in pgstac.
   Das kollidiert mit `catalog.load`, das das Dokument aus der Registry
   neu schreibt.

**F4 — Prüfungen am Eintrag (§3.1)**
1. Alle vier Regeln. **(Empfehlung)**
2. Nur die entschiedene (`catalog` ⇒ kein `viewer`).

**F5 — Collection in pgstac ohne gültiges `item_holding`**
1. `500` mit Log-Zeile „collection not loaded from the registry“; kein
   Rückfall auf pgstac (K-05, Regel I). **(Empfehlung)**
2. Wie heute als materialisiert behandeln.

**F6 — Weg zum Item im `tiler`**
1. `catalog.fetch_item` über `pgstac.get_item` und den vorhandenen
   `psycopg`-Pool. **(Empfehlung)**
2. HTTP-Aufruf an den STAC-Endpunkt des Prozesses `api`. Das wäre eine
   interne API als Abhängigkeit zwischen den Prozessen.
3. `pypgstac` mit eigener Verbindung je Abruf.

**F7 — Schreiben der Items**
1. `pgstac.upsert_items` in Blöcken über die übergebene `psycopg`-Verbindung;
   die Transaktion gehört dem Aufrufer. **(Empfehlung)**
2. `pypgstac.Loader` mit `Methods.upsert`. Der öffnet eine eigene Verbindung
   und lässt sich schlechter in einer zurückgerollten Test-Transaktion prüfen.

**F8 — PR-Größe**
1. Ein PR, obwohl er mit Tests über 400 Zeilen liegt. Die Teile sind nur
   zusammen prüfbar, wie bei M3-17. **(Empfehlung)**
2. K-03 (Lizenzprüfung, rund 120 Zeilen mit Tests) als eigener PR vorab.
