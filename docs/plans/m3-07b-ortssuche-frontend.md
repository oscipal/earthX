# M3-07b — Ortssuche: Frontend: Plan

**Aufgabe:** M3-07b aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B — Plan-Schritt.** Die Session hält nach diesem Plan an; Fragen an
Otto in §10.
**Ort im Repo:** `docs/plans/m3-07b-ortssuche-frontend.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` P8, M3-07b, §1.2
(Oberflächentexte nur Englisch), §3 (Reihenfolge an der Suchkachel
M3-06b → M3-07b → M3-12 → M3-10); `plans/m3-07a-ortssuche-backend.md` §§2, 7,
10, 13 (Route, Antwortform, Fehlerabbildung, Nutzungsbedingung);
`plans/m3-06b-aoi-upload-frontend.md` (Muster für Aufruf, Fehlerzeile, Tests);
`prototyp-inventar.md` F2; Log 20.09., 23.09. und 26.09.2026 (Ortssuche);
heutiger Code in `frontend/src/components/ControlPanel.tsx`,
`frontend/src/api.ts`, `frontend/src/store.ts` (`setAoi`, `flyTo`,
`lastAoi`), `frontend/src/geoUtils.ts` (`searchArea`, `bboxToPolygon`,
`MAX_INTERSECTS_POINTS`), `frontend/vite.config.ts`,
`backend/earthx/api/geocode_route.py`, `backend/earthx/adapters/nominatim.py`.

---

## 1. Ziel in einem Satz

Die Suchkachel bekommt ein eigenes Feld „Place“, das auf Absenden
`POST /geocode` fragt, die Treffer als Liste zeigt und den gewählten Treffer
als AOI übernimmt — mit sichtbarer OSM-Attribution und ohne Autocomplete.

---

## 2. Heutiger Stand

- **Route aus M3-07a** (auf `main`): `POST /geocode` mit `{"q": "<Text>"}`.
  `200` liefert

  ```json
  {
    "results": [
      { "name": "…", "display_name": "…", "kind": "boundary/administrative",
        "bbox": [west, south, east, north],
        "outline": { "type": "MultiPolygon", "coordinates": [] },
        "outline_simplified": true }
    ],
    "attribution": "© OpenStreetMap contributors",
    "attribution_url": "https://www.openstreetmap.org/copyright",
    "license": "ODbL-1.0"
  }
  ```

  Höchstens 5 Treffer. `outline` ist `Polygon`/`MultiPolygon` mit höchstens
  1 000 Punkten (= `MAX_INTERSECTS_POINTS`, M3-07a F4) oder `null` (Punkt-,
  Linien-Treffer, Umriss nicht vereinfachbar). `bbox` ist immer gesetzt und
  geprüft (nie west > ost). Kein Treffer: `200` mit `results: []`, die
  Attribution steht trotzdem darin.
- **Fehler der Route:** `422` (leer, über 200 Zeichen, Steuerzeichen; bei
  fehlendem oder falsch getyptem Feld die Liste von FastAPI), `503` „place
  search is not available“ (kein `EARTHX_GEOCODER_URL` gesetzt — ohne
  `Retry-After`; Postgres weg — mit `Retry-After: 5`), `503` „place search is
  rate-limited, try again shortly“ mit `Retry-After`, `502` (Quelle fehlerhaft
  oder unlesbar), `504` (Zeitablauf).
- **Die Ortssuche ist per Vorgabe aus.** `.env.example` und
  `docker-compose.yml` lassen `EARTHX_GEOCODER_URL` leer (M3-07a F1); README
  §2 sagt, wie man sie einschaltet. Eine Config-Route, an der das Frontend
  das vorher sehen könnte, gibt es nicht (`store.ts`: „no server config
  endpoint any more“).
- **Dev-Proxy** (`vite.config.ts`) leitet `/stac`, `/coverage`, `/aoi` und
  `/collections` weiter, **nicht `/geocode`** — ohne Ergänzung erreicht das
  Feld im Entwicklungsserver die Route nicht.
- **Suchkachel** (`ControlPanel.tsx`): oben „Scene name“ (M2-17), darunter
  „Area of interest“ mit `Toolbar` (Punkt, Rechteck, Polygon) und
  `AoiExtras` (Upload, „Last AOI“), dann Datensatz, Coverage, Datum und der
  eine „Search“-Knopf. Der Kommentar über `SceneNameField` begründet das
  einzelne Freitextfeld noch mit „location search is hidden until M3, F1“.
- **AOI setzen:** `setAoi(geom, point)` pflegt `aoi`, `aoiPoint` und
  `lastAoi` und stößt die Coverage-Aktualisierung an; `flyTo(bbox)` fliegt
  hin. Upload und Zeichenwerkzeug gehen beide diesen Weg.
- **Suche mit der AOI** (`geoUtils.ts::searchArea`): ein achsenparalleles
  Rechteck geht als `bbox`, ein anderes Polygon/MultiPolygon als
  `intersects`, über 1 000 Punkten als `bbox` mit Hinweis. Zuschnitt
  (`aoiClip.ts`) und Download (`access/download.py`) nehmen
  `Polygon`/`MultiPolygon` (in M3-06b nachgesehen). Ein Umriss aus der
  Ortssuche passt damit ohne weitere Arbeit in alle drei Wege.
- **Attribution auf der Karte:** Die Basiskarte ist Esri World Imagery; die
  Kartenattribution nennt heute kein OpenStreetMap.

---

## 3. Umfang

1. **API-Aufruf** `geocodePlace(q: string)` in `frontend/src/api.ts`, neben
   `uploadAoi`: `POST ${BASE}/geocode`, `Content-Type: application/json`,
   Körper `{"q": q}`. Fehler wie überall über `jsonOrThrow` → `HttpError`
   mit Status und `detail`. Typen `PlaceResult` und `PlaceSearchResponse` in
   `api.ts` wie die Antwort in §2.
2. **`frontend/src/placeSearch.ts` (neu)**, gebaut wie `aoiFile.ts`:
   - `searchPlaces(q)` wirft nie, liefert `{ results, attribution,
     attributionUrl }` oder `{ error }` mit einer fertigen Meldung (§6).
     Prüft die Antwort im Rahmen dessen, was das Frontend braucht: ein
     Treffer ohne gültige `bbox` (vier endliche Zahlen) wird verworfen, ein
     `outline`, der kein `Polygon`/`MultiPolygon` ist, gilt als `null`. Das
     ist Abwehr gegen eine unerwartete Antwort, keine zweite Prüfung der
     Geometrie.
   - `placeAoi(result)` liefert die AOI-Geometrie nach F1 und die Box zum
     Hinfliegen.
3. **`PlaceSearchField`** in `ControlPanel.tsx`, im Abschnitt „Area of
   interest“ über der `Toolbar` (Aufbau in §4). Lokaler Zustand im Bauteil
   (Text, Trefferliste, „läuft“); der Store bekommt kein neues Feld. Auswahl
   ruft `setAoi(geom)` und `flyTo(bbox)` wie Upload und Zeichnen; „Last AOI“
   funktioniert damit ohne Änderung.
4. **Attribution** nach F2 (§5).
5. **Dev-Proxy:** `'/geocode': { target: apiTarget, changeOrigin: true }` in
   `vite.config.ts`, Kommentar dort ergänzt (sitzt wie `/coverage` und
   `/aoi` auf der Basis-App von `api`).
6. **Aufräumen:** Der Kommentar über `SceneNameField` verliert den Satz zur
   ausgeblendeten Ortssuche und sagt stattdessen, dass Orte ein eigenes Feld
   haben (M3-07b) — der Grund für getrennte Felder bleibt derselbe (M2-17:
   nicht raten, was der Nutzer meinte).
7. **Doku:** `prototyp-inventar.md` F2 bekommt einen Nachtrag (Route über
   `gateway`, Suche nur auf Absenden, Umriss, Attribution); Zeile im
   `ENTSCHEIDUNGSLOG.md` mit Ottos Antworten; Stand von M3-07b im
   Aufgabenschnitt.

**Verhaltensänderungen gegenüber dem Prototyp (F2):** keine Vorschläge
während des Tippens (Nominatim verbietet Autocomplete, M3-07a §2.1); Enter
nimmt nicht mehr blind den ersten Treffer, sondern zeigt die Liste; der
Treffer wird als Umriss übernommen statt nur als Box (F1).

---

## 4. Ablauf in der Suchkachel

```
Area of interest
  [ Place ______________________ ] [Find]
  ┌ Treffer (höchstens 5) ───────────────────────┐
  │ Berlin                              boundary │
  │   Berlin, Germany                            │
  │ …                                            │
  │ © OpenStreetMap contributors                 │
  └──────────────────────────────────────────────┘
  [Point] [Rectangle] [Polygon] [Clear]   (Toolbar, unverändert)
  [⤒ Upload AOI] [↺ Last AOI]              (AoiExtras, unverändert)
```

- **Absenden:** Enter im Feld oder Knopf „Find“. Leerer oder nur aus
  Leerraum bestehender Text sendet nichts (Knopf gesperrt). `maxLength=200`
  am Feld, gleich dem Deckel der Route; der `422`-Zweig bleibt trotzdem
  abgebildet, weil die Route maßgeblich ist.
- **Während der Anfrage** ist der Knopf gesperrt (`aria-busy`, Text
  „Finding…“), damit ein Doppelklick nicht zwei Anfragen schickt — jede
  zählt gegen die Rate von 1/s über alle Nutzer. Eine neue Suche ersetzt die
  alte Liste; eine noch laufende ältere Anfrage, die später ankommt, wird
  verworfen (Zähler im Bauteil), damit die Liste immer zum Text im Feld
  passt.
- **Treffer:** je Zeile `name` fett, darunter `display_name` klein, rechts
  der erste Teil von `kind` (etwa „boundary“, „place“, „railway“) als Hinweis.
  Zeilen sind Knöpfe (Tastatur: Tab und Enter). Ist ein Umriss vereinfacht
  (`outline_simplified`), steht im `title` „Outline simplified“.
- **Auswahl:** AOI nach F1 setzen, hinfliegen, Liste schließen; der Text im
  Feld bleibt stehen. Die Datensuche startet **nicht** von selbst — wie bei
  Upload und Zeichnen ist „Search“ ein eigener Schritt.
- **Kein Treffer:** in der Liste „No place found.“ mit Attribution (die
  Antwort war trotzdem eine Nominatim-Antwort).
- **Fehler:** in der gemeinsamen Fehlerzeile (`setError`), Texte in §6. Die
  bisherige AOI bleibt.
- **Escape** im Feld oder ein neuer Text schließt die Liste.

Die Liste hängt im Fluss der Kachel, nicht als schwebendes Dropdown: Die
Kachel scrollt schon heute, und ein Overlay müsste sich mit dem
Zeichenwerkzeug und dem Einklappen der Kachel (`panelCollapsed`) vertragen.

**Ortssuche ausgeschaltet:** Das Feld ist immer sichtbar. Ist
`EARTHX_GEOCODER_URL` nicht gesetzt, liefert die erste Suche `503` ohne
`Retry-After`, und die Fehlerzeile sagt, dass die Ortssuche auf diesem Server
nicht eingeschaltet ist (§6). Das Feld vorher auszublenden hieße, beim Start
eine Probeanfrage zu schicken oder eine Config-Route zu bauen; beides ist
mehr, als die Aufgabe verlangt.

---

## 5. Attribution (→ F2)

Die Nutzungsbedingung verlangt „Clearly display attribution as suitable for
your medium“ (M3-07a §2.1); die Antwort trägt `attribution` und
`attribution_url` in jeder `200`. Das Frontend zeigt den Text aus der
Antwort, nicht eine eigene Konstante, damit ein Wechsel des Anbieters
(M3-07a F1) ohne Frontend-Änderung die richtige Attribution zeigt; als Link
nur, wenn `attribution_url` mit `https://` beginnt (`rel="noopener
noreferrer"`, `target="_blank"`).

Vorschlag (F2, Option 1): unter der Trefferliste, solange sie offen ist; und
nach der Auswahl eine kleine Zeile unter dem Feld — „<name> · © OpenStreetMap
contributors“ —, solange die AOI noch die aus der Ortssuche ist. Das Bauteil
merkt sich dafür die übernommene Geometrie und vergleicht sie per Identität
mit `aoi` im Store; zeichnet der Nutzer neu, lädt hoch oder löscht die AOI,
verschwindet die Zeile. Kein neues Store-Feld, keine Änderung an `MapView`.

---

## 6. Fehlerabbildung

Alle Texte englisch, ohne Suchtext und ohne Koordinaten (der Suchtext steht
ohnehin im Feld darüber). Muster wie M3-06b F1: eigene Texte für Netz,
Server und Rate; bei `422` der Text der Route mit Vorspann.

| Fall | Meldung (Vorschlag) |
|---|---|
| `422` mit `detail` als Text | `Could not search for this place: <detail>.` |
| `422` ohne lesbares `detail` (FastAPI-Liste) | `Could not search for this place.` |
| `503` mit `Retry-After` | `Place search is busy. Please try again in a few seconds.` |
| `503` ohne `Retry-After` | `Place search is not enabled on this server.` |
| `502`, `504` | `The place search service did not answer. Please try again.` |
| anderer Status | `Place search failed (<status>). Please try again.` |
| Netzwerkfehler (`fetch` wirft) | `Could not reach the server for place search.` |
| `200` ohne `results`-Liste | `Place search returned an answer that could not be read.` |

`Retry-After` unterscheidet die beiden `503`: Die Rate und ein Postgres-Ausfall
setzen ihn (beide vorübergehend), das fehlende `EARTHX_GEOCODER_URL` nicht
(dauerhaft, bis jemand den Server umstellt). Der Status allein reicht dafür
nicht, und den Text der Route abzugleichen bräche still, sobald er sich
ändert (M3-06b F1, Option 2). Dafür bekommt `HttpError` ein optionales Feld
`retryAfter` (Rohwert des Headers), gesetzt in `jsonOrThrow`; bestehende
Aufrufer merken davon nichts. Der Wert wird nicht als Sekundenzahl angezeigt:
„a few seconds“ stimmt für 1–5 s, und nach einem `429` der Quelle wären es
30 s — eine Zahl würde dann mehr versprechen, als der nächste Versuch hält.

---

## 7. Tests (Vitest)

`frontend/src/placeSearch.test.ts` (neu), Ergänzungen in `api.test.ts` und
`components/ControlPanel.test.tsx`; `fetch` über `vi.stubGlobal` wie in den
bestehenden Tests; alle Orte und Koordinaten erfunden.

- **Aufruf:** `POST` an `/geocode`, Körper genau `{"q": …}` als JSON, der
  Text steht in keiner URL; `retryAfter` in `HttpError` gesetzt bzw. leer.
- **Übernahme als AOI (Abnahme der Aufgabe):** Treffer mit `Polygon`- und
  mit `MultiPolygon`-Umriss → genau dieser Umriss wird `aoi` (nach F1),
  `aoiPoint` bleibt `null`, `lastAoi` folgt, `flyToBbox` ist die `bbox` des
  Treffers; Treffer mit `outline: null` → Rechteck aus der `bbox`
  (`bboxToPolygon`), `searchArea` macht daraus eine `bbox`-Suche.
- **Liste:** mehrere Treffer werden in Reihenfolge gezeigt, Auswahl schließt
  sie, keine Datensuche startet von selbst (`runSearch` nicht aufgerufen);
  `results: []` zeigt „No place found.“ mit Attribution.
- **Attribution:** Text und Link aus der Antwort; ein `attribution_url`
  ohne `https://` (etwa `javascript:`) wird nicht als Link gerendert; die
  Zeile unter dem Feld verschwindet, sobald `aoi` im Store eine andere
  Geometrie wird oder `null`.
- **Fehlerabbildung**, je eine Zeile aus §6, dazu: die bisherige AOI bleibt
  bei jedem Fehler unverändert.
- **Fehlerhafte Antworten:** `results` fehlt, ist kein Array, ist `null`;
  Treffer mit `bbox` aus drei Werten, als Text, mit `NaN`; `outline` mit
  `LineString` oder ohne `type` → Treffer verworfen bzw. Box statt Umriss,
  nie ein Absturz.
- **Zweckfremde Nutzung:** leerer Text und nur Leerraum → kein `fetch`;
  Enter während einer laufenden Anfrage → kein zweiter `fetch`; zwei Suchen
  kurz nacheinander, die erste antwortet zuletzt → die Liste zeigt die
  zweite; Text mit HTML (`<img src=x onerror=…>`) im `display_name` wird als
  Text gezeigt, nicht als Markup; sehr langer `display_name` bricht die
  Kachel nicht (CSS-Umbruch, geprüft per Klasse).

Dazu `npm run lint`, `npx tsc -b --pretty false`, `npm test`. Das Backend
bleibt unverändert; `ruff check backend`, `pytest` und `lint-imports` laufen
trotzdem einmal zur Bestätigung.

**Abnahme durch Otto** (laut Aufgabe): lokal `EARTHX_GEOCODER_URL` setzen
(README §2), einen Ort suchen, einen Treffer wählen und damit eine
Datensuche starten. Der PR nennt die Befehle. In der Cloud-Sitzung geht
keine Anfrage an Nominatim; die Tests laufen gegen gestubbte Antworten.

---

## 8. Größe

Geschätzt rund 150 Zeilen Code (`api.ts`, `placeSearch.ts`,
`ControlPanel.tsx`, `index.css`, `vite.config.ts`) und rund 250 Zeilen Tests,
dazu Doku — unter dem Richtwert von 400 Zeilen ohne Tests nicht gerechnet,
mit Tests knapp darüber. Ich halte den PR trotzdem zusammen: Die Tests
gehören zur Abnahme, und eine Aufteilung ließe ein Feld ohne Tests auf `main`.

---

## 9. Nicht in dieser Aufgabe

- Änderungen an der Route (M3-07a, erledigt).
- Autocomplete oder Vorschläge beim Tippen (verboten, M3-07a §2.1).
- Datensatz-Filter (M3-10) und Registry-Sonderfälle (M3-12) an derselben
  Kachel; M3-12 ist bereits auf `main`, M3-10 kommt danach.
- Die Klärung der Nominatim-Bedingungen für das erste öffentliche Deployment
  (Log 23.09.2026, bleibt offen).
- **Befund für diese Klärung:** Ein Umriss aus der Ortssuche geht als AOI
  auch in den Download-ZIP (P21: „einmal je ZIP die Original-AOI als
  GeoJSON“). Dieser Umriss ist OSM-Ableitung unter ODbL, die
  `ATTRIBUTION.txt` im ZIP nennt heute nur die Datenquelle des Datensatzes.
  Damit der ZIP das nennen könnte, müsste die AOI ihre Herkunft bis in die
  Download-Anfrage mitführen (Store, API, `access/download.py`) — das ist
  eine eigene Aufgabe. Ich schlage vor, den Punkt als offen ins Log zu
  schreiben (F3).
- Ein Produktions-Reverse-Proxy für `/geocode`: Es gibt noch kein Deployment
  des Frontends; das Thema kommt mit M6 (wie `/aoi` in M3-06b).

---

## 10. Fragen an Otto

**F1 — Umriss oder Bounding Box (Aufgabe: „Im Plan-Schritt vorschlagen“).**
(1) **Umriss als Vorgabe, wo es einen gibt, sonst die Box; keine Wahl.**
Die Ortssuche soll „mit Umriss“ kommen (P8, Aufgabenschnitt §2); der Umriss
passt nach M3-07a F4 immer als `intersects` in die Suche, der Zuschnitt
(P12) zeigt dann wirklich nur den Ort, und wer die Box will, zieht sie mit
dem Rechteck-Werkzeug. Punkt- und Linien-Treffer (Bahnhof, Straße) nehmen
die Box aus der Antwort. *(Empfehlung)*
(2) Umriss als Vorgabe wie in 1, dazu je Treffer ein kleiner Zweitknopf
„Box“, der stattdessen das Rechteck übernimmt. Nützlich, wo der Umriss für
die Aufgabe zu knapp ist (Küstenorte ohne Meer, Inseln); eine Bedienstelle
mehr je Zeile.
(3) Immer die Box, wie im Prototyp. Einfacher, aber die Suche trifft dann
auch Szenen neben dem Ort, und der Umriss aus M3-07a bliebe ungenutzt.
(4) Ein Schalter „Outline / Box“ am Feld, gilt für jede Auswahl.

**F2 — Wo die Attribution steht (§5).**
(1) Unter der offenen Trefferliste und danach als Zeile unter dem Feld,
solange die übernommene AOI aktiv ist; ohne Store-Änderung. *(Empfehlung)*
(2) Nur unter der offenen Trefferliste. Weniger Code; nach der Auswahl ist
die OSM-Herkunft der AOI nirgends mehr zu sehen.
(3) Wie 1, zusätzlich in der Kartenattribution (MapLibre), solange die AOI
aus der Ortssuche aktiv ist. Braucht ein Store-Feld für die Herkunft der AOI
und eine Änderung an `MapView`.

**F3 — OSM-Umriss im Download-ZIP (§9).**
(1) In M3-07b nichts daran ändern; eine Log-Zeile hält den Punkt als offen
fest, zur Klärung zusammen mit den Nominatim-Bedingungen vor dem ersten
öffentlichen Deployment. *(Empfehlung)*
(2) Als eigene Aufgabe in den Aufgabenschnitt aufnehmen (AOI-Herkunft bis
in `ATTRIBUTION.txt`), noch in M3.
(3) In diesem PR mit erledigen (berührt Store, API und `access/download.py`,
sprengt den Richtwert).

---

## 11. Umsetzung (26.09.2026)

Freigabe: F1 (1), F2 (1), F3 (3).

Umgesetzt wie oben, mit dieser Ergänzung zu F3: Die AOI trägt ihre Herkunft
als `properties`-Schlüssel auf der Geometrie selbst (nie als `Feature`, wie
Otto es verlangt hat — `placeAoi()` in `placeSearch.ts` liefert
`{ ...geometry, properties: { source, attribution, license } }`); der Store,
`searchArea` und der Download-Aufruf nehmen weiterhin eine bloße
`GeoJSON.Geometry` entgegen, ohne eigene Änderung.

**Kein Code in `access/download.py` musste dafür geändert werden.** Die
Route lässt Eigenschaften schon heute unverändert durch: `body.aoi` ist ein
`dict[str, Any]` (kein enges Pydantic-Modell, das sie abschneiden würde),
`parse_aoi_geometry` prüft mit `shapely.geometry.shape`, das nur `type` und
`coordinates` liest und jeden weiteren Schlüssel ignoriert, und
`build_download_zip` schreibt `aoi_geometry` unverändert über
`json.dumps(dict(aoi_geometry))` in `aoi.geojson`. Die „kleine Änderung, die
ausdrücklich erlaubt ist" war damit nicht nötig — ein neuer Test in
`test_download.py` (`test_aoi_geojson_keeps_extra_properties_the_caller_put_on_the_geometry`)
hält das als Verhalten fest, statt es unbelegt zu lassen. Eine hochgeladene
oder gezeichnete AOI trägt weiterhin keine `properties`.

Nebenbei: `HttpError` (`api.ts`) bekommt `retryAfter` (Rohwert des
`Retry-After`-Headers, `res.headers?.get(...)` — mit `?.`, damit bestehende
Tests mit einer Mock-`Response` ohne `headers`-Feld weiterlaufen). Der
Kommentar über `SceneNameField` verliert den Verweis auf „location search is
hidden until M3, F1". `frontend/package-lock.json` war zu Beginn dieser
Sitzung nicht vollständig installiert (`polyclip-ts` fehlte, wie in M3-24
beschrieben); `npm ci` vor dem ersten `tsc`-Lauf behoben.

**Getestet:** `npm run lint` (oxlint, sauber), `npx tsc -b --pretty false`
(sauber), `npm test` (469 bestanden, 21 Dateien). Backend unverändert bis auf
den einen neuen Test: `ruff check backend` (sauber), `pytest` vom
Repo-Wurzelverzeichnis ohne `backend/tests_live` (1671 bestanden), `lint-imports`
(12 Verträge, 0 gebrochen).
