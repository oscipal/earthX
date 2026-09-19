# M1-07 — STAC-API nach außen: Umsetzungsplan

**Status:** Plan, offen für Ottos OK. **Stufe B** laut `docs/plans/m1-fundament.md`
§3: Plan zuerst als Draft-PR, Umsetzung erst nach Ottos OK
(`projektplan.md` 1.2). Dieser PR ändert **keinen Produktivcode** — auch nicht
die zwei unten behandelten Nachträge aus M1-06.
**Aufgabe:** M1-07 aus `docs/plans/m1-fundament.md` §4, zusätzlich zwei
Nachträge aus M1-06 (siehe §7 und §8).
**Grundlage:** `architekturplan.md` 0 (STAC als Modell, zweistufiger Katalog,
ein Tor nach außen), 3.1 (Modulgrenzen; 7.3 betrifft die Processing-Ebene und
ist für M1-07 nicht einschlägig); `projektuebersicht.md` §2 Prinzipien 6
(„Standards raus") und 7
(„API-first"); `adr/0005` (Föderierte Item-Suche, alle sechs Regeln, §3.3,
§3.5, §3.7, §4, §6, §8 Punkt 5); `adr/0003` §11.2 (Attribution/Haftungssatz);
`adr/0002` §6 (CI-Befehle); `docs/ENTSCHEIDUNGSLOG.md` (STAC-Version/Lizenz-
Kopplung, die zwei offenen M1-06-Zeilen).
**Voraussetzungen — beide erledigt:** M1-04 (Registry, Katalogmodell, pgstac),
M1-06 (Earth-Search-Adapter, `earthx/adapters/`).

---

## 1. Ziel in einem Satz

Der eigene Katalog ist über `earthx.api` als STAC-API lesbar: Collections aus
dem eigenen pgstac, Items pro Collection entweder aus pgstac oder — für
`sentinel-2-c1-l2a` — live über `earthx.adapters.earth_search` föderiert,
ohne dass ein Client den Unterschied merkt außer an `earthx:source`.

## 2. Ausgangslage

- `backend/earthx/api/main.py` ist ein reiner Health-Stub (`FastAPI()`, ein
  `/health`); der Docstring verweist selbst auf M1-07.
- `stac-fastapi-pgstac` (und alles, was es an Fremdpaketen mitbringt) steht
  **noch nicht** in `backend/requirements.txt`. M1-07 fängt bei null an.
- `earthx.adapters.earth_search.search_items`/`get_item` und
  `earthx.catalog.search_cache.PostgresSearchCache` stehen fertig bereit;
  `adapters/cache.py:12` verweist ausdrücklich auf den künftigen Aufrufer
  „the `FederatingCoreCrudClient` in `api` from M1-07 on."
- `earthx.catalog.datasets.REGISTRY` kennt `sentinel-2-c1-l2a` mit
  `SourceInfo(adapter=AdapterKind.EARTH_SEARCH_V1, endpoint=..., source_collection_id=...)`;
  `catalog.collection.to_stac_collection` schreibt das als `earthx:source` in
  die Collection, die `catalog.pgstac.load_registry` nach pgstac schreibt.
- `earthx.api` darf laut 3.1 als einziges Modul `catalog` **und** `adapters`
  zusammen importieren — das ist die architektonische Grundlage dafür, dass
  die Verzweigung hier und nicht in `adapters` oder `catalog` selbst liegt.

## 3. Architekturentscheidung: `FederatingCoreCrudClient` (`adr/0005` Option 2)

Wie im angenommenen Spike entschieden, **Regel I**: eine Unterklasse von
`stac_fastapi.pgstac.core.CoreCrudClient`, die nur die vier öffentlichen
Methoden überschreibt — `item_collection`, `get_item`, `post_search`,
`get_search` — und **nicht** die private `_search_base` (§4, Gegen-Punkt der
Empfehlung: genau diese Bindung wird vermieden). Verzweigung je Methode:

1. Collection(s) aus dem Aufruf bestimmen (Pfadparameter oder `collections`
   im Suchkörper; keine `collections` angegeben oder mehrere → pro Collection
   aufteilen und zusammenführen, `adr/0005` §5 Regel I).
2. Für jede Collection **zuerst gegen das eigene pgstac prüfen**
   (`super().get_collection(...)` bzw. der interne Weg, den
   `CoreCrudClient` dafür schon hat) — unbekannt → `404`, das pgstac ohnehin
   wirft. Das deckt zugleich den Fall „Collection nie im Katalog" und
   „Collection im Katalog, aber pgstac gerade nicht erreichbar" mit
   pgstacs eigener Fehlerform ab, statt das doppelt zu bauen.
3. Gefundene Collection: `earthx:source.adapter` lesen.
   - Keine `earthx:source` oder ein unbekannter Wert → eigene Collection,
     `super()`-Aufruf (heutiger Stand: das ist in M1 immer der Fall, weil
     `sentinel-2-c1-l2a` die einzige Collection ist und föderiert wird —
     dieser Zweig hat also **noch kein** Beispiel, muss aber existieren,
     sobald ein zweiter, nicht-föderierter Datensatz dazukommt, ohne dass
     `FederatingCoreCrudClient` dafür geändert werden muss).
   - `AdapterKind.EARTH_SEARCH_V1` → `earthx.adapters.earth_search` aufrufen,
     mit der aus dem eigenen pgstac gelesenen `earthx:source.source_collection_id`
     als Ziel des Adapters, `gateway` und der `PostgresSearchCache` aus M1-06
     verdrahtet.

**Datenmodell-Übersetzung:** M1-06s `ItemPage.items` sind bereits vollständige
STAC-Items der Quelle (§4 des M1-06-Plans: „unverändert von der Quelle"), sie
müssen nur noch mit den Link-Objekten versehen werden, die
`stac-fastapi` von einer `ItemCollection`/Suchantwort erwartet
(`self`, `root`, `collection`, `next` mit unserer eigenen Marke aus
`ItemPage.next_page_token`). Das ist Übersetzungscode in
`FederatingCoreCrudClient`, keine Änderung an `adapters`.

## 4. Modulaufbau (Vorschlag)

```
backend/earthx/api/
  main.py                 instantiate_api() aus stac_fastapi.pgstac.app,
                           eigenes Präfix (§6), ENABLED_EXTENSIONS (§5),
                           FederatingCoreCrudClient als client=
  federating_client.py     FederatingCoreCrudClient, Collection-Verzweigung,
                           Item-/Suchantwort-Übersetzung aus adapters.ItemPage
  dependencies.py           Verdrahtung: Gateway-, Registry- und
                           SearchCache-Instanzen pro Request/Prozess
```

Nichts davon verletzt die Importregel: `api` darf alles (3.1); `adapters`,
`catalog` und `gateway` bleiben unverändert, wie in M1-06 §10 vorgesehen.

## 5. Zwei Datenbanktreiber nebeneinander (Reibungspunkt, **F1**)

`stac-fastapi-pgstac` verbindet über **`asyncpg` + `buildpg`**
(`stac_fastapi/pgstac/db.py`, `Requires-Dist: asyncpg`, `buildpg` im
Paket-Metadaten von `stac-fastapi.pgstac` 6.4.1 — geprüft an der echten
Paketmetadaten, nicht vermutet). Unser eigenes `catalog`-Modul verbindet
durchgehend über **`psycopg`** (`load.py`, `pgstac.py`, `search_cache.py`).
M1-07 bringt beide Treiber gegen dieselbe Postgres-Instanz zusammen: einen
`asyncpg`-Pool, den `stac_fastapi.pgstac.db.connect_to_db` selbst aufbaut und
den `CoreCrudClient` für alles nutzt, was er an `super()` durchreicht, und
einen `psycopg`-Pool für unsere eigenen Aufrufe (`REGISTRY`-Abgleich soweit er
über pgstac geht, `PostgresSearchCache`).

1. **Empfehlung: beide behalten, sauber getrennt.** Ein Umbau von M1-04/M1-06
   auf `asyncpg` wäre eine Rückwirkung auf bereits abgenommenen Code ohne
   fachlichen Gewinn, nur um einen zweiten Pool zu sparen. Zwei kleine Pools
   gegen eine `docker-compose`-Postgres mit Standardgrenzen sind unkritisch;
   `db_min_conn_size`/`db_max_conn_size` (stac-fastapi-Settings) und die
   eigene `psycopg`-Verbindung bleiben beide klein (Vorschlag: je 1–5),
   dokumentiert in `.env.example`.
2. Alternative: `PostgresSearchCache` auf `asyncpg` umschreiben, um den
   `stac-fastapi`-Pool mitzunutzen. Kostet eine Neuimplementierung von M1-06,
   für einen Pool, der in M1s Größenordnung nicht der Engpass ist.

## 6. Konformitätsklassen und `ENABLED_EXTENSIONS` (Regel VI)

**Befund an der echten Paketmetadaten von `stac-fastapi-pgstac` 6.4.1**
(`stac_fastapi/pgstac/app.py`, `models/extensions.py`): Ohne die
Umgebungsvariable `ENABLED_EXTENSIONS` sind **alle** Extensions an,
`filter` eingeschlossen — der Docstring sagt das ausdrücklich: „If the
variable is not set, enables all extensions." Regel VI verlangt aber, dass
die Landing Page in M1 **keine** `filter`-Konformitätsklasse führt. Das
bedeutet konkret: `ENABLED_EXTENSIONS` muss **explizit** gesetzt werden, ohne
`filter`.

**F2 — was noch außer `filter` ausschließen?** Vorschlag: auch **`sort`**
ausschließen. Das `sort`-STAC-Extension erlaubt einem Client, einen
beliebigen `sortby`-Schlüssel zu wählen; unser föderierter Pfad kann das für
Earth Search nicht einlösen, weil `adapters.earth_search.SearchParams`
(M1-06) kein Sortierfeld kennt — die Erweiterung müsste erst gebaut werden.
Damit gilt für `sort` dieselbe Begründung wie für `filter` in Regel VI:
nicht stillschweigend zusagen, was der föderierte Pfad nicht kann; **mit M3
neu zu prüfen**, wenn ohnehin CQL2 neu aufgerufen wird. `query`, `fields` und
die Standard-Pagination bleiben an.

**Konkreter Befund, der über „Extension ausschalten" hinausgeht:** Am
Quelltext von `stac_fastapi.types.search` und `stac_fastapi.api.models`
geprüft — `BaseSearchGetRequest`/`BaseSearchPostRequest` setzen **kein**
`extra="forbid"`. Ohne die `filter`-Extension kennt das erzeugte
Anfragemodell das Feld `filter` schlicht nicht, und Pydantics Vorgabe
(`extra="ignore"`) verwirft ein trotzdem mitgeschicktes `filter` **kommentarlos** —
genau das Verhalten, das der Abnahmefall „ein `filter`-Parameter wird nicht
stillschweigend verworfen" ausschließen soll. Das alleinige Ausschließen aus
`ENABLED_EXTENSIONS` reicht also **nicht**. `FederatingCoreCrudClient` (oder
eine vorgeschaltete Dependency) muss den Rohkörper (POST) bzw. die
Roh-Query (GET) selbst auf einen `filter`- oder `filter-lang`-Schlüssel
prüfen und mit `400` antworten, bevor das Anfragemodell ihn verwirft. Das ist
ein eigener Test in der Umsetzung, kein Nebeneffekt der Konfiguration.

## 7. Seitenmarke und `sortby` — Nachtrag aus M1-06

**Offener Punkt laut Log und M1-06-Plan §13:** `earthx.adapters.earth_search`
schickt bewusst kein `sortby`, verlässt sich also auf Earth Searchs
undokumentierte Vorgabesortierung; eine Sortierzusage nach außen sollte laut
`adr/0005` §8 Punkt 5 erst nach Prüfung an der Quelle erfolgen, weil eine
kaputte Marke exakt an der Feldzahl scheitert
(„`search_after has 1 value(s) but sort has 3`").

**Geprüft (drei Anfragen direkt gegen `earth-search.aws.element84.com/v1/search`,
nur Metadaten, keine AOI, vergleichbar mit dem Maßstab aus `adr/0005` §3):**

| `sortby` | Marke in `links[rel=next].body.next` |
|---|---|
| keins (Vorgabe) | `"<datetime>,<id>,<collection>"` — 3 Felder |
| `[{properties.datetime, desc}]` | `"<datetime>"` — 1 Feld |
| `[{id, asc}]` | `"<id>"` — 1 Feld |
| `[{properties.datetime, desc}, {id, asc}]` | `"<datetime>,<id>"` — 2 Felder |

Die Marke passt sich also **exakt** an die Zahl der mitgeschickten
Sortierfelder an, nicht an eine feste Zahl 3. Eine Folgeseite mit
`sortby` + der zurückgegebenen Marke funktioniert (Seite 2 mit
`sortby=[datetime desc]` setzt korrekt nach dem letzten Datum von Seite 1
fort, keine doppelten oder übersprungenen Treffer in der Stichprobe). Die
Quelle antwortet mit `200`, kein Fehler.

**Antwort auf die Ausgangsfrage:** Ja, die Seitenmarke verträgt `sortby` —
solange derselbe `sortby`-Wert bei **jeder** Folgeseite erneut mitgeschickt
wird (kein serverseitiger Zustand, Regel III gilt unverändert). Ein Risiko
bleibt: `properties.datetime` **allein** ist kein eindeutiger Schlüssel —
mehrere Kacheln derselben Szene können denselben Zeitstempel tragen. Ein
zweites Sortierfeld als Tie-Breaker behebt das, genau wie es die
undokumentierte Vorgabe der Quelle mit `id` und `collection` bereits tut.

**F3 — Empfehlung:** `earthx.adapters.earth_search._search_body` schickt ab
jetzt immer den festen Schlüssel
`sortby=[{"field": "properties.datetime", "direction": "desc"}, {"field": "id", "direction": "asc"}]`
mit — eine **eigene, deterministische** Vorgabesortierung statt der
undokumentierten der Quelle, unabhängig von einem künftigen `sort`-Extension-
Entscheid (§6 F2), weil sie nichts an einen Client zusagt, sondern nur unsere
eigene Vorgabe ersetzt. Der Wert ist konstant, kein Aufrufer-Parameter — er
gehört deshalb **nicht** in `_search_fingerprint` (der Cache-Schlüssel
bräuchte sonst eine nie wechselnde zusätzliche Komponente). Ändert sich der
Wert später (z. B. weil `sort` in M3 doch für Clients geöffnet wird), muss
die Token-Version (`{"v": 1, ...}`) hochgezählt werden, weil alte, im Cache
liegende Marken sonst mit der neuen Sortierung verwechselt würden. Das ist
eine Codeänderung in `earthx/adapters/earth_search.py` — technisch M1-06s
Modul, wird aber im Rahmen von M1-07 nachgezogen, wie im Log vermerkt.
*Alternative:* bei der undokumentierten Vorgabe bleiben. Nachteil: ein
stiller Verhaltenswechsel der Quelle bliebe unbemerkt (`adr/0005` §8 nennt
das „Annahme [A], nicht dokumentiert gefunden").

## 8. `docker-compose.yml`: fehlender `catalog.load`-Schritt — Nachtrag aus M1-06

**Bestätigt:** `docker-compose.yml` führt den Dienst `pgstac-migrate`
(`pypgstac migrate`) aus, aber an keiner Stelle im Repo läuft
`python -m earthx.catalog.load`. Ein frischer `docker compose up` hat damit
weder die `sentinel-2-c1-l2a`-Collection noch die Migration
`002_search_cache.sql` (Such-Cache-Tabelle) — beides braucht die STAC-API,
sobald sie läuft. Der offene Log-Eintrag weist das bereits M1-07 zu.
`earthx/catalog/load.py` existiert fertig und idempotent (`main()`:
Migrationen anwenden, Registry laden, committen), ruft aber selbst kein
`pypgstac migrate` auf (eigene, kleinere Migrationen vs. das pgstac-Kernschema
sind getrennte Zuständigkeiten).

**F5 — Vorschlag:** ein weiterer One-Shot-Dienst `catalog-load`, analog zu
`pgstac-migrate`:

```yaml
catalog-load:
  build:
    context: ./backend
  command: ["python", "-m", "earthx.catalog.load"]
  environment:
    PGHOST: postgres
    PGPORT: "5432"
    PGUSER: ${POSTGRES_USER}
    PGPASSWORD: ${POSTGRES_PASSWORD}
    PGDATABASE: ${POSTGRES_DB}
  depends_on:
    pgstac-migrate:
      condition: service_completed_successfully
  restart: "no"
```

`api` bekommt zusätzlich `depends_on: catalog-load: condition:
service_completed_successfully` (neben den bestehenden `postgres`/`minio`-
Bedingungen) — `tiler`, `worker`, `harvester` bleiben unverändert, sie
brauchen die Collection in M1 nicht. Der M1-08-CI-Job, der die Topologie
hochfährt und Health-Endpunkte prüft, deckt das mit ab, sobald `api`
erst nach erfolgreichem `catalog-load` gesund werden kann.

## 9. Präfix (**F4**)

Der Prototyp belegt `/api` (`backend/app/main.py:33`) und `/` (Startseite).
Vorschlag: eigenes Präfix **`/stac`** über `Settings(prefix_path="/stac")`
(existiert als Konfigurationsfeld in `stac_fastapi.pgstac.config.Settings`;
`ApiSettings` setzt kein `env_prefix`, die Umgebungsvariable heißt demnach
schlicht `PREFIX_PATH` — in der Umsetzung am laufenden Prozess zu
bestätigen) — kollidiert mit keiner
bestehenden Route, macht in einem STAC-Browser sofort erkennbar, was er vor
sich hat.

## 10. STAC-Version und Lizenzwert — nur eine Prüfpflicht, keine Entscheidung

`docs/ENTSCHEIDUNGSLOG.md` (2026-09-19) hält bereits fest: STAC 1.0.0 →
`license: "proprietary"`, STAC 1.1 → `license: "other"`, abgeleitet aus der
ausgelieferten Version, „entscheidet die `stac-fastapi-pgstac`-Version in
M1-07". Im Changelog von `stac-fastapi-pgstac` 6.4.0 steht: „Sort
conformance class version to v1.1.0 instead of v1.0.0" — das betrifft
zunächst nur die Konformitätsklasse der Sort-Extension, nicht das Feld
`stac_version` der Landing Page/Collections selbst. Dieses kommt aus
`stac_pydantic.version.STAC_VERSION`, also aus einer **transitiven**
Abhängigkeit mit Versionsspanne (`stac-pydantic<4.0,>=3.3.0`), nicht direkt
aus dem `stac-fastapi-pgstac`-Pin — der Wert kann sich damit auch ohne
Änderung unseres Pins verschieben. **Keine Vermutung an dieser Stelle:**
Die Umsetzung muss die tatsächlich ausgegebene `stac_version` messen und
mit einem Test festnageln, welcher Lizenzwert (`proprietary`/`other`) dabei
laut der bestehenden Ableitungsregel herauskommt. Das ist eine
Prüfpflicht in der Umsetzung, keine Entscheidung, die dieser Plan schon
trifft.

## 11. `requirements.txt` (**F6**)

Neu: `stac-fastapi.pgstac` (bringt `stac-fastapi.api`, `stac-fastapi.types`,
`stac-fastapi.extensions`, `asyncpg`, `buildpg`, `cql2`, `orjson`,
`brotli-asgi` u. a. mit). Registry-Abfrage: aktuell verfügbar sind 2.0.0 bis
7.0.0. Laut Changelog wurde die pgstac-Testgrundlage in 6.3.0 von 0.8.6 auf
höhere Versionen angehoben; unser Schema-Pin ist `pypgstac[psycopg]==0.9.12`
(`requirements.txt`). Vorschlag: eine **6.4.x**-Version pinnen (letzte vor
7.0.0, das frisch veröffentlicht und ungeprüft ist), exakter Patch-Level erst
in der Umsetzung gegen die echte `docker-compose`/CI-Postgres verifiziert —
ein Fehlschlag zeigt sich sofort und laut (unbekannte SQL-Funktion o. Ä.),
nicht still falsch. `pystac-client` bleibt gesperrt (Regel IV, unverändert
aus M1-06) und wird **nicht** durch `stac-fastapi`s eigene Abhängigkeiten
eingeschleust — keines der oben genannten Pakete zieht es mit.

## 12. Bewusst nicht in diesem PR

| Was | Warum |
|---|---|
| Jede Codeänderung (auch die in §7 und §8 skizzierten) | Stufe B: erst Ottos OK, dann Umsetzung |
| `filter`/CQL2 aktivieren | Regel VI, gilt unverändert bis M3 |
| `sort`-Extension für Clients öffnen | F2 — der föderierte Pfad kann es noch nicht einlösen |
| Transactions-, Catalogs- (Multi-Tenant-), Free-Text-Extension | nicht angefragt, Vorgabe ohnehin aus |
| Kacheln, Quicklooks | M2 (`m1-fundament.md` §2) |
| Umbau von `catalog`/`adapters` auf `asyncpg` | §5, kein fachlicher Gewinn in M1 |

## 13. Tests (Abnahme, für die Umsetzungs-PR(s))

| Gruppe | Fälle |
|---|---|
| Konformität (T-C: die laufende API braucht Postgres/pgstac, `adr/0002` §2 — nicht T-B, das ohne Datenbank auskommt) | automatischer Konformitätstest; Landing Page führt keine `filter`-Konformitätsklasse; `sort` ebenso, falls F2 wie vorgeschlagen entschieden wird |
| `filter` nicht still verworfen | ein `filter`-Parameter (GET **und** POST) ergibt `400`, nicht `200` mit ignoriertem Feld |
| Verzweigung (T-B, `MockTransport` hinter `gateway`) | `sentinel-2-c1-l2a`-Suche geht über den Adapter (Cache-Treffer erspart den Aufruf, prüfbar wie in M1-06); eine unbekannte Collection ergibt `404` aus dem eigenen pgstac, nie eine leere Earth-Search-Antwort |
| Item-Übersetzung | `ItemPage` → STAC-`ItemCollection` mit korrekten `next`-Links (eigene Marke aus M1-06, nie die durchgereichte) |
| `sortby`-Nachtrag (§7) | Paging über zwei Seiten mit festem `sortby`; eine kaputte Marke ergibt weiterhin unseren eigenen Fehler, nie den Elasticsearch-Text |
| compose (§8, CI-Job aus M1-08) | frischer `docker compose up`: `catalog-load` läuft nach `pgstac-migrate` durch, `api` wird erst danach gesund, `GET /stac/collections` listet `sentinel-2-c1-l2a` |
| STAC-Version/Lizenz (§10) | ein Test liest `stac_version` der laufenden API und die ausgegebene Collection-Lizenz und vergleicht sie gegen die Ableitungsregel |
| Anleitung (Abnahme M1-07 laut `m1-fundament.md`) | Schritt-für-Schritt im PR, wie Otto lokal einen STAC-Browser auf `/stac` richtet |

## 14. Risiken

| Risiko | Umgang |
|---|---|
| `stac-fastapi.pgstac`-Version passt nicht zu `pypgstac==0.9.12` (Schema-Drift) | in der Umsetzung zuerst gegen die Cloud-Postgres/CI prüfen, bevor die restliche Verkabelung folgt; F6 |
| Zwei Connection-Pools (asyncpg, psycopg) sprengen `max_connections` in engen Umgebungen (CI, kleine compose-Postgres) | beide Pools klein halten (§5), in `.env.example` dokumentieren |
| `sort`/`filter` doch stillschweigend erreichbar über einen Umweg (z. B. `fields`-Extension kombiniert mit rohem Query-String) | eigener Test pro Extension, nicht nur „Konformitätsklasse fehlt" |
| PR über dem 400-Zeilen-Richtwert (M1-fundament.md §6 nennt das Risiko schon für M1-03/04/06) | Umsetzung ggf. in mehrere PRs schneiden (z. B. Grundverkabelung+Verzweigung getrennt von §7/§8-Nachträgen), wie bei M1-03/M1-06 — konkreter Schnittvorschlag folgt mit Ottos Antworten zu F1–F6 |

## 15. Fragen an Otto

**F1 — zwei DB-Treiber nebeneinander (§5).** Empfehlung: **ja**, sauber
getrennt, kein Umbau von M1-04/M1-06.

**F2 — `sort`-Extension zusätzlich zu `filter` ausschließen (§6)?**
Empfehlung: **ja**, mit M3 neu zu prüfen.

**F3 — eigener fester `sortby` in `earth_search.py` statt der
undokumentierten Vorgabe (§7)?** Empfehlung: **ja**,
`[properties.datetime desc, id asc]`.

**F4 — API-Präfix (§9).** Empfehlung: **`/stac`**.

**F5 — compose-Nachtrag `catalog-load` (§8).** Empfehlung: **wie skizziert**,
als eigener One-Shot-Dienst nach `pgstac-migrate`, `api` wartet darauf.

**F6 — `stac-fastapi.pgstac`-Version (§11).** Empfehlung: **eine 6.4.x-Version**,
Patch-Level in der Umsetzung verifiziert; nicht das frische `7.0.0` ungeprüft.

Die Umsetzung beginnt erst mit Ottos Antwort (Stufe B). Jede Abweichung, die
sich beim Bauen ergibt, kommt wie bei M1-03 und M1-06 als eigener Abschnitt
in dieses Dokument und als Zeile ins Entscheidungslog.
