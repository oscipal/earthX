# M3-07a — Ortssuche: Recherche und Backend-Route: Plan

**Aufgabe:** M3-07a aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B — von Otto am 26.09.2026 freigegeben** mit F1 (1), F2 (1), F3 (1),
F4 (1), F5 (1) (§12), dazu vier Ergänzungen, die in die Umsetzung eingeflossen
sind:

- **Cache-Schlüssel:** Hash des normalisierten Suchtexts, nie der Klartext —
  wie `search_fingerprint` aus M3-08 (`earthx/adapters/nominatim.py::_cache_key`).
  Test dazu: `tests/integration/test_geocode_cache.py` liest die Tabelle direkt
  und prüft, dass kein Klartext darin steht (über `TestTheCache`, keine eigene
  Spalte dafür — die Nutzlast ist die fertige, bereits vereinfachte Antwort).
- **User-Agent:** `EarthX/0.1 (+https://github.com/oscipal/earthX)`, keine
  E-Mail-Adresse im Code; überschreibbar über `EARTHX_GEOCODER_USER_AGENT`.
- **F1 umgesetzt:** `.env.example` trägt `EARTHX_GEOCODER_URL` ohne Wert, mit
  Kommentar zur Nutzungsbedingung; README §2 „Ortssuche lokal einschalten"
  sagt, wie man sie einschaltet.
- **Attribution** kommt in jeder Antwort mit (`to_payload()`); die Anzeige ist
  M3-07b.

**Ort im Repo:** `docs/plans/m3-07a-ortssuche-backend.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` P3, P8, §1.3, M3-07a;
`prototyp-inventar.md` F2; `architekturplan.md` 3.1, 6.5, 12.3;
`KLAERUNGEN.md` B8, B9; `plans/m1-fundament.md` E4, E5; `adr/0001` §9.3;
`projektuebersicht.md` §2 (Ortssuche, ODbL-Attribution); Log 20.09. und
23.09.2026 (Ortssuche); heutiger Code in `earthx/gateway/`,
`earthx/api/dependencies.py`, `earthx/catalog/search_cache.py`,
`earthx/adapters/federated_search.py` (`MAX_INTERSECTS_POINTS`),
`earthx/logging.py`.

---

## 1. Ziel in einem Satz

Ein Ortsname wird auf Absenden über `gateway` bei Nominatim aufgelöst und
kommt als Liste von Treffern mit Bounding Box und — wo es einen gibt —
vereinfachtem Umriss zurück, samt OSM-Attribution, gecacht in Postgres, mit
höchstens einer Anfrage pro Sekunde an Nominatim über alle Prozesse und ohne
Suchtext oder Treffer im Log.

---

## 2. Recherche: Nutzungsbedingungen und Alternativen

Recherche am 26.09.2026. Die Live-Seiten von `operations.osmfoundation.org`,
`nominatim.org`, `osmfoundation.org` und `openstreetmap.org` sind aus der
Cloud-Umgebung gesperrt. Gelesen wurden deshalb die Quelldateien, aus denen
diese Seiten gebaut werden; die Zitate zur Nutzungsbedingung sind an der Datei
selbst nachgeprüft. **Abrufe:** 7 erfolgreiche Webabrufe auf 6 URLs, dazu
9 Websuchen als Zweitquelle; keine Anfrage an Nominatim selbst (die stehen in §3).

### 2.1 Nutzungsbedingung von `nominatim.openstreetmap.org`

Quelle: <https://operations.osmfoundation.org/policies/nominatim/>, gelesen
als Quelldatei
<https://raw.githubusercontent.com/openstreetmap/owg-website/gh-pages/policies/nominatim.md>.

| Punkt | Wortlaut (Auszug) | Folge für den Plan |
|---|---|---|
| Rate | „an absolute **maximum of 1 request per second**" | wie P8 |
| Summe | „the usage limits above apply **per website/application**: the sum of traffic by all your users should not exceed the limits" | Rate über alle Prozesse (§9), nicht je Prozess |
| Kennung | „Provide a valid HTTP Referer or User-Agent identifying the application (stock User-Agents as set by http libraries will not do)" | eigener User-Agent (§7); `httpx`-Vorgabe reicht nicht |
| Attribution | „Clearly display attribution as suitable for your medium" | Attribution in der Antwort, M3-07b zeigt sie (§7) |
| Lizenz | „Data is provided under the ODbL license which requires to share alike (although small extractions are likely to be covered by fair usage / fair dealing)" | Lizenz `ODbL-1.0` in der Antwort; der Cache hält nur gesuchte Einzeltreffer |
| Endnutzer | „Use that is directly triggered by the end-user (for example, user searches for something) is ok, provided that your number of users is moderate." | trägt P8 heute; „moderate" ist nicht beziffert (§2.3) |
| Wechsel | „Apps must make sure that they can switch the service at our request at any time (in particular, switching should be possible without requiring a software update). If at all possible, **set up a proxy** and also enable caching of requests." | Proxy und Cache sind unser Weg; der Wechsel ohne Release führt zu F1 (§6) |
| Autocomplete | „you must not implement such a service on the client side using the API" | P8 „ohne Autocomplete" ist Pflicht, nicht nur Wahl |
| Periodisch | „periodic requests from apps are considered bulk geocoding and as such are strongly discouraged" | nichts im Plan fragt periodisch; kein Vorwärmen des Caches |
| Kernfunktion | „Applications and services whose primary function is related to geocoding must run their own service." | trifft EarthX nicht; die Ortssuche ist eine Hilfe zur AOI |
| Änderung | „this usage policy may change without notice … you might have your access withdrawn" | kein SLA; Ausfall muss sauber als `503`/`502` enden (§7) |

Keine Frist für den Cache in der Bedingung; sie empfiehlt Caching nur.

### 2.2 Weitere Quellen

- **API** (<https://nominatim.org/release-docs/latest/api/Search/>, gelesen als
  `docs/api/Search.md` und `Output.md` im Repo `osm-search/Nominatim`):
  `polygon_threshold` ist eine Toleranz „in degrees"; `limit` höchstens 40;
  `boundingbox` ist „min latitude, max latitude, min longitude, max longitude"
  als Strings. Fehlerstatus sind dort nicht beschrieben; `429` bei zu hoher Rate
  und `403` bei Sperre stammen aus Community-Berichten (Zweitquelle).
- **Attribution und ODbL:** Die OSMF-Richtlinien (Attribution Guidelines,
  Geocoding Guideline) waren nur über Suchzusammenfassungen erreichbar, nicht
  wörtlich. Danach ist „© OpenStreetMap contributors" mit Link auf
  `openstreetmap.org/copyright` die übliche Form, und einzelne
  Geocoding-Treffer gelten nicht ohne Weiteres als abgeleitete Datenbank.
  **Nicht wörtlich belegt**; gehört zur offenen Klärung vor dem ersten
  öffentlichen Deployment (Log, Zeile „Nutzungsbedingungen … Nominatim").

### 2.3 Widerspruch zu P8?

**Nein.** Rate, Auslösung durch den Nutzer, Proxy mit Cache und kein
Autocomplete entsprechen der Bedingung, zum Teil wörtlich. Zwei Vorbehalte,
beide für später und beide schon im Log offen: „moderate number of users" ist
für eine öffentliche Plattform nicht gesichert, und der Zugang kann jederzeit
entzogen werden. Daraus folgt für jetzt nur, dass der Anbieter ohne Release
abschaltbar und austauschbar sein soll (F1).

Nebenbefund: Die Rate gilt je Anwendung. Ottos lokale Instanz und eine spätere
Cloud-Instanz teilen sich keine Datenbank und damit keinen Slot (§9). Solange
beides Entwicklung ist, bleibt die Summe weit unter 1/s; für das erste
Deployment ist das mit zu klären.

### 2.4 Alternativen

| Dienst | Token | Umriss | Befund |
|---|---|---|---|
| Nominatim, öffentlich | nein (User-Agent Pflicht) | ja | P8 |
| Nominatim, selbst betrieben | nein | ja | gleiche API, also nur ein anderer Endpunkt (F1); Betrieb mit Planet-Import ist groß, erst mit Deployment-Frage |
| Photon (komoot) | nein | **nein** („There is no support for full geometry output", README) | fällt weg, der Umriss ist Teil der Aufgabe |
| Pelias / geocode.earth | ja (gehostet) | ja | Token, kostenpflichtig |
| OpenCage, LocationIQ, Geoapify, MapTiler | ja | teils | Token, kostenpflichtig oder Freikontingent; nicht einzeln verifiziert |
| Google, Esri | ja | nein bzw. Zusatzprodukt | Token, kostenpflichtig, Speicherfristen (Google: Koordinaten höchstens 30 Tage) |

Token-frei und mit Umriss bleibt nur Nominatim, öffentlich oder selbst betrieben.

---

## 3. Messungen

Gemessen am 26.09.2026 aus der Cloud-Sitzung, gedrosselt auf höchstens eine
Anfrage pro Sekunde (1,5 s Pause), mit eigenem User-Agent
(`EarthX-dev/0.1 (+https://github.com/oscipal/earthX)`). **9 Anfragen an
`nominatim.openstreetmap.org`**: 1 × `/status`, 8 × `/search`
(`format=jsonv2`, `polygon_geojson=1`, `accept-language=en`).

| Anfrage | `polygon_threshold` | Status | Bytes | Zeit | Geometrie des 1. Treffers | Punkte |
|---|---|---|---|---|---|---|
| Stadt (Berlin) | 0,005 | 200 | 3 507 | 0,65 s | MultiPolygon | 127 |
| Kleine Gemeinde (St. Peter-Ording) | 0,005 | 200 | 920 | 0,48 s | MultiPolygon | 16 |
| Kleine Gemeinde (St. Peter-Ording) | 0,001 | 200 | 1 855 | 0,25 s | MultiPolygon | 57 |
| Großes Land (Russland) | 0,01 | 200 | 149 702 | 0,93 s | MultiPolygon | 6 223 |
| Großes Land (Russland) | 0,005 | 200 | 243 123 | 1,10 s | MultiPolygon | 10 133 |
| Großes Land (Russland) | 0,001 | 200 | 661 443 | 1,36 s | MultiPolygon | 27 633 |
| Sehenswürdigkeit (Brandenburger Tor), `limit=5` | 0,005 | 200 | 3 145 | 0,42 s | 3 × Polygon, 2 × Point | 4 bzw. 1 |
| Unsinn ohne Treffer | 0,005 | 200 | 2 | 0,42 s | — (leere Liste) | — |

Befunde, die der Plan verwendet:

- **Latenz 0,25–1,4 s** je Anfrage an Nominatim. Mit der Rate von 1/s wird ein
  Cache-Treffer der Normalfall sein müssen, sobald mehrere Nutzer suchen.
- **Nominatims eigene Vereinfachung reicht nicht als Deckel.** Auch bei
  0,01° hat Russland über 6 000 Punkte; ein fester Schwellwert, der große
  Länder klein macht, macht kleine Orte zu Dreiecken (St. Peter-Ording:
  16 Punkte bei 0,005°). Deshalb zwei Stufen: ein kleiner Schwellwert an der
  Quelle (0,001°, spart Bytes, erhält kleine Orte), dann eine adaptive
  Vereinfachung bei uns bis unter den Deckel (§7).
- **`boundingbox` kommt als vier Strings in der Reihenfolge
  `[süd, nord, west, ost]`** (wie der Prototyp schon umstellte, F2). Bei einem
  Land über die Datumsgrenze (Russland) liefert Nominatim `-180 … 180`, also
  keine Box mit west > ost. Die Route prüft trotzdem und reicht eine solche Box
  nie ungeprüft weiter (§7).
- **Punkt-Treffer** (z. B. Bahnhöfe) haben `geojson.type = "Point"` und eine
  kleine, nicht entartete `boundingbox`. Straßen kommen als `LineString`.
- **`licence`** steht in jedem Treffer:
  „Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright".
- Ohne Treffer antwortet Nominatim mit `200` und `[]`, nicht mit `404`.

---

## 4. Umfang aus dem Aufgabenschnitt

- Adapter über `gateway`, Route im Prozess `api`; nur Suche auf Absenden.
- Höchstens 1 Anfrage pro Sekunde an Nominatim über alle Prozesse.
- Cache in Postgres (E4); ein Ausfall des Caches macht nur langsamer (E5).
- Umriss als Polygon mit vereinfachter Punktanzahl, dazu die Bounding Box.
- Attribution „© OpenStreetMap contributors" in der Antwort.
- Suchtext und Ergebnisse nicht im Log.
- **Nicht hier:** das Frontend (M3-07b), die Klärung der Nominatim-Bedingungen
  für das erste öffentliche Deployment (Log 23.09.2026: bleibt offen).

---

## 5. Module und Prozess

Nach `architekturplan.md` 3.1, ohne neues Modul und ohne gelockerte Importregel:

| Datei | Modul | Inhalt |
|---|---|---|
| `earthx/adapters/nominatim.py` (neu) | `adapters` | Anfrage bauen, über `gateway` senden, Antwort prüfen und auf unsere Form bringen, Umriss vereinfachen. Protokolle `GeocodeCache` und `RateSlot` (wie `adapters/cache.py`: `adapters` spricht mit Quellen, nicht mit der Datenbank) |
| `earthx/catalog/geocode_cache.py` (neu) | `catalog` | Postgres-Umsetzung von Cache und Raten-Slot, gleiche drei Eigenschaften wie `search_cache.py` (Verbindung bleibt beim Aufrufer, Fehler sind seiner, jede Anweisung im eigenen Savepoint) |
| `earthx/catalog/migrations/00n_geocode.sql` (neu) | `catalog` | Tabellen für Cache und Slot (§8, §9); die Nummer wird beim Umsetzen nach dem Stand von `main` vergeben |
| `earthx/api/geocode_route.py` (neu) | `api` | Route, Eingabeprüfung, Zusammenbau, Fehlerabbildung, eine Log-Zeile |
| `earthx/api/dependencies.py`, `earthx/api/main.py` | `api` | eigenes `Gateway` für den Geocoder (F1), Router einhängen |
| `earthx/gateway/client.py` | `gateway` | `get()` bekommt `retry: bool = True` wie `post_json` schon hat (§9) |

`catalog` hält Cache und Slot, obwohl beides nicht zum STAC-Modell gehört, weil
dort heute alle Postgres-Stücke von `api` liegen (`search_cache`,
`stats_cache`, `local_coverage`); ein eigenes Modul dafür wäre ein neues Modul
in 3.1. `shapely` ist in `adapters` schon im Einsatz (`federated_search`).

---

## 6. Woher der Geocoder-Host in die Allowlist kommt (→ F1)

Heute baut `api/dependencies.py` genau ein `Gateway`, dessen Allowlist aus der
Registry stammt (Endpunkte und `asset_hosts`). Nominatim ist kein Datensatz und
gehört nicht in die Registry.

Die Nutzungsbedingung verlangt, den Dienst „at our request at any time" und
„without requiring a software update" wechseln zu können (§2.1). Für eine
Web-App ist unser Backend der verlangte Proxy: Browser brauchen nie ein Update.
Ob ein neues Release **unseres Backends** schon ein „software update" ist, sagt
die Bedingung nicht; sicher ist, was ohne Release geht.

**Vorschlag:** Der Endpunkt kommt aus einer Umgebungsvariable
`EARTHX_GEOCODER_URL`; **ungesetzt oder leer ist die Ortssuche aus** (`503`,
„Place search is not available"), wie ein leeres `EARTHX_ALLOWED_HOSTS` nichts
erlaubt. `docker-compose.yml` und `.env.example` setzen den öffentlichen
Nominatim-Endpunkt. Beim Start wird der Wert einmal geprüft (nur `https`,
Port 443, keine Zugangsdaten, kein Query, Host über `normalize_host`); ist er
ungültig, startet die Ortssuche nicht und sagt es in einer Log-Zeile ohne den
Wert.

`api` baut daraus ein **zweites, eigenes** `Gateway`, dessen `Policy` genau
diesen einen Host erlaubt und engere Grenzen setzt: eine Verbindung, Antwort
höchstens 2 MiB (gemessen: Russland bei 0,001° gut 0,65 MB), Lesezeit 10 s. Das
Registry-Gateway bleibt, wie es ist.

Damit: Abschalten und Wechsel (etwa auf ein selbst betriebenes Nominatim) sind
ein Neustart mit anderer Variable; keine Datensatz-Route erreicht den
Geocoder und die Ortssuche keine Datenquelle; die Variable verschiebt nur die
Allowlist dieses einen Gateways, nicht die der Datensätze (der Grund, warum
M1-04 die Allowlist aus der Umgebung in die Registry geholt hat, gilt hier nur
für einen einzigen, festen Zweck).

---

## 7. Anfrage und Antwort

**Eingang:** `POST /geocode` mit `{"q": "<Text>"}` (→ F5). Der Text wird
getrimmt und Leerraum zusammengefasst; leer, über 200 Zeichen oder mit
Steuerzeichen → `422` mit englischer Meldung, ohne den Text zu wiederholen.

**An Nominatim:** `GET /search` mit `q`, `format=jsonv2`, `polygon_geojson=1`,
`polygon_threshold=0.001`, `limit=5`, `accept-language=en` (Oberfläche nur
Englisch, D25) und einem User-Agent, der die Anwendung nennt
(`EarthX/<version> (+https://github.com/oscipal/earthX)`), gesetzt im Adapter,
nicht im Gateway.

**Antwort (Form für M3-07b):**

```json
{
  "results": [
    {
      "name": "…",
      "display_name": "…",
      "kind": "boundary/administrative",
      "bbox": [west, south, east, north],
      "outline": { "type": "MultiPolygon", "coordinates": [] },
      "outline_simplified": true
    }
  ],
  "attribution": "© OpenStreetMap contributors",
  "attribution_url": "https://www.openstreetmap.org/copyright",
  "license": "ODbL-1.0"
}
```

- `bbox` in unserer Reihenfolge `[west, süd, ost, nord]` als Zahlen. Eine Box,
  die nicht in −180…180/−90…90 liegt oder west > ost hat, wird verworfen,
  nicht repariert; der Treffer fällt dann ganz weg.
- `outline` nur für `Polygon`/`MultiPolygon`, sonst `null` (Punkt, Linie).
  Ungültige Umrisse (`shapely.is_valid` falsch) werden einmal mit
  `make_valid` versucht; bleibt kein Polygon übrig, `null`.
- **Deckel der Punktanzahl (→ F4):** Liegt der Umriss darüber, wird er mit
  `shapely.simplify(preserve_topology=True)` und wachsender Toleranz
  (verdoppelt ab 0,001°, höchstens 12 Schritte) vereinfacht, bis er
  darunter liegt; `outline_simplified` sagt, ob das geschah. Gelingt es nicht,
  `outline: null` und nur die Box.
- `kind` ist `category/type` von Nominatim, damit die Liste in M3-07b etwas
  unterscheiden kann; `osm_id`, `place_id`, `importance`, `lat/lon` und
  `licence` je Treffer gehen nicht hinaus (die Attribution steht einmal oben).

**Fehlerabbildung:**

| Fall | Antwort |
|---|---|
| kein Treffer | `200`, `results: []` |
| Eingabe leer, zu lang, Steuerzeichen | `422` |
| kein Raten-Slot in der Wartefrist (§9) | `503`, `Retry-After` |
| Nominatim `429` | `503`, `Retry-After` (§9) |
| Nominatim `5xx`, Zeitablauf, nicht erreichbar | `502` bzw. `504` |
| Nominatim `403` (Sperre) oder unerwartete Form | `502` |
| Antwort über 2 MiB | `502` |

Kein Fehlertext enthält den Suchtext oder den Auszug der Quelle
(`UpstreamError.excerpt` kann Teile der Anfrage spiegeln).

---

## 8. Cache (→ F3)

Eigene Tabelle `public.earthx_geocode_cache` (Schlüssel, Nutzlast `jsonb`,
Ablauf, Anlage), gleich gebaut wie `earthx_search_cache`, aber getrennt: Die
Suchcache-Tabelle trägt `dataset_id NOT NULL`, und ein Pseudo-Datensatz
„geocoder" darin wäre ein Sonderfall, den jede spätere Aufräumarbeit kennen
müsste.

- **Schlüssel:** SHA-256 über den normalisierten Text (klein, getrimmt,
  Leerraum zusammengefasst), den Host aus `EARTHX_GEOCODER_URL` und die
  festen Parameter (Schwellwert, Limit, Sprache, Deckel), damit eine Änderung der Parameter alte Einträge nicht
  wiederverwendet. Gespeichert wird die **fertige, vereinfachte** Antwort,
  nicht die Rohantwort von Nominatim.
- **Frist:** Vorschlag in F3. Leere Treffer bekommen eine kurze Frist (1 Tag),
  damit ein neu eingetragener Ort nicht lange fehlt. Fehler werden nie gecacht.
- **Ausfall (E5):** Lesen oder Schreiben schlägt fehl → Log-Zeile ohne Inhalt,
  Anfrage geht an Nominatim wie ohne Cache.
- **Aufräumen:** Wie beim Suchcache wird über die Frist hinweg gelesen, nicht
  gelöscht; ein Index auf `expires_at` liegt für den späteren Sweep bereit.

Datenschutz: Der Cache enthält keinen Suchtext, aber die Treffer. Wer die
Datenbank lesen kann, sieht also, *welche* Orte gesucht wurden, nicht von wem
und nicht mit welchem Wortlaut. Das ist dieselbe Lage wie beim Suchcache mit
AOIs.

---

## 9. Rate über alle Prozesse (→ F2)

Das Gateway kann die Rate nicht halten: Es läuft auch im lokalen Runner und
darf keinen Plattformdienst kennen (B9), und ein Token-Bucket im Speicher gilt
nur für einen Prozess. Die gemeinsame Stelle aller `api`-Prozesse ist Postgres.

**Vorschlag: ein Slot-Zeiger in Postgres.** Eine Zeile
`public.earthx_rate_slots(name, next_slot)`; eine einzige Anweisung reserviert
atomar den nächsten freien Zeitpunkt:

```sql
UPDATE public.earthx_rate_slots
   SET next_slot = greatest(next_slot, clock_timestamp()) + interval '1 second'
 WHERE name = 'nominatim'
RETURNING next_slot - interval '1 second';   -- der eigene Slot
```

Der Aufrufer schläft bis zu seinem Slot und sendet dann. Liegt der Slot mehr
als 2 s in der Zukunft, sendet er nicht, sondern antwortet `503` mit
`Retry-After`; der reservierte Slot verfällt ungenutzt (das hält die Rate
höchstens niedriger, nie höher). Keine Sperre wird über die Wartezeit
gehalten, keine Pool-Verbindung blockiert.

Dazu:

- **Keine Wiederholung im Gateway** für diesen Aufruf (`get(..., retry=False)`):
  Jede Wiederholung wäre eine weitere Anfrage ohne Slot.
- **Nominatim antwortet `429`:** Der Slot-Zeiger wird um feste 30 s nach vorn
  geschoben; bis dahin antworten alle Prozesse ohne Anfrage mit `503`. Fest,
  weil `UpstreamError` nur Status und Auszug trägt, keine Header; das Gateway
  dafür zu erweitern lohnt erst, wenn ein `429` tatsächlich vorkommt.
- **Cache-Treffer brauchen keinen Slot**, der Cache wird zuerst gefragt.
- **Postgres nicht erreichbar:** Die Ortssuche antwortet `503`, statt ohne
  gemeinsame Rate zu senden (Variante in F2). Das weicht von E5 ab, das nur für
  Caches gilt: Der Slot ist eine Zusage an die Quelle, kein Beschleuniger.

---

## 10. Logging

- Die Route schreibt eine Zeile je Anfrage: Ergebnis (`hit`, `empty`,
  `rejected`, `rate_limited`, `upstream_error`), Anzahl Treffer, Cache ja/nein,
  Dauer, Upstream-Status. Nie Suchtext, Treffernamen, Koordinaten oder
  `exc_info` eines Gateway-Fehlers (dessen Text kann den Auszug der Quelle
  tragen).
- Das Gateway loggt wie immer Host, Pfad `/search` und den HMAC der
  Query (`_query_digest`), nicht die Query selbst.
- Das Zugriffslog (`RequestIdMiddleware`) sieht nur `POST /geocode`; mit F5 (1)
  steht der Text auch in keinem Query-String, den ein späterer Reverse-Proxy
  mitschreiben könnte.

---

## 11. Tests

Alle ohne Netz; Nominatim-Antworten als **synthetische** Fixtures unter
`backend/tests/fixtures/nominatim/` (erfundene Orte und Koordinaten, keine
Kopie echter OSM-Daten), eingespielt über `httpx.MockTransport` am Gateway.

**Adapter (`tests/earthx/adapters/test_nominatim.py`):**
- Treffer mit Umriss: Box umgestellt auf `[w, s, e, n]`, Umriss unverändert
  unter dem Deckel, `outline_simplified: false`.
- Umriss über dem Deckel: vereinfacht, darunter, gültig, `outline_simplified: true`.
- Treffer nur mit Punkt, Treffer als Linie: `outline: null`, Box vorhanden.
- Kein Treffer: `[]`.
- Unerwartete Form (kein Array, Box mit drei Werten, Box als Text, west > ost,
  Breite über 90): Treffer verworfen bzw. `502`, nie ein Absturz.
- Ungültiger Umriss (Selbstschnitt): repariert oder `null`.
- User-Agent und Parameter der ausgehenden Anfrage wie in §7.
- Quelle `429`, `500`, `503`, `403`,
  Zeitablauf, Antwort über 2 MiB: richtige Ausnahme, **genau eine** Anfrage
  (keine Wiederholung).

**Route (`tests/earthx/api/test_geocode_route.py`):**
- Leere Eingabe, nur Leerraum, 201 Zeichen, Steuerzeichen, fehlendes Feld,
  falscher Typ, GET statt POST: `422` bzw. `405`.
- Fehlerabbildung aus der Tabelle in §7, `Retry-After` gesetzt.
- Attribution, Lizenz und Link in jeder `200`-Antwort, auch bei `results: []`.
- **Kein Suchtext im Log:** ein markanter Suchtext und ein markanter TrefferName
  aus der Fixture tauchen in keiner Log-Zeile auf (`caplog` über alle Logger,
  Erfolg, Cache-Treffer und jeder Fehlerfall).
- Cache fällt aus (Protokoll-Double wirft): Antwort kommt trotzdem von der
  Quelle.

**Mit echtem Postgres (`tests/integration/test_geocode_cache.py`):**
- Cache: Schreiben, Lesen, Ablauf, gleicher Text in anderer Schreibweise trifft
  denselben Eintrag, anderer Parameter-Satz nicht.
- **Rate greift:** mehrere gleichzeitige Reservierungen über getrennte
  Verbindungen bekommen Slots im Abstand von mindestens 1 s; über der
  Wartefrist kommt „kein Slot"; nach einem `429` liegt der Zeiger um die
  Frist weiter vorn.
- Postgres weg beim Slot: `503`, keine Anfrage an die Quelle.

**Importregeln:** `lint-imports` grün; `test_no_outbound_outside_gateway.py`
deckt die neuen Dateien ohne Änderung ab.

**Nach der Umsetzung im PR:** Latenz der Route per `curl` gegen die laufende
`api` (M2-13): kalt (mit Nominatim) und aus dem Cache, gedrosselt, mit Zahl
der Anfragen.

---

## 12. Fragen an Otto

**F1 — Geocoder-Host in der Allowlist (§6).**
(1) Endpunkt aus `EARTHX_GEOCODER_URL`, ungesetzt = Ortssuche aus;
**eigenes Gateway** nur mit diesem Host und engeren Grenzen. Wechsel und
Abschalten ohne Release. *(Empfehlung)*
(2) Endpunkt als Konstante im Code, eigenes Gateway wie in 1; Wechsel nur per
Release unseres Backends.
(3) Host zusätzlich in die Allowlist des bestehenden Registry-Gateways
(Konstante oder Variable); einfacher, aber alle Routen von `api` erreichen dann
den Geocoder.
**Otto: 1.**

**F2 — Rate über alle Prozesse (§9).**
(1) Slot-Zeiger in Postgres, höchstens 2 s Wartezeit, sonst `503`; Postgres
weg → `503`. *(Empfehlung)*
(2) wie 1, aber Postgres weg → Begrenzer im Speicher je Prozess (1/s; hält die
Rate nur, solange es einen `api`-Prozess gibt, wie heute in compose).
(3) Advisory Lock in Postgres, über die Wartezeit gehalten (blockiert eine
Pool-Verbindung je wartender Anfrage).
**Otto: 1.**

**F3 — Cache-Frist (§8).** Die Bedingung nennt keine Frist (§2.1). Leere
Treffer in allen Fällen 1 Tag.
(1) 30 Tage. Umrisse und Namen ändern sich selten; ein Monat hält die Last an
Nominatim klein, ohne dass eine korrigierte Grenze lange fehlt. *(Empfehlung)*
(2) 7 Tage.
(3) 90 Tage.
**Otto: 1.**

**F4 — Deckel der Punktanzahl (§7).**
(1) 1 000 Punkte — gleich `MAX_INTERSECTS_POINTS` (M3-08), damit der Umriss
ohne weitere Vereinfachung als `intersects` in die Suche passt. *(Empfehlung)*
(2) 20 000 wie beim AOI-Upload (M3-06a); die Suche fiele dann bei großen
Umrissen auf die Bounding Box zurück (M3-08 F2a).
(3) 500.
**Otto: 1.**

**F5 — Form der Route (§7, §10).**
(1) `POST /geocode` mit JSON-Körper: Der Suchtext steht in keiner URL.
*(Empfehlung)*
(2) `GET /geocode?q=…`: einfacher, aber der Text steht im Query-String, den
unser Zugriffslog zwar weglässt, ein späterer Proxy aber mitschreiben könnte.
**Otto: 1.**

---

## 13. Umsetzung (26.09.2026)

Umgesetzt wie oben, mit diesen Ergänzungen gegenüber dem Plan-Text:

- **`gateway.get()` bekommt `retry: bool = True`**, mit demselben Vorzeichen wie
  bei `post_json` (Vorgabe sicher, Abweichler explizit). Bisher galt für jede
  `GET`-Anfrage stillschweigend „immer wiederholbar"; das wird jetzt vom
  Aufrufer entschieden, nicht mehr an der Methode festgemacht. Rückwirkungsfrei
  für jeden bestehenden Aufrufer (kein Aufrufer übergab bisher `retry`), eigener
  Test in `tests/earthx/gateway/test_client.py`.
- **`gateway.inspect_url`/`UrlParts` sind jetzt aus `earthx.gateway` exportiert**
  (waren nur intern in `gateway.policy`), damit `api.dependencies` den
  konfigurierten Endpunkt einmal beim Start prüfen kann, ohne selbst `urllib`
  zu importieren (verboten laut `http-only-in-gateway`).
- **`.importlinter` unverändert** — die neuen Dateien liegen in bereits
  bestehenden Modulen (`adapters`, `catalog`, `api`) und erben deren Verträge.
- Migration `005_geocode.sql`; `earthx_rate_slots` bekommt keine Startzeile,
  der erste `reserve()`/`push_back()` legt die Zeile selbst an (`ON CONFLICT`).
- `tests/integration/conftest.py::SHIPPED_TABLES` und die feste Liste der
  Migrationen in `tests/integration/test_migrations.py` um die zwei neuen
  Tabellen bzw. `005_geocode` ergänzt.

**Getestet:** `pytest` (1567 bestanden, inklusive `tests/integration` gegen die
echte Postgres dieser Sitzung), `ruff check backend`, `lint-imports`. Latenz
und Anzahl der Anfragen an Nominatim: siehe §3 (Plan-Schritt); in dieser
Umsetzungssitzung ging keine weitere Anfrage an die echte Quelle — alle Tests
laufen gegen synthetische Fixtures unter `tests/fixtures/nominatim/`.
