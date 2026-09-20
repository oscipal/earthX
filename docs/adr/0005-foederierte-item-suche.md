# ADR 0005 — Föderierte Item-Suche für Sentinel-2 L2A

- **Status:** **Angenommen** von Otto am 2026-09-19. Die drei Fragen aus §7
  sind beantwortet: F1 mit der Präzisierung „7 Tage statt 24 h", F2 mit der
  Verschärfung „in M1 gar keine Filter-Extension", F3 wie empfohlen. Die
  Empfehlung in §5 gibt den entschiedenen Stand wieder.
- **Datum:** 2026-09-19
- **Aufgabe:** M1-05 laut `docs/plans/m1-fundament.md` §4 (Spike aus
  `architekturplan.md` 15.2, „Föderierte Item-Suche").
- **Autonomiestufe:** C — nur recherchiert, gemessen und berichtet. Kein
  Produktivcode geändert, keine Datei außerhalb von `docs/` angefasst, keine
  Pixel gelesen.
- **Grundlage:** `architekturplan.md` 5.2, 5.3, 6.1, 6.3, 6.5, 13, 15.2;
  `KLAERUNGEN.md` B8, B10, B13; `adr/0001` §7 (Z1, Z9), §8, §9.1, §9.3;
  `adr/0003` §11.2 (Sentinel-2 L2A, Earth Search v1); `adr/0004` §3
  (Messungen gegen dieselbe Quelle); `docs/plans/m1-fundament.md` §1 (E4, E5).
- **Betroffen:** `architekturplan.md` 5.2, 6.1; Planung M1-06, M1-07;
  Entscheidungslog (auch die offene Zeile „Ratengrenzen der Anbieter").

---

## Methode und Belegstufen

Gearbeitet wurde in einer Cloud-Sitzung vom 19.09.2026;
`earth-search.aws.element84.com` war erreichbar. Belegstufen wie in `adr/0004`:

- **M** — in dieser Sitzung gemessen; die Anfrage steht im Text.
- **P** — am Primärdokument oder am Quelltext der Bibliothek gelesen.
- **S** — Suchtreffer mit Link, Primärdokument nicht gelesen.
- **A** — eigene Ableitung aus M/P/S, als Argument gekennzeichnet.

Wo ein Beleg fehlt, steht „unbelegt". §8 listet, was offen blieb.

**Nur Metadaten, bewusst sparsam.** Alle Abrufe waren STAC-Metadaten-Anfragen
(`/`, `/search`, `/aggregate`, `/collections/…/items/…`). Der Umfang lag bei rund
110 Anfragen über etwa 50 Minuten, davon zwei Bursts mit 20 und 30 parallelen
Anfragen zur Messung der Ratengrenzen (§3.6). Es wurden keine Assets geladen.

---

## 1. Kontext und Problem

`architekturplan.md` 5.2 legt fest: Collections liegen im eigenen pgstac, Items
werden live bei der Quelle abgefragt. Für den Nutzer soll der Unterschied
unsichtbar sein — beide Wege liefern dieselbe STAC-Antwort. `adr/0003` hat
Sentinel-2 L2A über Earth Search v1 als ersten Datensatz gesetzt; dessen Items
liegen also **nicht** in unserem pgstac, die Collection schon.

Daraus folgen vier Fragen, die M1-06 und M1-07 vor sich hertragen:

1. Kann `stac-fastapi-pgstac` die Item-Suche für **eine** Collection an einen
   Adapter abgeben, oder braucht es eine eigene Route davor?
2. Was kostet Earth Search an Latenz, Nutzlast und Ratengrenzen, und welcher
   Cache-TTL ist vertretbar?
3. Wie funktionieren Paging und Such-ID, wenn die Seitenmarke von einer fremden
   API kommt und unser Prozess zwischendurch neu startet (`adr/0001` §8)?
4. Läuft `pystac_client` über `gateway` (B8), oder braucht es einen eigenen
   Client?

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Eine STAC-Antwort nach außen; föderiert und eigen sind nicht unterscheidbar | `architekturplan.md` 5.2 |
| K2 | Jeder ausgehende Request geht durch `gateway`, Redirects eingeschlossen | `KLAERUNGEN.md` B8 |
| K3 | Kein Endpunkt setzt eine vorherige Suche voraus; Neustart ändert nichts | `adr/0001` §7 (Z1), §8 |
| K4 | Ein leerer Zwischenspeicher macht nur langsamer, nie 404 | E5, `adr/0001` §9.3 |
| K5 | Rücksicht auf die Quelle: wenige, kleine, gebündelte Anfragen | `architekturplan.md` 6.5 |
| K6 | Interaktiv: gefilterte Suche unter etwa 1 s | `projektuebersicht.md`, K6 aus `adr/0004` |
| K7 | Keine Abhängigkeit, die wir nicht in `gateway` kontrollieren können | B8, B9 |
| K8 | Konformitätsklassen der eigenen API müssen stimmen, auch wenn upstream weniger kann | `architekturplan.md` 5.3 |

---

## 3. Was gemessen wurde

### 3.1 Was Earth Search v1 kann — und was nicht — **[M]**

```
curl -s https://earth-search.aws.element84.com/v1 | jq -r '.conformsTo[]'
```

Angeboten werden `core`, `collections`, `ogcapi-features`, `item-search`, dazu
`#fields`, `#sort`, `#query` auf beiden Pfaden und
`https://api.stacspec.org/v0.3.0/aggregation`.

**Entscheidend ist, was fehlt: `filter` (CQL2).** Earth Search kennt nur die
ältere Query-Extension. `stac-fastapi-pgstac` weist CQL2 dagegen standardmäßig
aus. Eine eigene API, die CQL2 in der Landing Page verspricht und einen
CQL2-Filter auf einer föderierten Collection stillschweigend verwirft, verletzt
K8. Das ist eine harte Vorgabe für M1-07 (§6).

### 3.2 Latenz und Nutzlast — **[M]**

Alle Werte sind `curl`-Gesamtzeiten aus dieser Sitzung. Suchfenster, wo nicht
anders angegeben: `bbox=[8,47,12,51]` (Mitteleuropa), Juni 2024, 273 Treffer.

| Anfrage | Zeit | Nutzlast |
|---|---|---|
| Landing Page | 0,53 s | 3,4 kB |
| `POST /search`, `limit=10` (5 Läufe) | **0,43–0,71 s** | 177 kB |
| `POST /search`, `limit=100` | 1,01 s | 1,76 MB |
| `POST /search`, `limit=500` (273 geliefert) | 2,54 s | 4,82 MB |
| `POST /search`, `limit=1000` | 1,38 s | 4,82 MB |
| `POST /search`, `limit=10000` | 1,55 s | 4,82 MB |
| dieselbe Suche mit `fields` (nur `id`, `datetime`, `eo:cloud_cover`) | **0,58 s** | **54 kB** |
| `GET /search`, `limit=10` | 0,95 s | 177 kB |
| `GET /collections/…/items/{id}` (3 Läufe) | 0,62–1,12 s | 17,6 kB |

Drei Dinge daraus:

1. **K6 ist erfüllt**, solange die Seite klein bleibt. Eine Seite mit 10 Items
   liegt zuverlässig unter 0,75 s.
2. **Ein Item kostet rund 17,7 kB** — bei 23 Assets je Szene. Die Nutzlast, nicht
   die Datenbank, ist der Kostentreiber. Eine Seite mit 100 Items sind 1,8 MB.
3. **`limit` ist oben nicht gedeckelt**: `limit=10000` wird ohne Fehler
   angenommen. Die Obergrenze muss also **bei uns** stehen, nicht upstream
   **[M]**. Ohne eigene Deckelung kann ein einziger Nutzer-Request eine
   Antwort im dreistelligen Megabyte-Bereich auslösen — das ist zugleich eine
   Anforderung an die Größenbegrenzung des Gateways (M1-03).

`fields` senkt dieselbe Trefferzahl von 4,82 MB auf 54 kB, also um den Faktor 89,
und die Zeit von 2,54 s auf 0,58 s **[M]**. Für Zeitleiste und Trefferübersicht
ist das die richtige Anfrage; für die STAC-Antwort nach außen nicht, weil dort
vollständige Items geschuldet sind.

### 3.3 Paging ist eine Keyset-Marke, keine Sitzung — **[M]**

Der `next`-Link kommt als POST-Link mit Rumpf zurück; die Marke steht im Feld
`next`:

```json
{"rel":"next","method":"POST","href":".../v1/search","merge":false,
 "body":{…,"next":"2024-06-29T10:27:26.277000Z,S2A_T32UQU_20240629T102556_L2A,sentinel-2-c1-l2a"}}
```

Die Marke ist also `datetime,id,collection` — die Sortierschlüssel des letzten
Items, nicht ein Versatz und keine serverseitige Sitzung. Fünf Seiten à 50 Items
über das Jahr 2024 (3510 Treffer) kosteten 0,64 / 0,98 / 0,82 / 0,80 / 0,83 s bei
je rund 882 kB **[M]**: **kein Aufschlag beim Tiefblättern**.

Drei Folgerungen:

- Die Marke ist **zustandslos und überlebt jeden Neustart** auf beiden Seiten.
  Sie erfüllt K3 ohne eigenes Zutun **[A]**.
- Die Vorgabesortierung ist `datetime` absteigend. Neu eintreffende Items haben
  das neueste `datetime` und landen deshalb **vor** jeder ausgegebenen Marke.
  Blättern während laufender Aufnahme liefert also keine Dubletten und
  überspringt nichts — anders als bei einer Versatz-Paginierung **[A]**.
- Eine kaputte Marke wird mit `400` und dem Text
  `"search_after has 1 value(s) but sort has 3."` quittiert **[M]**. Das ist ein
  durchgereichter Elasticsearch-Interna-Text. Unsere Marke muss deshalb
  **unsere eigene** sein (§5, Regel III), nicht die durchgereichte.

### 3.4 Zwischenspeicher: kein `Cache-Control`, aber ein brauchbares ETag — **[M]**

Earth Search antwortet hinter CloudFront, setzt aber **kein `Cache-Control`**;
drei identische Anfragen ergaben dreimal `x-cache: Miss from cloudfront`
(deckt sich mit `adr/0004` §3.2). Es setzt jedoch ein **stabiles schwaches
ETag**, und zwar unterschiedlich verwertbar:

| Weg | ETag gesetzt | `If-None-Match` beantwortet |
|---|---|---|
| `GET /search` | ja | **`304`, 0 B** **[M]** |
| `POST /search` | ja | **nein — `200` mit vollem Rumpf** **[M]** |

Das ETag einer historischen Suche war nach 20 Minuten unverändert **[M]**.

**Wie schnell veraltet eine Antwort wirklich?** Zwei Messungen:

- Global trafen am 18.09.2026 **19 658** Items ein, am 19.09. bis 10:48 UTC
  **3 987** (`/aggregate`, `total_count`) — rund 820 Items je Stunde weltweit
  **[M]**. Das neueste Item hatte `datetime` 07:38 UTC und `created` 09:47 UTC:
  **rund zwei Stunden** von der Aufnahme bis in den Katalog **[M]**.
- Im **geschlossenen** Fenster Juni 2024 über Mitteleuropa ist das jüngste
  `updated` der **30.06.2024** — seit 15 Monaten hat sich dort nichts geändert
  **[M]**.

Daraus folgt die TTL-Empfehlung (§5, Regel II): **Was zählt, ist nicht das Alter
der Anfrage, sondern ob ihr Zeitfenster den Jetzt-Rand berührt.** Ein
geschlossenes historisches Fenster ist über Monate stabil; nur der offene Rand
bewegt sich, und auch der nur im Stundentakt.

### 3.5 Fehlerverhalten der Quelle — **[M]**

| Fall | Antwort |
|---|---|
| unbekannte Collection | **`200`, `matched: 0`** |
| leeres Ergebnis (Pazifik) | `200`, `matched: 0` |
| kaputtes `datetime` | `400` „datetime value is invalid, does not match RFC3339 format" |
| `bbox` verdreht (SW > NE) | `400` „Invalid bbox, SW latitude must be less than NE latitude" |
| `bbox` außerhalb ±90 | **`200`**, still geduldet |
| Polygon mit 2 Stützpunkten | `400` „invalid number of points in LinearRing" |
| Item-ID gibt es nicht | `404` „Not Found" |
| kaputte Seitenmarke | `400` (Elasticsearch-Text, §3.3) |

**Die erste Zeile ist die gefährliche.** Ein Tippfehler in der Collection-ID
liefert keine `404`, sondern eine leere, gültig aussehende Trefferliste. Unsere
API muss die Collection deshalb **gegen den eigenen pgstac prüfen**, bevor sie
föderiert — sonst wird aus „gibt es nicht" stillschweigend „gibt es nichts". Das
ist ein Abnahmekriterium für M1-06 (§6).

Auch Zeile 5 ist zu behandeln: Eine `bbox` außerhalb ±90 nimmt die Quelle
kommentarlos an. Die Eingabeprüfung gehört zu uns, nicht zur Quelle.

### 3.6 Ratengrenzen: keine erkennbar — **[M]**

Die offene Log-Zeile „Ratengrenzen der Anbieter" lässt sich für Earth Search
nun teilweise schließen:

- 20 parallele `GET /search` (`limit=1`, verschiedene Tage): **20× `200`**.
- 30 parallele `GET /search` (anderer Monat): **30× `200`**, 0,31–1,09 s.
- In insgesamt rund 110 Anfragen dieser Sitzung **kein einziges `429`**, kein
  `Retry-After`, kein `X-RateLimit-*`-Header.

Auch bei 30 gleichzeitigen Anfragen blieb die Latenz im Bereich der
Einzelmessung — der Dienst skaliert breit. **Das ist kein Freibrief:** Eine
nicht dokumentierte und nicht angekündigte Grenze kann jederzeit eingeführt
werden, und K5 verlangt Rücksicht unabhängig davon. Die Log-Zeile bleibt für
die übrigen Anbieter offen.

### 3.7 `stac-fastapi-pgstac` hat keinen Delegationspunkt — aber die Bibliothek trägt die Erweiterung — **[P]**

Gelesen wurde `stac_fastapi/pgstac/core.py` auf `main` (732 Zeilen). Alle vier
item-seitigen Methoden — `item_collection`, `get_item`, `post_search`,
`get_search` — laufen in genau eine private Methode zusammen:

```python
async def _search_base(self, search_request, request) -> ItemCollection:
    ...
    q, p = render("SELECT * FROM search(:req::text::jsonb);", req=search_request_json)
    item_collection = await conn.fetchval(q, *p)
```

Es gibt **keinen Verzweigungspunkt je Collection**, keinen Hook, keine
registrierbare Backend-Schnittstelle: Der Weg führt unbedingt in die
pgstac-Funktion `search()` **[P]**.

Die Gegenprobe fällt aber günstig aus: `stac_fastapi.api.app.StacApi` hält den
Client als **gewöhnliches Attribut**
(`client: AsyncBaseCoreClient | BaseCoreClient = attr.ib()`) und registriert die
Routen gegen dessen Methoden **[P]**. Ein Unterklassen-Client ist damit der
vorgesehene Weg, nicht ein Kniff. Im Projekt selbst ist genau dieses Vorgehen
als Anwendungsfall benannt: Issue `stac-utils/stac-fastapi-pgstac#380`
(„Make API customization easier", eröffnet 04.05.2026, inzwischen geschlossen)
nennt „patching the `_search_base` method of the
`stac_fastapi.pgstac.core.CoreCrudClient`" als Motivation für weniger
Boilerplate **[S]**.

**Kurz: delegieren kann die Bibliothek nicht, ersetzen lässt sie sich sauber.**

### 3.8 `pystac_client` passt nicht zu B8 — **[P]**

Gelesen wurde `pystac_client/stac_api_io.py` (332 Zeilen) und `client.py` auf
`main`. Vier Befunde, jeder für sich schon ein Hindernis:

1. **Synchron.** `StacApiIO` arbeitet auf `requests.Session`; `request()` gibt
   einen String zurück **[P]**. In einem `async`-FastAPI-Prozess blockiert das
   die Ereignisschleife oder braucht einen Threadpool.
2. **Eigene Sitzung.** `__init__` legt mit `self.session = Session()` eine eigene
   Sitzung an und hängt einen eigenen `HTTPAdapter` mit `urllib3.Retry` ein
   **[P]**. Einspeisen lässt sich nur eine ganze `StacApiIO`-Unterklasse
   (`Client.open(stac_io=…)`) oder ein `request_modifier` **[P]**.
3. **Redirects entziehen sich der Prüfung.** `request()` ruft
   `self.session.send(prepped, timeout=…)` ohne `allow_redirects` auf; in
   `requests/sessions.py` steht dort `kwargs.setdefault("allow_redirects", True)`
   **[P]**. Eine Weiterleitung wird also von `requests` selbst verfolgt — ohne
   dass `gateway` das Ziel je sieht. Das ist **genau der Fall, den B8
   ausschließt** („Redirects nur innerhalb der Allowlist").
4. **Fehler verlieren ihre Form.** Alles außer `200` wird in einen `APIError`
   mit Textrumpf umgewandelt **[P]**. Ein `304` aus §3.4 ist dort ein Fehler,
   und die Unterscheidung `400` gegen `404` gegen `429` geht verloren — sie ist
   aber genau das, was M1-06 testen soll.

Ein eigener Client über `httpx.AsyncClient` in `gateway` kostet für den hier
nötigen Umfang — `POST /search` mit Seitenmarke und `GET /collections/…/items/{id}`
— wenige Dutzend Zeilen und hat keinen dieser vier Nachteile **[A]**.

---

## 4. Optionen

**Option 1 — Eigene Route vor `stac-fastapi-pgstac`.** Ein eigener Router fängt
die Item-Pfade ab, entscheidet je Collection und reicht den eigenen Fall an die
pgstac-App weiter.
*Für:* keine Berührung der Bibliothek.
*Gegen:* Zwei Routensätze müssen dieselben Links, Konformitätsklassen und
Fehlerformen erzeugen; `POST /search` über mehrere Collections lässt sich nicht
sauber aufteilen. Verstößt gegen K1, sobald jemand eigene und föderierte
Collection in einer Suche mischt.

**Option 2 — Unterklasse von `CoreCrudClient`.** Ein
`FederatingCoreCrudClient` überschreibt `item_collection`, `get_item`,
`post_search`, `get_search` und entscheidet je Collection anhand von
`earthx:source` aus dem eigenen pgstac: eigene Items → `super()`; föderierte →
Adapter über `gateway`.
*Für:* Ein Routensatz, eine Linkerzeugung, eine Fehlerform (K1). Der von der
Bibliothek vorgesehene Erweiterungspunkt (§3.7). Gemischte Suchen sind
behandelbar, weil die Verzweigung **innerhalb** einer Antwort liegt.
*Gegen:* Bindung an eine private Methode (`_search_base`) — Versionspflege
nötig, wenn wir sie überschreiben statt nur die vier öffentlichen Methoden.

**Option 3 — Eigene STAC-API, pgstac nur als Datenbank.** Alles selbst bauen.
*Für:* volle Kontrolle.
*Gegen:* Konformität, Links, Paginierung, Extensions und Fehlerformen selbst
pflegen. Widerspricht `architekturplan.md` 5.3 („pgstac + stac-fastapi-pgstac als
Katalogkern und zugleich öffentliche STAC-API").

**Option 4 — Items doch materialisieren.** Sentinel-2 L2A nach pgstac ernten.
*Gegen:* 30,4 Mio. Items für eine Collection (`adr/0004` §3.2), täglich rund
20 000 neue (§3.4). Das ist die Ausnahme aus `architekturplan.md` 5.2 für Quellen
**ohne** Such-API; Earth Search hat eine. Verstößt gegen den tragenden Satz
„Frische, keine Synchronisation, keine Speicherkosten".

---

## 5. Empfehlung

**Option 2**, mit sechs Regeln.

**Regel I — Verzweigen an der Collection, nicht an der Route.** Der
`FederatingCoreCrudClient` überschreibt nur die **vier öffentlichen** Methoden.
Er liest `earthx:source` der betroffenen Collection aus dem eigenen pgstac (ein
Feld, das `architekturplan.md` 5.1 ohnehin vorsieht) und ruft für eigene Items
unverändert `super()`. `_search_base` bleibt unberührt — das hält die Bindung an
eine private Methode aus dem Code heraus. Eine Suche ohne `collections` oder über
mehrere Collections wird je Collection aufgeteilt und zusammengeführt.
Eine Collection, die weder im eigenen pgstac noch in der Registry steht, ergibt
`404` — nicht die leere Liste aus §3.5.

**Regel II — Zwei Cache-Fristen, entschieden am Zeitfenster.** Der Such-Cache
liegt im Anwendungs-Cache in Postgres (E4). Schlüssel ist der Hash der
normalisierten Suche einschließlich Seitenmarke (das ist zugleich Z9 aus
`adr/0001`). Vorschlag:

| Fall | TTL | Begründung aus §3.4 |
|---|---|---|
| Zeitfenster endet in der Vergangenheit (mehr als **7 Tage** zurück) | **24 h** | seit 15 Monaten unverändert |
| Zeitfenster offen oder bis „jetzt" | **5 min** | rund 820 neue Items je Stunde weltweit, ~2 h Verzug bis in den Katalog |
| Einzelnes Item per ID | **24 h** | `updated` bewegt sich nur in den ersten Stunden nach der Aufnahme |

Die Grenze von sieben Tagen ist Ottos Präzisierung zur Empfehlung von 24 h: Sie
deckt **Nachlieferungen** ab — Szenen, die verspätet oder neu verarbeitet in den
Katalog kommen. Die Messung in §3.4 belegt nur, dass ein 15 Monate altes Fenster
stillsteht; wie lange der Rand tatsächlich nachzittert, ist damit **nicht**
gemessen (§8). Sieben Tage sind die vorsichtige Seite dieser Unkenntnis.

Der Cache ist reiner Beschleuniger: Fällt er aus, wird live gefragt (K4, E5).
Ein Test hierfür ist Abnahme von M1-06.

**Regel III — Eine eigene, undurchsichtige Seitenmarke.** Nach außen geben wir
`token=<base64>` aus; darin stecken Quell-ID, Hash der Suche und die
Upstream-Marke aus §3.3. Drei Gründe: Der Elasticsearch-Text aus §3.5 gehört
nicht in unsere API; die Form der eigenen und der föderierten Marke bleibt gleich
(K1); und die Marke bleibt zustandslos, überlebt also den Neustart (K3).
**Keine serverseitige Such-Sitzung.** Die Such-ID für Mosaike
(`architekturplan.md` 6.3) ist eine andere Sache und gehört zu M2 (E3) — sie wäre
ein Cache-Eintrag mit Adresse, nicht eine Sitzung.

**Regel IV — Eigener Client in `gateway`, kein `pystac_client`.** Ein schmaler
`httpx.AsyncClient` hinter der Gateway-Schnittstelle (§3.8). `pystac_client`
bleibt im Prototyp (`backend/app/stac.py`) und wandert nicht mit. Die Abhängigkeit
kann aus dem Zielpfad herausbleiben; die Importregel aus M1-02 (HTTP-Clients nur
in `gateway`) nennt `pystac_client` ohnehin bereits.

**Regel V — Seitengröße deckeln, Anfragen verschlanken.** Weil upstream nicht
deckelt (§3.2): eigene Obergrenze **`limit ≤ 100`** nach außen, Vorgabe 10.
Wo nur Zeit, Ort und Wolkenanteil gebraucht werden (Zeitleiste,
Trefferübersicht), wird upstream mit `fields` gefragt — Faktor 89 weniger Bytes
bei gleicher Trefferzahl. Die vollständigen Items werden nur für die Seite
geholt, die der Nutzer tatsächlich sieht.

**Regel VI — In M1 keine Filter-Extension ausweisen.** Die Landing Page der
eigenen API führt `filter`/CQL2 gar nicht auf, und die Extension wird in
`stac-fastapi-pgstac` nicht eingeschaltet. Das ist schärfer als „für föderierte
Collections nicht ausweisen" und in M1 die einfachere Wahrheit: Es gibt in M1
**keine** eigenen Items (`adr/0003`: Sentinel-2 L2A ist föderiert), also keine
Collection, auf der CQL2 funktionieren würde. Eine Unterscheidung je Collection
hätte nichts zu unterscheiden. **Mit M3 neu zu prüfen** — dort kommt mit der
ersten Nicht-STAC-Quelle die erste Collection mit materialisierten Items
(`architekturplan.md` 15.1, Inkrement 3), und damit erstmals ein Fall, in dem
CQL2 etwas leisten könnte.

---

## 6. Folgen

**Für M1-06 (Earth-Search-Adapter):**

- Abnahmefall zusätzlich zu den im Plan genannten: **unbekannte Collection ergibt
  `404`, nicht die leere Liste** (§3.5).
- Abnahmefall: `bbox` außerhalb ±90 und verdrehte `bbox` werden **bei uns**
  abgewiesen, nicht erst upstream (§3.5).
- Der Fall „Neustart zwischen Suche und Item-Abruf" (`adr/0001` §8) ist ohne
  Zusatzaufwand erfüllbar, weil Earth Search Items per ID ohne vorherige Suche
  liefert (0,62–1,12 s, §3.2) und die Seitenmarke zustandslos ist (§3.3).
- Synthetische Fixtures sollten die gemessenen Formen abbilden: Antwortrumpf mit
  `context`/`numberMatched`, `next`-Link als POST-Link **mit Rumpf**, die acht
  Fehlerformen aus §3.5. Dass die Fixtures synthetisch bleiben, ändert die
  Lizenzlage der Earth-Search-Metadaten nicht — die bleibt offen (§8).

**Für M1-07 (STAC-API nach außen):** Die Konformitätsklassen der eigenen Landing
Page müssen zur **schwächsten** beteiligten Quelle passen (K8). Earth Search kann
kein CQL2 (§3.1); in M1 gibt es keine andere Quelle. Nach Regel VI weist die
eigene API `filter`/CQL2 in M1 deshalb **gar nicht** aus. Abnahmefall: Die
Landing Page führt keine `filter`-Konformitätsklasse, und ein `filter`-Parameter
wird nicht stillschweigend verworfen. Der Punkt ist mit M3 erneut aufzurufen,
sobald es eigene Items gibt.

**Für M1-03 (Gateway):** Die Größenbegrenzung muss großzügig genug für eine
Seite mit 100 Items sein (§3.2: rund 1,8 MB) und eng genug, um eine
4,8-MB-Antwort abzufangen. Vorschlag: 8 MB je Antwort, gemessen am Rumpf. Die
Obergrenze paralleler Verbindungen je Host darf für Earth Search bei 30 liegen,
ohne dass die Quelle drosselt (§3.6) — konservativ vorgeschlagen sind **6**.

**Nicht geändert:** `architekturplan.md` 5.2 bleibt gültig; dieses ADR füllt nur
den „alt"-Zweig seines Ablaufdiagramms mit Messwerten aus.

---

## 7. Fragen an Otto — beantwortet am 2026-09-19

**F1 — Cache-Fristen (Regel II).** **Empfehlung angenommen, mit einer
Präzisierung:** Ein Zeitfenster gilt erst als geschlossen, wenn sein Ende **mehr
als 7 Tage** zurückliegt (statt 24 h), wegen möglicher Nachlieferungen. Die
Fristen selbst bleiben: 24 h für geschlossene Fenster, 5 min für den offenen
Rand, 24 h für Einzel-Items. Regel II ist entsprechend gefasst.

**F2 — CQL2 auf föderierten Collections (§6).** **Angenommen, und schärfer
gefasst:** In M1 wird `filter`/CQL2 **gar nicht** ausgewiesen, weil es noch keine
eigenen Items gibt. Mit M3 neu zu prüfen. Das ist Regel VI.

**F3 — Obergrenze der Seitengröße (Regel V).** **Empfehlung angenommen:**
`limit ≤ 100`, Vorgabe 10.

---

## 8. Was offen blieb

1. **Lizenz der Earth-Search-Metadaten** für aufgezeichnete Fixtures — in
   `m1-fundament.md` §4 (M1-06) ausdrücklich Otto vorbehalten. Dieser Spike hat
   sie **nicht** geprüft und schlägt sie nicht ein. Solange sie offen ist,
   bleiben Fixtures synthetisch.
   **Nachtrag 19.09.2026 (erledigt):** Otto hat entschieden, dass **dauerhaft nicht
   aufgezeichnet wird**. Die Lizenzfrage stellt sich für Fixtures damit nicht mehr;
   sie bleiben synthetisch, und dass die Quelle sich bewegt, merkt der T-D-Test.
2. **Ratengrenzen der übrigen Anbieter.** Für Earth Search ist die Frage mit
   §3.6 beantwortet, soweit sie sich ohne mutwillige Last beantworten lässt. Die
   Log-Zeile bleibt für EOPF und Copernicus DEM offen.
3. **Verhalten bei einer Störung der Quelle.** Ein echter `5xx` oder ein
   Zeitablauf ließ sich nicht herbeiführen, ohne die Quelle zu belasten. Das
   Verhalten des Adapters in diesem Fall ist deshalb nur aus der Spezifikation
   abgeleitet, nicht gemessen — M1-06 muss es gegen Fixtures prüfen.
4. **Gemischte Suchen über eigene und föderierte Collections** sind in Regel I
   vorgesehen, in M1 aber nicht auf die Probe zu stellen: Es gibt vorerst nur
   eine Collection, und die ist föderiert. Der Fall wird erst mit dem dritten
   Inkrement (`architekturplan.md` 15.1) real.
   **Nachtrag 2026-09-20 (D8):** Mit dem zweiten Datensatz in M2 bleibt die
   gemischte Suche weiterhin abgelehnt (`400`); der Viewer sucht je Datensatz.
   Umgesetzt wird sie erst mit eigenen Items in M3, wie Regel I es vorsieht.
5. **Sortierung.** Dass Earth Search ohne `sortby` nach `datetime` absteigend
   sortiert, ist aus der Seitenmarke abgelesen, nicht dokumentiert gefunden
   **[A]**. Wenn unsere API eine Sortierung zusichert, muss sie sie ausdrücklich
   mitschicken.
6. **Wie lange der Rand nachzittert.** Gemessen ist nur, dass ein 15 Monate altes
   Fenster stillsteht (§3.4), und dass das jüngste `updated` im Fenster Juni 2024
   rund vier Stunden nach der Aufnahme liegt. Wie häufig Szenen **später** neu
   verarbeitet oder nachgeliefert werden, ist damit **nicht** gemessen. Die
   Sieben-Tage-Grenze aus F1 ist die vorsichtige Antwort darauf, keine Messung.
   Nachzuholen wäre sie mit einer Stichprobe über `updated` gegen `datetime` über
   mehrere Monate — lohnend erst, wenn der Cache tatsächlich Last trägt.

---

## 9. Quellen

**Gemessen (M) — Earth Search v1**, `https://earth-search.aws.element84.com/v1`:
Landing Page; `POST`/`GET /search` mit `limit`, `fields`, `sortby`, `next`;
`GET /collections/sentinel-2-c1-l2a/items/{id}`; `GET /aggregate` mit
`total_count`. Sitzung vom 19.09.2026, rund 110 Anfragen, nur Metadaten.

**Quelltext (P):**

- `stac-utils/stac-fastapi-pgstac`, `stac_fastapi/pgstac/core.py` (`main`)
- `stac-utils/stac-fastapi`, `stac_fastapi/api/stac_fastapi/api/app.py` (`main`)
- `stac-utils/pystac-client`, `pystac_client/stac_api_io.py`, `client.py` (`main`)
- `psf/requests`, `src/requests/sessions.py` (`main`), Zeile 670

**Suchtreffer (S):**

- `stac-utils/stac-fastapi-pgstac` Issue #380, „Make API customization easier"

**Im Repo:** `architekturplan.md` 5.2, 5.3, 6.1, 6.3, 6.5, 15.2;
`KLAERUNGEN.md` B8, B10, B13; `adr/0001`, `adr/0003` §11.2, `adr/0004` §3;
`docs/plans/m1-fundament.md` §1, §4.
