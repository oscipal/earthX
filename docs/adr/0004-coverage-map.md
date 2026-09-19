# ADR 0004 — Technische Umsetzung der Coverage Map

- **Status:** Vorschlag. Entscheidung liegt bei Otto.
- **Datum:** 2026-09-19
- **Aufgabe:** M1-09 laut `docs/plans/m1-fundament.md` §4.
- **Autonomiestufe:** C — nur recherchiert, gemessen und berichtet. Kein
  Produktivcode geändert, keine Daten heruntergeladen, keine Datei außerhalb von
  `docs/` angefasst.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §2 (Coverage Map), §5;
  `KLAERUNGEN.md` B8, B12; `architekturplan.md` 5.1, 5.2, 5.3, 15.3;
  `docs/prototyp-inventar.md` F12, N3; `adr/0001` §9.1, §9.3; `adr/0003`;
  Entscheidungslog-Zeile „Technische Umsetzung der Coverage Map".
- **Betroffen:** `architekturplan.md` 5.2, 6.3; `projektuebersicht.md` §5
  (Onboarding-Checkliste); Entscheidungslog; Planung M2.

---

## Methode und Belegstufen

Gearbeitet wurde in einer Cloud-Sitzung vom 19.09.2026. Anders als bei `adr/0003`
zum Zeitpunkt seiner Entstehung war **`earth-search.aws.element84.com` diesmal
erreichbar** (Egress-Freigabe wirkt laut Entscheidungslog erst in neu gestarteten
Sitzungen — diese ist eine solche). Die Messungen in §3 sind deshalb echte
Messungen gegen die reale Quelle, keine Schätzungen.

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

| # | Kriterium | Herkunft |
|---|---|---|
| K1 | Reagiert auf Filter (Zeitraum, Wolken, weitere Suchkriterien) | `ENTSCHEIDUNGEN` §2 |
| K2 | Vollständigkeit ist entweder gegeben oder **sichtbar ausgewiesen** | `ENTSCHEIDUNGEN` §2; F12/N3 |
| K3 | Funktioniert für föderierte **und** für eigene Items, mit demselben Ergebnisformat | `architekturplan.md` 5.2 |
| K4 | Dienste bleiben zustandslos; ein leerer Zwischenspeicher macht nur langsamer, nie 404 | `adr/0001` §8, §9.3; E5 |
| K5 | Alles Ausgehende über `gateway`, konservative Last auf der Quelle | `KLAERUNGEN` B8; `m1-fundament.md` §6 |
| K6 | Interaktiv bedienbar: Antwortzeit im Bereich weniger hundert Millisekunden | `projektuebersicht.md` Prinzipien |
| K7 | Läuft auf dem Stack, den die Cloud-Umgebung und CI hergeben — ohne eigenes Image nur für eine Extension | `docs/cloud-umgebung.md`; `adr/0002` §1 |
| K8 | Kosten wachsen nicht linear mit der Katalogsgröße | `architekturplan.md` 15.3 |

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

Der gefilterte Fall — der häufige — liegt durchweg **unter einer halben Sekunde
bei wenigen Kilobyte**. Das erfüllt K6 mit Abstand und macht Vektorkacheln für
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
- `pgstac/sql/004_search.sql` (28 kB, 567 Zeilen) enthält **keinen einzigen
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
3. **Die Footprint-Überlappung kostet rund das Vierfache** des
   Zentroid-Binnings (A1 gegen B1, A2 gegen B2), weil jedes Item mit mehreren
   Zellen verknüpft wird. Das ist der Preis der Semantik aus §3.3, Falle 2.

Der Messaufbau ist mit 2 Mio. Items zwei Größenordnungen kleiner als die 30 Mio.
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

| Fall | Weg |
|---|---|
| Quelle mit Aggregation-Extension (Sentinel-2 L2A über Earth Search) | **Option 1 oben:** `GET /aggregate` über `gateway` |
| Items im eigenen pgstac | **Option 1 unten:** SQL in PostGIS |
| Quelle ohne Aggregation-Extension | **Option 6:** Stichprobe, immer als solche ausgewiesen |

Dazu **Option 2 nur für den einen ungefilterten Weltüberblick** — die Ansicht
ohne jeden Filter, die jeder Nutzer als erstes sieht und die nach §3.6 mit 2,0
bis 7,8 s die einzige wirklich teure ist. Sie hat definitionsgemäß keine Filter
und ist damit gefahrlos vorberechenbar. Fällt die Vorberechnung aus, antwortet
Option 1 langsamer statt gar nicht — das ist die Regel E5 / `adr/0001` §9.3 (K4),
und sie gehört als Test hinterlegt.

**Gitter: Geotile.** Als einziges Gitter auf beiden Seiten verfügbar, seine
Präzision *ist* die Zoomstufe der Karte, und in PostGIS ohne Extension
nachbaubar (§3.7). H3 wäre fachlich besser, scheitert an K7. Die gewählte
Stufe leitet sich aus dem sichtbaren Kartenausschnitt ab, gedeckelt so, dass die
erwartete Zellenzahl deutlich unter der Kappungsgrenze aus §3.3 bleibt.

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
direkt: `numberMatched` steht in jeder STAC-Suchantwort — für den gemessenen
Filter lieferte `/search` mit `limit=1` in 0,35 s `numberMatched: 22619`
**[M]**. Unterhalb einer Schwelle (Vorschlag: 500) werden die echten Footprints
gezeichnet, darüber die Dichte. Das ist filterabhängig und damit richtiger als
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
500 kB geht.

**Zwischenspeicher: Postgres, kurz, schlüsselbasiert.** Anwendungs-Cache laut
E4, Schlüssel ist der normalisierte Filter samt Gitterstufe. Die TTL gehört zum
Spike M1-05, der dieselbe Frage für die Item-Suche stellt — eine Antwort für
beide. Der Upstream setzt kein `Cache-Control` und CloudFront liefert
durchgehend `Miss` (§3.2); unser Zwischenspeicher ist also der einzige, der
überhaupt wirkt. Und er darf ausfallen, ohne dass etwas fehlschlägt (K4).

**Gateway.** Jeder `/aggregate`-Aufruf läuft über `gateway` (B8, K5). Zwei
Anforderungen fallen für M1-03 ab: Die Route muss **GET mit langer
Abfragezeichenfolge** können (§3.1), und sie braucht eine Obergrenze für die
URL-Länge, die den `414` vermeidet, bevor die Anfrage das Haus verlässt (§3.4).

## 6. Folgen

- **M2** baut die Coverage Map auf dieser Nahtstelle. Die Onboarding-Checkliste
  (B12) bekommt als Pflichtpunkt nicht „Coverage Map existiert", sondern
  „Coverage-Anbieter ist zugeordnet und die Vollständigkeitsprobe greift".
- **M1-03** (Fetch-Gateway) erhält zwei zusätzliche Anforderungen (§5, Gateway).
- **M1-05** (Spike föderierte Item-Suche) sollte die TTL-Frage für Suche und
  Coverage gemeinsam beantworten; die Latenzzahlen aus §3.2 sind dort
  wiederverwendbar.
- **M1-04**: Der Registry-Eintrag braucht ein Feld für den Coverage-Weg und ein
  Capability-Flag für Einmal-Produkte. Das ist kein neues Konzept, sondern ein
  Eintrag mehr in der ohnehin vorgesehenen Flag-Liste (B10).
- Die offene Log-Zeile „Technische Umsetzung der Coverage Map" wird durch dieses
  ADR beantwortet, sobald Otto entscheidet.
- `adr/0003` §10.4 („Ratengrenzen offen") bleibt offen — §3.2 konnte sie nicht
  ermitteln, weil der Dienst keine entsprechenden Kopfzeilen sendet.
- Ein Nebenbefund für `docs/cloud-umgebung.md` §6: `earth-search.aws.element84.com`
  ist in dieser Sitzung erreichbar; die Tabelle dort führt ihn noch als gesperrt.
  Nicht in diesem PR geändert, weil M1-09 nur `docs/adr/` betrifft.

## 7. Fragen an Otto

1. **Zählweise.** Eine Aufnahme zählt in **eine** Zelle (Zentroid) — nicht in
   jede berührte, wie im Prototyp. Grund: Der föderierte Weg kann es nicht
   anders (§3.3), und zwei Definitionen wären schlimmer als eine gröbere.
   (a) *Empfehlung:* so übernehmen, Legende sagt „Mittelpunkt in der Zelle".
   (b) Überlappungszählung erzwingen — dann müssen alle Footprints geerntet
   werden (Option 5, 30 Mio. Items für einen Datensatz).
2. **Vektorkacheln.** (a) *Empfehlung:* in M2 nicht, GeoJSON reicht laut
   Messung; Umkehrschwelle ~500 kB je Antwort. (b) gleich mit Kachelserver
   bauen — ein fünfter Prozess gegen M1-08.
3. **Umschaltpunkt Dichte → Footprints** bei `numberMatched < 500`.
   (a) *Empfehlung:* 500. (b) anderer Wert. (c) feste Zoomstufe statt
   Trefferzahl.
4. **Status dieses ADR.** (a) *Empfehlung:* auf „angenommen" setzen, M2 baut
   darauf. (b) als Vorschlag stehen lassen, bis M2 ansteht.

## 8. Was offen blieb

1. **Ratengrenzen von Earth Search** — keine `X-RateLimit-*`- oder
   `Retry-After`-Kopfzeilen, rund 40 Anfragen ohne Drosselung (§3.2). Nicht
   geschätzt; die Gateway-Grenzen bleiben deshalb konservativ.
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
6. **`h3-pg` aus anderer Quelle.** Im Ubuntu-Archiv dieser Umgebung nicht
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
