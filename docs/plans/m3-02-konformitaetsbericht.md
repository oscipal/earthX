# M3-02 — Architektur-Konformitätsbericht

**Status:** Bericht der Stufe C vom 23.09.2026. Nur gelesen, kein Code geändert.
**Ort im Repo:** `docs/plans/m3-02-konformitaetsbericht.md`
**Stand des Codes:** `main` bei Commit `f0f670d` (nach PR #73).
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` (M3-02, P10, P18);
`architekturplan.md` 3.1, 3.2, 5.1, 5.2, 6.1–6.5, 12.4, 13; `KLAERUNGEN.md`
B8–B13; `CLAUDE.md` („Unverrückbar“, „Arbeitsweise“); `projektplan.md` 7;
`adr/0004`, `adr/0005`, `adr/0006`; `ENTSCHEIDUNGSLOG.md`.

**Schwere:**

- **Blocker** — verletzt eine unverrückbare Regel aus `CLAUDE.md` oder den
  Klärungen, heute und im laufenden Betrieb.
- **Schuld** — Abweichung vom Architekturplan, die beim Ausbau in M3/M4 stört
  oder einen Datensatz falsch behandeln würde, der noch nicht da ist.
- **Hinweis** — Kleinigkeit: veraltete Doku, toter Rest, Doppelung.

Jeder Fund trägt eine Kennung (K-xx für Backend und Querschnitt, F-xx für das
Frontend), eine Fundstelle und einen Vorschlag, in welche Aufgabe des M3-Plans
er gehört. Jeder Fund ist am Code nachgeprüft; was nur vermutet ist, steht als
„unbelegt“ da.

---

## 0. Kurzfassung

- **Ein Blocker:** Der Prozess `api` schreibt die AOI-Bounding-Box der Suche
  im Klartext ins Log, über das Standard-Access-Log von uvicorn (K-01). Die
  vorhandene Logging-Konfiguration mit Request-ID und Geometrie-Reduktion ist
  in keinem Prozess eingebunden (K-02).
- **Die Importverträge halten** (12 von 12), und im Code gibt es keine
  Umgehung, die sie nicht fassen: alles Ausgehende läuft über `gateway`, GDAL
  sieht nur geprüfte Pfade, der Zarr-Reader holt jedes Byte über `gateway`.
- **Die Schulden sammeln sich an einer Stelle:** Das Registry- und
  Dispatch-Modell kennt nur die beiden föderierten STAC-Quellen. Eine Quelle
  mit materialisierten Items hat heute keinen Platz darin (K-05), die
  Coverage-Route verdrahtet Earth Search und EOPF fest (K-06), und die
  Zugriffsauflösung liegt im Prozess-Modul `api/tiler.py` statt hinter einer
  Adapter-Nahtstelle (K-04). Das ist Eingabe für M3-11 und M3-14.
- **Die Kachelroute prüft die Lizenzstufe nicht** (K-03). Heute folgenlos,
  weil beide Datensätze die Stufe `processing` tragen; für den dritten
  Datensatz entscheidet Otto die Stufe erst nach M3-01.
- **Frontend:** 16 datensatz- oder quellenspezifische Stellen (Abschnitt 5).
  Ein statisches globales Raster in EPSG:4326 — wie die Kandidaten Hansen GFC
  und Copernicus DEM — träfe mindestens vier davon hart: keine
  Quicklook-Platzierung außerhalb von UTM (F-03), keine Anzeige der Ausdehnung
  eines Einmal-Produkts in der Coverage (F-07), ein Datumsfeld ohne Zeitachse
  (F-06), eine Vorschau-Stufe, die bei `min_zoom = 0` fast nichts zeigt (F-05).

| Schwere | K-Funde (Backend, Querschnitt) | F-Funde (Frontend, Abschnitt 5) | Summe |
|---|---|---|---|
| Blocker | 1 | 0 | 1 |
| Schuld | 8 | 8 | 16 |
| Hinweis | 19 | 8 | 27 |

---

## 1. Prüflauf dieser Sitzung

Aus dem Repo-Wurzelverzeichnis bzw. `frontend/`, Python 3.11 der Session:

| Prüfung | Ergebnis |
|---|---|
| `ruff check backend` | All checks passed |
| `lint-imports --config .importlinter` | 12 Verträge eingehalten, 0 gebrochen (97 Dateien, 293 Abhängigkeiten) |
| `pytest` | 1067 bestanden, 0 fehlgeschlagen (728 Warnungen, vor allem `rioxarray`/`zarr` Deprecation) |
| `npm run lint` (oxlint) | ohne Befund |
| `npx tsc -b --pretty false` | ohne Befund |
| `npx vitest run` | 13 Dateien, 222 Tests bestanden |

Vorgehen: alle Module unter `backend/earthx/` und `frontend/src/` gelesen, die
Fundstellen per `grep` gegengeprüft; ungenutzte Symbole mit einem kleinen
AST-Skript außerhalb des Repos gesucht (jede Definition, die außer an ihrer
eigenen Stelle nirgends im Paket vorkommt).

---

## 2. Backend: Verantwortlichkeiten, Umgehungen, Regeln

### K-01 — AOI-Bounding-Box im Access-Log des Prozesses `api` · **Blocker**

- **Fundstelle:** `docker-compose.yml:89` startet `uvicorn earthx.api.main:app`
  ohne `--no-access-log` und ohne eigene Log-Konfiguration. uvicorn 0.53
  schreibt je Anfrage Pfad **mit Query-String** ins Log
  (`uvicorn/protocols/utils.py:58`, `get_path_with_query_string`).
- **Was dort landet:** Der Viewer sucht per
  `GET /stac/search?collections=…&bbox=<AOI-Bbox>` (`frontend/src/api.ts:92`,
  aufgerufen aus `store.ts:816` und `:842` mit `polygonBbox(aoi)`), und die
  Coverage-Route nimmt `bbox` und `intersects` als Query-Parameter
  (`backend/earthx/api/coverage_route.py:65–75`). Beides steht damit
  koordinatengenau im Log.
- **Regel:** `CLAUDE.md` „Unverrückbar“ (keine exakten AOIs in Logs);
  `projektplan.md` 7, Punkt 6. `gateway` selbst hält sich daran — es loggt nur
  einen Hash des Query-Strings (`gateway/client.py:71`) — aber die Anfrage an
  den eigenen Prozess wird vorher schon geloggt.
- **Nicht betroffen:** `tiler` (Kachel-URLs tragen keine AOI; der Download
  schickt die AOI im `POST`-Body).
- **Vorschlag:** kleine eigene Aufgabe der Stufe A **vor** M3-08, zusammen mit
  K-02; M3-08 bringt `intersects` als weiteren Query-Parameter und setzt
  voraus, dass das Access-Log die Geometrie nicht mitschreibt. Siehe Frage 1.

### K-02 — Logging-Konfiguration aus M1-01 ist nirgends eingebunden · **Schuld**

- **Fundstelle:** `backend/earthx/logging.py:77` (`configure_logging`), `:90`
  (`RequestIdMiddleware`), `:127` (`summarize_geometry`). Keines der drei wird
  außerhalb von `backend/tests/test_logging.py` aufgerufen; kein Prozess
  (`api/main.py`, `api/tiler.py`, `jobs/main.py`, `discovery/main.py`) ruft
  `add_middleware` oder `configure_logging`.
- **Folge:** Die Prozesse loggen im Textformat von uvicorn, ohne Request-ID;
  die Felder aus `extra=` (z. B. `api/tiler.py:461–469`) fallen im
  Standard-Formatter weg. `architekturplan.md` 12.4 und der Docstring von
  `logging.py` („Every process logs one JSON object per line“) beschreiben
  einen Zustand, den es im Betrieb nicht gibt. Die Tests prüfen die Bausteine,
  nicht ihre Verwendung.
- **Vorschlag:** mit K-01 in derselben Aufgabe; dazu ein Test, der für jeden
  Prozess-Einstiegspunkt die Middleware nachweist.

### K-03 — Kachelroute prüft die Lizenzstufe nicht · **Schuld**

- **Fundstelle:** Der Download verlangt `LicenseTier.PROCESSING`
  (`api/tiler.py:402`). Die Kachel-, Statistik-, Info- und Punkt-Routen laufen
  über `dataset_asset_path` (`api/tiler.py:346`) und prüfen die Stufe gar
  nicht; `backend/tests/earthx/api/test_tiler.py` hat keinen Lizenz-Test.
  `DatasetConfig._check_license_tier` (`catalog/registry.py:530`) verbietet
  auch nicht, dass ein Eintrag der Stufe `catalog` ein `viewer`-Feld trägt.
- **Regel:** `KLAERUNGEN.md` B11 — Anzeige (Kacheln, Quicklooks über eigene
  Dienste) erst ab Stufe „Anzeige“; ND-Datensätze nur als Katalogeintrag mit
  Link.
- **Folge heute:** keine, beide Einträge tragen `processing`. Ein dritter
  Datensatz der Stufe `catalog` bekäme trotzdem Kacheln.
- **Vorschlag:** M3-11, vor dem Registry-Eintrag des dritten Datensatzes
  (Otto stuft dessen Lizenz nach M3-01 ein). Siehe Frage 2.

### K-04 — Zugriffsauflösung liegt im Prozess-Modul `api/tiler.py` · **Schuld**

- **Fundstelle:** `api/tiler.py:279` (`_resolve_asset_path`: Reader-Wahl nach
  `format`, Asset-Href, Zarr-Variablentrennung), `:166` (`_target_gsd`:
  Wahl der Zarr-Stufe aus der Kachelgeometrie), `:140` (`_proj_code`).
  Die Datei ist mit 608 Zeilen das größte Modul in `api`.
- **Regel:** `architekturplan.md` 6.1 ordnet „Zugriffsauflösung — welche
  lesbare Adresse und welcher Reader gehören zu diesem Asset?“ den Adaptern zu,
  genutzt von `access` **und `processing`**. Der heutige Ort ist mit Ottos
  Antwort 5 vom 20.09.2026 begründet (`access` darf `gateway` nicht
  importieren), aber `processing` (M4) darf `api` nicht importieren und müsste
  die Auflösung dann ein zweites Mal bauen.
- **Vorschlag:** M3-14 (`adr/0011`) als Frage „wo lebt die
  Zugriffsauflösung“; kein Umbau in M3.

### K-05 — Für materialisierte Items gibt es im Registry-Modell keinen Platz · **Schuld**

- **Fundstelle:** `catalog/registry.py:56–60` (`AdapterKind` kennt nur
  `earth-search-v1` und `eopf-stac-v1`), `:199–214` (`SourceInfo.adapter` ist
  Pflicht). `api/federating_client.py:256–271` und `:288–290` behandeln jede
  Collection mit bekanntem Adapter als föderiert und jede andere als eigene
  pgstac-Collection.
- **Folge:** Der dritte Datensatz (ohne Such-API, Items im eigenen pgstac,
  `architekturplan.md` 5.2) lässt sich heute nur eintragen, wenn M3-11 das
  Modell ändert — entweder ein weiterer `AdapterKind`, den die Föderation als
  „eigen“ erkennt, oder eine eigene Kennzeichnung der Item-Haltung. Umgekehrt
  würde ein Tippfehler im Adapterwert, der pgstac erreicht, still als „eigen“
  gelten (`ValueError` → `None`, Zeile 270) und eine leere, gültig aussehende
  Antwort liefern — gegen `adr/0005` Regel I.
- **Vorschlag:** M3-11 im Plan-Schritt (Feldform vorschlagen, B10: ohne
  Vorgabewert); Beobachtung für M3-14.

### K-06 — Coverage-Route verdrahtet die Quellen fest · **Schuld**

- **Fundstelle:** `api/coverage_route.py:116–117`:
  `source = aggregate_coverage if is_upstream else sample_coverage`.
  `upstream-aggregation` heißt damit immer Earth Search, `sample` immer EOPF
  (`adapters/eopf_sample_coverage.py` sucht über `eopf_stac`).
  `local-sql` antwortet `501` (`:56`, `:91–99`).
- **Folge:** Die Suche wählt den Adapter über `AdapterKind`
  (`adapters/__init__.py:45–48`), die Coverage nur über den Provider. Eine
  dritte Quelle mit Stichprobe oder eigener Aggregation landet beim falschen
  Adapter; eine Quelle mit materialisierten Items braucht den noch fehlenden
  SQL-Weg aus `adr/0004`.
- **Vorschlag:** M3-11 (Coverage laut `adr/0009`); Beobachtung für M3-14.

### K-07 — Architekturplan 6.1 widerspricht 3.1 bei „genutzt von“ · **Schuld**

- **Fundstelle:** `architekturplan.md` 6.1 nennt als Nutzer der Fähigkeiten
  Suche und Aggregation das Modul `catalog`. `catalog` darf laut 3.1 aber nur
  `gateway` importieren, also keinen Adapter aufrufen. Im Code komponiert
  `api` (`api/federating_client.py`, `api/coverage_route.py`); `catalog`
  liefert nur Modelle, die Nahtstelle (`catalog/coverage.py`) und den Cache.
- **Vorschlag:** M3-14 klärt in `adr/0011`, wer die Fähigkeiten aufruft;
  danach eine Zeile in 6.1.

### K-08 — `max_cloud_cover` ist ein generischer Parameter mit optischer Bedeutung · **Hinweis**

- **Fundstelle:** `catalog/coverage.py:135` (Feld der `CoverageQuery`),
  `api/coverage_route.py:75`; übersetzt zu `eo:cloud_cover` in
  `adapters/earth_search_coverage.py:252–253` und
  `adapters/eopf_sample_coverage.py:192–207`.
- **Folge:** Ein Datensatz ohne `eo:cloud_cover` nimmt den Parameter an. Im
  Stichprobenweg fällt dann jedes Item aus der Stichprobe (Zeile 206–207) und
  die Karte ist leer statt abgewiesen. Das Frontend setzt den Parameter heute
  nicht (`store.ts:97`).
- **Vorschlag:** M3-11 (dritter Datensatz ohne Wolkenbedeckung); ob die Route
  ihn dann mit `400` abweist, im Plan-Schritt.

### K-09 — Adapter lesen den Registry-Inhalt, nicht nur Modelle · **Hinweis**

- **Fundstelle:** `from earthx.catalog.datasets import REGISTRY` als
  Vorgabewert des Parameters `registry` in `adapters/__init__.py:38`,
  `earth_search.py:58`, `earth_search_coverage.py:58`,
  `eopf_sample_coverage.py:67`, `eopf_stac.py:59`.
- **Regel:** `architekturplan.md` 3.1: `adapters` importiert `catalog` „nur
  Modelle“. Die Importverträge fassen das nicht, weil sie Module, nicht Inhalte
  unterscheiden.
- **Vorschlag:** M3-14 (Signaturen: Registry als Argument ohne Vorgabe).

### K-10 — Fetch-Gateway nur teilweise nach 6.5 · **Hinweis**

- **Vorhanden:** Allowlist, SSRF-Prüfung, Redirects innerhalb der Allowlist,
  Größen- und Zeitlimits, Backoff mit `Retry-After`
  (`gateway/client.py:45–49`), Obergrenze paralleler Verbindungen je Host
  (`:90–92`, `:284–286`).
- **Fehlt:** Token-Bucket, Circuit Breaker, Bündelung identischer Anfragen,
  Metriken je Host. Die Verbindungsgrenze gilt je `Gateway`-Instanz, nicht je
  Prozess: `readers/zarr_reader.py:276` öffnet für jeden Store und jede
  Event-Loop ein eigenes `Gateway`; GDAL-Lesezugriffe (COG) laufen an der
  Grenze ganz vorbei (bekannt, B8).
- **Vorschlag:** M3-07a braucht eine prozessübergreifende Rate (1 Anfrage/s an
  Nominatim) und sollte sie so bauen, dass sie das fehlende Token-Bucket
  werden kann; der Rest bleibt vorgemerkt (M5 Health, M6 Egress).

### K-11 — Zwei Quellen der Wahrheit für den Adapter einer Collection · **Hinweis**

- **Fundstelle:** `api/federating_client.py:264` liest `earthx:source` aus dem
  pgstac-Dokument; `adapters/__init__.py:51–55` und `api/tiler.py` lesen die
  Python-Registry. Beide stammen aus derselben Quelle (B13 Punkt 3), laufen aber
  auseinander, solange `earthx.catalog.load` nach einer Registry-Änderung nicht
  erneut lief.
- **Vorschlag:** M3-13 (gemischte Suche baut den Dispatch ohnehin um).

### K-12 — Capability-Flags werden veröffentlicht, aber kaum durchgesetzt · **Hinweis**

- **Fundstelle:** `catalog/registry.py:107–120`. Gelesen werden nur
  `single_coverage_product` (`api/coverage_route.py:86`,
  `catalog/registry.py:567`) und — als Absicht — `quad_pol`. `roi` begrenzt
  den AOI-Download nicht; `time_range` liest das Frontend nicht (F-06).
- **Regel:** B10 fordert gesetzte Flags; dass sie an der Route greifen, fordert
  B10 nicht ausdrücklich — daher Hinweis.
- **Vorschlag:** `time_range` in M3-12 (F-06); die übrigen mit den Operatoren
  in M4.

---

## 3. Toter Code

| # | Fundstelle | Befund | Schwere | Vorschlag |
|---|---|---|---|---|
| K-13 | `gateway/policy.py:96` `policy_from_env`, `:20` `ALLOWED_HOSTS_ENV`, Re-Export in `gateway/__init__.py:23` | Seit M1-04 kommt die Allowlist aus der Registry (`api/dependencies.py:27`); aufgerufen nur noch in `tests/earthx/gateway/test_policy.py`; die Umgebungsvariable steht in keiner Compose- oder Beispieldatei | Hinweis | M3-07a — dort ist zu entscheiden, woher der Geocoder-Host in die Allowlist kommt; danach entfernen oder wiederverwenden |
| K-14 | `catalog/coverage.py:289` `CoverageCache` | Protocol ohne Verwender, auch nicht in Tests; die Coverage-Wege nutzen `adapters.cache.SearchCache` | Hinweis | M3-11 (lokaler SQL-Weg) oder entfernen |
| K-15 | `catalog/stats_cache.py:47` `stats_cache_key` | Nirgends aufgerufen, auch nicht in Tests | Hinweis | M3-04 berührt den Kachelpfad; dort entfernen |
| K-16 | `frontend/src/api.ts:251`, `:262`; `store.ts:550`; `download.ts:80–89`; Kommentar `DownloadDialog.tsx:16` | Das Frontend schickt `language` im Download-Body; `DownloadRequest` (`api/tiler.py:372–384`) kennt das Feld nicht mehr, pydantic verwirft es still. Rest der Sprachwahl, die Otto am 22.09.2026 gestrichen hat | Hinweis | M3-12 (räumt dieselben Dateien auf) |

`jobs/main.py` und `discovery/main.py` sind absichtliche Stubs (M4, M5) und kein
toter Code.

---

## 4. Doku, die nicht mehr zum Code passt

| # | Fundstelle | Widerspruch | Schwere | Vorschlag |
|---|---|---|---|---|
| K-17 | `backend/earthx/__init__.py:3` | „Lives next to the prototype package `app`“ — der Prototyp ist entfernt (`adr/0008`) | Hinweis | M3-15 (Aufräumen) |
| K-18 | `backend/earthx/api/main.py:13–14` | „the prototype under `backend/app` already answers under `/api` and `/`; this API must never shadow it“ — `backend/app` gibt es nicht mehr; das Präfix `/stac` bleibt richtig, die Begründung nicht | Hinweis | M3-15 |
| K-19 | `backend/earthx/gateway/__init__.py:7` | „The GDAL configuration follows in M1-03c.“ — `gateway/gdal.py` besteht | Hinweis | M3-15 |
| K-20 | `backend/earthx/gateway/policy.py:64` | „Until M1-04 the caller is `policy_from_env`“ — Zeitangabe überholt (vgl. K-13) | Hinweis | mit K-13 |
| K-21 | `architekturplan.md` 13 | Die Zeilen `stac.py`, `auth.py`, `store.py`, `/api/coverage` beschreiben den entfernten Prototyp als Bestand; die Route heißt heute `/coverage/{dataset_id}` (`api/coverage_route.py:65`) | Hinweis | M3-15, oder M3-00, falls dort noch offen |
| K-22 | `architekturplan.md` 5.2, letzter Absatz | „Das Fallback ‚nächstgelegenes Datum‘ … sind Abfragen auf dieser Schicht …, nicht Logik im Frontend“ — Otto hat am 20.09.2026 (M2-07a, Frage 5) den Fallback im Frontend entschieden (`frontend/src/dateFallback.ts`); der Plan ist nicht nachgezogen | Hinweis | M3-15 als Nachtrag in 5.2; ob der Fallback später in den Katalog wandert, siehe Frage 4 |
| K-23 | `frontend/src/mapLayers.ts:36`, `:45` | „same-origin proxied image“ — seit D14 lädt der Browser den Quicklook direkt vom Asset-Host (`:76–82` sagt es richtig, mit `crossOrigin = 'anonymous'`) | Hinweis | M3-12 |
| K-24 | `backend/earthx/logging.py:1–7` und `architekturplan.md` 12.4 | beschreiben JSON-Logs mit Request-ID in jedem Prozess; siehe K-02 | (in K-02) | mit K-01/K-02 |

Geprüft und stimmig: die zehn `earthx:`-Felder aus 5.1 stehen alle in
`catalog/collection.py:121–178`; die vier Prozesse aus 3.2 stehen mit ihren
Einstiegspunkten in `docker-compose.yml`; `earthx:health` trägt kein Prüfdatum
(M2-08-3); `.importlinter` entspricht Spalte 3 von 3.1
(`tests/test_module_boundaries.py`).

---

## 5. Datensatz- und quellenspezifische Stellen im Frontend (Eingabe für M3-12)

Maßstab: Das Frontend soll keinen Datensatz und keine quellenspezifische
Eigenschaft kennen (P10, M3-Abnahme 1). „Dritter Datensatz“ meint unten einen
Kandidaten aus P1, etwa ein statisches globales Raster in EPSG:4326 ohne
Wolkenbedeckung, ohne dichte Zeitachse und ohne `s2:`-Eigenschaften. Welcher
Kandidat es wird, entscheidet Otto nach `adr/0009`; die Spalte „trifft den
dritten?“ ist deshalb eine Einschätzung je Kandidatentyp.

Schon aus dem Katalog und damit **kein** Fund: Gruppierungsschlüssel
(`earthx:viewer.group_by`, `datasets.ts:42–45`), freigegebene Zoomstufen
(`datasets.ts:60–67`), Standard-Darstellung (`earthx:default_render`,
`datasets.ts:50–52`), Reifegrad (`earthx:maturity`), Lizenz-Flags und
Nutzungsbedingungen, Wahl des Quicklook-Assets über Rollen
(`datasets.ts:143–149`). Keine Datensatz-Kennung steht als Literal in einer
Verzweigung; die Kennungen kommen nur in Kommentaren vor
(`datasets.ts:157`, `:165`; `ResultsPanel.tsx:76`).

### 5.1 Quellenspezifische Eigenschaften und Schwellen

| # | Fundstelle | Was spezifisch ist | Schwere | trifft den dritten? | Vorschlag |
|---|---|---|---|---|---|
| F-01 | `grouping.ts:86`, `:102–106` | `DATATAKE_PROPERTY = 's2:datatake_id'`; `displayGroupBy` gruppiert die Trefferliste danach, wenn alle Items die Eigenschaft tragen (D30, V-4) | Schuld | nein direkt (fällt auf `group_by` zurück); aber jede weitere Quelle mit Überflug-Kennung braucht eine neue Konstante | M3-12, Registry-Feld (im Plan bekannt) |
| F-02 | `mapLayers.ts:41`, `:46–64` | `NODATA_THRESHOLD = 16`: jeder Quicklook-Pixel mit R, G, B ≤ 16 wird durchsichtig — passend für die schwarzen Ränder der Sentinel-2-JPEGs | Schuld | ja bei dunklen Bildinhalten (Wasser, Schatten, Rampen einer Farbskala, die bei Schwarz beginnt) | M3-12, Registry-Feld (im Plan bekannt) |
| F-03 | `geoUtils.ts:86–99`, `:160` | `utmProj4Def` akzeptiert nur EPSG:326xx/327xx; `quicklookCoords` gibt sonst `null` — kein Quicklook wird platziert | Schuld | **ja**: Hansen GFC und Copernicus DEM liegen in EPSG:4326; ihre Quicklooks (falls vorhanden) erschienen nicht | M3-12 oder M3-11: EPSG:4326 (und `proj:bbox`) zulassen; kein Registry-Feld nötig |
| F-04 | `geoUtils.ts:138–146` | `georeferencedExtent` sucht zuerst `assets.visual` (Sentinel-2-Asset), dann das erste Asset mit `proj:transform` | Hinweis | nein (Rückfall greift) | M3-12: Asset aus `earthx:default_render.assets[0]` statt Literal |

### 5.2 Feste Blöcke der Suchkachel und Einmal-Produkte

| # | Fundstelle | Was spezifisch ist | Schwere | trifft den dritten? | Vorschlag |
|---|---|---|---|---|---|
| F-05 | `datasets.ts:153–192` (`quicklookPlan`) | Ohne Quicklook-Asset wird eine Kachel auf `min_zoom` als Vorschau genommen; der Kommentar (`:166–170`) sagt selbst, dass das bei `min_zoom = 0` eine Weltkachel wird, die auf ein Item zugeschnitten fast nichts zeigt | Schuld | **ja**, wenn der dritte Datensatz global ab z0 freigegeben ist und keine Thumbnails hat | M3-12, Feld für die Vorschau-Stufe (der Kommentar schlägt es selbst vor) |
| F-06 | `ControlPanel.tsx:312–317` | Block „Acquisition date“ immer sichtbar und Teil jeder Suche; `earthx:capabilities.time_range` wird im Frontend nicht gelesen | Schuld | **ja** bei einem Einmal-Produkt ohne Zeitachse | M3-12 (Capability lesen) |
| F-07 | `api.ts:219` (`extent`), `coverage.ts:140–147`; keine Verwendung von `extent` in `store.ts`, `MapView.tsx`, `mapLayers.ts` | Für ein Einmal-Produkt antwortet die Route mit `extent` und leeren Zellen (`catalog/coverage.py:335–352`); das Frontend zeichnet die Ausdehnung nicht. ENTSCHEIDUNGEN §2 verlangt sie („bei Einmal-Produkten durch die Ausdehnung allein“) | Schuld | **ja**, die Coverage bliebe leer | M3-11 (Coverage des dritten Datensatzes) oder M3-12 |
| F-08 | `ControlPanel.tsx:137–157`, Platzhalter `:149` | Feld „Scene name“ immer sichtbar, Platzhalter `S2C_T32TNT_20260920T103025_L2A` | Hinweis | ja (Szenennamen gibt es bei einem Einmal-Produkt kaum) | M3-10 oder M3-12: Platzhalter aus dem Katalog oder neutral |
| F-09 | `store.ts:878` | Fehlertext „the two catalogues name the same scene differently“ — setzt genau zwei Datensätze desselben Sensors voraus | Hinweis | ja (drei Kataloge) | M3-10 |
| F-10 | `ControlPanel.tsx:159–190` (`DatasetSelector`) | Datensätze als feste Knopfreihe | Schuld (bekannt) | ja bei drei und mehr | M3-10 (P9) |
| F-11 | `mapLayers.ts:82` | Quicklook immer mit `crossOrigin = 'anonymous'` vom Asset-Host (D14); `earthx:access.cors` ist zwar typisiert (`types.ts:38`, `:94`), wird aber nicht gelesen. Eine Quelle ohne CORS-Header verliert den Quicklook ohne Rückfall auf die Vorschau-Kachel | Schuld | offen, hängt am CORS-Befund in `adr/0009` | M3-11/M3-12 |

### 5.3 Doppelte Konstanten und feste Zahlen

| # | Fundstelle | Was | Schwere | Vorschlag |
|---|---|---|---|---|
| F-12 | `datasets.ts:28` `MAX_TILE_ZOOM = 22` | Spiegelt `catalog.registry.MAX_TILE_ZOOM` | Hinweis | vorerst so lassen; Test, der beide Werte vergleicht, in M3-12 |
| F-13 | `coverage.ts:130` `FOOTPRINT_FETCH_LIMIT = 500` | Spiegelt `catalog.coverage.FOOTPRINT_THRESHOLD`; die Antwort trägt schon `footprints_advised` | Hinweis | M3-12 prüfen, ob die Konstante entfallen kann |
| F-14 | `coverage.ts:123` `FOOTPRINT_MIN_ZOOM = 4` | „etwa ein Land im Blick“ — für ein globales Einmal-Produkt ohne Footprints bedeutungslos | Hinweis | mit F-07 |
| F-15 | `store.ts:23` `MAX_SEARCH_ITEMS = 300` | Richtwert des Prototyps, laut Kommentar bis zum Bedarf fest | Hinweis | keine Aufgabe |
| F-16 | `dateFallback.ts:11` `FALLBACK_STAGE_DAYS = [7, 30, 90]` | Fenster passen zu einer Wiederholrate von Tagen; bei einem Einmal-Produkt läuft der Fallback ins Leere | Hinweis | mit F-06 (ohne Zeitachse kein Fallback) |

**Vorschlag für den Test aus M3-12:** Er sucht in `frontend/src` außerhalb der
`*.test.*`-Dateien und außerhalb von Kommentaren nach (a) den Kennungen aus
`catalog/datasets.py` und (b) Eigenschaftsnamen mit Präfix einer
STAC-Erweiterung einer Quelle (`s2:`, `eo:`, `sat:`, `grid:`, `mgrs:`,
`landsat:`). `proj:` bleibt erlaubt: Die Projection-Erweiterung ist
quellenübergreifend, und `geoUtils.ts` braucht sie.

---

## 6. Fehlende Fehlerfall-Tests

Die Suite ist bei den Fehlerpfaden des Backends dicht: Gateway (abgewiesener
Host, private Adresse, Redirect, Zeitablauf, Größendeckel), Download
(Lizenzstufe, AOI, Größendeckel), Coverage-Route, Zarr-Reader (fehlende
Gruppe, Variable, CRS, kaputte `multiscales`, nicht lesbarer Store),
Adapter (Upstream-Fehler, falsche Form, Cache-Ausfall). Fehlend:

| # | Fundstelle | Was fehlt | Schwere | Vorschlag |
|---|---|---|---|---|
| K-25 | alle Prozess-Einstiegspunkte | Ein Test, dass keine Koordinate einer Anfrage im Log des Prozesses landet — die vorhandenen Tests (`tests/test_logging.py`) prüfen die Middleware isoliert, nicht die laufende App (siehe K-01/K-02) | Schuld | mit K-01 |
| K-26 | `api/tiler.py:346` | Kein Test, dass eine Kachel für einen Datensatz der Stufe `catalog` abgewiesen wird (folgt aus K-03) | Schuld | M3-11 |
| K-27 | `frontend/src/aoiFile.ts` | Ganz ohne Test: kaputtes JSON, KML ohne Koordinaten, falscher Geometrietyp, große Datei | Hinweis | entfällt mit M3-06b (das Parsen wandert ins Backend, M3-06a testet dort jeden dieser Fälle) |
| K-28 | `frontend/src/components/*.tsx` außer `StatusBar`, `AppTopBar` | Keine Komponententests; laut Log vom 20.09.2026 (F2 a) nur Logik-Tests vorgesehen | Hinweis | keine Aufgabe; Regel steht |
| K-29 | `api/coverage_route.py:75` | Kein Test für `max_cloud_cover` an einem Datensatz ohne `eo:cloud_cover` (folgt aus K-08) | Hinweis | M3-11 |

---

## 7. Zuordnung zu den Aufgaben

| Aufgabe | Funde |
|---|---|
| neue kleine Aufgabe vor M3-08 (Frage 1) | K-01, K-02, K-24, K-25 |
| M3-04 | K-15 |
| M3-07a | K-10 (Rate), K-13, K-20 |
| M3-10 | F-08, F-09, F-10 |
| M3-11 | K-03, K-05, K-06, K-08, K-14, K-26, K-29, F-07, F-11 |
| M3-12 | K-16, K-23, F-01 bis F-06, F-12, F-13 |
| M3-13 | K-11 |
| M3-14 (`adr/0011`) | K-04, K-05, K-06, K-07, K-09 als Beobachtungen |
| M3-15 | K-17, K-18, K-19, K-21, K-22 |
| M4 und später | K-10 (übrige Punkte), K-12 |
| keine | F-14 bis F-16 (mit F-06/F-07 erledigt), K-27, K-28 |

---

## 8. Fragen an Otto

1. **AOI im Access-Log (K-01, K-02).** Wie beheben?
   1. Eigene kleine Aufgabe der Stufe A **vor** M3-08: Access-Log von uvicorn
      durch eine eigene Zeile ohne Query-String ersetzen, `configure_logging`
      und `RequestIdMiddleware` in `api` und `tiler` einbinden, Test gegen die
      laufende App. **(Empfehlung)**
   2. In M3-08 mitnehmen, weil M3-08 ohnehin „keine Koordinaten im Log“
      testet.
   3. Nur `--no-access-log` in `docker-compose.yml`; Logging-Aufbau später.
2. **Lizenzstufe an der Kachelroute (K-03).** Wann schließen?
   1. In M3-11, bevor der dritte Datensatz eingetragen wird; dazu eine
      Registry-Prüfung, dass `catalog`-Einträge kein `viewer` tragen.
      **(Empfehlung)**
   2. Sofort als eigene Aufgabe der Stufe A.
   3. Erst, wenn ein Datensatz der Stufe `catalog` kommt.
3. **Zugriffsauflösung in `api/tiler.py` (K-04).** Soll M3-14 den Ort der
   Zugriffsauflösung ausdrücklich als Frage aufnehmen?
   1. Ja, als eigene Option in `adr/0011`; Umbau frühestens mit M4.
      **(Empfehlung)**
   2. Nein, der Ort ist mit Antwort 5 vom 20.09.2026 entschieden.
4. **Datums-Fallback im Frontend (K-22).** Architekturplan 5.2 sieht ihn im
   Katalog.
   1. Plan in M3-15 an die Entscheidung vom 20.09.2026 anpassen, Fallback
      bleibt im Frontend. **(Empfehlung)**
   2. Als Punkt „Nach M3 vorgemerkt“ für den Katalog aufnehmen.
