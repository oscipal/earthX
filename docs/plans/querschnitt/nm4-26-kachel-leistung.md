# NM4-26 — Kacheln schneller: Durchsatz von `tiler` und `gateway`

**Stand:** 25.10.2026, Plan zur Freigabe (§7–§16); bis zur Freigabe ist kein Produktivcode geändert. Beauftragt am 24.10.2026 von Otto (Backlog-Punkt 26 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung, Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** hohe Priorität; sofort möglich (Backend). Höchstens zwei Stufe-B-Sessions gleichzeitig; nicht gleichzeitig mit NM4-04 oder NM4-19 (`tiler`).
**Startsatz:** „Führe Aufgabe NM4-26 aus `docs/plans/querschnitt/nm4-26-kachel-leistung.md` aus.“

## 1. Anlass

Ottos Messung im Browser (25.10.2026, lokal mit `docker compose`): Eine NDVI-Vorschau braucht rund 40 s für 325 Anfragen. Einzelne Kacheln (rund 30–35 kB) brauchen 1,7 bis 6,5 s, mit gleichmäßig steigenden Zeiten – die Anfragen warten in einer Schlange. Auch reine `visual`-Kacheln ohne Rechnung brauchen 2,6 bis 4,2 s. Dasselbe Bild schon vor UI-01a (Stand `745ecb2`), es ist also keine Regression aus UI-01a. Daneben: Die Suche (`search`, je 1,9 MB) wird beim Öffnen dreimal geladen, und eine `statistics`-Anfrage mit `op` endete mit `400`.

## 2. Soll

- Kacheln einer Ansicht kommen deutlich schneller; das Ziel legt der Plan nach der Messung fest (Vorschlag: eine typische Ansicht in unter 10 s, einzelne Kachel ohne Warteschlange unter 1 s).
- Die Suche wird beim Öffnen genau einmal geladen.
- Die `statistics`-Anfrage der Vorschau scheitert nicht mehr mit `400` (Ursache finden; falls Frontend falsche Parameter schickt, dort beheben).

## 3. Umfang

- **Messung zuerst** (lokal in der Session, synthetische Quelle über die Testnähte und, wo möglich, Zeitanteile im Code): Zeit je Kachel aufgeteilt in Warten, Item holen, COG-Lesen über `gateway`, Rechnen, Kodieren. Tabelle im PR.
- **Recherche mit Quellen (Pflicht, rechenrelevant):** Gleichzeitigkeit im `tiler` (Prozesse/Threads von uvicorn, Threadpool von FastAPI/Starlette für synchrone Routen, rio-tiler-Empfehlungen), GDAL-Einstellungen für entfernte COGs (`GDAL_HTTP_MULTIPLEX`, `GDAL_HTTP_VERSION`, `VSI_CACHE`, `GDAL_CACHEMAX`, `GDAL_DISABLE_READDIR_ON_OPEN`, `CPL_VSIL_CURL_ALLOWED_EXTENSIONS`), Verbindungen offen halten über `gateway` (Keep-Alive, Pool), Item-Cache.
- Die doppelte bzw. dreifache Suche im Frontend: Ursache (Effekt mit wechselnden Abhängigkeiten, StrictMode, Neuaufbau) finden und beheben.

## 4. Im Plan klären (mit Optionen und Empfehlung)

- Welche Stellschrauben zuerst (Gleichzeitigkeit, GDAL, Verbindungen, Caches) – mit Zahlen und Kosten (Speicher je Prozess, Grenze 500 MB im Worker gilt nicht für den `tiler`, aber Speicher des Hosts nennen).
- Wirkung auf die Bitgleichheit Kachel ↔ Job (darf sich nicht ändern; Tests aus `adr/0014` §6.3 laufen weiter).
- Ob etwas davon `docker-compose.yml` braucht (Variablen, Prozesszahl) und wie es in Produktion aussieht.

## 5. Grenzen

- Ausgehende Requests bleiben ausschließlich über `gateway`; die Prüfungen in `gateway` (B8/B9) werden nicht gelockert.
- `.github/` bleibt unverändert.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Messung vorher/nachher mit derselben Methode im PR; Test für „Suche genau einmal“ und für die `statistics`-Ursache, die am alten Code scheitern; Bitgleich-Tests weiter grün.
- Nachtrag in `adr/0006` bzw. `architekturplan.md`, falls sich Gleichzeitigkeit oder Verbindungen grundlegend ändern.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.

---

# Plan (25.10.2026)

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung.

## 7. Kurzfassung

- **Hauptursache: zwei GDAL-Einstellungen.** Mit `GDAL_HTTP_MULTIRANGE=YES` liest GDAL die Blöcke einer Kachel parallel. Dieser Weg schreibt nicht in den `/vsicurl/`-Cache [P], und der Cache hat nur 16 MB [P]. Jede Kachel lädt deshalb die Blöcke neu, die ihre Nachbarn schon geholt haben. Für die Ansicht in §8 holt GDAL 1,72 GB von der Quelle, gebraucht werden 284 MB [M]. Mit `SERIAL` und 256 MB Cache wird jedes Byte einmal geholt.
- **Wirkung [M]:** Die gemessene Ansicht (13 Szenen × 25 NDVI-Kacheln, 325 Anfragen, Quelle mit EU-Latenz) dauert 28,3 s statt 45,6 s. Bei 100 Mbit/s zur Quelle sind es 38,4 s statt 145,3 s. Die Kacheln sind byte-identisch, Kachel ↔ Job ist also nicht berührt.
- **Die Warteschlange liegt im Browser, nicht im `tiler`:** Über HTTP/1.1 öffnet der Browser 6 Verbindungen je Host [P]. Die 325 Anfragen warten dort, im `tiler` gibt es keine Schlange (Wartezeit auf einen Thread ~0 ms [M]). Mehr Gleichzeitigkeit (HTTP/2 davor, mehrere Prozesse) hilft erst, wenn die Quelle schnell genug liefert. Jeder Prozess hat seinen eigenen Cache, die Bytes von der Quelle verdoppeln sich dann [M].
- **10 s für diese Ansicht sind mit dem `tiler` allein nicht erreichbar:** 284 MB müssen von der Quelle kommen, bei 100 Mbit/s sind das schon 23 s. Eine Ansicht mit einer Szene (25 Kacheln) braucht bei 100 Mbit/s 5,9 s statt 10,5 s. Der große Hebel für viele Szenen ist eine Mosaik-Kachel mit Operator statt 13 übereinanderliegender Ebenen (NM4-04), hier nicht im Umfang.
- **Suche „dreifach“:** Es sind drei Seiten zu je 100 Szenen (`MAX_SEARCH_ITEMS = 300`, Plattformgrenze 100 je Seite, `adr/0005` Regel V), keine Wiederholung [P]. Frage 6.
- **`statistics` mit `op` → `400`:** Ursache am Code nicht eindeutig; Kandidaten in §12. Frage 7.
- **Umsetzung in einem PR** (nach Freigabe): GDAL-Profil des `tiler` in `gateway`, Item-Abrufe der Einzelkachel bündeln, Test „jede Suchseite genau einmal“, Ursache und Test für `statistics`. 512er-Kacheln, HTTP/2 und `Cache-Control` sind je eine Frage an Otto.

## 8. Messung

### 8.1 Methode

Das Gerüst liegt in `scripts/tile-bench/` (Aufruf in §17.1). Es misst den echten `tiler` (`earthx.api.tiler.build_app`, echte Lebensdauer mit Postgres, ein Prozess wie in `docker-compose.yml`). Ersetzt sind nur die drei Nähte, die auch die Tests ersetzen:

1. Der Namensauflöser antwortet aus dem Speicher.
2. Der Transport des `gateway` antwortet mit einem handgeschriebenen synthetischen Item, nach 300 ms (Item-Abruf bei der Quelle).
3. Der `/vsicurl/`-Pfad aus der geprüften Adresse zeigt auf einen lokalen Server.

Alles dazwischen ist der ausgelieferte Code: Registry, Lizenz, Zoomprüfung, `check_url`, Item-Cache in Postgres, Reader, Operator, Render.

- **Quelle:** synthetische COGs im Aufbau der Earth-Search-Dateien. Gelesen am 25.10.2026 an `TCI`/`B04` einer echten Szene: 10980², Blöcke 1024, DEFLATE, Übersichten 2–16 [M]. Inhalt ist Rauschen über einem Verlauf, Größe wie echt (synthetisch 355/248 MB, echt 308/225 MB). Ein HTTP/1.1-Server mit Keep-Alive bildet eine ferne Quelle nach: 170 ms bis zum ersten Byte je Anfrage, 350 ms je neue Verbindung (TCP + TLS), wahlweise eine gemeinsame Leitung von 100 Mbit/s. Die Latenzwerte sind abgeleitet [A], nicht bei Otto gemessen: EU → `us-west-2`, gemessen aus dieser Sitzung über den Proxy 0,37 s TLS-Aufbau und 0,48 s bis zum ersten Byte.
- **Ansicht:** wie die NDVI-Vorschau in `processingPreview.ts`, also eine Ebene je Szene. 13 Szenen × 5×5 Kacheln 256 px auf z11 = 325 Anfragen, alle auf einmal gestellt, über höchstens 6 Verbindungen (Browser, HTTP/1.1). Die 13 Szenen haben denselben Fußabdruck, das ist für die Bytes eine obere Schranke. Gemessen wird die Wandzeit bis zur letzten Kachel.
- **Phasen je Kachel** (Median/Mittel in ms): `item` (Item holen, mit Cache), `syncdeps_wait`/`endpoint_wait` (Warten auf einen Thread), `open` (COG öffnen, Header), `read` (Blöcke lesen, dekomprimieren, umprojizieren), `compute` (Operator), `encode` (PNG), dazu `total`. Die Zeiten kommen aus Hüllen um dieselben Funktionen, nicht aus Code im Produkt.
- **Wie im Image:** `boto3` liegt nur im Dev-Lock (über `moto`). Damit legt rasterio bei jedem `rasterio.Env` eine AWS-Sitzung an, rund 100 ms CPU je Kachel [M], die das Image nicht kennt. Das Gerüst setzt es deshalb beiseite. Dieser Befund gilt nur für die Entwicklungsumgebung.

### 8.2 Ergebnis

Rechner der Sitzung: 4 Kerne, 16 GB. Jede Zeile ist ein frischer Prozess mit leerem Item- und Statistik-Cache.

Spalten: Wandzeit bis zur letzten Kachel; Zeit einer Kachel im `tiler`, ihr `open`, `read` und `encode` (je Median/Mittel in ms); Bytes von der Quelle; davon gebraucht (Vereinigung der Byte-Bereiche je Datei). „S1“ = `SERIAL` + 256 MiB Cache (§10). Quelle mit EU-Latenz (170 ms je Anfrage, 350 ms je Verbindung), Leitung unbegrenzt oder 100 Mbit/s.

| Ansicht | Leitung | Stand | Wandzeit | Kachel | `open` | `read` | `encode` | Quelle | gebraucht |
|---|---|---|---|---|---|---|---|---|---|
| NDVI, 13 Szenen × 25 (325 Anfragen) | unbegrenzt | heute | **45,6 s** | 878/823 | 389/278 | 442/449 | 31/33 | 1719 MB | 284 MB |
| | unbegrenzt | S1 | **28,3 s** | 388/497 | 8/58 | 145/247 | 34/39 | 301 MB | 284 MB |
| | 100 Mbit/s | heute | **145,3 s** | 2559/2655 | 428/322 | 2095/2269 | 28/30 | 1770 MB | 284 MB |
| | 100 Mbit/s | S1 | **38,4 s** | 370/682 | 8/49 | 142/470 | 33/37 | 302 MB | 284 MB |
| `visual`, 13 × 25 (325) | unbegrenzt | heute | **30,1 s** | 496/526 | 173/119 | 263/268 | 39/44 | 1266 MB | 212 MB |
| | unbegrenzt | S1 | **22,9 s** | 346/390 | 5/31 | 128/167 | 42/53 | 214 MB | 212 MB |
| | 100 Mbit/s | heute | **103,4 s** | 1889/1883 | 198/148 | 1617/1666 | 35/37 | 1255 MB | 212 MB |
| | 100 Mbit/s | S1 | **32,1 s** | 344/559 | 4/33 | 127/357 | 40/50 | 224 MB | 212 MB |
| NDVI, 1 Szene × 25 (25) | unbegrenzt | heute | **4,3 s** | 610/935 | 8/263 | 462/449 | 31/37 | 100 MB | 22 MB |
| | unbegrenzt | S1 | **4,0 s** | 631/894 | 19/272 | 432/349 | 52/51 | 40 MB | 22 MB |
| | 100 Mbit/s | heute | **10,5 s** | 2765/2311 | 7/276 | 2182/1836 | 33/36 | 103 MB | 22 MB |
| | 100 Mbit/s | S1 | **5,9 s** | 1007/1283 | 12/272 | 831/794 | 34/41 | 40 MB | 22 MB |
| NDVI, 13 × 9 Kacheln 512 px (117), dieselbe Fläche | unbegrenzt | S1 + S3 | **23,0 s** | 1003/1125 | 8/115 | 536/534 | 121/142 | 284 MB | 284 MB |
| | 100 Mbit/s | S1 + S3 | **33,4 s** | 1281/1667 | 6/116 | 1024/1216 | 119/136 | 285 MB | 284 MB |
| wie oben, 4 Prozesse, 24 Verbindungen (S4) | unbegrenzt | S1 + S3 + S4 | **13,3 s** | 2363/2367 | 49/413 | 896/913 | 168/214 | 586 MB | 284 MB |
| | 100 Mbit/s | S1 + S3 + S4 | **40,0 s** | 7091/7646 | 14/407 | 5825/6644 | 118/141 | 471 MB | 284 MB |
| NDVI 13 × 25, 4 Prozesse, 24 Verbindungen | unbegrenzt | S1 + S4 | **19,0 s** | 1308/1263 | 23/192 | 514/534 | 55/66 | 739 MB | 284 MB |
| | 100 Mbit/s | S1 + S4 | **42,6 s** | 1592/2963 | 22/165 | 447/2170 | 42/61 | 472 MB | 284 MB |
| NDVI 13 × 25, Quelle ohne Latenz | unbegrenzt | heute | **23,8 s** | 405/412 | 53/51 | 146/153 | 36/43 | 1715 MB | 284 MB |
| | unbegrenzt | S1 | **23,8 s** | 404/413 | 12/19 | 144/151 | 38/45 | 290 MB | 284 MB |

In allen Zeilen mit 6 Verbindungen wartet eine Kachel im `tiler` im Median 0–1 ms auf einen Thread für den Endpunkt und 1–29 ms für die synchronen Abhängigkeiten. Der Operator (`compute`) kostet 1–12 ms. Ottos Zahlen (rund 40 s für 325 Anfragen, Kacheln 1,7–6,5 s im Browser) liegen zwischen den Zeilen „heute“ ohne und mit Leitungsgrenze.

### 8.3 Was die Zahlen sagen

- **B1 Die Schlange steht im Browser.** Im Browser wartet eine Kachel im Median 26 s (Spalte „Time“ in DevTools), im `tiler` dauert sie 0,9 s. Die Zeiten steigen gleichmäßig an, weil 325 Anfragen über 6 Verbindungen nacheinander abgearbeitet werden. Das deckt sich mit Ottos Beobachtung.
- **B2 GDAL holt das Sechsfache.** Heute 1719 MB für eine Ansicht, die 284 MB braucht (`visual`: 1266 für 212 MB). Ursache sind `MULTIRANGE=YES` und der 16-MB-Cache (R2–R5). Auch der Header einer Datei fällt aus dem Cache: Jede Kachel öffnet ihre COGs mit 1–2 Anfragen neu (`open` im Mittel 278 ms).
- **B3 Mit S1 kommt jedes Byte einmal.** 301 statt 1719 MB, `open` 58 statt 278 ms im Mittel. Was über 284 MB hinausgeht, kommt aus der ersten Welle: Sechs gleichzeitige kalte Kacheln derselben Datei holen dieselben Blöcke, bevor einer im Cache liegt. GDAL bündelt gleichzeitige Fehlgriffe nicht.
- **B4 Bei begrenzter Leitung zählen nur die Bytes.** 1770 MB über 100 Mbit/s sind 142 s, gemessen 145 s; 302 MB sind 24 s, gemessen 38 s. Ottos Leitung kenne ich nicht. Die Prüfanleitung (§16) misst die Bytes des `tiler` über `docker stats`.
- **B5 Ohne Latenz rechnet der `tiler` an seiner Grenze.** Ohne Netzverzögerung brauchen heute und S1 gleich lange (23,8 s): ein Prozess, 6 Anfragen gleichzeitig, ~0,4 s je NDVI-Kachel. Darunter kommt man nur mit weniger Anfragen (S3) oder mehr Prozessen (S4).
- **B6 Mehr Prozesse kosten Bytes.** Mit 4 Prozessen hat jeder seinen eigenen Cache: 471–739 statt 285–302 MB von der Quelle. Ohne Leitungsgrenze ist das die schnellste Variante (13,3 s mit 512 px). Bei 100 Mbit/s ist die Ansicht damit langsamer (40,0 bzw. 42,6 s statt 33,4 bzw. 38,4 s).
- **B7 Eine Szene:** 10,5 → 5,9 s bei 100 Mbit/s, 4,3 → 4,0 s ohne Grenze. Hier dominiert die erste Welle (B3).
- **B8 Das Item kommt mehrfach.** Für eine kalte Szene holt der `tiler` das Item bis zu fünfmal gleichzeitig von der Quelle, für 13 Szenen 13–17-mal (S2). Danach kommt es aus dem Cache in Postgres (Median 2–17 ms).
- **B9 Nur in der Entwicklungsumgebung:** Mit `boto3` (Dev-Lock) kostet jede Kachel ~100 ms CPU in `botocore` (§17.2). Das Image ist nicht betroffen. Ein Test unter `pytest`, der Kachelzeiten misst, wäre davon verzerrt.

## 9. Recherche

Alle Quellen abgerufen am 25.10.2026; GDAL am Tag `v3.12.2`, der Version im rasterio-Wheel.

| # | Aussage | Quelle | Beleg |
|---|---|---|---|
| R1 | `GDAL_HTTP_MULTIRANGE` steuert, wie die `ReadMultiRange()`-Anfragen des GeoTIFF-Treibers bedient werden: `YES` (Vorgabe) parallel über HTTP/2-Multiplexing oder mehrere Verbindungen, `SINGLE_GET` alle Bereiche in einem GET (von S3 nicht unterstützt), `SERIAL` einer nach dem anderen | [`configoptions.rst`](https://github.com/OSGeo/gdal/blob/v3.12.2/doc/source/user/configoptions.rst) | [P] |
| R2 | Der Weg `YES` (`VSICurlHandle::ReadMultiRange`, `cpl_vsil_curl.cpp` Z. 2507–2772) kopiert die Antworten nur in die Puffer des Aufrufers (`memcpy`, Z. 2730) und ruft weder `GetRegion` noch `AddRegion` auf. `SERIAL` und eine einzelne Range gehen über `VSIVirtualHandle::ReadMultiRange` (Z. 2530) zu `VSICurlHandle::Read()` (Z. 2361), das den Cache liest (Z. 2402) und füllt (Z. 2350) | [`cpl_vsil_curl.cpp`](https://github.com/OSGeo/gdal/blob/v3.12.2/port/cpl_vsil_curl.cpp), selbst gelesen | [P] |
| R3 | Der GeoTIFF-Treiber hält die per Multirange geholten Bytes nur für die Dauer eines `IRasterIO` und gibt sie dann frei (`VSIFree(pBufferedData)`) | [`gtiffdataset.cpp`](https://github.com/OSGeo/gdal/blob/v3.12.2/frmts/gtiff/gtiffdataset.cpp), [`gtiffdataset_read.cpp`](https://github.com/OSGeo/gdal/blob/v3.12.2/frmts/gtiff/gtiffdataset_read.cpp) `CacheMultiRange` | [P] über Zusammenfassung |
| R4 | `CPL_VSIL_CURL_CACHE_SIZE`: globaler LRU-Cache über alle geladenen Inhalte, Vorgabe 16 MB (1000 × 16384 Byte). Er überlebt das Schließen einer Datei. Gelesen wird der Wert **einmal je Prozess**, beim ersten Zugriff (statischer Initialisierer, `cpl_vsil_curl.cpp` Z. 133–214) | `virtual_file_systems.rst`; `cpl_vsil_curl.cpp` | [P] |
| R5 | `VSI_CACHE`/`VSI_CACHE_SIZE`: Cache je Dateihandle, wird beim Schließen verworfen. Der `tiler` öffnet je Kachel neu, der Cache nützt also nur innerhalb einer Kachel | `virtual_file_systems.rst` | [P] |
| R6 | `GDAL_HTTP_MULTIPLEX` und `GDAL_HTTP_VERSION=2` wirken nur auf einer HTTP/2-Verbindung, `GDAL_HTTP_MERGE_CONSECUTIVE_RANGES` nur im Weg `YES` | `configoptions.rst` | [P] |
| R7 | S3 spricht HTTP/1.1. Gemessen: Antwort `HTTP/1.1` vom Asset-Bucket. Eine Primäraussage von AWS zu HTTP/2 wurde nicht gefunden | eigene Messung; [re:Post](https://repost.aws/questions/QU22F0GAPNRfmTPdW283_i7A/does-amazon-s3-support-http-2) | [M], [S] |
| R8 | Chromium erlaubt 6 Verbindungen je Host („Default to allow up to 6 connections per host“); HTTP/2 bündelt die Anfragen über eine Verbindung | [`client_socket_pool_manager.cc`](https://github.com/chromium/chromium/blob/main/net/socket/client_socket_pool_manager.cc); [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Connection_management_in_HTTP_1.x) | [P] |
| R9 | Vite 8 bedient mit `server.https` immer HTTP/2 (`http2.createSecureServer`, `allowHTTP1`), auch mit `server.proxy`. Vite 7 fiel bei Proxy auf HTTP/1.1 zurück | [`http.ts` v8.0.0](https://github.com/vitejs/vite/blob/v8.0.0/packages/vite/src/node/http.ts), [v7.0.0](https://github.com/vitejs/vite/blob/v7.0.0/packages/vite/src/node/http.ts) | [P] |
| R10 | Synchrone Routen und Abhängigkeiten laufen im AnyIO-Threadpool, Vorgabe 40 Plätze je Prozess | [AnyIO `threads.rst`](https://github.com/agronholm/anyio/blob/master/docs/threads.rst), [Starlette `threadpool.md`](https://github.com/Kludex/starlette/blob/main/docs/threadpool.md) | [P] |
| R11 | `uvicorn --workers N` startet N Prozesse an einem gemeinsamen Socket; jeder hat eigene GDAL-Caches und eigene 40 Threads | [uvicorn `settings.md`](https://github.com/Kludex/uvicorn/blob/master/docs/settings.md), `supervisors/multiprocess.py` | [P]; Caches je Prozess [A] |
| R12 | TiTiler empfiehlt `CPL_VSIL_CURL_CACHE_SIZE=200000000`, `GDAL_CACHEMAX=200`, `VSI_CACHE=TRUE`, `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`, `GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES`, `GDAL_HTTP_MULTIPLEX=YES`. `GDAL_HTTP_MULTIRANGE` erwähnt die Seite nicht. Das Image startet mit `WEB_CONCURRENCY=1` | [`performance_tuning.md`](https://github.com/developmentseed/titiler/blob/main/docs/src/advanced/performance_tuning.md), [`Dockerfile`](https://github.com/developmentseed/titiler/blob/main/dockerfiles/Dockerfile) | [P] |
| R13 | MapLibre-Raster-Quellen haben die Vorgabe `tileSize` 512. Mit 256 fordern sie Kacheln eine Stufe feiner an | [Style-Spec `v8.json`](https://github.com/maplibre/maplibre-style-spec/blob/main/src/reference/v8.json), `covering_tiles.ts` | [P] |
| R14 | `max-age`: Eine Antwort ist frisch, solange ihr Alter darunter liegt (RFC 9111 §5.2.2.1). `immutable` (RFC 8246): keine Nachfrage während der Frische | [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111#section-5.2.2.1); RFC 8246 | [P]; [S] |

Ableitung [A]: R2, R3 und R5 erklären die Messung vollständig. Liest eine Kachel mehrere Blöcke, holt sie diese über `YES` an jedem Cache vorbei. Nach der Kachel sind die Bytes weg (R3, R5). Die Nachbarkachel liest dieselben Blöcke deshalb noch einmal. Mit `SERIAL` landen sie im globalen Cache (R2, R4), und der muss groß genug sein für die Blöcke, die eine Ansicht gleichzeitig braucht. Der Preis von `SERIAL` sind nacheinander statt parallel gestellte Anfragen, wenn eine Kachel mehrere neue Blöcke braucht. Über HTTP/1.1 zu S3 (R7) ist `YES` ohnehin kein Multiplexing, sondern mehrere Verbindungen.

## 10. Stellschrauben: Optionen und Empfehlung

Reihenfolge nach Nutzen je Aufwand. Zahlen aus §8.2, Speicher als RSS des `tiler`-Prozesses am Ende der Ansicht [M].

| # | Stellschraube | Wirkung [M] | Kosten | Empfehlung |
|---|---|---|---|---|
| S1 | **GDAL-Profil des `tiler`:** `GDAL_HTTP_MULTIRANGE=SERIAL`, `CPL_VSIL_CURL_CACHE_SIZE=256 MiB` | Bytes von der Quelle 1,72 GB → 0,30 GB; Ansicht 45,6 → 28,3 s ohne, 145,3 → 38,4 s mit 100-Mbit/s-Leitung; `open` 278 → 58 ms im Mittel | RSS ~300 → ~⟨RSS⟩ MB je Prozess. Neue Blöcke einer Kachel kommen nacheinander statt parallel (spürbar nur bei kaltem Cache und vielen Blöcken je Kachel); Zuschnitt siehe §13 | **jetzt**, ohne Änderung an `docker-compose.yml` |
| S2 | **Item-Abrufe der Einzelkachel bündeln** wie bei der Mosaik-Kachel (`mosaic_tiles.ItemFetches`, M4-17b) | eine statt bis zu 6 Item-Abfragen je kalter Szene (gemessen 5 für 1 Szene, 15 für 13) | ~20 Zeilen; derselbe Weg wie die Mosaik-Kachel | **jetzt** |
| S3 | **512er-Kacheln** im Frontend (`tileSize: 512`, `tilesize=512`) | ein Drittel der Anfragen (325 → 117); Ansicht 23,0 statt 28,3 s (100 Mbit/s: 33,4 statt 38,4 s), gleiche Bytes | ändert die Zuordnung Kartenzoom → Kachelstufe (`TILE_LEVEL_AHEAD`, `previewMaxZoom`, `zoomHint`), die freigegebenen Stufen je Datensatz (`earthx:viewer`, `adr/0007` §12.10) und die Grenzen der Mosaik-Kachel (M4-17 §5: eine Kachel deckt die vierfache Fläche) | **eigene Aufgabe** (Frage 3) |
| S4 | **Mehr Gleichzeitigkeit:** HTTP/2 zum Browser (TLS davor) und `uvicorn --workers 4` | ohne Leitungsgrenze 13,3 s (512 px) bzw. 19,0 s (256 px); bei 100 Mbit/s 40,0 bzw. 42,6 s, also langsamer als S1 allein (24 Anfragen gleichzeitig, 4 Prozesse) | Bytes von der Quelle ×2–2,5 (586–739 statt 284–302 MB), weil jeder Prozess eigene Caches hat; RSS ×4 (~2,0 GB gesamt); TLS lokal braucht ein Zertifikat (neues Werkzeug oder Abhängigkeit) | **mit M6** (Frage 4) |
| S5 | PNG schneller kodieren (`ZLEVEL=1`) | Kodieren 45 → 25 ms je NDVI-Kachel (echte Szene, §17.4) | +2 % Größe | später; zählt erst, wenn der `tiler` rechengebunden ist |
| S6 | Threadpool (40), `GDAL_HTTP_VERSION`, `GDAL_HTTP_MULTIPLEX`, `CPL_VSIL_CURL_USE_HEAD=NO`, `VSI_CACHE` | keine messbare Wirkung: Warten auf einen Thread ~0 ms; S3 spricht HTTP/1.1 (R7); ohne `HEAD` 32,4 statt 32,0 s | — | **unverändert lassen** |

**Nicht empfohlen:** eine gröbere Übersichtsstufe wählen lassen (`GDAL_OVERVIEW_OVERSAMPLING_THRESHOLD`). Das spart Bytes, ändert aber die Pixel der Vorschau, also Bitgleichheit und Bildschärfe.

**Verbindungen über `gateway` (Keep-Alive, Pool):** Hier ist nichts zu tun [M]. Der `httpx`-Client des `gateway` hält seine Verbindungen ohnehin offen. Ein Item kommt einmal je Szene, danach aus dem Cache in Postgres (Median 2–12 ms). GDAL hält je Thread eine Verbindung: Mit `SERIAL` sind es genau 6 Verbindungen für 325 Kacheln, mit `YES` 12. GDAL läuft dabei wie bisher an der Verbindungsgrenze des `gateway` vorbei (KLAERUNGEN B8, `adr/0006` §8 Punkt 2). Daran ändert S1 nichts, die Adressprüfung vor GDAL bleibt.

**Gleichzeitigkeit im `tiler` (Prozesse/Threads):** Ein Prozess mit 40 Threads reicht, solange der Browser 6 Anfragen gleichzeitig schickt. Über 24 Verbindungen bremst ein Prozess (GIL): Die Wartezeit auf einen Thread steigt auf ~100 ms, die Rechenschritte werden 3–5× langsamer [M]. Mehrere Prozesse lohnen sich erst mit S4.

## 11. Die Suche „dreifach“

**Befund am Code [P]:** Im Browser gibt es eine einzige Stelle, die sucht: `POST /stac/search` in `searchItems` (`frontend/src/api.ts`). `runSearch` (`store.ts`) ruft sie über `searchAllPages(query, MAX_SEARCH_ITEMS)` auf. Die Schleife holt Seiten zu je 100 Szenen nacheinander, bis 300 Szenen da sind oder die Quelle keine nächste Seite nennt. Mehr als 100 je Seite lässt die Plattform nicht zu (`MAX_LIMIT = 100`, `adr/0005` Regel V). Eine Suche mit mindestens 300 Treffern sind damit genau drei `POST`, die sich nur im `token` unterscheiden. 100 Szenen zu je ~19 kB ergeben die 1,9 MB je Antwort.

Kein Effekt löst eine Suche aus. `StrictMode` (`main.tsx`) verdoppelt nur das Laden der Collections beim Start (`App.tsx`), und das Öffnen eines Permalinks ist gegen Wiederholung gesichert (`permalink.ts`). Weitere Suchen kommen nur aus dem Rückfall bei leerem Ergebnis (`runFallback`) und aus der Abdeckungskarte, wenn sie eingeschaltet ist (bis zu 5 Seiten je Kartenbewegung).

**Offen:** Im Browser habe ich das in dieser Sitzung nicht nachgestellt. `api` erreicht Earth Search aus der Sitzung nicht: Der Client verbindet sich mit der geprüften Adresse, und der Proxy der Sitzung lässt das nicht durch. Das ist so gewollt (B8). Die Prüfung im Browser folgt in der Umsetzung, mit einer nachgestellten Suchantwort (§16).

Was „genau einmal“ heißen soll, ist Frage 6.

## 12. `statistics` mit `op` → `400`

Die Vorschau holt die Statistik für die erste Szene (`buildOperatorStatisticsUrl`) mit genau den Parametern ihrer Kacheln: `asset`, `op`, `op_version`, `params`. Schlägt sie fehl, wird das still gemerkt (`failedMeasures`), und die URL wird nicht noch einmal gefragt. Das passt zu „einmal `400`“.

| Kandidat | Wo | trifft nur `statistics`? | Bewertung |
|---|---|---|---|
| K1 Formel oder Parameter ungültig (halb getippt, eine Funktion außerhalb von R5, `in_max` ≤ `in_min` bei `normalize`) | `_operator_step` → `params: …` (`api/tiler.py`) | nein, die Kacheln derselben Formel scheitern ebenso | gemessen: `(nir-red)/(nir+` → `400 "params: expression: … not a valid expression"`. Bei einer einstufigen Kette fragt die Vorschau ohne TileJSON-Probe zuerst die Statistik, 400 ms nach dem letzten Tastendruck |
| K2 Optionen der Übersicht abgelehnt (`TileOptionRefused`: `max_size` über 1024, Resampling nicht `nearest`, weitere Leseoptionen) | `processing/tile.py` `preview` | ja | das Frontend sendet keine dieser Optionen; mit den Vorgaben von TiTiler antwortet der Aufruf `200` [M] |
| K3 die erste Szene selbst (fehlende Bandangaben, anderer Datensatz, z. B. Zarr) | `describe_bands`, `ZarrReader` | nein, auch ihre Kacheln | ohne Ottos Szene nicht zu prüfen |

Am wahrscheinlichsten ist K1. Er widerspricht aber Ottos Beobachtung, wenn dabei alle Kacheln heil blieben. Die Antwort trägt den Grund im Feld `detail`. Frage 7 bittet um diesen Text. Ohne ihn setze ich K1 um: Auch eine Kette mit einem Schritt fragt zuerst die TileJSON-Probe, die es für mehrere Schritte schon gibt. Eine Ablehnung zeigt das Panel wie dort an, und weder Statistik noch Kacheln einer abgelehnten Formel gehen hinaus.

## 13. Bitgleichheit, Zuschnitt, Jobs

- **Kachel ↔ Job (`adr/0014` §6.3, §6.4):** S1 ändert, wie die Bytes geholt werden, nicht welche. 18 Kacheln sind mit alter und neuer Einstellung byte-identisch [M]: NDVI und `visual`, z10/z11/z14, 256 und 512 px (§17.3). Der Vergleichstest T1 ↔ T2 und die übrigen Tests laufen in der Umsetzung unverändert mit. S2 ändert nur, wie oft ein Item geholt wird.
- **Zuschnitt (`POST …/download`):** Er läuft im `tiler`-Prozess unter denselben GDAL-Optionen (`state.earthx_gdal_options`) und liest viele Blöcke auf einmal. Mit `SERIAL` gehen diese Anfragen nacheinander statt parallel. Gemessen: ⟨CROP⟩. Bitgleichheit des ZIP-Inhalts: ⟨CROPHASH⟩.
- **Worker und Runner** lesen über `readers.process_gdal_options()` dieselben Grundoptionen. Ihr Lastprofil ist anders: große Fenster am Stück, 500 MB Speichergrenze im Worker (`adr/0013`). S1 soll deshalb nur für den `tiler` gelten (Frage 1). Für die Jobs ist das ungemessen und bleibt unverändert.
- **`CPL_VSIL_CURL_CACHE_SIZE` wird einmal je Prozess gelesen** (R4). Ein Wert, der nur in manchen `rasterio.Env` des Prozesses steht, wirkt deshalb nur, wenn GDAL zufällig dort zum ersten Mal liest. Im `tiler` tragen alle Wege dieselben Optionen: Kachel, Statistik, TileJSON, Mosaik, Ergebnis-Kacheln und Zuschnitt. Ein Test hält genau das fest.

## 14. `docker-compose.yml` und Produktion

- **S1 und S2 brauchen keine Änderung an `docker-compose.yml`.** Die Werte leben wie alle GDAL-Optionen in `gateway/gdal.py` (KLAERUNGEN B8), nicht in Umgebungsvariablen des Dienstes. So kann ein Start ohne die Variable nicht stillschweigend auf 16 MB zurückfallen.
- **Speicher des Hosts:** Der `tiler` wächst von ~300 auf ~⟨RSS⟩ MB. Mit `api`, `worker` (Grenze 500 MB je Kind), Postgres und Garage braucht das lokale `docker compose` damit rund ⟨HOST⟩ GB. Ottos Rechner kenne ich nicht.
- **Produktion (M6):** Der `tiler` skaliert waagerecht (`architekturplan.md` 3.2, 12.1); jede Instanz hat ihren eigenen Cache von 256 MB. Mehr Gleichzeitigkeit kommt dort vom CDN bzw. Reverse-Proxy mit HTTP/2 vor dem `tiler` (`architekturplan.md` 12.3) und von mehr Instanzen, nicht von `--workers` in einem Container. Ob `adr/0006` oder `architekturplan.md` einen Nachtrag brauchen, hängt an Frage 4. Mit S1 und S2 ändern sich weder Gleichzeitigkeit noch Verbindungen grundlegend. Ein kurzer Nachtrag in `adr/0006` §8 Punkt 4 (`MERGE_CONSECUTIVE_RANGES` nicht verglichen) hält den Befund zu `MULTIRANGE` trotzdem fest.

## 15. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Für wen gilt das neue GDAL-Profil (S1)?**
1. Nur für den `tiler`: `gateway/gdal.py` bekommt `tile_gdal_options(policy)` = Grundoptionen + `SERIAL` + 256 MiB Cache. Worker und Runner bleiben unverändert. **(Empfehlung)**
2. Für alle Prozesse (`gdal_options` selbst). Der Worker bekäme 256 MiB über seiner 500-MB-Grenze; ungemessen.

**Frage 2 — Größe des `/vsicurl/`-Caches im `tiler`?**
1. 256 MiB: deckt die gemessene Ansicht (284 MB verschieden, gelesen 301 MB). **(Empfehlung)**
2. 128 MiB: halber Speicher. Bei Ansichten mit vielen Szenen holt GDAL wieder mehrfach.
3. 512 MiB: Reserve für größere Ansichten. Gemessen ohne Unterschied zu 256 MiB (37,0 statt 38,2 s).

**Frage 3 — 512er-Kacheln (S3)?**
1. Eigene Aufgabe nach dieser, Stufe B. Sie berührt die Zoomlogik des Frontends, die freigegebenen Stufen je Datensatz und die Grenzen der Mosaik-Kachel. **(Empfehlung)**
2. In dieser Aufgabe mit umsetzen (PR deutlich über 400 Zeilen).
3. Nicht weiter verfolgen.

**Frage 4 — Mehr Gleichzeitigkeit (S4: HTTP/2 zum Browser, mehrere Prozesse)?**
1. Nicht jetzt. Mit M6 kommen CDN bzw. Reverse-Proxy mit HTTP/2 vor den `tiler`; bis dahin ein Prozess. Begründung: Bei begrenzter Leitung zur Quelle gewinnt es nichts und verdoppelt die Bytes. **(Empfehlung)**
2. Jetzt `--workers 2` für den `tiler` in `docker-compose.yml`. Mehr Speicher, mehr Bytes, im Browser weiter 6 Verbindungen.
3. Jetzt lokal HTTP/2: Vite mit `server.https`, braucht ein lokales Zertifikat (neues Werkzeug oder Paket).

**Frage 5 — `Cache-Control` für Kacheln (offen seit `adr/0006` §8 Punkt 3)?**
1. Weiter offen bis M6 (CDN). **(Empfehlung, denn die Lebensdauer hängt an Ablauf und Änderung der Items der Quelle)**
2. Jetzt `Cache-Control: public, max-age=3600` auf Kachel, TileJSON und Statistik. Zurückzoomen und Schwenken lädt dann aus dem Browser-Cache.

**Frage 6 — Was heißt „Suche genau einmal“?**
1. Jede Seite genau einmal: Drei Seiten bei ≥ 300 Treffern bleiben, ein Test sichert, dass keine Seite doppelt kommt, auch unter `StrictMode` und beim Öffnen eines Permalinks. **(Empfehlung)**
2. Eine Anfrage: zuerst nur die erste Seite (100 Szenen), weitere über „Load more“. Die Zeitleiste zeigt dann zunächst weniger.
3. Kleinere Antworten: nur die Felder, die der Viewer braucht (`fields`). Je Seite deutlich unter 1,9 MB, weiter drei Anfragen.
Und: Hast du drei gleiche Anfragen gesehen oder drei mit verschiedenem `token` im Rumpf?

**Frage 7 — `statistics` → `400`: Hast du den Text im Feld `detail` der Antwort (DevTools → Response)?**
1. Ja, der Text ist: … (dann gezielt diese Ursache)
2. Nein: Ich setze K1 um (Probe vor der Statistik auch bei einem Schritt, Ablehnung im Panel) und prüfe im Browser. **(Empfehlung, falls kein Text da ist)**

## 16. Umsetzung nach Freigabe

Ein Branch, ein Draft-PR, kleine Commits; Richtwert unter 400 Zeilen ohne das Messgerüst.

1. **`gateway/gdal.py`:** `tile_gdal_options(policy)` (Frage 1, 2), in `api/tiler.py` als `earthx_gdal_options`. Tests:
   - Das Profil enthält `SERIAL` und die Cache-Größe, die Grundoptionen bleiben gleich.
   - `process_gdal_options()` des Workers bleibt unverändert.
   - Alle Wege des `tiler` (Kachel, Statistik, TileJSON, Mosaik, Ergebnis, Zuschnitt) laufen mit demselben Profil (§13).
   - Gegen ein lokales COG über HTTP: Zwei Nachbarkacheln holen die gemeinsamen Blöcke einmal. Am alten Profil schlägt das fehl.
2. **Item-Abrufe der Einzelkachel über `ItemFetches`** (S2). Test: sechs gleichzeitige kalte Kacheln einer Szene holen das Item einmal; ein Fehler kommt bei allen gleich an.
3. **Suche** nach Frage 6. Test im Stil von `store.sections.test.ts`: Er zählt die `POST /stac/search` je Seite und `token` nach `runSearch`, beim Öffnen der App unter `StrictMode` und beim Öffnen eines Permalinks.
4. **`statistics`** nach Frage 7. Test: Die alte Logik schickt eine ungültige Formel an `/statistics`, die neue nicht und zeigt die Ablehnung.
5. **Nachtrag** in `adr/0006` §8 (Befund `MULTIRANGE`, R2), Zeile im Entscheidungslog, Backlog-Punkt 26 als erledigt mit PR-Nummer.
6. **Messung nachher** mit `scripts/tile-bench` in denselben Zeilen wie §8.2. Prüfung im echten Browser (Chromium der Sitzung) mit nachgestellter Suchantwort: Hell und Dunkel, schmales Fenster.
7. Vor „fertig“: `main` holen, `ruff check backend`, `pytest`, `lint-imports`, Frontend `npm run lint`, `npx tsc -b`, `npm test`.

**Prüfanleitung für Otto (nach der Umsetzung, PowerShell 5.1 und Browser):**

```powershell
docker compose up -d --build tiler
# Bytes der Quelle vorher/nachher: Netz-Eingang des tiler vor und nach einer Ansicht
docker stats --no-stream --format "{{.Name}} {{.NetIO}} {{.MemUsage}}" | Select-String tiler
```

Im Browser: DevTools → Network, Filter `tiles`, „Disable cache“ an, dieselbe NDVI-Vorschau wie am 25.10. öffnen. Zu vergleichen sind die Zeit bis zur letzten Kachel (Fußzeile „Finish“), die Spalte „Time“ der letzten Kacheln und der Zuwachs von NetIO beim `tiler`. Erwartet: deutlich weniger Eingang beim `tiler` und kürzere Zeiten. Die Warteschlange im Browser („Queueing“/„Stalled“) bleibt bei 6 Verbindungen sichtbar (Frage 4).

## 17. Messanhang

### 17.1 Aufruf

Das Gerüst unter `scripts/tile-bench/` ist kein Test und läuft weder in der CI noch unter `pytest`. Es braucht Postgres mit den eigenen Migrationen (`python -m earthx.catalog.load`) und rund 850 MB Platz für die COGs.

```bash
source .venv/bin/activate; set -a; source .env.test; set +a
python -I scripts/tile-bench/make_cogs.py /tmp/tb/cogs          # einmal, ~30 s
export COGS=/tmp/tb/cogs OUT=/tmp/tb/out
NEW="CPL_VSIL_CURL_CACHE_SIZE=268435456,GDAL_HTTP_MULTIRANGE=SERIAL"
scripts/tile-bench/bench.sh today_ndvi                            # heute, ohne Leitungsgrenze
MBIT=100 scripts/tile-bench/bench.sh today_ndvi_100               # heute, 100 Mbit/s
EXTRA_GDAL=$NEW scripts/tile-bench/bench.sh gdal_ndvi             # mit S1
EXTRA_GDAL=$NEW scripts/tile-bench/bench.sh t512 --z 10 --side 3 --tilesize 512
EXTRA_GDAL=$NEW WORKERS=4 scripts/tile-bench/bench.sh h2w4 --z 10 --side 3 --tilesize 512 --conns 24
```

`bench.sh` leert vor jedem Lauf den Item- und den Statistik-Cache in Postgres. Es startet Quelle und `tiler` frisch und gibt zwei JSON-Zeilen aus: die Sicht des Clients (`view.py`) und die Phasen und Bytes (`summary.py`). In der Umsetzung kommt S1 in den Code, dann misst `bench.sh` ohne `EXTRA_GDAL` den neuen Stand. `EXTRA_GDAL=GDAL_HTTP_MULTIRANGE=YES,CPL_VSIL_CURL_CACHE_SIZE=16384000` stellt den alten wieder her.

### 17.2 Vorläufe

Vor dem endgültigen Gerüst liefen dieselben Messungen mit einem Vorläufer im Scratchpad: dieselbe Quelle, derselbe `tiler`, dasselbe Item aus einer echten Szene statt eines handgeschriebenen. Daraus stammen:

- **`boto3`:** 25 `visual`-Kacheln nacheinander, mit `cProfile`: 231 ms je Kachel. 2,62 von 5,77 s liegen in `rasterio.session.Session.from_environ` → `botocore`. Ohne `boto3` sind es 153 ms je Kachel (NDVI).
- **Eine Szene, seriell, 1 GiB Cache:** `YES` 90,6 MB, `SERIAL` 21,8 MB, `SINGLE_GET` 122,8 MB, `YES` ohne `MERGE_CONSECUTIVE_RANGES` 90,6 MB; gebraucht 21,8 MB.
- **Nur der Cache größer, ohne `SERIAL`:** 1,18 GB statt 1,72 GB; die Ansicht dauert 32,0 s statt 47,4 s. **Nur `SERIAL`, Cache 16 MB:** 1,75 GB, 58,9 s. Beide Einstellungen braucht es zusammen.
- **Cache 256 gegen 512 MiB** bei 100 Mbit/s: 38,2 gegen 37,0 s, 294 gegen 292 MB von der Quelle.
- **Ohne `HEAD`** (`CPL_VSIL_CURL_USE_HEAD=NO`): 32,4 gegen 32,0 s.

### 17.3 Bitgleichheit

`hashes.py` (Scratchpad): je drei Nachbarkacheln für NDVI und `visual` auf z11/256, z10/512 und z14/256, SHA-256 der Antwort, einmal mit den heutigen Optionen und einmal mit S1. Ergebnis: 18 von 18 gleich.

### 17.4 Kodieren

Eine echte NDVI-Kachel z11 aus `S2A_T32TPT_20260830T102039_L2A` (nur im Speicher, nicht abgelegt), `ImageData.render`, bestes von 5:

| Format | Größe | Zeit |
|---|---|---|
| PNG (heute) | 127 kB | 44,9 ms |
| PNG `ZLEVEL=1` | 125 kB | 25,2 ms |
| WebP verlustfrei | 44 kB | 53,1 ms |

Die synthetische Kachel kodiert gleich schnell (46,8 ms, 101 kB). Für das Kodieren ist das Gerüst damit nicht zu günstig.
