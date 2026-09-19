# M1-06 — Earth-Search-Adapter: Umsetzungsplan

**Status:** **Umgesetzt am 19.09.2026.** Von Otto angenommen, **F1 bis F5 wie
empfohlen**; **F6 (Lizenz für aufgezeichnete Fixtures) bleibt offen**, die Fixtures
sind deshalb synthetisch. Die drei Schritte aus F1 liegen als drei Commits in **einem**
PR statt in drei — die Sitzung ist an einen Branch gebunden; der Schnitt bleibt am
Commit ablesbar. **Stufe B** laut `docs/plans/m1-fundament.md` §3: Plan zuerst als
Draft-PR, Umsetzung nach Ottos OK (`projektplan.md` 1.2).
**Aufgabe:** M1-06 aus `docs/plans/m1-fundament.md` §4.
**Grundlage:** `architekturplan.md` 3.1, 5.1, 5.2, 6.1; `KLAERUNGEN.md` B8, B9, B13;
`adr/0001` §7 (Z1), §8, §9.3; `adr/0003` §11.2 (Sentinel-2 L2A, Legal Notice);
`adr/0004` §5, §6 (Coverage-Felder, Cache-Fristen); `adr/0005` (Föderierte
Item-Suche, alle sechs Regeln); `adr/0002` §2 (T-A/T-B/T-C/T-D).
**Voraussetzungen — alle erledigt:** M1-02 (Paketgerüst, Importregeln scharf),
M1-03 (Gateway, `earthx/gateway/`), M1-04 (Registry und pgstac, `earthx/catalog/`),
M1-05 (Spike, `adr/0005` angenommen).

---

## 1. Ziel in einem Satz

`earthx.adapters.earth_search` beantwortet Item-Suche und Einzel-Item-Abruf für
`sentinel-2-c1-l2a` über Earth Search v1 — jeder Aufruf durch `gateway`, jede
Antwort STAC-förmig wie ein eigenes Item, unabhängig davon, ob sie aus dem
Anwendungs-Cache oder live kommt.

## 2. Warum die Regeln aus `adr/0005` hier und nicht in M1-07 stehen

`adr/0005` Regel I sagt: Der `FederatingCoreCrudClient` liest `earthx:source` und
verzweigt je Collection — das ist die Verkabelung, sie gehört laut Aufgabenschnitt
zu M1-07 und lebt in `api` (3.1: „setzt alles zusammen", darf alles importieren).
M1-06 liefert das, wohin verzweigt wird: eine Funktion, die für **eine** Collection
Suche und Zugriffsauflösung beantwortet, mit allem, was `adr/0005` dafür verlangt
(Collection-Prüfung, eigene Seitenmarke, Cache-Fristen, Deckel). M1-07 ruft sie nur
noch auf. Ohne diese Vorarbeit könnte M1-06 seine eigenen Abnahmekriterien
(unbekannte Collection → 404-Fall, Cache-Test, Neustart-Test) gar nicht prüfen,
weil sie erst als HTTP-Antwort sichtbar würden.

## 3. Modulaufbau

```
backend/earthx/adapters/
  __init__.py          öffentliche Fläche: search_items, get_item, PageToken,
                        SearchParams, ItemPage, InvalidQuery, UnknownCollection
  earth_search.py       Earth-Search-Protokoll: Request bauen, Antwort lesen,
                        Fehlerformen abbilden, Seitenmarke kodieren/dekodieren
  cache.py               SearchCache-Protokoll (Struktur, keine Implementierung)

backend/earthx/catalog/
  search_cache.py        PostgresSearchCache: Tabelle earthx_search_cache lesen
                          und schreiben, TTL nach adr/0005 Regel II
  migrations/
    002_search_cache.sql  Tabelle earthx_search_cache
```

**Warum die Tabelle in `catalog` liegt, nicht in `adapters`:** `architekturplan.md`
3.1 weist `catalog` „pgstac, Suche" zu und die einzige eigene Migration bisher
(`M1-04b`) liegt dort. Die Importregel erlaubt `adapters → catalog` (die
Randbemerkung „nur Modelle" ist nicht maschinell geprüft, siehe §9 F2), aber nicht
umgekehrt — `catalog` darf `adapters` nicht importieren. Der Cache bleibt deshalb
hinter einem in `adapters` definierten `Protocol` (`cache.py`): `earth_search.py`
kennt nur `get`/`set`, nicht `psycopg`. Wer die konkrete `PostgresSearchCache`
zusammensteckt, ist Sache des Aufrufers — in M1-06 die T-C-Tests, ab M1-07 der
`FederatingCoreCrudClient` in `api`. So bleibt `adapters` frei von einer
Datenbankabhängigkeit, obwohl der Cache eine hat (analog zur Trennung von `Policy`
und `Gateway` in M1-03).

## 4. Schnittstelle

```python
# adapters/__init__.py, re-exportiert aus earth_search.py

@dataclass(frozen=True)
class SearchParams:
    bbox: tuple[float, float, float, float] | None
    datetime_range: tuple[datetime | None, datetime | None]
    limit: int = 10                      # Vorgabe, Regel V
    page_token: str | None = None        # unsere eigene Marke, Regel III

@dataclass(frozen=True)
class ItemPage:
    items: tuple[dict[str, object], ...]  # STAC Items, unveraendert von der Quelle
    matched: int | None                   # aus context.matched, wenn die Quelle es liefert
    next_page_token: str | None           # unsere Marke, oder None am Ende
    from_cache: bool

class InvalidQuery(ValueError):
    """bbox oder limit verletzen unsere eigenen Regeln (adr/0005 §3.5, Regel V)."""

class UnknownCollection(LookupError):
    """dataset_id ist nicht im eigenen Katalog (adr/0005 Regel I)."""

async def search_items(
    dataset_id: str,
    params: SearchParams,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> ItemPage: ...

async def get_item(
    dataset_id: str,
    item_id: str,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> dict[str, object]:
    """Wirft UnknownCollection oder gateway.UpstreamError(404, ...)."""
```

```python
# adapters/cache.py — Struktur, keine Postgres-Abhaengigkeit

class SearchCache(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, *, ttl_s: float) -> None: ...
```

`cache=None` ist ein gültiger Aufruf: Kein Cache bedeutet nur langsamer, nie ein
Fehler (E5) — genau der Zustand, den der Abnahmetest „geleerter Cache" prüft.

## 5. Die sechs Regeln aus `adr/0005`, umgesetzt

| Regel | Umsetzung |
|---|---|
| I — Collection zuerst gegen den eigenen Katalog prüfen | `registry.get(dataset_id)` zuerst; `UnknownDatasetError` aus `catalog.registry` wird zu `UnknownCollection` (eigener Typ hier, damit `adapters` keinen internen Katalogfehler nach außen reicht) |
| II — zwei Cache-Fristen | `_ttl_for(params) -> float`: `datetime_range`-Ende `None` oder < 7 Tage in der Vergangenheit → 300 s; sonst → 86 400 s. Einzel-Item (`get_item`) immer 86 400 s |
| III — eigene, undurchsichtige Seitenmarke | `_encode_token(dataset_id, search_hash, upstream_marker) -> str` (base64 von JSON), `_decode_token` das Gegenstück; der Elasticsearch-Text aus `adr/0005` §3.3 verlässt `earth_search.py` nie |
| IV — eigener Client, kein `pystac_client` | `gateway.Gateway.post_json` für `/search`, `.get` für `/collections/{id}/items/{id}`; kein neuer Import, `pystac_client` bleibt in `.importlinter` gesperrt |
| V — Seitengröße deckeln | `params.limit` wird vor dem Cache-Lookup geprüft (§6); Vorgabe 10 ist der Dataclass-Default |
| VI — kein CQL2 in M1 | betrifft M1-07 (Landing Page); hier gibt es ohnehin keinen `filter`-Parameter in `SearchParams` |

## 6. Eingabeprüfung — bei uns, nicht erst upstream (`adr/0005` §3.5)

Vor jedem Cache-Lookup und vor jedem Request an `gateway`:

- **bbox außerhalb ±90 Breite** → `InvalidQuery`. (Länge wird nicht geprüft; ein
  Datumsgrenzen-Fall ist laut `SpatialExtent` in `catalog.registry` ohnehin noch
  nicht unterstützt und hier kein neues Problem.)
- **verdrehte bbox** (`south >= north` oder `west >= east`) → `InvalidQuery`.
- **`limit > 100`** → `InvalidQuery` (siehe §9 F3 — Alternative wäre stilles
  Deckeln; Empfehlung ist die Ablehnung, konsistent mit der bbox-Prüfung).
- **`limit <= 0`** → `InvalidQuery`.

Diese vier Fälle sind die T-A-Tests der Aufgabe: reine Funktionen, kein Netz,
kein Postgres.

## 7. Anwendungs-Cache

**Schlüssel:** `sha256(dataset_id + normalisierte bbox + normalisierter
datetime_range + limit + page_token)`, hexdigest — „normalisiert" heißt: `bbox`
und Zeiten werden als ihre STAC-Textform gehasht, nicht als Python-Objekt (sonst
hasht `1.0` anders als `1`). Für `get_item` ist der Schlüssel
`dataset_id + item_id`, TTL immer 24 h (Regel II, dritte Zeile).

**Ablauf in `search_items`:**

1. Eingaben prüfen (§6).
2. Collection nachschlagen (§5, Regel I).
3. Cache-Schlüssel bilden, `cache.get(key)` — Fehler beim Cache (z. B. Postgres
   nicht erreichbar) werden geloggt und wie ein Fehltreffer behandelt (E5); ein
   Fehltreffer ist **kein** Fehler.
4. Bei Treffer: `ItemPage` aus dem gespeicherten JSON, `from_cache=True`.
5. Bei Fehltreffer: `gateway.post_json(...)`, Antwort in `ItemPage` übersetzen,
   `cache.set(key, ..., ttl_s=_ttl_for(params))` — auch dieser Schreibfehler wird
   nur geloggt, die Antwort geht trotzdem an den Aufrufer (E5 gilt für Lesen
   **und** Schreiben des Caches gleichermaßen; ein Fehlschlag beim Schreiben darf
   die Anfrage nicht scheitern lassen).

**Aufräumen:** keine eigene Aufräum-Aufgabe in M1. Eine Zeile wird beim Lesen auf
`expires_at` geprüft und bei Ablauf wie ein Fehltreffer behandelt; sie bleibt
liegen. Bei einer Collection und wenigen parallelen Nutzern ist das
Datenvolumen in M1 klein; ein Aufräum-Issue folgt, sobald das nicht mehr stimmt.

**Migration `002_search_cache.sql`:**

```sql
CREATE TABLE public.earthx_search_cache (
    cache_key   text PRIMARY KEY,
    dataset_id  text NOT NULL,
    payload     jsonb NOT NULL,
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX earthx_search_cache_expires_at_idx ON public.earthx_search_cache (expires_at);
```

`public.` ausdrücklich, aus demselben Grund wie `earthx_migrations` (M1-04b): pgstac
setzt `search_path = pgstac, public` auf seinen Rollen, eine unqualifizierte Tabelle
läge sonst im falschen Schema.

## 8. Restart-Sicherheit (`adr/0001` §8)

Der Abnahmefall „Neustart zwischen Suche und Item-Abruf ändert nichts" ist ein
Test, kein Zusatzcode: Eine Seitenmarke wird kodiert, ein neuer `Gateway` und eine
neue `PostgresSearchCache`-Instanz (oder `cache=None`) werden gebaut, und dieselbe
Marke wird dekodiert und aufgelöst. Weil `PageToken` nur Text ist und der Cache nur
über den Schlüssel angesprochen wird, gibt es keinen Prozessspeicher, der das
brechen könnte — der Test belegt das, er erzwingt es nicht.

## 9. Fragen an Otto

**F1 — Schnitt in PRs.** Adapter-Logik, Cache-Migration und -Anbindung, Fixtures
und der T-D-Workflow zusammen liegen deutlich über dem 400-Zeilen-Richtwert
(zum Vergleich: M1-03 kam auf drei PRs bei rund 900 Zeilen für weniger Umfang).
Vorschlag, analog zu M1-03:

1. **M1-06a** — `adapters/earth_search.py` ohne Cache: Eingabeprüfung (§6),
   Collection-Prüfung, Anfrage- und Antwortübersetzung, eigene Seitenmarke,
   Fehlerabbildung, synthetische Fixtures, T-A- und T-B-artige Tests mit
   `MockTransport` hinter `gateway`. `adapters/cache.py` nur als Protokoll, überall
   mit `cache=None` aufgerufen.
2. **M1-06b** — `catalog/search_cache.py`, `002_search_cache.sql`,
   Cache-Verdrahtung in `earth_search.py`, T-C-Tests (Treffer, Fehltreffer,
   TTL-Grenze, Cache-Ausfall macht nur langsamer, Neustart-Test).
3. **M1-06c** — Live-Smoke-Workflow (T-D) in `.github/workflows/`, zeitgesteuert,
   nie im PR-Lauf; Abnahmebericht-Notiz für M1-10.

*Empfehlung: ja, drei PRs.* Alternative: zwei PRs (a+b zusammen, wenn Otto den
Zeilenrichtwert hier lockern will), c bleibt wegen `.github/` ohnehin eigenständig
sichtbar.

**F2 — Cache hinter einem Protokoll in `adapters`, Implementierung in `catalog`
(§3).** Das hält `adapters` frei von `psycopg`, kostet aber eine zusätzliche
Naht, die M1-07 wieder zusammenstecken muss.
1. **So wie in §3 beschrieben** — Protokoll in `adapters`, `PostgresSearchCache`
   in `catalog`, Verdrahtung bei den Aufrufern (Tests jetzt, `api` ab M1-07).
2. Cache-Zugriff direkt in `adapters/earth_search.py` mit `psycopg`, dafür ein
   Ausnahmeeintrag im Importvertrag `http-only-in-gateway`-artig für `psycopg` in
   `adapters`.

*Empfehlung: 1.* Kein neuer Importvertrag nötig, und die Trennung entspricht der
bereits bestehenden zwischen `gateway.Policy` (Wert) und `gateway.Gateway`
(Ausführung).

**F3 — `limit > 100`: ablehnen oder deckeln (§6)?** Der Aufgabentext erlaubt
beides ausdrücklich.
1. **Ablehnen** (`InvalidQuery`), konsistent mit der bbox-Prüfung — der Aufrufer
   merkt sofort, dass sein Wert verworfen wurde, statt eine stillschweigend
   kleinere Seite zu bekommen.
2. Deckeln auf 100 und in der Antwort vermerken.

*Empfehlung: 1.*

**F4 — Unbekannte Collection: `UnknownDatasetError` aus `catalog.registry`
direkt durchreichen, oder in einen eigenen `adapters.UnknownCollection` packen
(§4)?**
1. **Eigener Typ in `adapters`** — die öffentliche Fläche von `adapters` hängt
   dann nicht an der genauen Fehlerhierarchie von `catalog`.
2. `UnknownDatasetError` direkt durchreichen.

*Empfehlung: 1.*

**F5 — Live-Smoke-Workflow (T-D): Häufigkeit und Rahmen.** `adr/0002` §2 sagt nur
„zeitgesteuert, nie im PR-Lauf"; kein Zeitplan steht in `docs/`.
1. **Täglich, ein Lauf**, nur Metadaten (`/collections/sentinel-2-c1-l2a`, eine
   kleine `/search`, ein `get_item` auf ein bekanntes, aktuelles Item) — hält die
   Rücksicht aus `adr/0005` §3.6 (K5) auch langfristig ein.
   Fehlschlag öffnet kein PR-rotes Signal, sondern nur den Workflow-Lauf selbst
   (sichtbar in den Actions, wie ein rot gewordener Cronjob).
2. Wöchentlich.

*Empfehlung: 1* — täglich, aber mit einer einzigen kleinen Anfrage, nicht mit
einem vollen Testlauf.

**F6 — Lizenz der Earth-Search-Metadaten für aufgezeichnete Fixtures.** `adr/0005`
§8 Punkt 1 lässt das ausdrücklich offen und der Aufgabentext verbietet, das hier
selbst zu entscheiden: **Diese Frage stellt der PR, er beantwortet sie nicht.**
Bis zur Klärung bleiben alle Fixtures synthetisch, nach dem Muster der in
`adr/0005` §3 gemessenen Formen (Antwortrumpf mit `context`/`numberMatched`,
`next`-Link als POST-Link mit Rumpf, die acht Fehlerformen aus §3.5).

## 10. Bewusst nicht in M1-06

| Was | Warum, und wann |
|---|---|
| `FederatingCoreCrudClient`, Einbindung in `api`, Konformitätsklassen | M1-07 — braucht `earthx:source` aus dem eigenen pgstac und lebt in `api` (einziges Modul, das `catalog` und `adapters` zusammen importieren darf) |
| `filter`/CQL2-Ausweisung oder -Ablehnung | M1-07, Regel VI |
| Coverage-Aggregation über den Adapter | M2 (`adr/0004`); die vierte Adapter-Fähigkeit „Aggregation" bleibt für M1-06 ungenutzt |
| Materialisierte Items, Harvester | betrifft nur Quellen ohne Such-API; Earth Search hat eine (`architekturplan.md` 5.2, Ausnahme greift nicht) |
| Aufräumen abgelaufener Cache-Zeilen | §7 — kein Risiko in M1s Größenordnung |
| Rate-Limiting am Adapter selbst | `gateway` trägt bereits den Deckel von 6 Verbindungen je Host (M1-03); ein weiterer Deckel hier wäre doppelt gehalten |

## 11. Tests (Abnahme)

| Gruppe | Fälle |
|---|---|
| Eingabeprüfung (T-A) | bbox-Breite außerhalb ±90; bbox verdreht; `limit` 0, negativ, 101, 100 (Grenze gültig); Vorgabe 10 ohne `limit` |
| Collection (T-A/T-B) | unbekannte `dataset_id` → `UnknownCollection`; bekannte `dataset_id` mit fremdem Adapter-Typ (falls je ein zweiter existiert) wird nicht heimlich als Earth Search behandelt |
| Suche (T-B, synthetische Fixtures) | leere Treffer (`matched: 0`); Upstream-`400`/`404`/`429` bleiben unterscheidbar (`gateway.UpstreamError.status_code`); `UpstreamTimeout`/`UpstreamUnreachable` propagieren statt eine leere Seite vorzutäuschen; Paging über zwei Seiten mit der eigenen Marke; eine kaputte fremde Marke (direkt an `_decode_token` gereicht) ergibt einen eigenen Fehler, nie den durchgereichten Elasticsearch-Text |
| Zugriffsauflösung (T-B) | `get_item` für ein vorhandenes Item; `get_item` für ein fehlendes Item → `404` bleibt `404` |
| Cache (T-C, gegen Postgres) | Treffer erspart den `gateway`-Aufruf (Zähler oder `MockTransport`-Assertion); Fehltreffer schreibt; TTL-Grenze bei 7 Tagen (Fenster schließt genau daran); Cache nicht erreichbar → Antwort kommt trotzdem, nur langsamer (E5); Neustart zwischen Suche und `get_item` (§8) |
| Wächter | `earth_search.py` importiert `psycopg` nicht (Grep-Test, analog zum bestehenden Importvertrags-Test) |

## 12. Risiken

| Risiko | Umgang |
|---|---|
| Cache-Schlüssel hasht `bbox`/`datetime` uneindeutig (z. B. `47.0` vs `47`) | Normalisierung über die STAC-Textform vor dem Hash (§7), mit Test belegt |
| Drei PRs verlängern den Review-Stau | Jeder PR ist für sich klein und abnehmbar, wie bei M1-03 |
| T-D-Workflow wird zu einer zweiten, ungeprüften Fehlerquelle in `.github/` | Nur eine kleine, seltene Anfrage (F5); Fehlschlag ist sichtbar, aber blockiert kein PR |
| Die Lizenzfrage (F6) bleibt offen und synthetische Fixtures veralten gegen die echte Quelle unbemerkt | genau dafür existiert T-D (§1) |

## 13. Was bei der Umsetzung anders kam

Vier Punkte, an denen der Code vom Plan abweicht. Sie stehen so auch im
Entscheidungslog:

1. **Eine `bbox` mit `west > east` wird zugelassen.** §6 wollte sie als „verdreht"
   abweisen. So schreiben GeoJSON und STAC aber eine Box über die Datumsgrenze, und
   Earth Search liest sie so. Abgewiesen wird deshalb nur, was die Quelle selbst
   abweist (`south >= north`) und was sie still duldet (Breiten außerhalb ±90) —
   letzteres ist der Fall, um den es `adr/0005` §3.5 geht.
2. **Die Item-ID wird geprüft, nicht maskiert.** Zum Maskieren bräuchte es
   `urllib.parse`, und `urllib` ist außerhalb von `gateway` gesperrt. Ein Muster für
   STAC-IDs ist ohnehin die schärfere Prüfung: Es sperrt `../` mit, statt es
   unauffällig umzuschreiben.
3. **Drei Migrationstests brauchten einen sauberen Stand.** `earthx.catalog.load`
   committet, also trägt die Datenbank nach einem vollen Lauf wirklich die Version
   `002` — ein Test, der dieselbe Nummer für eine eigene Datei benutzt, las das als
   nachträglich geänderte Migration. Die Tests setzen jetzt beide Tabellen zurück und
   laufen auf einer gebrauchten wie auf einer frischen Datenbank.
4. **Zwei Kleinigkeiten an der Schnittstelle aus §4:** `SearchParams` trägt `start`
   und `end` einzeln statt als Tupel, und `SearchCache.set` nimmt die `dataset_id`
   mit — ohne sie ließe sich die gleichnamige Spalte der Tabelle nicht füllen.

Das Review des Branches fand zwei Dinge, die still falsch statt laut kaputt gewesen
wären, beide inzwischen behoben und im Log vermerkt:

- **Der Cache lief ohne Savepoint** auf der Verbindung des Aufrufers. Eine
  fehlgeschlagene Anweisung hätte die ganze Transaktion abgebrochen — ab M1-07 die des
  Requests. E5 galt damit nur im Adapter, nicht im Prozess.
- **Ein Redirect mit 301/302/303 verwarf den Request-Rumpf** (Verhalten aus M1-03).
  Aus `POST /search` wäre ein `GET /search` geworden und die ungefilterte Vorgabeseite
  der Quelle die Antwort auf eine AOI-Suche.

Offen geblieben und im Log als solches vermerkt: **`sortby` wird bewusst nicht
mitgeschickt** — ein ausdrückliches Sortierfeld bräche vermutlich die Seitenmarke
(deren Feldzahl dazu passen muss), und das lässt sich nur an der Quelle messen. Vor
einer Sortierzusage nach außen in M1-07 zu klären.

Dazu kam ein Befund **außerhalb** von M1-06, den Otto am 19.09.2026 entschieden hat:
Der Importvertrag `http-only-in-gateway` zählte auch indirekte Ketten und verbot
damit jeden Import von `gateway` — `gateway.policy` zerlegt URLs mit `urllib.parse`.
Der Vertrag zählt jetzt direkte Importe; die Syntaxbaum-Prüfung bleibt als zweite
Sperre daneben. Für `access` und `processing` steht derselbe Fall noch offen
(Entscheidungslog).
