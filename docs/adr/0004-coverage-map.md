# ADR 0004 — Technische Umsetzung der Coverage Map

- **Status:** Angenommen. Von Otto am 19.09.2026 entschieden; die fünf Fragen
  aus §7 sind dort beantwortet.
- **Datum:** 2026-09-19
- **Aufgabe:** M1-09 laut `docs/plans/m1-fundament.md` §4.
- **Autonomiestufe:** C — nur recherchiert, gemessen und berichtet. Kein
  Produktivcode geändert, keine Daten heruntergeladen, keine Datei außerhalb von
  `docs/` angefasst.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §2 (Coverage Map), §5;
  `KLAERUNGEN.md` B8, B12; `architekturplan.md` 5.1, 5.2, 5.3, 6.1, 15.3;
  `projektuebersicht.md` Prinzip 10;
  `docs/prototyp-inventar.md` F12, N3; `adr/0001` §9.1, §9.3; `adr/0003`;
  Entscheidungslog-Zeile „Technische Umsetzung der Coverage Map".
- **Betroffen:** `architekturplan.md` 5.2, **6.1**, 6.3; `projektuebersicht.md` §5
  (Onboarding-Checkliste); Entscheidungslog; Planung M2.

---

## Methode und Belegstufen

Gearbeitet wurde in einer Cloud-Sitzung vom 19.09.2026.
**`earth-search.aws.element84.com` war erreichbar.** Das ist keine Neuigkeit:
`adr/0003` §10.1 führt den Host seit dem 18.09.2026 als erreichbar (HTTP 200),
nachdem Otto Egress freigegeben hatte — nur der ursprüngliche Teil von
`adr/0003` beschreibt noch den Stand davor. Neu ist allein, dass hier zum
ersten Mal die **Aggregations-Endpunkte** abgefragt wurden. Die Zahlen in §3
sind echte Messungen gegen die reale Quelle, keine Schätzungen.

Jede Aussage trägt eine Belegstufe:

- **M** — in dieser Sitzung selbst gemessen; der Befehl steht im Text.
- **P** — am Primärdokument gelesen (Spezifikation, Quelltext der Bibliothek).
- **S** — Suchtreffer mit Link, Primärdokument nicht gelesen.
- **A** — eigene Ableitung aus M/P/S; als Argument gekennzeichnet, nicht als Beleg.

Wo ein Beleg fehlt, steht „unbelegt" statt einer Zahl. §8 listet, was offen blieb.

**Nur Metadaten.** Alle Abrufe waren STAC-Metadaten-Anfragen (`/`,
`/aggregations`, `/aggregate`, `/search` mit `limit=1`). Es wurden keine Pixel
gelesen und keine Dateien geladen. Der Umfang lag bei rund 40 Anfragen über
etwa 20 Minuten — bewusst vorsichtig, wie in `m1-fundament.md` §6 für Spikes
gefordert.

---

## 1. Kontext und Problem

`ENTSCHEIDUNGEN` §2 legt fest, **was** die Coverage Map zeigt: eine Heatmap der
Abdeckungsdichte (Anzahl Aufnahmen pro Rasterzelle, logarithmische Farbskala mit
Legende), ergänzt um Footprints ab einer Zoomstufe oder bei wenigen Aufnahmen,
um die bloße Ausdehnung bei Einmal-Produkten und um ein Zeit-Histogramm. Sie
reagiert auf **Filter** (Zeitraum, Suchkriterien), nicht nur auf den Datensatz.
Offen ist, **wie** das technisch entsteht.

Der Prototyp (`prototyp-inventar.md` F12) löst das so: Ein Skript holt bis zu
5000 Footprints, rastert sie in ein 1°-Lon/Lat-Gitter, zählt pro Zelle die
**überlappenden** Aufnahmen und schreibt eine GeoJSON-Datei je Collection; das
Frontend zeichnet daraus einen `fill`-Layer, der linear über `count` von Blau
nach Rot interpoliert. Drei Eigenschaften daran tragen nicht weiter:

1. Es ist eine **Stichprobe**, die in der Oberfläche nicht als solche
   ausgewiesen ist (F12, N3).
2. Es ist **nicht filterabhängig** — die Datei gilt pro Collection, nicht pro
   Anfrage.
3. Es ist eine **vorab erzeugte Datei auf der Platte**, also genau der Zustand,
   den `adr/0001` aus den Diensten herausziehen will.

Die eigentliche Schwierigkeit ist der zweistufige Katalog aus
`architekturplan.md` 5.2: **Collections liegen im eigenen pgstac, Items dagegen
in der Regel nicht.** Für Sentinel-2 L2A (`adr/0003`) sind die Items föderiert
und liegen bei Earth Search. Eine Heatmap über „alle Footprints" muss also über
Daten aggregieren, die wir gar nicht haben — und das filterabhängig, also ohne
die Möglichkeit, das Ergebnis einfach einmal vorzuberechnen.

## 2. Kriterien

> **Zu den Kürzeln E1–E8.** Sie stehen in `docs/plans/m1-fundament.md` §1 und
> sind seit **M1-00 entschieden** — Otto hat E1 bis E8 am 19.09.2026 wie
> empfohlen bestätigt, jede mit einer eigenen Zeile im Entscheidungslog. Dieses
> ADR benutzt zwei davon, beide also festen Stands: **E4** (Anwendungs-Cache in
> Postgres) und **E5** (ein fehlgeschlagener Zwischenspeicher macht nur
> langsamer, nie 404).

| # | Kriterium | Herkunft |
|---|---|---|
| K1 | Reagiert auf Filter (Zeitraum, Wolken, weitere Suchkriterien) | `ENTSCHEIDUNGEN` §2 |
| K2 | Vollständigkeit ist entweder gegeben oder **sichtbar ausgewiesen** | `ENTSCHEIDUNGEN` §2; F12/N3 |
| K3 | Funktioniert für föderierte **und** für eigene Items, mit demselben Ergebnisformat | `architekturplan.md` 5.2 |
| K4 | Dienste bleiben zustandslos; ein leerer Zwischenspeicher macht nur langsamer, nie 404 | `adr/0001` §8, §9.3; E5 (fest seit M1-00) |
| K5 | Alles Ausgehende über `gateway`, konservative Last auf der Quelle | `KLAERUNGEN` B8; `m1-fundament.md` §6 |
| K6 | Interaktiv bedienbar: gefilterte Coverage-Antwort **unter 1 s, typisch unter 0,5 s** | Ottos Setzung vom 19.09.2026 (§7 Frage 4); in `docs/` stand zuvor kein Latenzziel |
| K7 | Läuft auf dem Stack, den die Cloud-Umgebung und CI hergeben — ohne eigenes Image nur für eine Extension | `docs/cloud-umgebung.md`; `adr/0002` §1 |
| K8 | Kosten wachsen nicht linear mit der Katalogsgröße; grobe Kostenabschätzung pro Request | `projektuebersicht.md` Prinzip 10 (Kostenbewusstsein) |

## 3. Was gemessen wurde

### 3.1 Earth Search kann filterabhängig aggregieren — **[M]**

Die Landing Page von Earth Search v1 weist die Konformitätsklasse
`https://api.stacspec.org/v0.3.0/aggregation` aus und verlinkt `aggregate` und
`aggregations`. Das war in der Vorrecherche unbelegt geblieben; hier ist es am
Dienst selbst geprüft:

```
curl -s https://earth-search.aws.element84.com/v1 | jq -r '.conformsTo[]'
  ... https://api.stacspec.org/v0.3.0/aggregation
```

**Zu den `total_count`-Werten unten:** Sie schwanken zwischen den Messungen um
einige Dutzend (30 356 426 bis 30 356 454). Das ist kein Messfehler, sondern der
laufende Zugang neuer Szenen während der rund 20 Minuten Messdauer. Für die
Vollständigkeitsprobe in §5 ist das unschädlich, weil dort `total_count` und
Zellsumme aus **derselben** Antwort stammen.

Für `sentinel-2-c1-l2a` bietet der Dienst elf Aggregationen an — darunter
`total_count`, `datetime_frequency`, `cloud_cover_frequency` und die drei
Gitter-Aggregationen `grid_geohash_frequency`, `grid_geohex_frequency`,
`grid_geotile_frequency`.

**Wichtig für die Umsetzung:** `/aggregate` antwortet nur auf **GET**. Ein POST
mit demselben Rumpf liefert `404 NotFound` **[M]**. Das ist eine harte Vorgabe
für das Gateway (M1-03) und für die AOI-Übergabe (§3.4).

### 3.2 Latenz und Antwortgröße — **[M]**

Alle Werte sind `curl`-Gesamtzeiten aus dieser Sitzung, Median aus mehreren
Läufen wo angegeben. Die Collection enthielt beim Abruf **30 356 426 Items**
(`total_count`, ganze Collection, ohne Filter).

| Anfrage | Zellen | Zeit | Nutzlast |
|---|---|---|---|
| ganze Collection, `total_count` + `datetime_frequency` (monatlich) | 133 Monate | 0,50 s | 10 kB |
| ganze Collection, `grid_geotile_frequency` z3 | 64 | 0,79 s | 3,9 kB |
| ganze Collection, `grid_geotile_frequency` z5 (5 Läufe) | 821 | 0,66–1,09 s | 46 kB |
| ganze Collection, `grid_geohash_frequency` p2 | 776 | 0,98 s | 40 kB |
| ganze Collection, `grid_geohex_frequency` p2 | 3729 | 1,59 s | 239 kB |
| **gefiltert** (bbox Mitteleuropa, Jahr 2024, `eo:cloud_cover < 20`): `total_count` + Gitter p3 + Histogramm (5 Läufe) | 81 + 12 | **0,28–0,56 s** | 5,4 kB |
| dieselbe Filterung, `grid_geohash_frequency` p5 | 536 | 0,63 s | 28 kB |
| dieselbe Filterung, `grid_geotile_frequency` z8 | 117 | 0,32 s | 6,7 kB |

Der gefilterte Fall — der häufige — liegt bei **0,28 bis 0,63 s und 5 bis 28 kB**,
je nach verlangter Gitterfeinheit. Das erfüllt K6 mit Abstand und macht Vektorkacheln für
diesen Zweck vorerst entbehrlich (§4, Option 4).

Ratengrenzen ließen sich nicht ermitteln: Der Dienst liefert weder
`X-RateLimit-*` noch `Retry-After`, und keine der rund 40 Anfragen wurde
gedrosselt **[M]**. Die offene Log-Zeile „Ratengrenzen der Anbieter" bleibt also
offen. Er antwortet hinter CloudFront, setzt aber **kein `Cache-Control`**;
drei identische Anfragen ergaben dreimal `x-cache: Miss from cloudfront` **[M]**.
Ein Zwischenspeicher auf unserer Seite ist damit der einzige, der wirkt.

### 3.3 Zwei Fallen in der Upstream-Aggregation — **[M]**

**Falle 1: Die Zellenzahl ist bei 10 000 hart gekappt, und `overflow` lügt.**

| Anfrage | Zellen | Summe der Zählwerte | `total_count` | gemeldetes `overflow` |
|---|---|---|---|---|
| gefiltert, Geohash p3 | 81 | 3848 | 3848 | 0 |
| gefiltert, Geohex p6 | 484 | 3848 | 3848 | 0 |
| **ganze Collection, Geohash p4** | **10 000** | **7 789 162** | **30 356 452** | **0** |
| **ganze Collection, Geohash p5** | **10 000** | **5 114 041** | **30 356 454** | **0** |

In den beiden unteren Zeilen fehlen drei Viertel bzw. fünf Sechstel aller
Aufnahmen, und der Dienst meldet trotzdem `overflow: 0`. Ein
`grid_geohash_frequency_size=50000` änderte nichts — der Parameter wird
ignoriert, das Ergebnis bleibt bei exakt 10 000 Zellen **[M]**. Eine Oberfläche,
die das ungeprüft zeichnet, zeigt eine **stillschweigend abgeschnittene Karte**
und nennt sie vollständig. Genau der Fehler, den K2 verbietet.

Daraus folgt eine prüfbare Regel, die zugleich K2 erfüllt (§5, Regel V):
`sum(buckets) == total_count` ist die **Vollständigkeitsprobe**. Sie kostet
nichts, weil `total_count` in derselben Antwort mitgeliefert wird.

**Falle 2: Eine Aufnahme zählt in genau eine Zelle.** In allen ungekappten
Messungen ist die Summe der Zählwerte exakt gleich `total_count` — auch bei
Geohash p12, wo die Zellen zentimetergroß sind und 3848 Aufnahmen auf 2568
Zellen fallen **[M]**. Der Dienst bint also über einen einzelnen
repräsentativen Punkt je Item (Zentroid), nicht über die Fläche des Footprints.
Die Referenzimplementierung der Extension kennt beide Varianten
(`centroid_*_grid_frequency` und `geometry_*_grid_frequency`) **[S]**; Earth
Search bietet nur die kurzen Namen an und verhält sich zentroidbasiert **[M]**.

Das ist ein **semantischer Unterschied zum Prototyp**, der jede überlappende
Aufnahme in jeder berührten Zelle zählt. Beide Zahlen sind vertretbar, aber es
muss eine sein, sonst zeigen eigener und föderierter Pfad Verschiedenes (K3).

### 3.4 Die AOI muss in die URL passen — **[M]**

Weil `/aggregate` nur GET annimmt, geht ein Polygon als `intersects`-Parameter
in die Abfragezeichenfolge. Gemessene Grenze:

| Stützpunkte | URL-Länge | Antwort |
|---|---|---|
| 100 | 2,7 kB | 200 |
| 200 | 5,4 kB | 200 |
| 300 | 8,1 kB | **414 URI Too Long** |
| 500 | 13,5 kB | **414 URI Too Long** |

Die Grenze liegt zwischen 5,4 und 8,1 kB, also beim üblichen 8-kB-Limit. Für
die Coverage Map über eine vom Nutzer hochgeladene AOI heißt das: **vereinfachen
oder auf die Bounding-Box zurückfallen**, und in beiden Fällen kennzeichnen.

### 3.5 pgstac kann es nicht — **[P]**

Für den eigenen Katalog gibt es die Gegenprobe nicht als fertiges Feature:

- `stac_fastapi/pgstac/extensions/__init__.py` auf `main` exportiert
  `QueryExtension`, `FiltersClient`, `FreeTextExtension` — **keine Aggregation**
  **[P]** (`raw.githubusercontent.com/stac-utils/stac-fastapi-pgstac/main/...`).
- `src/pgstac/sql/004_search.sql` (28 kB, 567 Zeilen) enthält **keinen einzigen
  Treffer** für `aggregat`, `geohash`, `geohex` oder `geotile` **[P]**.
- Der Feature-Request `stac-utils/pgstac#257` „Aggregation Extension" ist seit
  dem 17.04.2024 offen und kommentarlos; der Antragsteller selbst zweifelt dort
  an der Eignung von PostgreSQL für diese Aufgabe **[S]**.

Für Items im eigenen pgstac ist die Aggregation also **selbst zu bauen**. Ob
PostgreSQL das trägt, war damit die zweite Messfrage.

### 3.6 PostGIS trägt es — **[M]**

Messaufbau in dieser Sitzung: Postgres 16.13 mit PostGIS 3.4.2, **2 000 000
synthetische Footprints** (1°-Kacheln, Zeitraum 2015–2026, Wolkenanteil
gleichverteilt; rein synthetisch, keine echten Szenen — `ENTSCHEIDUNGEN` §4),
GiST-Index auf der Geometrie, B-Tree auf `datetime` und `cloud_cover`.
Tabellengröße 468 MB. Zahlen sind `EXPLAIN ANALYZE`-Ausführungszeiten.
**Erzeugung und Abfragen stehen vollständig in §10**, damit die Zahlen
nachvollziehbar sind und nicht geglaubt werden müssen.

| Verfahren | Umfang | Zeit |
|---|---|---|
| A1 `ST_SquareGrid` 1°, **Footprint-Überlappung** | ganze Welt, ungefiltert | **7 817 ms** |
| A2 dasselbe | gefiltert (Europa, 2024, Wolken < 20) | **218 ms** |
| B1 Zentroid-Binning per `floor()` | ganze Welt, ungefiltert | **1 986 ms** |
| B2 dasselbe | gefiltert | **37 ms** |
| C Zeit-Histogramm `date_trunc('month', …)` | gefiltert, 132 Monate | **55 ms** |
| D1 Abfrage gegen materialisierte Sicht (Zelle × Monat × Wolkenklasse) | gefiltert | **6 ms** |
| D2 dieselbe Sicht | ganze Welt, ungefiltert | **154 ms** |
| D3 `REFRESH MATERIALIZED VIEW` | 2 Mio. Items → 1,94 Mio. Zeilen, 124 MB | **6 246 ms** |
| E `ST_AsMVT` über die Weltzellen | 50 901 Zellen | **614 ms** |

Drei Dinge fallen auf:

1. **Der gefilterte Fall ist billig** (37–218 ms), weil die Indizes greifen. Das
   ist der Fall, den K1 fordert und den der Nutzer sieht.
2. **Der teure Fall ist der ungefilterte Weltüberblick** (2,0–7,8 s) — und
   genau der hat keine Filter und ist deshalb **vorberechenbar**. Die
   materialisierte Sicht drückt ihn auf 154 ms und ist in 6,2 s neu gebaut.
3. **Die Footprint-Überlappung kostet ein Mehrfaches** des Zentroid-Binnings:
   Faktor 3,9 ungefiltert (A1 gegen B1), Faktor 5,9 gefiltert (A2 gegen B2),
   weil jedes Item mit mehreren Zellen verknüpft wird. Das ist der Preis der Semantik aus §3.3, Falle 2.

Der Messaufbau ist mit 2 Mio. Items rund fünfzehnmal kleiner als die 30,4 Mio.
Items von Sentinel-2 L2A. Er beweist **nicht**, dass der eigene pgstac einen
Katalog dieser Größe ungefiltert in Echtzeit aggregiert — er zeigt, dass der
gefilterte Fall auch bei einem Vielfachen davon im Rahmen bleibt, weil die Kosten
an der Trefferzahl hängen und nicht an der Katalogsgröße **[A]**.

### 3.7 Gitterwahl: was der Stack hergibt — **[P]/[M]/[S]**

| Gitter | global | in Postgres verfügbar | in Earth Search |
|---|---|---|---|
| Lon/Lat-Gitter | nein, polverzerrt | nativ per SQL | nein |
| `ST_SquareGrid` / `ST_HexagonGrid` | nein, planare Kachelung | PostGIS-Kern ab 3.1 **[S]**, hier 3.4.2 **[M]** | nein |
| Geohash | ja, ungleiche Zellen | `ST_GeomFromGeoHash` u. a. im Kern **[S]** | `grid_geohash_frequency` **[M]** |
| Geotile (XYZ z/x/y) | ja, Web-Mercator | über `ST_TileEnvelope` nachbaubar **[A]** | `grid_geotile_frequency` **[M]** |
| H3 | ja, hexagonal | **`h3-pg` ist im Ubuntu-Archiv dieser Umgebung nicht verfügbar** **[M]**; Apache-2.0, gepflegt, Binärpakete beim Projekt **[P]** | `grid_geohex_frequency` **[M]** |
| S2 | ja | keine reife Extension gefunden **[S]** | nein |

`h3-pg` wäre fachlich das sauberste Gitter (flächengleich, keine Polverzerrung),
scheitert hier aber an K7: In der geprüften Umgebung liefert
`pg_available_extensions` nach Installation von `postgresql-16-postgis-3` genau
zehn `postgis*`-Einträge und **keinen `h3`** **[M]**. H3 hieße ein eigenes
Postgres-Image bauen — für M2 unverhältnismäßig.

**Geotile** ist das einzige Gitter, das auf beiden Seiten verfügbar ist, dessen
Präzision direkt die Zoomstufe der Karte ist und dessen Zellen sich in PostGIS
mit `ST_TileEnvelope` ohne Extension erzeugen lassen. Das macht die Wahl **[A]**.

## 4. Optionen

**Option 1 — Aggregation pro Anfrage, oben wie unten.**
Föderierte Items: `/aggregate` am Upstream. Eigene Items: SQL in PostGIS. Ein
gemeinsames Ergebnisformat, kein vorberechneter Zustand.
*Dafür:* erfüllt K1 und K3 unmittelbar; K4 trivial, weil es keinen Zustand gibt;
gemessen schnell genug für den gefilterten Fall (0,28–0,56 s föderiert, 37–218 ms
lokal). *Dagegen:* der ungefilterte Weltüberblick kostet oben die Kappung bei
10 000 Zellen und unten 2,0–7,8 s.

**Option 2 — Vorberechnete Zeitscheiben (materialisierte Sicht).**
Zelle × Zeitscheibe × grob gestufte Filterdimension wird materialisiert, die
Anfrage summiert darüber.
*Dafür:* 6 ms gefiltert, 154 ms für die Welt; Neuaufbau in 6,2 s.
*Dagegen:* trägt nur Filter, die vorher bekannt und grob gestuft sind — bei einer
freien CQL2-Suche bricht es weg; für **föderierte** Items setzt es Harvesting
voraus (Option 5); PostgreSQL-Sichten sind nicht inkrementell, `REFRESH` baut
komplett neu **[S]**.

**Option 3 — Nur vorberechnen, nicht filtern (Status quo).**
*Dafür:* billig. *Dagegen:* verletzt K1 direkt. Ausgeschieden.

**Option 4 — Vektorkacheln (`ST_AsMVT`, pg_tileserv/Martin/TiPg).**
*Dafür:* skaliert auf beliebig viele Zellen; Martin reicht Query-Parameter an
die SQL-Funktion durch, filterabhängige Kacheln sind vorgesehen **[S]**.
*Dagegen:* jede Filterkombination erzeugt einen eigenen Kachelsatz — der Cache
vervielfacht sich mit den Filtern, und keine Quelle belegt, wie große Kataloge
das eindämmen **[S]**. Vor allem: Die gemessenen Nutzlasten sind **5–46 kB**
(§3.2) bzw. 50 901 Zellen in 614 ms (§3.6 E). Dafür braucht es keinen
Kachelserver **[A]**. Ein zusätzlicher Prozess widerspräche außerdem der
Vier-Prozess-Topologie aus M1-08.

**Option 5 — Footprints föderierter Items in den eigenen pgstac ernten.**
*Dafür:* ein einziger Aggregationspfad, volle Filterfreiheit, Option 2 anwendbar.
*Dagegen:* 30 Mio. Items für **einen** Datensatz (§3.2); das ist genau die
Synchronisation, die `architekturplan.md` 5.2 für Items ausdrücklich vermeidet
(„Frische, keine Synchronisation, keine Speicherkosten"). Für einen Katalog mit
vielen Datensätzen skaliert es nicht (K8).

**Option 6 — Live-Stichprobe mit Ausweisung (Prototyp-Weg, ehrlich gemacht).**
Footprints ziehen, selbst rastern, „Stichprobe (n von N)" anzeigen.
*Dafür:* funktioniert gegen jede Quelle, auch ohne Aggregation-Extension.
*Dagegen:* teuer (der Prototyp braucht ~20 s für 1500 Footprints, F12) und
liefert grundsätzlich weniger, als Option 1 gemessen in 0,3 s vollständig
liefert. Als **Rückfallebene** für Quellen ohne Aggregation bleibt sie nötig.

## 5. Empfehlung

**Ein Anbieter-Begriff, drei Umsetzungen, eine gemeinsame Antwort.**

Im Modul `catalog` entsteht eine schmale Nahtstelle — nennen wir sie den
*Coverage-Anbieter* — mit einer Frage („Dichte für Datensatz X unter Filter F,
auf Gitterstufe z") und einer Antwort. Welcher Weg sie beantwortet, entscheidet
der Registry-Eintrag des Datensatzes, nicht der Aufrufer. Das ist dieselbe
Trennung, die `architekturplan.md` 5.2 für die Item-Suche zieht, und sie hält den
Unterschied zwischen eigenem und föderiertem Katalog aus der Oberfläche heraus
(K3).

**Wo welcher Teil liegt.** Die Nahtstelle und das SQL gehören nach `catalog`
(„STAC-Modell, pgstac, Suche", 3.1). Das Wissen darüber, *wie* eine konkrete
Quelle aggregiert — dass Earth Search `/aggregate` nur per GET annimmt, wie die
Parameter heißen, wo gekappt wird —, gehört nach `adapters` („Protokolle der
Quellen"). Sonst wandert quellenspezifisches Protokollwissen nach `catalog` und
verschiebt die Modulgrenze inhaltlich, auch wenn der Import erlaubt bliebe.
Praktisch heißt das: **Aggregation wird eine vierte, optionale
Adapter-Fähigkeit** neben Discovery, Suche und Zugriffsauflösung. Otto hat das
am 19.09.2026 angenommen; `architekturplan.md` 6.1 ist entsprechend gefasst —
die Liste der Fähigkeiten ist nicht mehr abschließend, und die Rückfallebene für
Quellen ohne Aggregation ist die ausgewiesene Stichprobe (Option 6).

| Fall | Weg |
|---|---|
| Quelle mit Aggregation-Extension (Sentinel-2 L2A über Earth Search) | **Option 1 oben:** `GET /aggregate` über `gateway` |
| Items im eigenen pgstac | **Option 1 unten:** SQL in PostGIS |
| Quelle ohne Aggregation-Extension | **Option 6:** Stichprobe, immer als solche ausgewiesen |

Dazu **Option 2 nur für den einen ungefilterten Weltüberblick** — die Ansicht
ohne jeden Filter, die jeder Nutzer als erstes sieht und die nach §3.6 mit 2,0
bis 7,8 s die einzige wirklich teure ist. Sie hat definitionsgemäß keine Filter
und ist damit gefahrlos vorberechenbar. Fällt die Vorberechnung aus, antwortet
Option 1 langsamer statt gar nicht — das ist Regel E5 (`m1-fundament.md` §1,
fest seit M1-00) und `adr/0001` §9.3 (K4), und sie gehört als Test hinterlegt.

**Gitter: Geotile.** Als einziges Gitter auf beiden Seiten verfügbar, seine
Präzision *ist* die Zoomstufe der Karte, und in PostGIS ohne Extension
nachbaubar (§3.7). H3 wäre fachlich besser, scheitert an K7. Die gewählte
Stufe leitet sich aus dem sichtbaren Kartenausschnitt ab, gedeckelt so, dass die
erwartete Zellenzahl deutlich unter der Kappungsgrenze aus §3.3 bleibt.

Dazu kommt ein **zweiter Deckel je Datensatz**, den Otto am 19.09.2026
festgelegt hat: Die feinste zulässige Gitterstufe ergibt sich aus der typischen
Footprint-Größe des Datensatzes, die dafür als Feld im Registry-Eintrag steht
(M1-04). Für Sentinel-2 L2A ist das **höchstens Geotile z8**. Grund ist die
Zählweise: Wird die Zelle kleiner als ein Footprint, zählt die Zentroid-Regel
eine Szene weiterhin in genau eine Zelle, und die Karte zeigt ein Punktmuster
statt einer Abdeckung (§3.3). Unterhalb des Deckels greift stattdessen der
Umschaltpunkt auf Footprints.

**Zählweise: eine Aufnahme, eine Zelle (Zentroid).** Nicht, weil sie besser
wäre — die Überlappungszählung des Prototyps beschreibt „Abdeckung" ehrlicher —,
sondern weil der föderierte Weg nichts anderes kann (§3.3) und zwei verschiedene
Zahlen für denselben Begriff schlimmer sind als eine gröbere (K3). Die Legende
sagt es ausdrücklich: „Aufnahmen mit Mittelpunkt in der Zelle". Wo die Zelle
kleiner wird als ein Footprint, ist die Dichtekarte ohnehin das falsche Mittel —
dort greift der Umschaltpunkt.

**Regel V — Vollständigkeitsprobe.** Jede Antwort trägt ein Pflichtfeld mit
genau drei möglichen Werten, und der Wert wird geprüft, nicht behauptet:

| Wert | Bedingung | Anzeige |
|---|---|---|
| `vollstaendig` | `sum(Zellen) == total_count` | Legende ohne Zusatz |
| `gekappt` | `sum(Zellen) < total_count` (Kappung, §3.3) oder AOI vereinfacht (§3.4) | „zeigt N von M Aufnahmen" |
| `stichprobe` | Weg über Option 6 | „Stichprobe: n von N Aufnahmen" |

Damit ist K2 nicht eine Frage der Sorgfalt beim Programmieren, sondern eine
Zusicherung, die sich testen lässt — und die Falle aus §3.3 kann nicht
unbemerkt durchrutschen. `total_count` kostet nichts extra: Es kommt in
derselben Upstream-Antwort mit, und lokal ist es dieselbe `WHERE`-Klausel.

**Umschaltpunkt Dichte → Footprints: an der Trefferzahl, nicht am Zoom.**
`ENTSCHEIDUNGEN` §2 nennt „ab einer bestimmten Zoomstufe **oder** bei wenigen
Aufnahmen". Beides ist dieselbe Frage, und die Trefferzahl beantwortet sie
direkt: `numberMatched` steht in jeder STAC-Suchantwort und kostet mit `limit=1`
rund 0,6 s **[M]**. Für den Beispielausschnitt (bbox Mitteleuropa, Jahr 2024)
liefert `/search` **22 619** Aufnahmen; mit `eo:cloud_cover < 20` sind es
**3848** — und das ist exakt der `total_count`, den `/aggregate` unter
demselben Filter meldet (§3.3). Beide Endpunkte zählen also dasselbe, was die
Vollständigkeitsprobe zusätzlich absichert. Der Sprung von 22 619 auf 3848
zeigt zugleich, warum die Schwelle am Filter hängen muss und nicht am Zoom.
Unterhalb einer Schwelle — von Otto am 19.09.2026 auf **`numberMatched < 500`**
festgelegt — werden die echten Footprints gezeichnet, darüber die Dichte. Das ist filterabhängig und damit richtiger als
eine feste Zoomstufe: Ein enger Zeitraum lässt auch weit herausgezoomt nur
wenige Szenen übrig. Der Zoom bleibt als zusätzliche Bremse, damit bei weitem
Ausschnitt nicht doch 500 Polygone im Browser landen.

**Einmal-Produkte: aus dem Collection-`extent`.** Ein Datensatz mit einer
einzigen Abdeckung braucht keine Dichte, sondern seine Ausdehnung — die steht
spezifikationskonform in `extent.spatial.bbox` der Collection **[S]** und liegt
für jede Collection im eigenen pgstac. Welcher Fall vorliegt, sagt ein
Capability-Flag im Registry-Eintrag (B10: jeder Datensatz schaltet jede
Fähigkeit ausdrücklich frei), keine Heuristik.

**Zeit-Histogramm: derselbe Anbieter, derselbe Filter.** Föderiert über
`datetime_frequency` (0,50 s für 133 Monate, §3.2), lokal über `date_trunc`
(55 ms, §3.6). Weil es in derselben Anfrage mitkommt, kostet es faktisch nichts.

**Darstellung: `fill`-Layer, nicht `heatmap`.** Der MapLibre-`heatmap`-Typ ist
punktbasiert und mischt Intensität mit Radius und Zoom **[S]**; der Zählwert
einer Zelle wäre daraus nicht ablesbar, und die Legende, die
`ENTSCHEIDUNGEN` §2 fordert, hätte keinen definierten Bezug. Die geforderte
Heatmap-Wirkung entsteht als Choropleth über die Gitterzellen — so macht es der
Prototyp bereits (`coverage-heat` ist ein `fill`-Layer). Zwei Änderungen daran:
die Skala wird **logarithmisch** (`["interpolate", ["linear"], ["log10",
["get","n"]], …]`; `n ≥ 1`, also kein Definitionsproblem), und die Stützstellen
werden aus dem Maximum der Antwort abgeleitet statt auf eine Aufnahmedichte
geeicht, die es nur bei BIOMASS gab (F12).

**Keine Vektorkacheln in M2.** Nicht grundsätzlich, sondern weil die Messung sie
nicht rechtfertigt: 5–46 kB je Antwort (§3.2) und 50 901 Weltzellen in 614 ms
(§3.6 E). Die Entscheidung ist umkehrbar — die Nahtstelle des
Coverage-Anbieters liefert Zellen mit Zählwert, und ob die als GeoJSON oder als
MVT über die Leitung gehen, ist eine Frage der Darstellung, keine der
Architektur. Ausgelöst würde die Umkehr, wenn eine Antwort regelmäßig über etwa
500 kB geht — eine **eigene Setzung** ohne Beleg, hergeleitet aus dem
schlechtesten gemessenen Fall (520 kB, Geohash p3 über die ganze Welt, §3.2),
nicht aus einer Quelle. Siehe §7 Frage 2.

**Zwischenspeicher: Postgres, kurz, schlüsselbasiert.** Anwendungs-Cache laut
E4 (`m1-fundament.md` §1, fest seit M1-00), Schlüssel ist der normalisierte
Filter samt Gitterstufe. Die Fristen sind dieselben wie für die Item-Suche —
Otto hat sie am 19.09.2026 für die Coverage-Aggregation ausdrücklich aus
`adr/0005` F1 übernommen: **24 h**, wenn das Zeitfenster geschlossen ist, also
sein Ende mehr als **7 Tage** zurückliegt, und **5 min** am offenen Rand
(Zeitfenster offen oder bis „jetzt"). Damit gilt für Suche und Coverage
dieselbe Regel, was der Spike M1-05 ohnehin angestrebt hatte. Der Upstream setzt kein `Cache-Control` und CloudFront liefert
durchgehend `Miss` (§3.2); unser Zwischenspeicher ist also der einzige, der
überhaupt wirkt. Und er darf ausfallen, ohne dass etwas fehlschlägt (K4, Regel E5).

**Gateway.** Jeder `/aggregate`-Aufruf läuft über `gateway` (B8, K5). Zwei
Anforderungen fallen für M1-03 ab: Die Route muss **GET mit langer
Abfragezeichenfolge** können (§3.1), und sie braucht eine Obergrenze für die
URL-Länge, die den `414` vermeidet, bevor die Anfrage das Haus verlässt (§3.4).

## 6. Folgen

- **M2** baut die Coverage Map auf dieser Nahtstelle. Die Onboarding-Checkliste
  (B12) bekommt als Pflichtpunkt nicht „Coverage Map existiert", sondern
  „Coverage-Anbieter ist zugeordnet und die Vollständigkeitsprobe greift".
- **M1-03** (Fetch-Gateway) erhält zwei zusätzliche Anforderungen (§5, Gateway).
- **M1-05** (Spike föderierte Item-Suche) ist inzwischen als `adr/0005`
  angenommen. Die TTL-Frage ist dort mit F1 beantwortet, und die Coverage
  übernimmt dieselben Fristen (§5, Zwischenspeicher); die Latenzzahlen aus §3.2
  sind dort wiederverwendet.
- **M1-04**: Der Registry-Eintrag braucht ein Feld für den Coverage-Weg, ein
  Capability-Flag für Einmal-Produkte und die **typische Footprint-Größe**, aus
  der sich der Deckel der Gitterstufe ergibt (§5, Gitter). Die ersten beiden
  sind kein neues Konzept, sondern je ein Eintrag mehr in der ohnehin
  vorgesehenen Flag-Liste (B10).
- **`architekturplan.md` 6.1** führt Aggregation als vierte, optionale
  Adapter-Fähigkeit; die Liste dort ist nicht mehr abschließend und nennt die
  ausgewiesene Stichprobe als Rückfallebene.
- Die offene Log-Zeile „Technische Umsetzung der Coverage Map" ist mit diesem
  ADR beantwortet und im Entscheidungslog auf „entschieden" gesetzt.
- `adr/0003` §10.4 („Ratengrenzen offen") ist für Earth Search inzwischen
  nachgemessen — nicht hier, sondern in `adr/0005` §3.6: keine Drosselung bei 30
  parallelen Anfragen, konservativ vorgeschlagen sind 6 Verbindungen je Host.
  Für EOPF und Copernicus DEM bleibt die Zeile offen.
- Der Nebenbefund zu `docs/cloud-umgebung.md` §6 ist nachgezogen:
  `earth-search.aws.element84.com` steht dort jetzt als freigegeben und
  erreichbar, nicht mehr als gesperrt.

## 7. Fragen an Otto — beantwortet am 2026-09-19

1. **Zählweise.** Eine Aufnahme zählt in **eine** Zelle (Zentroid) — nicht in
   jede berührte, wie im Prototyp. Grund: Der föderierte Weg kann es nicht
   anders (§3.3), und zwei Definitionen wären schlimmer als eine gröbere.
   (a) *Empfehlung:* so übernehmen, Legende sagt „Mittelpunkt in der Zelle".
   (b) Überlappungszählung erzwingen — dann müssen alle Footprints geerntet
   werden (Option 5, 30 Mio. Items für einen Datensatz).
   → **(a) angenommen, mit einer Ergänzung:** Zusätzlich deckelt jeder Datensatz
   seine feinste Gitterstufe anhand der typischen Footprint-Größe aus seinem
   Registry-Eintrag; für Sentinel-2 L2A ist das höchstens Geotile z8. Damit
   bleibt die Zentroid-Zählung dort, wo sie trägt (§5, Gitter).
2. **Vektorkacheln.** (a) *Empfehlung:* in M2 nicht, GeoJSON reicht laut
   Messung; Umkehrschwelle ~500 kB je Antwort. (b) gleich mit Kachelserver
   bauen — ein fünfter Prozess gegen M1-08.
   → **(a) angenommen:** keine Vektorkacheln in M2.
3. **Umschaltpunkt Dichte → Footprints** bei `numberMatched < 500`.
   (a) *Empfehlung:* 500. (b) anderer Wert. (c) feste Zoomstufe statt
   Trefferzahl.
   → **(a) angenommen:** Schwelle `numberMatched < 500`, der Zoom bleibt als
   zusätzliche Bremse.
4. **Latenzziel (K6).** In `docs/` steht keines; „wenige hundert Millisekunden"
   ist meine Setzung. (a) *Empfehlung:* so übernehmen und als Zeile ins
   Entscheidungslog. (b) anderer Wert. (c) kein Ziel festlegen — dann entfällt
   K6 als Kriterium.
   → **(b):** Das Ziel für die gefilterte Coverage ist **unter 1 s, typisch
   unter 0,5 s**. K6 ist entsprechend gefasst und steht als Zeile im
   Entscheidungslog.
5. **Status dieses ADR.** (a) *Empfehlung:* auf „angenommen" setzen, M2 baut
   darauf. (b) als Vorschlag stehen lassen, bis M2 ansteht.
   → **(a) angenommen:** Status „angenommen" (Kopf dieses Dokuments).

Zwei Festlegungen kamen mit derselben Antwort dazu, ohne eigene Frage gewesen zu
sein: **Aggregation als vierte, optionale Adapter-Fähigkeit** (§5, §6;
`architekturplan.md` 6.1) und die **Cache-Fristen** der Coverage-Aggregation, die
denen aus `adr/0005` F1 folgen (§5, Zwischenspeicher).

## 8. Was offen blieb

1. **Ratengrenzen von Earth Search** — keine `X-RateLimit-*`- oder
   `Retry-After`-Kopfzeilen, rund 40 Anfragen ohne Drosselung (§3.2). Nicht
   geschätzt; die Gateway-Grenzen bleiben deshalb konservativ. **Nachgetragen:**
   `adr/0005` §3.6 hat den Befund mit rund 110 Anfragen und zwei Bursts (20 und
   30 parallel) bestätigt und schlägt 6 parallele Verbindungen je Host vor.
2. **Verhalten bei 30 Mio. Items im eigenen pgstac.** Der Messaufbau hatte
   2 Mio. (§3.6). Für den föderierten Sentinel-2-Fall ist das ohne Belang —
   dort aggregiert der Upstream —, für einen künftig materialisierten Katalog
   wäre es vor dem Bau nachzumessen.
3. **UI-Konvention für „Stichprobe"** bei vergleichbaren Katalogen (Planetary
   Computer, Copernicus Browser, EarthExplorer, STAC Browser) — keine benannte
   Konvention auffindbar **[S]**. Regel V in §5 ist deshalb eigene Festlegung,
   keine Übernahme.
4. **Ob Earth Search die Kappung bei 10 000 dokumentiert.** Gemessen ja (§3.3),
   in der Aggregation-Spezifikation (Reifegrad „Proposal", v0.3.0, Abschnitt
   „Aggregation Types" selbst als unvollständig markiert) nicht beschrieben
   **[P]**. Die Vollständigkeitsprobe aus Regel V ist die Antwort darauf, dass
   man sich auf `overflow` nicht verlassen kann.
5. **Exakte URL-Längengrenze** — eingegrenzt auf 5,4 bis 8,1 kB (§3.4), nicht
   weiter bisektiert, weil 8 kB als Annahme ohnehin die sichere Seite ist.
6. **Kosten als Geld, nicht als Laufzeit.** K8 und §3.6 messen Antwortzeit und
   Speicherplatz. `projektuebersicht.md` Prinzip 10 verlangt zusätzlich „eine
   grobe Kostenabschätzung pro Request". Die fehlt hier, und sie lässt sich
   nicht seriös nachtragen: Für den föderierten Weg hängt sie an den
   Ratengrenzen von Earth Search (Punkt 1), für den eigenen an einer
   Cloud-Entscheidung, die laut `architekturplan.md` 15.3 erst nach Inkrement 4
   fällt. Was benannt werden kann: Jede Kartenbewegung mit geändertem Filter ist
   **eine** `/aggregate`-Anfrage an eine fremde Infrastruktur. Bei vielen
   gleichzeitigen Nutzern ist der Zwischenspeicher aus §5 deshalb nicht nur eine
   Beschleunigung, sondern die einzige Rücksichtnahme auf die Quelle, die wir
   haben (K5). Vor dem Bau in M2 gehört eine Obergrenze pro Nutzer und Minute
   dazu.
7. **Der Auftragsrahmen wurde gedehnt.** M1-09 verlangt „Stand der Technik mit
   Quellen"; Latenzmessungen gegen Earth Search sind laut `m1-fundament.md` §4
   Gegenstand des Spikes **M1-05**. Hier wurde live gemessen, weil die zentrale
   Frage — kann der Upstream überhaupt aggregieren — ohne Messung unbeantwortbar
   blieb und die Vorrecherche sie ausdrücklich offen ließ. Umfang: rund 40
   Metadaten-Anfragen, keine Pixel, keine Downloads. Otto sollte das wissen; die
   Zahlen sind in M1-05 wiederverwendbar (§6).
8. **`h3-pg` aus anderer Quelle.** Im Ubuntu-Archiv dieser Umgebung nicht
   vorhanden **[M]**; das Projekt liefert eigene Binärpakete für Ubuntu 22.04+
   **[P]**. Ob die in CI und Cloud-Umgebung einsetzbar wären, wurde nicht
   geprüft — erst relevant, wenn Geotile sich als zu grob erweist.

## 9. Quellen

**Gemessen [M]** — alle in dieser Sitzung, 19.09.2026:
`GET https://earth-search.aws.element84.com/v1` ·
`/v1/collections/sentinel-2-c1-l2a/aggregations` · `/v1/aggregate` (GET, diverse
Parameter) · `/v1/search?limit=1` · Postgres 16.13 / PostGIS 3.4.2 mit
`EXPLAIN ANALYZE` auf 2 Mio. synthetischen Footprints ·
`pg_available_extensions`.

**Primärdokument [P]:**
- STAC Aggregation Extension v0.3.0 (Reifegrad „Proposal"):
  https://github.com/stac-api-extensions/aggregation
- `stac-fastapi-pgstac`, `extensions/__init__.py` auf `main`:
  https://github.com/stac-utils/stac-fastapi-pgstac
- `pgstac`, `src/pgstac/sql/004_search.sql`:
  https://github.com/stac-utils/pgstac
- `h3-pg` (Apache-2.0, Binärpakete, PostgreSQL 14–18):
  https://github.com/postgis/h3-pg
- Earth Search v1 README: https://github.com/Element84/earth-search

**Suchtreffer [S]:**
- `pgstac` Issue #257 „Aggregation Extension", offen seit 17.04.2024:
  https://github.com/stac-utils/pgstac/issues/257
- Referenzimplementierung mit `centroid_*` und `geometry_*`-Varianten:
  https://github.com/stac-utils/stac-fastapi-elasticsearch-opensearch (`docs/src/aggregation.md`)
- `ST_SquareGrid` / `ST_HexagonGrid` ab PostGIS 3.1: https://postgis.net/docs/ST_SquareGrid.html ·
  https://www.crunchydata.com/blog/waiting-for-postgis-3.1-grid-generators
- `ST_AsMVT` / `ST_AsMVTGeom`: https://postgis.net/docs/ST_AsMVT.html
- Martin (MapLibre), Function Sources mit `query_params`:
  https://maplibre.org/martin/sources-pg-functions.html
- pg_tileserv: https://github.com/CrunchyData/pg_tileserv · TiPg:
  https://developmentseed.org/timvt/function_layers/
- MVT-Kacheln hinter CDN-Cache:
  https://www.crunchydata.com/blog/production-postgis-vector-tiles-caching
- Materialisierte Sichten sind in PostgreSQL nicht inkrementell:
  https://www.epsio.io/blog/postgres-refresh-materialized-view-a-comprehensive-guide
- Zeit-Buckets (`date_trunc`, `date_bin` ab PG 14):
  https://www.crunchydata.com/blog/easy-postgresql-time-bins
- `numberMatched` / `numberReturned` statt der abgekündigten Context Extension:
  https://github.com/stac-api-extensions/context
- STAC Collection `extent.spatial.bbox`:
  https://github.com/radiantearth/stac-spec/blob/master/collection-spec/collection-spec.md
- MapLibre Style Spec, `heatmap`-Layer und `interpolate`-Ausdrücke:
  https://maplibre.org/maplibre-style-spec/expressions/

---

## 10. Messanhang

Damit die Zahlen in §3.4 und §3.6 nachvollziehbar sind. Alles lief in dieser
Sitzung; nichts davon gehört ins Repo, es ist Messwerkzeug.

### 10.1 URL-Längengrenze (§3.4)

Polygone mit wachsender Stützpunktzahl gegen `/aggregate`, jeweils als
`intersects`-Parameter:

```bash
for n in 100 150 200 300 500; do
  python3 -c "
import json, urllib.parse
n=$n
ring=[[5+(i%50)*0.01, 45+(i//50)*0.01] for i in range(n)]; ring.append(ring[0])
print(urllib.parse.quote(json.dumps({'type':'Polygon','coordinates':[ring]})))" > p.txt
  echo -n "n=$n urllen=$(wc -c < p.txt): "
  curl -sS -G https://earth-search.aws.element84.com/v1/aggregate \
    --data "intersects=$(cat p.txt)" \
    --data 'collections=sentinel-2-c1-l2a&aggregations=total_count' \
    -o /dev/null -w 'http=%{http_code}\n'
done
```

### 10.2 Aufbau der Messtabelle (§3.6)

Rein synthetisch, keine echten Szenen (`ENTSCHEIDUNGEN` §4). Die Footprints sind
1°-Kacheln in Anlehnung an die Größenordnung einer MGRS-Kachel, gleichverteilt
über Längengrad und über das Breitenband −56° bis 84°:

```sql
CREATE EXTENSION postgis;
CREATE TABLE items (
  id bigserial PRIMARY KEY,
  datetime timestamptz NOT NULL,
  cloud_cover smallint NOT NULL,
  geom geometry(Polygon,4326) NOT NULL
);
INSERT INTO items (datetime, cloud_cover, geom)
SELECT timestamptz '2015-07-01' + (random()*4000)::int * interval '1 day',
       (random()*100)::int,
       ST_MakeEnvelope(lon, lat, lon+1.0, lat+1.0, 4326)
FROM (SELECT -180 + random()*360 AS lon, -56 + random()*140 AS lat
      FROM generate_series(1, 2000000)) s;
CREATE INDEX items_geom_gix ON items USING GIST (geom);
CREATE INDEX items_dt_idx   ON items (datetime);
CREATE INDEX items_cc_idx   ON items (cloud_cover);
ANALYZE items;
```

Der Filter, der in allen „gefiltert"-Zeilen steht:

```sql
WHERE geom && ST_MakeEnvelope(-10,35,30,60,4326)
  AND datetime >= '2024-01-01' AND datetime < '2025-01-01'
  AND cloud_cover < 20
```

### 10.3 Die gemessenen Abfragen (§3.6)

```sql
-- A  Footprint-Überlappung auf 1°-Gitter (A1 ohne, A2 mit dem Filter oben)
SELECT g.i, g.j, count(*) FROM items i
JOIN LATERAL ST_SquareGrid(1.0, i.geom) g ON ST_Intersects(i.geom, g.geom)
GROUP BY g.i, g.j;

-- B  Zentroid-Binning (B1 ohne, B2 mit dem Filter oben)
SELECT floor(ST_X(ST_Centroid(geom))), floor(ST_Y(ST_Centroid(geom))), count(*)
FROM items GROUP BY 1,2;

-- C  Zeit-Histogramm
SELECT date_trunc('month', datetime) m, count(*) FROM items
WHERE geom && ST_MakeEnvelope(-10,35,30,60,4326) AND cloud_cover < 20
GROUP BY 1 ORDER BY 1;

-- D  Vorberechnung: Zelle x Monat x Wolkenklasse
CREATE MATERIALIZED VIEW cov_cell_month AS
SELECT floor(ST_X(ST_Centroid(geom)))::int AS x,
       floor(ST_Y(ST_Centroid(geom)))::int AS y,
       date_trunc('month', datetime)::date AS month,
       (cloud_cover/20)::smallint          AS cc_class,
       count(*)::int                       AS n
FROM items GROUP BY 1,2,3,4;
CREATE INDEX ON cov_cell_month (month, cc_class);
CREATE INDEX ON cov_cell_month (x,y);
-- D1 gefiltert, D2 ohne Zeitfilter, D3 REFRESH MATERIALIZED VIEW

-- E  MVT-Kodierung der Weltzellen
SELECT ST_AsMVT(t,'coverage') FROM (
  SELECT sum(n) AS n,
         ST_AsMVTGeom(ST_Transform(ST_MakeEnvelope(x,y,x+1,y+1,4326),3857),
                      ST_TileEnvelope(0,0,0)) AS geom
  FROM cov_cell_month GROUP BY x,y) t;
```

Gemessen wurde jeweils die `Execution Time` aus `EXPLAIN (ANALYZE, BUFFERS,
TIMING OFF)`, bei `REFRESH` die Laufzeit der Anweisung. Die Testdatenbank wurde
nach der Messung verworfen.
