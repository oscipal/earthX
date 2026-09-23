# ADR 0010 — Coverage: vorberechneter Zählwürfel

- **Status:** Entwurf, wartet auf Otto (§9).
- **Datum:** 2026-09-23
- **Aufgabe:** M3-05 laut `docs/plans/m3-dritte-quelle-und-interface.md` §4.
- **Autonomiestufe:** C — gemessen, recherchiert und berichtet. Kein
  Produktivcode geändert, keine Daten ins Repo, keine Datei außerhalb von
  `docs/` angefasst.
- **Grundlage:** `plans/m2-format-und-viewer.md` D26; `plans/m2-05-coverage.md`
  F3; `adr/0004` (ganz, besonders §3.3, §3.6, §5 Regel V); `adr/0005` Regel II;
  `adr/0007` §12 (EOPF); `architekturplan.md` 3.1, 3.2; `KLAERUNGEN.md` B8, B9,
  B10; `ENTSCHEIDUNGSLOG.md` Zeilen „Coverage-Heatmap im Viewer zurückgestellt"
  (20.09.), „M2-07c abgeschlossen im kleinstmöglichen Umfang" (22.09.),
  „Heatmap-Zählwürfel (D26)" (23.09.); `plans/m3-02-konformitaetsbericht.md`
  K-06, K-07.
- **Betroffen, falls angenommen:** `adr/0004` §5 (Nachtrag), `plans/m2-05-coverage.md`
  F3 (aufgehoben), `catalog/registry.py` (`CoverageInfo`), eine Migration in
  `catalog`, `api/coverage_route.py`, Prozess `harvester`; Entscheidungslog.

---

## Methode und Belegstufen

Gearbeitet wurde in einer Cloud-Sitzung am 23.09.2026, etwa 17:30 bis 17:55 UTC.
Belegstufen wie in `adr/0004`:

- **M** — in dieser Sitzung gemessen; das Vorgehen steht in §12.
- **P** — am Primärdokument gelesen (Spezifikation, Quelltext).
- **S** — Suchtreffer mit Link, Primärdokument nicht gelesen.
- **A** — eigene Ableitung aus M/P/S, als Argument gekennzeichnet.

**Last auf den Quellen.** Earth Search: **476 Anfragen**, alle Metadaten
(`/aggregate`, `/aggregations`, `/search` mit `fields`), streng nacheinander,
zusammen 183 s Antwortzeit und 24 MB. EOPF: **12 Anfragen**, 23 MB. Keine
Drosselung, kein Fehler außer einem absichtlich provozierten `502` (§3.5).
Das ist mehr als in `adr/0004` (40) und `adr/0005` (110), weil die Frage
„was kostet die Erstbefüllung" nur mit echten Zerlegungen beantwortbar war;
hochgerechnet wird ab einem vollständig gemessenen Monat, nicht durch Befüllen.

**Postgres synthetisch.** Größe und Latenz sind an einem synthetischen Würfel
in der lokalen Wegwerf-Datenbank der Sitzung gemessen (Postgres 16.13,
PostGIS 3.4.2, 4 vCPU, 15 GB RAM, Vorgaben: `shared_buffers` 128 MB,
`work_mem` 4 MB, JIT an). Die **Zellmenge** ist echt — die 49 699 z9-Zellen,
in die Earth Search die Aufnahmen vom Juni 2025 legt —, die **Zählwerte** sind
Zufallszahlen. Die Zellmenge liegt nur in der Sitzung, nicht im Repo.

---

## 1. Kontext und Frage

`adr/0004` lässt die Coverage je Anfrage von der Quelle aggregieren; M2-05 F3
hat für den ungefilterten Weltüberblick ausdrücklich **keine Vorberechnung**
gewählt. Seitdem ist der Weltüberblick auf **Geotile z6** gedeckelt, weil
Earth Search ab z7 bei 10 000 Zellen kappt (`adr/0004` §3.3, Nachtrag). Eine
z6-Zelle ist am Äquator rund 625 km breit. Otto hat die Heatmap deshalb am
20.09.2026 als „in der Übersicht zu grob" zurückgestellt (D26) und einen
Kandidaten genannt: **Zählwürfel je Datensatz, Zelle z9 × Monat × Wolkenklasse,
täglich aktualisiert.**

Dieses ADR misst den Kandidaten und seine Alternativen. Es beantwortet:
Erstbefüllung, tägliche Aktualisierung, Größe in Postgres, Abfragelatenz für
Weltansicht und AOI, Verhalten bei einer Quelle nur mit Stichprobe (EOPF), Ort
der Berechnung und den Erhalt von Regel V.

**Was die Oberfläche heute schickt [M, Code].** `frontend/src/store.ts`
(`refreshCoverage`) ruft die Route mit `zoom`, `bbox` (nur aus der echten
Such-AOI) und `datetime` auf. `datetime` ist tagesgenau (`YYYY-MM-DDT00:00:00Z`
bis `…T23:59:59Z`) und beim Start leer. **Einen Wolkenfilter setzt die
Oberfläche nirgends** — `maxCloudCover` gibt es nur im API-Client
(`api.ts:227`). Die Route nimmt `max_cloud_cover` an, aber kein Bedienelement
füllt es.

## 2. Kriterien

K1 bis K8 aus `adr/0004` §2 gelten unverändert, besonders K2 (Vollständigkeit
geprüft oder sichtbar), K4 (leerer Zwischenspeicher macht nur langsamer, nie
404), K5 (Last auf der Quelle), K6 (gefiltert unter 1 s, typisch unter 0,5 s).
Dazu drei aus der Aufgabe:

| # | Kriterium | Herkunft |
|---|---|---|
| K9 | Nicht im Worker-Kern; Vertrag `no-database-in-worker-core` bleibt | `KLAERUNGEN` B9; M3-05 |
| K10 | Pflichtfeld `completeness` bleibt, mit den drei Werten aus Regel V | `adr/0004` §5 |
| K11 | Weltüberblick feiner als z6 | D26 |

## 3. Was gemessen wurde

### 3.1 Umfang und Zeitverteilung von Sentinel-2 L2A — [M]

`sentinel-2-c1-l2a` bei Earth Search: **30 422 969 Items**, verteilt auf 132
Monatsbuckets (2015-10 bis 2026-09). **112 Monate** tragen Items; 2015-10 bis
2017-10 sind leer, 2022-01 bis 2022-11 fast leer (≤ 40 000 je Monat, meist
unter 2 000). Volle Monate liegen heute bei **430 000 bis 487 000 Items**.

### 3.2 Warum der Würfel nicht aus einer Anfrage je Monat entsteht — [M]/[P]

Ein einzelner Monat (Juni 2025, 459 298 Items), weltweit, ohne Wolkenfilter:

| Stufe | Zellen | Summe | Vollständig | Zeit | Nutzlast |
|---|---|---|---|---|---|
| z6 | 1 866 | 459 298 | ja | 0,59 s | 100 kB |
| z7 | 6 628 | 459 298 | ja | 0,50 s | 352 kB |
| z8 | **10 000** | 333 420 | **nein** | 1,00 s | 539 kB |
| z9 | **10 000** | 204 772 | **nein** | 0,69 s | 546 kB |

Die Kappung aus `adr/0004` §3.3 greift also schon **für einen einzigen Monat**
ab z8. Auch `grid_code_frequency` (MGRS-Kachel statt Geotile) kappt bei 10 000
(276 111 von 459 298) **[M]**.

Die Ursache steht im Quelltext von `stac-server`, der Software hinter Earth
Search: `grid_geotile_frequency` ist eine OpenSearch-`geotile_grid`-Aggregation
über `properties.proj:centroid` **ohne** `size`; `grid_code_frequency` setzt
`size: 10000` ausdrücklich **[P]** (`src/lib/database.ts` auf `main`). OpenSearch
setzt für `geotile_grid` 10 000 als Vorgabe **[S]**. Eine seitenweise
**Composite**-Aggregation, die alle Zellen liefern könnte, nutzt `stac-server`
nicht **[P]**; die Aggregation-Extension kennt kein Paging **[P]**. Der Quelltext
auf `main` ist nicht zwingend der bei Earth Search laufende Stand.

Nebenbefund **[P]/[M]**: Die Wolkenklassen der Quelle sind fest verdrahtet
(`<5`, `5–15`, `15–40`, `≥40`), nicht parametrierbar. Wolkenklassen des Würfels
müssen deshalb über getrennte Anfragen mit `query` entstehen.

### 3.3 Erstbefüllung: Zerlegung in Kacheln — [M]

Weg: erst eine Anfrage auf z3 (liefert `total_count` und die z3-Kacheln mit
Daten), dann je z3-Kachel eine Anfrage auf z9 mit deren `bbox`; aus der Antwort
zählen nur Zellen **innerhalb** der Kachel (die `bbox` trifft auch Items, deren
Mittelpunkt nebenan liegt). Eine z3-Kachel enthält höchstens 64 × 64 = 4 096
z9-Zellen, die Kappung kann also nicht greifen. Die Summe aller Teile muss
gleich dem `total_count` der ersten Anfrage sein — das ist Regel V, nur je
Monat und Klasse statt je Anfrage.

**Juni 2025, z9, fünf Wolkenklassen zu je 20 %:**

| Klasse | Items | z9-Zellen | Anfragen | Dauer | Nutzlast | Summe == Gesamt |
|---|---|---|---|---|---|---|
| < 20 | 137 906 | 34 525 | 46 | 17,9 s | 2,0 MB | ja |
| 20–40 | 51 590 | 26 293 | 46 | 17,9 s | 1,6 MB | ja |
| 40–60 | 46 528 | 24 832 | 46 | 15,6 s | 1,5 MB | ja |
| 60–80 | 49 641 | 25 275 | 46 | 16,9 s | 1,5 MB | ja |
| ≥ 80 | 173 633 | 39 028 | 47 | 16,4 s | 2,3 MB | ja |
| **Monat** | **459 298** | **149 953 Zeilen** | **231** | **84,7 s** | **8,9 MB** | ja |

Ohne Klassen, nur z9: 49 699 Zellen, 47 Anfragen, 17,1 s. Für andere Monate:
Juni 2020 (368 643 Items) 45 478 Zellen in 46 Anfragen; Dezember 2018 (8 149
Items) 6 949 Zellen in 45 Anfragen. Die Anfragezahl hängt an der Zahl der
z3-Kacheln (44–46), nicht am Umfang des Monats. Längste Einzelanfrage 0,79 s.

**Die Probe schlägt tatsächlich an.** Juni 2020 ergab **368 642 von 368 643**:
ein Item fiel durch die Zerlegung. Vermutung **[A]**, nicht geprüft: ein
Footprint über die Datumsgrenze, dessen Mittelpunkt in einer Kachel liegt, die
seine Geometrie nicht schneidet. Genau dafür ist Regel V da — der Monat wäre
`truncated`, nicht stillschweigend „vollständig".

**Leichtere Variante, z8 ohne Klassen [M].** Eine z2-Kachel enthält 64 × 64 =
4 096 z8-Zellen, also genügt die Zerlegung nach z2:

| Monat | Items | z8-Zellen | Anfragen | Dauer | Nutzlast | Summe == Gesamt |
|---|---|---|---|---|---|---|
| 2025-06 | 459 298 | 22 387 | 13 | 6,0 s | 1,3 MB | ja |
| 2026-09 (bis heute) | 353 465 | 25 823 | 17 | 6,3 s | 1,5 MB | ja |

**Hochrechnung auf den ganzen Katalog [A]:**

| Variante | Anfragen | Dauer nacheinander | Nutzlast roh | Zeilen |
|---|---|---|---|---|
| D26: z9 × Monat × 5 Klassen | 112 × 5 × ~46 ≈ **25 800** | ≈ 2,6 h | ≈ 1,0 GB | ≈ **11,9 Mio.** |
| z9 × Monat | 112 × ~46 ≈ 5 200 | ≈ 32 min | ≈ 300 MB | ≈ 4,5 Mio. |
| **z8 × Monat** | 112 × ~15 ≈ **1 700** | ≈ **12 min** | ≈ 150 MB | ≈ **2,5 Mio.** |

Die Zeilenzahl für D26 folgt aus dem Monatshistogramm, gedeckelt auf die
gemessenen 150 000 Zeilen eines vollen Monats (§12.3). Mit gzip schrumpft die
Nutzlast etwa um den Faktor 15 (gemessen an einer z9-Teilanfrage: 122,5 kB roh,
8,4 kB gzip **[M]**). Parallel mit den 6 Verbindungen je Host aus `adr/0005`
§3.6 teilt sich die Dauer entsprechend — die Last auf der Quelle nicht.

### 3.4 Tägliche Aktualisierung — [M]

Neue Items je Tag (Feld `created`, 16. bis 22.09.2026): **14 917 bis 15 929**.
Earth Search nimmt `created` und `updated` als `query` auf `/aggregate` an,
zusammen mit `datetime_frequency`. Damit sagt **eine** Anfrage (0,3–0,6 s),
welche Monate sich seit dem letzten Lauf geändert haben:

| `updated` seit | geänderte Items | betroffene Monate |
|---|---|---|
| 22.09.2026 00:00 | 25 919 | nur 2026-09 |
| 24.08.2026 | 482 576 | 2026-08, 2026-09 |
| 01.06.2026 | 1 847 483 | 2026-05 bis 2026-09, **dazu 2024-10, 2024-11, 2024-12** (46 350 Items) |

Die Quelle pflegt also nicht nur den laufenden Monat nach, sondern gelegentlich
auch Monate, die fast zwei Jahre zurückliegen. Ein Würfel, der nur den
laufenden Monat erneuert, würde dort unbemerkt veralten. Der Weg ist deshalb:
**geänderte Monate erkennen, jeden davon ganz neu zählen, Regel V je Monat
prüfen.** Kosten je geändertem Monat: 231 Anfragen (D26) oder 13–17 (z8).
Typisch sind ein bis zwei Monate am Tag.

Das Schreiben ist billig: einen Monat (150 000 Zeilen) in beiden Tabellen
ersetzen dauert **2,1 s** in einer Transaktion (§3.6).

### 3.5 Befüllung über `/search` statt `/aggregate` — [M]

Mit `fields` (nur `id`, `bbox`, `datetime`, `eo:cloud_cover`) liefert
`/search` 1 000 Items in **0,40 s und 248 kB** (rund 250 B je Item). Ohne
`fields` bricht `limit=1000` nach 2,9 s mit **`502`** ab. Hochgerechnet
**[A]**: 30,4 Mio. Items sind rund 30 400 Seiten, gut 3 h und 7,5 GB. Für
das **Nachführen** wäre der Weg billig (15 500 neue Items am Tag = 16 Seiten,
7 s), aber er sieht Änderungen und Löschungen nur, wenn wir je Item speichern,
was wir gezählt haben — das ist das Ernten der Items (Option 5 in `adr/0004`),
das `architekturplan.md` 5.2 für föderierte Quellen ausschließt.

### 3.6 Größe in Postgres — [M], synthetisch

Tabelle `cube(dataset smallint, month date, cc smallint, x smallint, y smallint,
n integer)`, Primärschlüssel `(dataset, month, cc, x, y)`, **11 901 229 Zeilen**
(die D26-Variante für Sentinel-2 L2A, §3.3):

| Teil | Größe |
|---|---|
| Tabelle | 592 MB |
| Primärschlüssel | 358 MB |
| zweiter Index `(dataset, x, y, month, cc) INCLUDE (n)` für AOI-Abfragen | 460 MB |
| **zusammen** | **1,41 GB** |
| Verdichtung auf z5 (258 800 Zeilen, in 1,25 s gebaut) | 21 MB |

Pro Zeile rund 80 B mit Primärschlüssel — der Zeilenkopf von Postgres
überwiegt die 16 B Nutzdaten. **Hochgerechnet [A]:** die z8-Variante
(≈ 2,5 Mio. Zeilen) liegt bei rund 200 MB mit Primärschlüssel, 300 MB mit
AOI-Index. Jeder weitere Datensatz kommt in seiner Größe hinzu. Der Würfel
wächst bei Sentinel-2 um rund 150 000 Zeilen (D26) bzw. 23 000 Zeilen (z8) je
Monat.

Aufbau: Erzeugen 13,0 s, sortiert einfügen 38,7 s, `VACUUM ANALYZE` 0,9 s.

### 3.7 Abfragelatenz — [M], synthetisch

`EXPLAIN (ANALYZE, TIMING OFF)`, drei Läufe, Median. „Europa" ist der
Beispielausschnitt aus `adr/0004` §10.2 (−10…30° O, 35…60° N).

| Abfrage | ohne AOI-Index | mit AOI-Index / Verdichtung |
|---|---|---|
| Welt z3, alle Monate, alle Klassen | 536 ms | **21 ms** (aus z5) |
| Welt z5/z6, Jahr 2024, Wolken < 40 % | 190 ms | **3 ms** (z5, aus z5) |
| Welt z6, alle Monate, Wolken < 40 % | 309 ms | — |
| Welt z3, letzte 12 Monate | 253 ms | — |
| **Welt z8, alle Monate** | **672 ms** | — |
| **Welt z9, alle Monate** | **903 ms** | — |
| Welt z9, Jahr 2024, Wolken < 40 % | 229 ms | — |
| Europa z8, alle Monate | 283 ms | 137 ms |
| Europa z9, Jahr 2024, Wolken < 40 % | 87 ms | — |
| eine z6-Kachel auf z9, alle Monate | 240 ms | **6 ms** |
| Zeit-Histogramm Europa, Wolken < 40 % | 248 ms | 74 ms |
| Zeit-Histogramm Welt, Wolken < 40 % | — | 15 ms (aus z5) |

Alles bleibt unter 1 s (K6). Über 0,5 s liegen nur die feinen Weltansichten
über den ganzen Zeitraum (z8: 672 ms, z9: 903 ms) — dafür bräuchte es eine
Verdichtung „alle Monate" je Zelle, die bei jeder Monatserneuerung mitläuft
**[A]**. Der AOI-Index lohnt sich bei kleinen AOIs (240 → 6 ms), kostet aber
460 MB.

### 3.8 Nutzlast der Weltansicht — [M], synthetisch

Antwort im heutigen Format (`{"k":"z/x/y","n":…}`, F4 aus M2-05), alle Monate:

| Stufe | Zellen | roh | gzip |
|---|---|---|---|
| z6 | 1 866 | 58 kB | 11 kB |
| z7 | 6 628 | 206 kB | 36 kB |
| **z8** | **22 387** | **704 kB** | 116 kB |
| **z9** | **49 699** | **1,58 MB** | 246 kB |

Der synthetische Würfel kennt nur die Zellen eines Monats. Über alle Monate
sind es mehr: live gemessen hat z6 über den ganzen Katalog 2 863 statt 1 866
Zellen (§3.9). Mit demselben Faktor **[A]** läge z8 bei rund 1,1 MB, z9 bei
rund 2,4 MB.

**z8 und z9 reißen damit die Umkehrschwelle von ~500 kB aus `adr/0004` §5**,
ab der Vektorkacheln neu zu erwägen sind. Die Schwelle ist dort ohne
Kompression gesetzt; `api` komprimiert heute nicht (kein `GZipMiddleware`,
**[M]** Code).

### 3.9 Vergleich: der heutige Live-Weg — [M]

Dieselben Fragen direkt an `/aggregate`, je eine Anfrage:

| Abfrage | Zeit | Nutzlast | Zellen | Vollständig |
|---|---|---|---|---|
| Welt z6, ganzer Katalog | 1,52 s | 166 kB | 2 863 | ja |
| Welt z6, 2024, Wolken < 40 % | 0,68 s | 148 kB | 2 756 | ja |
| Europa z8, ganzer Katalog | 0,63 s | 58 kB | 865 | ja |
| Europa z8, 2024, Wolken < 40 % | 0,61 s | 45 kB | 825 | ja |

Mit einer AOI von Europas Größe ist der Live-Weg auf z8 **vollständig und
schnell genug** — dort bringt der Würfel wenig. Sein Nutzen liegt allein im
**Weltüberblick feiner als z6** (K11), den der Live-Weg nur über 13 bis 46
Anfragen je Kartenbild liefern könnte (6–18 s, §3.3).

### 3.10 Quelle nur mit Stichprobe: EOPF — [M]

`sentinel-2-l2a-zarr3` bei EOPF: keine Aggregation-Extension, **kein
`numberMatched`**, aber `fields`, `sort` und `filter`. Zeitliche Ausdehnung laut
Collection: 16.07. bis 22.09.2026 — ein rollendes Fenster von rund 68 Tagen.

| Anfrage | Zeit | Nutzlast |
|---|---|---|
| 100 Items ohne `fields` | 2,38 s | 1,48 MB |
| 100 Items mit `fields` | 0,90 s | 28 kB |
| ein Tag (15.09.) vollständig, `limit=1000`, `fields` | 3,9 s, 2 Seiten | 354 kB, **1 334 Items** |

Hochgerechnet **[A]**: rund 90 000 Items im Fenster, eine vollständige
Aufzählung mit `fields` kostet rund 90 Seiten, 3 min und 25 MB. Weil das
Fenster rollt und alte Items herausfallen, müsste der Würfel täglich **ganz**
neu gezählt werden; ein Nachführen nur des Neuen würde Gelöschtes nie
abziehen.

Das Problem für Regel V: EOPF nennt **keine Gesamtzahl**. Eine vollständige
Aufzählung bis zur letzten Seite ist die bestmögliche Zählung, aber sie ist
nicht gegen eine Zahl der Quelle geprüft. Heute gilt: fehlt `total_count`,
ist das Ergebnis nie `complete` (`adr/0004` §5, Nachtrag 20.09.). Ob eine
lückenlose Aufzählung als `complete` gelten darf, ist eine Frage an Otto (§9,
F5).

### 3.11 Aus der Cloud-Sitzung nicht erreichbar — [M]

`apt.postgresql.org` (PGDG, dort läge `postgresql-16-h3`) und
`planetarycomputer.microsoft.com` (stac-geoparquet-Exporte) antworten mit
`403` am Egress-Proxy. H3 und die geoparquet-Exporte sind deshalb nur aus
Quellen belegt, nicht gemessen.

## 4. Stand der Technik und Alternativen

**stac-geoparquet mit spaltenbasierter Abfrage.** Die Spezifikation liegt bei
`radiantearth/stac-geoparquet-spec` und ist noch nicht in Version 1 **[S]**.
Planetary Computer veröffentlicht für große Collections, darunter
`sentinel-2-l2a`, ein Asset `geoparquet-items`, zeitlich partitioniert **[S]**;
Aktualisierungstakt und Größe sind unbelegt. **Earth Search bietet keinen
solchen Export** (README) **[P]**. DuckDB liest GeoParquet über HTTP mit
Range-Requests **[S]**. Für uns hieße das: Planetary Computer statt Earth
Search als Zählquelle — eine andere Quelle mit eigenem Stand als die, aus der
gesucht und angezeigt wird. Die Zahlen der Heatmap passten dann nicht mehr zu
den Suchtreffern (K3, `adr/0004` §5 Regel V), und DuckDB wäre eine neue
Laufzeitabhängigkeit. Aus der Sitzung nicht erreichbar (§3.11).

**Anderes Zellraster: H3.** Fachlich weiterhin das bessere Gitter
(`adr/0004` §3.7). `h3-pg` ist laut Projekt als PGDG-Paket
`postgresql-<version>-h3` erhältlich **[S]**; die PGDG-Quelle ist aus der
Cloud-Umgebung gesperrt (§3.11), das Ubuntu-Archiv führt es nicht
(`adr/0004` §3.7, **[M]** dort). Earth Search liefert `grid_geohex_frequency`
mit derselben 10 000-Kappung **[M]** in `adr/0004`. Ein Wechsel des Gitters
ändert die Frage nach Zerlegung, Größe und Aktualisierung nicht, nur die
Zellform.

**Vektorkacheln.** `ST_AsMVT` aus dem Würfel über eine Route in `api` braucht
keinen neuen Prozess (`adr/0004` §3.6 E: 50 901 Zellen in 614 ms). Kachelserver
wie pg_tileserv (CrunchyData) oder Martin wären ein fünfter Prozess **[S]**;
PMTiles als statische Datei im Objektspeicher **[P]** käme erst mit einem
Objektspeicher im Betrieb (M4). Filterbare Zählwerte lösen verbreitete
Beispiele entweder mit einem Kachelsatz je Filterkombination oder mit
Zählwerten je Monat als Feature-Eigenschaft und Filter im Client **[S]**.
Vektorkacheln sind **keine Alternative zum Würfel**, sondern eine
Darstellungsschicht darüber; nötig werden sie erst, wenn der Würfel
Weltansichten über 500 kB liefert (§3.8).

**Composite-Aggregation an der Quelle.** OpenSearch kann mit `composite` und
`after_key` alle Zellen einer `geotile_grid`-Aggregation seitenweise liefern
**[P]**. `stac-server` nutzt das nicht (§3.2), und wir können es nicht
nachrüsten. Das wäre ein Beitrag an `stac-server` und eine Erweiterung der
Aggregation-Spezifikation, nichts, worauf M3 bauen kann.

**Inkrementelle Pflege in Postgres.** `pg_ivm` (PostgreSQL-Lizenz, PG 13–18)
pflegt materialisierte Sichten per Trigger **[S]** — hilft nur, wenn die
Einzelitems in Postgres liegen, was für föderierte Items nicht gilt (§3.5).
TimescaleDB Continuous Aggregates stehen unter der Timescale License, nicht
Apache-2.0 **[S]**; eine Lizenzfrage, die der Nutzen nicht rechtfertigt
**[A]**. Für den Würfel reicht einfaches Ersetzen je Monat (2,1 s, §3.4);
eine Partitionierung nach Monat macht daraus später ein Austauschen von
Partitionen, ist aber bei 2,5 bis 12 Mio. Zeilen nicht nötig **[A]**.

**Vergleichbare Portale.** Sentinel Hub (Statistical API) aggregiert
Pixelwerte, keine Szenenzahlen je Zelle **[S]**; NASA CMR liefert
Treffer- und Facettenzahlen je Collection, eine räumliche Dichte ist unbelegt
**[S]**. Eine übernehmbare Konvention für eine Heatmap der Aufnahmedichte fand
sich nicht — wie schon in `adr/0004` §8.3.

## 5. Ort der Berechnung

`jobs` und `processing` dürfen keine Datenbank berühren (B9, Vertrag
`no-database-in-worker-core`). Der Würfel braucht aber beides: Lesen der Quelle
über `gateway` und Schreiben in Postgres. Er gehört deshalb **nicht** in den
Worker, und der Vertrag bleibt unverändert (K9).

Die Aufteilung folgt `adr/0004` §5 und `architekturplan.md` 3.1:

| Teil | Modul | Grund |
|---|---|---|
| Zerlegung in Kacheln, Erkennen geänderter Monate über `updated`, 10 000-Grenze | `adapters` | Protokollwissen über Earth Search |
| Tabelle, Migration, Abfrage, Regel V je Monat, die Regel „kann der Würfel diese Anfrage beantworten" als reine Funktion | `catalog` | Coverage-Nahtstelle, Postgres |
| Wahl zwischen Würfel und Live-Weg je Anfrage | `api` (`coverage_route.py`) | dort wird heute komponiert; `catalog` darf keinen Adapter rufen (M3-02 K-07, Klärung in `adr/0011`) |
| Anstoßen: täglich, geänderte Monate, Fortschritt | `discovery` | darf `adapters`, `catalog`, `gateway` (3.1) |
| Prozess | `harvester` | laut 3.2 „I/O-lastig, geplant, Fortschritt in Postgres"; läuft in `docker-compose.yml` bereits als Hülle |

**Anstoß.** Einen Zeitplaner gibt es nicht. Zwei Wege ohne neuen Dienst
**[A]**: eine Schleife im `harvester`, die sich über ein
`pg_try_advisory_lock` gegen einen zweiten `harvester` absichert, oder ein
Kommando (`python -m earthx.discovery …`), das ein äußerer Zeitplaner aufruft.
Der erste Weg läuft lokal und in der Cloud gleich; der zweite braucht einen
Zeitplaner, den es heute nicht gibt. Welchen der `harvester` für die dritte
Quelle (P4, M3-11) bekommt, sollte für beides gelten.

**Zustand.** Der Würfel ist Zustand in Postgres, aber kein Zustand eines
Dienstes: `api` liest ihn nur. Fehlt er oder ist er veraltet, antwortet der
Live-Weg — gröber und langsamer, nie mit 404 (K4, E5). Das gehört als Test
hinterlegt, wie `adr/0004` §5 es für den Weltüberblick schon verlangt.

## 6. Optionen

**Option A — Heutiger Weg (M2-05 F3).** Keine Vorberechnung, Weltüberblick
höchstens z6.
*Dafür:* kein Zustand, kein Prozess, jede Filterkombination. *Dagegen:*
erfüllt K11 nicht; D26 bleibt offen.

**Option B — Heutiger Weg, Weltüberblick fest auf z6.** Der am 20.09. im
M2-07c-PR vorgeschlagene und zurückgestellte Eingriff in
`level_for_viewport`: ohne AOI immer z6 anfordern, statt die Stufe aus dem
Kartenzoom abzuleiten (heute bei Zoom 1,6 nur Stufe 1, vier Zellen à 180°).
*Dafür:* klein, sofort, keine neuen Teile; beseitigt den gröbsten Teil der
Beschwerde. *Dagegen:* 625 km bleiben 625 km.

**Option C — Zählwürfel wie in D26: z9 × Monat × 5 Wolkenklassen.**
*Dafür:* feinster Weltüberblick; Wolkenfilter in fünf Stufen ohne Live-Weg.
*Dagegen:* ≈ 25 800 Anfragen Erstbefüllung, 231 je geändertem Monat,
≈ 1,4 GB je Datensatz mit AOI-Index (§3.3, §3.6). z9 liegt **über dem Deckel
z8**, den Otto am 19.09. für beide Sentinel-2-Datensätze gesetzt hat: Eine
z9-Zelle ist mit rund 78 km kleiner als ein 110-km-Footprint, die
Zentroid-Zählung zeigt dort Punktmuster statt Abdeckung (`adr/0004` §5). Die
Weltansicht auf z9 wiegt 1,6 bis 2,4 MB (§3.8). Die Wolkenklassen bedienen
einen Filter, den die Oberfläche nicht hat (§1).

**Option D — Schlanker Würfel: z8 × Monat, ohne Wolkenklasse.**
*Dafür:* ≈ 1 700 Anfragen Erstbefüllung (≈ 12 min), 13–17 je geändertem
Monat, ≈ 200–300 MB je Datensatz (§3.3, §3.6); z8 ist genau der Deckel des
Datensatzes; der laufende Monat ließe sich statt täglich auch stündlich
erneuern (17 Anfragen, 6 s). Weltüberblick z7 in rund 300 kB und alle Stufen
bis z6 aus einer Verdichtung in Millisekunden.
*Dagegen:* beantwortet nur Anfragen, deren Zeitraum aus ganzen Monaten besteht
oder offen ist, und ohne Wolkenfilter; alles andere bleibt beim Live-Weg. Die
Weltansicht auf z8 reißt die 500-kB-Schwelle (§3.8).

**Option E — Ernten der Items (`adr/0004` Option 5).** Nicht neu; die Messung
bestätigt die Gründe dagegen: ≈ 30 400 Seiten, 7,5 GB für einen Datensatz,
und Pflege je Item (§3.5). Ausgeschieden.

**Option F — Zählquelle stac-geoparquet (Planetary Computer).** Andere Quelle
als die angezeigte, unklarer Takt, neue Laufzeitabhängigkeit (§4).
Ausgeschieden.

## 7. Empfehlung

**Option D, in dieser Form.** Der Würfel ist ein **zusätzlicher Weg im
Coverage-Anbieter**, kein Ersatz. Je Anfrage gilt (Regel in `catalog`, Wahl in
`api`, §5):

| Anfrage | Weg |
|---|---|
| ohne AOI, Zeitraum offen oder ganze Monate, kein Wolkenfilter | Würfel, bis z8 |
| sonst | Live-Weg wie heute (`adr/0004`) |
| Würfel leer, veraltet oder Monat nicht geprüft | Live-Weg (K4) |

Damit gilt: Der Würfel bedient genau die Ansicht, die D26 beanstandet — den
Weltüberblick beim Start, ohne AOI und ohne Datum —, und alles, was der
Live-Weg schon gut kann (AOI, beliebige Tage, Wolkenfilter, später CQL2 aus
M3-13), bleibt dort. Mit AOI ist der Würfel verzichtbar: Europa auf z8 ist
live vollständig und in 0,6 s da (§3.9). Den AOI-Index (460 MB bei C)
braucht D damit nicht.

**Regel V bleibt, je Monat geprüft (K10).** Neben dem Würfel steht je Datensatz
und Monat eine Zeile mit `total_count` der Quelle, gezählter Summe und Zeitpunkt
der Zählung. Eine Antwort aus dem Würfel ist `complete`, wenn jeder beteiligte
Monat geprüft vollständig ist, sonst `truncated` mit „zeigt N von M". Der Fall
Juni 2020 (§3.3) wäre damit sichtbar statt verschluckt. Neu ist eine Angabe
„Stand der Zählung" in der Antwort; sie ersetzt kein Pflichtfeld, sie ergänzt
es, weil der Würfel bis zu einen Tag alt sein kann, der Live-Weg am offenen
Rand nur 5 min (`adr/0005` Regel II).

**Aktualisierung.** Täglich eine Anfrage mit `updated` seit dem letzten Lauf
(§3.4); jeder geänderte Monat wird ganz neu gezählt und in einer Transaktion
ersetzt. Das fängt auch das Nachpflegen alter Monate, das die Quelle
tatsächlich tut.

**Ort.** Wie in §5: Protokoll in `adapters`, Tabelle und Abfrage in `catalog`,
Wahl in `api`, Anstoß in `discovery`, Prozess `harvester`, gesichert über eine
Advisory-Lock-Schleife. `jobs` und `processing` bleiben ohne Datenbank.

**Registry.** Ein neues Feld in `CoverageInfo`, ohne Vorgabewert (B10), das je
Datensatz sagt, ob ein Würfel geführt wird. Sentinel-2 L2A: ja. EOPF: siehe
§9 F5.

**Vorher, unabhängig davon: Option B.** Der zurückgestellte Eingriff in
`level_for_viewport` kostet wenig und hilft sofort; er wird durch D nicht
überflüssig, sondern ist ihr Rückfall, wenn der Würfel fehlt.

**Warum nicht C.** Drei Gründe, alle aus der Messung: (1) z9 widerspricht dem
Deckel z8, den Otto aus der Footprint-Größe abgeleitet hat; (2) die
Wolkenklassen verfünffachen Anfragen und Zeilen für einen Filter, den die
Oberfläche nicht hat — kommt er, lässt sich die Klasse nachrüsten, weil jeder
Monat ohnehin ganz neu gezählt werden kann; (3) die Weltansicht auf z9 liegt
bei 1,6 bis 2,4 MB und erzwänge Vektorkacheln.

**Darstellung.** Weltansicht aus dem Würfel zunächst höchstens **z7**
(rund 300 kB, unter der Schwelle); z8 erst mit Kompression oder Vektorkacheln
(§9 F3).

## 8. Folgen, falls angenommen

- `plans/m2-05-coverage.md` F3 ist aufgehoben; `adr/0004` §5 bekommt einen
  Nachtrag „Würfel für den Weltüberblick", mit Verweis hierher.
- Eine Bauaufgabe der Stufe B, frühestens mit dem `harvester` aus M3-11 (P4)
  oder danach; laut Plan ist der Bau nicht Teil von M3 (P13).
- `CoverageInfo` bekommt ein Feld; die Onboarding-Checkliste Punkt 2 prüft bei
  gesetztem Feld zusätzlich, dass der Würfel je Monat Regel V besteht.
- Die Antwort der Route bekommt „Stand der Zählung"; das Frontend zeigt ihn in
  der Legende.
- Die Last auf Earth Search steigt um rund 1 700 Anfragen einmalig und
  15–35 Anfragen am Tag, sinkt aber für jeden Weltüberblick ohne AOI auf null.

## 9. Fragen an Otto

1. **F1 — Welche Würfelform?**
   (a) *Empfehlung:* **z8 × Monat, ohne Wolkenklasse**, nur für Anfragen ohne
   AOI (Option D). (b) z9 × Monat × 5 Wolkenklassen wie in D26 (Option C).
   (c) kein Würfel, nur Option B.
2. **F2 — Zeiträume, die keine ganzen Monate sind.**
   (a) *Empfehlung:* Live-Weg wie heute. (b) Auf ganze Monate runden und in
   der Legende ausweisen. (c) Würfel tageweise führen (rund fünfmal mehr
   Zeilen, unbelegt).
3. **F3 — Feinste Weltstufe aus dem Würfel.**
   (a) *Empfehlung:* **z7** (rund 300 kB), z8 erst mit Kompression.
   (b) z8 sofort, dazu `GZipMiddleware` in `api` (116 kB gzip, §3.8) und die
   Schwelle aus `adr/0004` §5 auf komprimierte Größe umstellen.
   (c) z8 als Vektorkacheln über `ST_AsMVT` in `api`.
4. **F4 — Anstoß der Aktualisierung.**
   (a) *Empfehlung:* Schleife im `harvester` mit Advisory Lock. (b) Kommando
   für einen äußeren Zeitplaner. (c) Erst mit dem Queue-ADR in M4 klären.
5. **F5 — EOPF (Quelle ohne Gesamtzahl).**
   (a) *Empfehlung:* **kein Würfel**, `sample` bleibt; das Fenster ist klein,
   der Datensatz „staging". (b) Täglich vollständig aufzählen (≈ 90 Seiten)
   und eine lückenlose Aufzählung als `complete` werten — das ändert
   Regel V, die heute ohne Gesamtzahl nie `complete` erlaubt.
6. **F6 — Option B vorziehen?**
   (a) *Empfehlung:* ja, als kleine Aufgabe der Stufe A in M3.
   (b) nein, zusammen mit dem Würfel.

## 10. Was offen blieb

1. **Der verlorene Datensatz im Juni 2020** (§3.3) ist nicht aufgeklärt. Vor dem
   Bau prüfen, ob er an der Datumsgrenze oder an einem fehlenden
   `proj:centroid` liegt; das entscheidet, ob die Zerlegung eine Randregel
   braucht.
2. **Zeilenzahl über alle Monate** ist aus einem gemessenen Monat hochgerechnet,
   nicht über den Katalog gezählt (§3.3, §12.3).
3. **Weltansicht über alle Monate** ist aus der Zellmenge eines Monats gebaut;
   die echte Zahl liegt höher (§3.8).
4. **Composite-Aggregation**: ob `stac-server` sie aufnehmen würde, ist
   nicht erfragt (§4).
5. **H3 aus PGDG** und **stac-geoparquet von Planetary Computer**: aus der
   Sitzung gesperrt, nur aus Quellen (§3.11).
6. **Ratengrenzen**: auch 476 Anfragen blieben ohne Drosselung; eine
   Obergrenze ist weiterhin nicht bekannt (`adr/0004` §8.1).
7. **Geld**: wie in `adr/0004` §8.6 nicht bezifferbar; der Würfel verlagert
   Kosten von vielen Nutzeranfragen auf einen täglichen Lauf.

## 11. Quellen

**Gemessen [M]**, 23.09.2026: `earth-search.aws.element84.com/v1`
(`/collections/sentinel-2-c1-l2a/aggregations`, `/aggregate` mit
`total_count`, `datetime_frequency`, `cloud_cover_frequency`,
`grid_code_frequency`, `grid_geotile_frequency`, `query` auf `eo:cloud_cover`,
`created`, `updated`; `/search` mit `fields`) · `stac.core.eopf.eodc.eu`
(`/`, `/collections/sentinel-2-l2a-zarr3`, `/search`) · Postgres 16.13 /
PostGIS 3.4.2 · Code: `frontend/src/store.ts`, `frontend/src/api.ts`,
`backend/earthx/catalog/registry.py`, `backend/earthx/catalog/datasets.py`,
`backend/earthx/api/`.

**Primärdokument [P]:**
- `stac-server`, `src/lib/database.ts` auf `main`:
  https://github.com/stac-utils/stac-server
- STAC Aggregation Extension: https://github.com/stac-api-extensions/aggregation
- OpenSearch Composite-Aggregation:
  https://docs.opensearch.org/latest/aggregations/bucket/composite/
- Earth Search README: https://github.com/Element84/earth-search
- PMTiles: https://github.com/protomaps/PMTiles

**Suchtreffer [S]:**
- stac-geoparquet: https://github.com/stac-utils/stac-geoparquet ·
  https://github.com/radiantearth/stac-geoparquet-spec
- Planetary Computer, geoparquet-Exporte:
  https://planetarycomputer.microsoft.com/docs/quickstarts/stac-geoparquet/ ·
  https://github.com/microsoft/PlanetaryComputer/discussions/238
- DuckDB `httpfs` und `spatial`:
  https://duckdb.org/docs/current/core_extensions/httpfs/https ·
  https://duckdb.org/docs/lts/core_extensions/spatial/overview
- `h3-pg`: https://github.com/postgis/h3-pg
- Elasticsearch `geotile_grid`:
  https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-geotilegrid-aggregation
- pg_tileserv: https://github.com/CrunchyData/pg_tileserv · Martin:
  https://maplibre.org/martin/
- `pg_ivm`: https://github.com/sraoss/pg_ivm · TimescaleDB-Lizenzen:
  https://github.com/timescale/timescaledb/blob/main/LICENSE
- Sentinel Hub Statistical API:
  https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Statistical.html
- NASA CMR Search API: https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html

---

## 12. Messanhang

Alles lief in der Sitzung; nichts davon gehört ins Repo. Die Wegwerf-Tabellen
wurden nach der Messung verworfen.

### 12.1 Zerlegung eines Monats (§3.3)

```python
def tile_bbox(z, x, y):                     # Geotile -> lon/lat
    n = 2**z
    lat = lambda t: math.degrees(math.atan(math.sinh(math.pi * (1 - 2*t/n))))
    return (x/n*360 - 180, lat(y + 1), (x + 1)/n*360 - 180, lat(y))

# 1. Anfrage: total_count + grid_geotile_frequency auf Stufe pz (3 bzw. 2)
# je Kachel (pz, x, y) mit Daten: grid_geotile_frequency auf Stufe z (9 bzw. 8),
#   bbox = tile_bbox(pz, x, y), gleiche datetime/query
#   behalten nur Zellen mit (cx >> (z-pz), cy >> (z-pz)) == (x, y)
# Probe: sum(behaltene Zählwerte) == total_count der 1. Anfrage
```

Parameter je Anfrage: `collections=sentinel-2-c1-l2a`, `datetime=<Monat>`,
`aggregations=…`, `grid_geotile_frequency_precision=<z>`, `bbox=…`,
bei Klassen `query={"eo:cloud_cover":{"gte":a,"lt":b}}`.

### 12.2 Geänderte Monate (§3.4)

```
GET /v1/aggregate?collections=sentinel-2-c1-l2a
    &aggregations=total_count,datetime_frequency
    &query={"updated":{"gte":"<letzter Lauf>"}}
```

### 12.3 Synthetischer Würfel (§3.6, §3.7)

Zeilen je Monat `min(items, 150000 · items/459298 · 1,3, 150000)` aus dem
Monatshistogramm, auf fünf Klassen verteilt im Verhältnis vom Juni 2025;
Zellen je Monat und Klasse zufällig aus der echten z9-Zellmenge vom Juni 2025.

```sql
CREATE TABLE cube (
  dataset smallint NOT NULL, month date NOT NULL, cc smallint NOT NULL,
  x smallint NOT NULL, y smallint NOT NULL, n integer NOT NULL,
  PRIMARY KEY (dataset, month, cc, x, y));
INSERT INTO cube
SELECT 1, p.month, p.cc, s.x, s.y, 1 + floor(random() * s.w / 3)::int
FROM plan p CROSS JOIN LATERAL
     (SELECT x, y, w FROM mask ORDER BY random() + p.k*0 LIMIT p.k) s;
CREATE INDEX cube_xy ON cube (dataset, x, y, month, cc) INCLUDE (n);
CREATE TABLE cube_z5 AS
SELECT dataset, month, cc, (x>>4)::smallint x, (y>>4)::smallint y, sum(n)::int n
FROM cube GROUP BY 1,2,3,4,5;

-- Beispiele: Welt auf Stufe z (Verschiebung 9-z), Europa auf z9
SELECT x>>1, y>>1, sum(n) FROM cube WHERE dataset=1 GROUP BY 1,2;          -- Welt z8
SELECT x, y, sum(n) FROM cube
WHERE dataset=1 AND x BETWEEN 241 AND 298 AND y BETWEEN 148 AND 202
  AND month BETWEEN '2024-01-01' AND '2024-12-01' AND cc <= 1 GROUP BY 1,2;
-- Monat ersetzen: DELETE … WHERE month = '2025-06-01'; INSERT …; in einer Transaktion
```

Gemessen wurde die `Execution Time` aus `EXPLAIN (ANALYZE, TIMING OFF)`, drei
Läufe, Median.
