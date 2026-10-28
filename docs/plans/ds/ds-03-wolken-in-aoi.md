# DS-03 — Wolkenanteil in der AOI

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung, Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach DS-02. Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe DS-03 aus `docs/plans/ds/ds-03-wolken-in-aoi.md` aus.“

## 1. Anlass

Die Wolkenangabe der Quelle (`eo:cloud_cover`) gilt für die ganze Szene (rund 110 × 110 km). Otto möchte nach dem Wolkenanteil **in seiner AOI** filtern und sortieren.

## 2. Soll

- Für die Treffer einer Suche (nach der groben Vorauswahl über die Szene) berechnet die Plattform den Anteil bewölkter Pixel in der AOI aus der Klassifizierung (`SCL`, Klassen wie bei `mask`), auf einer groben Übersichtsstufe.
- Ergebnis je Szene, etwa „Clouds in AOI: 3 %“; Filter und Sortierung danach in „Advanced search“ bzw. der Trefferliste.
- Nur für Datensätze mit Klassifizierungsschicht (Registry, wie `earthx:mask`); sonst erscheint die Möglichkeit nicht.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Messung und Recherche (Pflicht, rechenrelevant):** Zeit und Bytes je Szene bei verschiedenen Übersichtsstufen; Genauigkeit gegen volle Auflösung; Stand der Technik (etwa übliche AOI-Wolkenstatistik aus SCL bzw. Cloud-Masken) mit Quellen.
- Schnittstelle: AOI nur im Body (POST), nie in URL oder Log; Cache je Szene und AOI-Hash (Hash nicht geloggt); Obergrenze der Szenen je Anfrage; schrittweise Anzeige.
- Welche Klassen zählen als Wolke (Vorschlag wie die Vorgabe von `mask`: 3, 8, 9, 10) und wie mit „no data“ in der AOI umgegangen wird.
- Grenzen der Klassifizierung (Zirren, Schnee) im Tooltip benennen.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Anteil gegen eine unabhängige Rechnung auf synthetischen Rastern; AOI nie im Log/URL; Obergrenze; Datensatz ohne Klassifizierung zeigt die Möglichkeit nicht.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.

## 6. Plan (28.10.2026, Stufe B, kein Produktivcode)

Vorgelegt zur Freigabe; bis dahin ändert dieser PR nur Dokumente. Grundlage ist `main` nach #227 (DS-02a und DS-02b gemergt, DS-02c noch nicht begonnen). Belegstufen wie in DS-02: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen (Wegwerf-Skripte, nichts davon im Repo), [A] eigene Ableitung, [S] nur aus Suchtreffern oder Foren belegt (die meisten Primärquellen waren aus der Sitzung nicht erreichbar).

### 6.0 Kurzfassung

- **Messung:** Die SCL-Datei einer Szene ist klein (0,13–4,8 MB, Median 1,5 MB) und hat Übersichten 2, 4, 8, 16 (40–320 m), gerechnet mit `MODE`. Je Szene kostet das Lesen der AOI kalt 0,3–0,75 s und meist unter 150 KB; 48 Szenen mit 8 parallelen Lesern dauern 3–4 s [M]. Die Zeit hängt an der Zahl der Anfragen, kaum an der Stufe.
- **Genauigkeit:** Hat die AOI auf der gelesenen Stufe mindestens 10 000 Pixel, liegt der Anteil im 95. Perzentil 1,1 und höchstens 1,9 Prozentpunkte neben der vollen Auflösung; mit weniger als 100 Pixeln bis 26 Prozentpunkte [M]. Empfehlung: **die gröbste Stufe mit mindestens 10 000 Pixeln in der AOI, sonst 20 m** (Frage 1).
- **Definition:** `eo:cloud_cover` ist bei allen 48 Szenen exakt der Anteil der Klassen 8, 9, 10 an den Pixeln mit SCL ≠ 0 [M]. Empfehlung: „Clouds in AOI“ zählt dieselben Klassen über dieselben Pixel, nur in der AOI. Damit sind beide Werte vergleichbar (Frage 3). Ohne gültiges Pixel in der AOI gibt es keinen Wert (Frage 4).
- **Nutzen:** Der Anteil in einer 10-km-AOI weicht bei 22 % der Szenen um mehr als 20 Prozentpunkte vom Wert der Szene ab [M].
- **Schnittstelle:** eigene Route `POST /collections/{dataset}/aoi-clouds` im `tiler` nach dem Muster von NM4-19 (AOI und Item-IDs nur im Body, höchstens 25 Szenen je Anfrage). Das Frontend fragt nach jeder Ergebnisseite schrittweise nach, filtert und sortiert in der Trefferliste. Die Suche und ihre Seiten bleiben unverändert (Frage 2).
- **Registry:** `MaskSource` bekommt `cloud_classes` und `cloud_note`; die Möglichkeit erscheint nur bei Datensätzen mit Klassifizierung und Wolkenklassen und nur mit AOI.
- **Schnitt:** DS-03a Backend nach Freigabe in dieser Session; DS-03b Frontend nach dem Merge von DS-02c in neuer Session (Frage 6).

### 6.1 Stand im Code [P]

- **Klassifizierung:** `DatasetConfig.mask` (`MaskSource`, M4-18) nennt Asset `scl`, alle Klassen mit Namen, die Vorauswahl für `mask` ({3, 8, 9, 10}) und Quelle; veröffentlicht als `earthx:mask`. Der DEM hat `mask=None`.
- **Vorbild NM4-19:** `POST /collections/{dataset}/statistics` (`api/area_statistics.py`) nimmt die AOI nur im Body (1 MB, 20 000 Positionen, `415`/`413`/`422`), speichert im Statistik-Cache (`earthx_stats_cache`, Schlüssel SHA-256, nie geloggt, 7 Tage, abgeräumt von `jobs/cleanup.py`) und schreibt genau eine Logzeile ohne AOI, Item oder Schlüssel. Ein Fehler von GDAL geht nur als Art in das Log.
- **DS-02:** `earthx:`-Eigenschaften sind für Filter reserviert, die die Plattform rechnet, und bis DS-03 `400` (`adr/0021` §2.7, Plan §6.9). Die Oberfläche „Advanced search“ (DS-02c) gibt es noch nicht.
- **Trefferliste:** Seiten zu 100 Items (`store.ts`, `PAGE_LIMIT`), gruppiert nach Überflug (`results_group_by`: `datetime`, `s2:datatake_id`), Gruppen nach Datum; eine Zeile zeigt Uhrzeit und Kennung, keinen Wolkenwert, keine Sortierwahl.
- **Items holen:** Der `tiler` holt Items einzeln über `item_source` (Item-Cache in Postgres). Die Suche füllt diesen Cache nicht; 25 einzelne Abrufe kosten bei Earth Search je 0,13–0,45 s, eine Suche mit `ids` für 25 Items 0,28 s, für 48 Items 0,55 s [M].

### 6.2 Messungen [M]

Earth Search v1, `sentinel-2-c1-l2a`, 48 Szenen aus sechs Regionen und Jahreszeiten (Alpen Sommer, Amazonas Regenzeit, Sahara, Norwegen Schnee, Küste Portugal Herbst, Ganges Monsun), je Region über den Wolkenanteil der Szene von 0 bis 100 % verteilt. GDAL wie `gateway.gdal_options` (HTTP/2, Multirange); Bytes und Anfragen aus dem GDAL-Debug-Log. Die Messung lief aus der Cloud-Sitzung über einen Proxy; aus einem Rechenzentrum in Europa sind die Zeiten eher kürzer.

**6.2.1 Aufbau der SCL-Datei:** COG, `uint8`, 5490 × 5490 Pixel zu 20 m, Blöcke 512², Deflate mit Prädiktor, `nodata` 0, Übersichten 2, 4, 8, 16, Tag `OVR_RESAMPLING_ALG=MODE` (je Block die häufigste Klasse). Die Recherche fand dazu keine Dokumentation von Element 84 [S]; gemessen am Objekt.

**6.2.2 Zeit und Bytes je Szene, kalt, nacheinander** (16 Szenen, kreisförmige AOI in der Mitte der Kachel; Median, in Klammern 90. Perzentil bzw. Maximum):

| AOI-Durchmesser | Stufe | Zeit | Bytes | Anfragen | Pixel in der AOI |
|---|---|---|---|---|---|
| 1 km | 20 m | 0,54 s (0,68) | 48 KB (80) | 4 | 1 968 |
| 10 km | 20 m | 0,64 s (0,75) | 52 KB (125) | 5 | 196 060 |
| 10 km | 80 m | 0,41 s (0,47) | 48 KB (96) | 4 | 12 281 |
| 30 km | 20 m | 0,74 s (0,85) | 149 KB (363) | 7 | 1 764 344 |
| 30 km | 160 m | 0,42 s (0,47) | 48 KB (64) | 5 | 27 621 |
| 110 km (ganze Kachel) | 20 m | 1,62 s (2,01) | 989 KB (2 150) | 4 | 23 633 820 |
| 110 km | 320 m | 0,31 s (0,40) | 32 KB (32) | 3 | 92 776 |

Öffnen allein (Größe und Kopf): 0,29–0,39 s. Die vollständige Tabelle (vier Größen × fünf Stufen) liegt im Messanhang §6.16.

**6.2.3 Viele Szenen** (48 Szenen, Leser parallel in Threads):

| AOI | Stufe | parallel | Dauer | Bytes gesamt |
|---|---|---|---|---|
| 10 km | 20 m | 1 | 26,2 s | 3,2 MB |
| 10 km | 20 m | 8 | 4,1 s | 3,2 MB |
| 10 km | 20 m | 16 | 2,7 s | 3,2 MB |
| 10 km | 80 m | 8 | 3,1 s | 2,5 MB |
| 30 km | 20 m | 8 | 4,3 s | 8,4 MB |
| 30 km | 80 m | 8 | 3,8 s | 3,2 MB |
| 110 km | 20 m | 8 | 9,3 s | 47,7 MB |
| 110 km | 80 m | 8 | 3,7 s | 7,2 MB |

**6.2.4 Genauigkeit gegen volle Auflösung:** 1 440 AOIs (Kreise mit 1, 3, 10, 30, 100 km Durchmesser, je Szene sechs zufällig gelegt, mindestens 10 % gültige Pixel), Anteil der Klassen 8, 9, 10 an den gültigen Pixeln, Maske über Pixelmitten. Fehler in Prozentpunkten gegen 20 m; nur die 516 AOIs mit gemischtem Himmel (Bezug zwischen 1 und 99 %), denn ganz klare oder ganz bedeckte AOIs treffen jede Stufe genau. Median / 95. Perzentil / Maximum:

| AOI | 40 m | 80 m | 160 m | 320 m |
|---|---|---|---|---|
| 1 km | 0,4 / 1,1 / 1,7 | 1,0 / 3,9 / 6,1 | 2,6 / 8,1 / 13,3 | 7,1 / 21,6 / 26,0 |
| 3 km | 0,1 / 0,3 / 0,4 | 0,2 / 1,1 / 2,0 | 0,7 / 3,4 / 5,3 | 2,2 / 8,2 / 12,0 |
| 10 km | 0,0 / 0,1 / 0,2 | 0,2 / 0,8 / 1,1 | 0,4 / 1,4 / 2,6 | 0,8 / 2,9 / 4,8 |
| 30 km | 0,0 / 0,1 / 0,1 | 0,1 / 0,5 / 0,7 | 0,2 / 1,3 / 1,8 | 0,6 / 2,8 / 3,7 |
| 100 km | 0,0 / 0,1 / 0,1 | 0,1 / 0,4 / 0,5 | 0,2 / 0,8 / 1,1 | 0,2 / 1,7 / 1,9 |

Nach der Zahl der Pixel, die die AOI auf der gelesenen Stufe hat (alle Stufen zusammen, gemischter Himmel):

| Pixel in der AOI | Fälle | `MODE`-Übersicht | zum Vergleich: jedes k-te Pixel |
|---|---|---|---|
| unter 100 | 164 | 3,2 / 15,4 / 26,0 | 3,0 / 14,2 / 33,5 |
| 100–1 000 | 266 | 0,7 / 3,1 / 6,1 | 0,7 / 3,2 / 6,6 |
| 1 000–10 000 | 368 | 0,3 / 1,8 / 3,7 | 0,2 / 0,9 / 2,0 |
| 10 000–100 000 | 500 | 0,1 / 1,1 / 1,9 | 0,1 / 0,3 / 0,5 |
| über 100 000 | 766 | 0,0 / 0,5 / 1,1 | 0,0 / 0,1 / 0,2 |

- `MODE` verzerrt im Mittel kaum (+0,01 bis +0,22 Prozentpunkte, bei 320 m −0,26), streut aber je AOI mehr als jedes k-te Pixel, weil kleine Wolken und Lücken in der Mehrheit ihres Blocks verschwinden [M, A]. Jedes k-te Pixel wäre genauer, spart aber keine Bytes: GDAL muss dafür die Blöcke der vollen Auflösung laden [A].
- Mit den Klassen 3, 8, 9, 10 (mit Schatten) sind die Fehler fast gleich.

**6.2.5 Szene und AOI:**
- Anteil der Klassen 8, 9, 10 an den Pixeln mit SCL ≠ 0 über die ganze Datei = `eo:cloud_cover` des Items, bei 48 von 48 Szenen auf drei Nachkommastellen. Mit Schatten (3) wären es im Median 0,2, höchstens 13,2 Prozentpunkte mehr. Klasse 1 (gesättigt oder defekt) kam in keiner der 48 Szenen vor.
- Abstand zwischen AOI und Szene, Klassen 8, 9, 10: AOI 1 km im Median 4,2 Prozentpunkte, bei 28 % der AOIs über 20; 10 km 4,1 bzw. 22 %; 30 km 3,0 bzw. 19 %.

### 6.3 Stand der Technik

- **Rechenweg:** Sentinel Hub und Copernicus Data Space rechnen den Wolkenanteil einer AOI mit der Statistical API: SCL je Pixel auf 0/1 abbilden, `dataMask` auf SCL ≠ 0, Mittelwert über die AOI, auf 20 m [S: [CDSE-Forum](https://forum.dataspace.copernicus.eu/t/cloud-percentage/438), [Planet-Community](https://community.planet.com/analysis-apis-81/statistical-api-creating-a-cloud-free-datamask-5760)]. Das ist der hier vorgeschlagene Weg. Bei Sentinel Hubs Wolkenmaske mit 160 m gibt es bei kleinen AOIs nur 0 oder 100 % ([Forum](https://community.planet.com/sentinel-hub-81/cloud-coverage-is-always-100-4218), [S]); das deckt sich mit §6.2.4.
- **Klassen:** kein Konsens. Häufig 3, 8, 9, 10 [S]; Sentinel Hubs Skript „cloud statistics“ nennt 1, 3, 8, 9, 10 [S: [custom-scripts](https://custom-scripts.sentinel-hub.com/sentinel-2/cloud_statistics)]. `eo:cloud_cover` zählt 8, 9, 10 ohne Schatten (§6.2.5 [M]); die STAC-EO-Extension verlangt für `eo:cloud_cover` eine Schätzung in Prozent ohne No-Data ([P: stac-extensions/eo](https://github.com/stac-extensions/eo)).
- **Andere Werkzeuge:** Google Earth Engine empfiehlt für Wolken die eigenen Masken (s2cloudless, Cloud Score+) statt SCL [S]; odc-stac und Planetary Computer zeigen SCL nur an, ohne AOI-Statistik [S]. Eine STAC-Erweiterung für „Wolken in der AOI“ wurde nicht gefunden [S].
- **Grenzen von SCL** (alle [S]): Baetens et al. 2019 ([Remote Sensing 11(4) 433](https://www.mdpi.com/2072-4292/11/4/433)): Gesamtgenauigkeit Sen2Cor 84 % (MAJA 91 %, Fmask 90 %), helle Flächen und Gebäude werden zu Wolken, im Gebirge bei trockener Luft wird Cirrus gemeldet. ESA-Validierung der Collection 1: 94 % ohne, 78 % mit Schnee; Cirrus über Schnee wird oft Schnee, Schatten auf Schnee oft klar. Zekoll et al. 2021 ([Remote Sensing 13(1) 137](https://www.mdpi.com/2072-4292/13/1/137)): Cirrus und Schatten mit hoher Präzision, aber geringer Trefferquote, also eher unterschätzt. CMIX (Skakun et al. 2022, RSE 274): Sentinel-2-Masken 80–89 % je Referenz, dünne Wolken am unsichersten.
- **Folgen für den Tooltip** [A]: dünne Zirren können fehlen, Schnee und helle Flächen als Wolke zählen; Schatten zählen nicht mit (bei K1, §6.6).

### 6.4 Rechenstufe (Frage 1)

| | Stufe | Fehler (gemischter Himmel, p95/max) | Kosten je Szene | Für / Gegen |
|---|---|---|---|---|
| **L1** | gröbste Übersicht, auf der die AOI noch ≥ 10 000 Pixel hat; sonst 20 m | ≤ 1,1 / 1,9 pp | 0,3–0,6 s, meist unter 100 KB | genau genug für ganze Prozent; wenig CPU |
| L2 | immer 20 m | 0 | 0,5–1,6 s, bis 2 MB, ganze Kachel 23 Mi Pixel CPU | exakt; ganze Kacheln 9 s für 48 Szenen |
| L3 | fest 320 m | bis 26 pp bei kleinen AOIs | 0,3 s, 32 KB | billig, für kleine AOIs falsch |
| L4 | wie L1 mit 1 000 Pixeln | ≤ 1,8 / 3,7 pp | etwas weniger | kaum billiger als L1 (die Zeit hängt an den Anfragen) |

**Empfehlung L1.** Die Stufe ergibt sich aus der Fläche der AOI im Raster der Szene, vor dem Lesen; Rechnung wie `processing.core.area_factor`, aber auf die vorhandenen Übersichten gerundet. Die Antwort nennt die Stufe (`resolution` in m), der Tooltip nennt sie nicht. Bei 1–3 km AOIs ist das 20 m, ab etwa 10 km 80 m, bei ganzen Kacheln 320 m.

### 6.5 Schnittstelle (Frage 2)

| | Weg | Für | Gegen |
|---|---|---|---|
| **S1** | eigene Route `POST /collections/{dataset}/aoi-clouds` im `tiler`; Body `{"aoi": …, "items": [Kennungen]}`; das Frontend fragt nach jeder Seite in Portionen nach, filtert und sortiert die geladenen Treffer | schrittweise Anzeige; Suche, Seitenmarken und Cache der Suche bleiben unverändert; Muster von NM4-19 | Filter wirkt nur auf geladene Seiten (Hinweis „of 100 loaded“) |
| S2 | `earthx:aoi_cloud_cover` in `query_by_collection` von `POST /stac/search` (Skizze DS-02 §6.9): `api` rechnet für jede Seite und wirft heraus, was nicht passt | ein Weg für Oberfläche und API-Clients | eine Seite wartet auf bis zu 100 Messungen (≈ 8 s), Seiten werden ungleich lang oder leer, Seitenmarken und Fingerabdrücke brauchen den Filter, keine schrittweise Anzeige |
| S3 | S1 jetzt, S2 später für die öffentliche API (M6) | | zwei Wege |

**Empfehlung S1** (S2 als Notiz für M6). Die Reservierung `earthx:` aus DS-02 bleibt `400`, bis die öffentliche API einen Bedarf zeigt.

Regeln für S1:
1. Body nur `application/json`, höchstens 1 MB (`413`), AOI `Polygon`/`MultiPolygon` mit höchstens 20 000 Positionen und den Prüfungen von `recipe.Aoi` (`422`), wie NM4-19. Ohne AOI `422`.
2. `items`: 1–25 Kennungen, jede einmal, Form wie im Pfad der Item-Route; mehr ist `413`. Der Datensatz im Pfad muss `cloud_classes` haben, sonst `404` („this dataset has no cloud classification“).
3. Die Items holt die Route mit **einer** Suche nach `ids` über den Adapter (0,3 s für 25 [M]), nicht 25 Einzelabrufe; Items aus dem Item-Cache werden genommen.
4. Gelesen wird je Szene das Asset aus `mask.asset` über `access` (Zugriffsauflösung, `gateway`-geprüfte Adresse), höchstens 8 Szenen gleichzeitig je Anfrage [M: 8 Leser für 48 Szenen 3–4 s].
5. Antwort je Kennung: `cloud_percent` (eine Nachkommastelle) oder `null`, `data_percent` (Anteil der AOI mit gültigen Pixeln, §6.7), `resolution` (m). Eine Szene, die nicht lesbar ist, bekommt `"error": "unreadable"` und hält die anderen nicht auf; ein Item, das die Quelle nicht kennt, `"error": "not found"`. Die Antwort trägt keine AOI und keinen Schlüssel; `Cache-Control: no-store`.
6. Fehlertexte von GDAL und der Quelle gehen weder in die Antwort noch ins Log (wie DS-02 C, NM4-19).

### 6.6 Wolkenklassen (Frage 3)

| | Klassen (Sentinel-2) | Für | Gegen |
|---|---|---|---|
| **K1** | 8, 9, 10 | dieselbe Definition wie `eo:cloud_cover` [M] und wie der Filter „Cloud cover“ aus DS-02; Szene und AOI direkt vergleichbar | Schatten stören auch |
| K2 | 3, 8, 9, 10 (Vorauswahl von `mask`) | was `mask` vorschlägt, häufig in Foren [S] | Wert der Szene und der AOI nicht vergleichbar (bis 13 pp) |
| K3 | zwei Werte: Wolken (8, 9, 10) und Schatten (3) | beides sichtbar | mehr Text, zweiter Filter |

**Empfehlung K1.** Der Tooltip sagt, dass Schatten nicht mitzählen. Die Klassen stehen als Daten in der Registry (`cloud_classes`, §6.10), nicht im Code.

### 6.7 No data (Frage 4)

- **Nenner:** gültige Pixel in der AOI, also SCL ≠ 0 (der `nodata`-Wert der Datei, nicht eine Zahl im Code), wie bei `eo:cloud_cover` [M]. Klasse 1 (gesättigt oder defekt) zählt im Nenner und nicht als Wolke, wie bei `eo:cloud_cover` (kam in den 48 Szenen nicht vor).
- **Datenanteil:** `data_percent` = gültige Pixel / Pixel der AOI; Teile der AOI außerhalb der Kachel zählen als ohne Daten.

| | ohne Daten | Für / Gegen |
|---|---|---|
| **N1** | kein gültiges Pixel: `null`, Anzeige „—“ mit Tooltip „No data in the AOI“; sonst der Wert, und der Tooltip nennt den Datenanteil („Measured on 64 % of the AOI“) | ehrlich, einfach; ein Wert aus 2 % der AOI sieht aus wie einer aus 100 % (der Tooltip sagt es) |
| N2 | wie N1, aber unter 10 % Datenanteil kein Wert | verhindert Werte aus Splittern; die Grenze ist willkürlich |

**Empfehlung N1.** Ist ein Filter gesetzt, fällt eine Szene mit `null` heraus (sie zeigt die AOI nicht).

### 6.8 Szene und Überflug (Frage 5)

Die Liste zeigt Überflüge (Gruppen) mit Szenen darunter. Der Wert steht an jeder Szene (Soll). Für die Gruppe und die Sortierung:

| | Wert der Gruppe | Für / Gegen |
|---|---|---|
| **G1** | aus den Zählungen der Szenen: Summe Wolkenpixel / Summe gültige Pixel | ein Wert für den Überflug über die ganze AOI; die Überlappung benachbarter Kacheln (rund 10 km) zählt doppelt, beide Kacheln stammen aus demselben Überflug [A] |
| G2 | genau wie im Mosaik (erste gültige Szene je Pixel) | gleich dem Mosaik; mehr Code, die Szenen müssen zusammen gelesen werden, kein Cache je Szene |
| G3 | kein Wert an der Gruppe; Sortierung nach dem kleinsten Wert der Szenen | einfach; ein Überflug mit einer klaren Randkachel steht oben |

**Empfehlung G1.** Die Antwort trägt dafür je Szene auch die Zählungen (`cloud_pixels`, `data_pixels`); die Gruppe zeigt ihren Wert im Kopf, die Sortierung „Clouds in AOI“ ordnet Gruppen danach, innerhalb der Gruppe bleibt die Reihenfolge. Der Filter wirkt auf Szenen; eine Gruppe ohne passende Szene verschwindet.

### 6.9 Obergrenze, schrittweise Anzeige, Cache, Log

- **KE1 Obergrenze:** 25 Szenen je Anfrage (Antwort in etwa 2 s [A aus §6.2.3 und §6.1]). Das Frontend misst alle geladenen Treffer des gezeigten Datensatzes, Portion für Portion in der Reihenfolge der Liste, höchstens zwei Anfragen gleichzeitig; „Load more“ misst die neue Seite. Eine Seite mit 100 Szenen ist damit nach etwa 4–8 s fertig, die ersten Werte nach 2 s.
- **KE2 Schrittweise Anzeige:** Bis zum Wert zeigt die Zeile „…“; Filter und Sortierung wirken auf gemessene Szenen, ungemessene stehen bis dahin am Ende der Liste und bleiben sichtbar. Ändern sich AOI oder Suche, werden laufende Anfragen abgebrochen.
- **KE3 Cache:** je Szene und AOI im Statistik-Cache, Schlüssel SHA-256 über `{"kind": "aoi-clouds/v1", "earthx": <Version>, "dataset", "item", "asset", "classes", "aoi"}` (AOI kanonisch); Inhalt nur Zahlen. Lebensdauer 7 Tage wie NM4-19 (der Schlüssel ist aus der AOI rückrechenbar), abgeräumt vom bestehenden Aufräumer. Nie in Log, URL oder Antwort. Im Browser hält der Store die Werte je AOI und Szene für die Sitzung.
- **KE4 Log:** eine Zeile „aoi clouds measured“ mit Datensatz, Anzahl Szenen, davon aus dem Cache, unlesbar, Stufen, Sekunden; keine AOI, Kennung, Schlüssel oder Adresse. Das Zugriffslog nennt nur Methode, Pfad (ohne AOI) und Status.

### 6.10 Registry

`MaskSource` bekommt zwei Felder, ohne Vorgabewert (B10):

```python
cloud_classes: frozenset[int]  # Klassen, die als Wolke zählen; leer = kein „Clouds in AOI“
cloud_note: str                # Tooltip-Satz zu den Grenzen der Klassifizierung, englisch
```

- Prüfung beim Start: `cloud_classes` ⊆ `classes`, ohne den `nodata`-Wert; ist es nicht leer, ist `cloud_note` nicht leer.
- Sentinel-2: `cloud_classes={8, 9, 10}` (K1), `cloud_note` „Sen2Cor's classification can miss thin cirrus and can take snow or bright ground for clouds.“
- Veröffentlicht in `earthx:mask` als `cloud_classes` (aufsteigend) und `cloud_note`. Das Frontend zeigt die Möglichkeit nur, wenn `cloud_classes` nicht leer ist und eine AOI gesetzt ist. Ein neuer Datensatz mit Klassifizierung braucht keinen Code, nur diese Daten.
- Erwogen und nicht empfohlen: `cloud_classes` aus `suggested` ableiten. `suggested` ist eine Vorauswahl für das Maskieren und enthält Schatten (K2).

### 6.11 Oberfläche (englisch, DS-03b)

- **Zeile:** rechts neben der Uhrzeit ein kurzer Wert „☁ 3 %“ (ganze Prozent, „<1 %“ unter 1), „…“ während der Messung, „—“ ohne Daten. Tooltip: „Clouds in AOI: share of the AOI's valid pixels classified as cloud (classes 8, 9, 10). Measured on 64 % of the AOI. Cloud shadows do not count.“ plus `cloud_note`. Bei einer unlesbaren Szene: „—“, Tooltip „Could not be measured“.
- **Gruppe:** derselbe Wert im Kopf (G1).
- **Sortierung:** in der Trefferliste ein kleiner Umschalter „Sort: Date | Clouds in AOI“, nur sichtbar, wenn der gezeigte Datensatz die Möglichkeit hat und eine AOI gesetzt ist.
- **Filter:** in „Advanced search“ (DS-02c) beim Datensatz ein Bereich „Clouds in AOI“ 0–100 % in derselben Form wie die Filter der Registry (DS-02 §6.9), nur mit AOI. Er geht nicht an die Quelle, sondern wirkt auf die Trefferliste; der Kopf der Liste zeigt dann „12 of 40 scenes“, Tooltip „Clouds in AOI filters the loaded scenes“.
- Hell/Dunkel über die vorhandenen Farbtoken; schmales Fenster wie die übrige Trefferliste.

### 6.12 Module [P, A]

- `access/aoi_clouds.py` (neu): öffnet ein Klassifizierungs-Asset über die bestehende Zugriffsauflösung, wählt die Stufe (§6.4), zählt Wolken- und gültige Pixel in der AOI (Pixelmitten, wie die Maske des Jobs). `access` darf `readers` und `catalog`; kein neuer Import.
- `api/aoi_clouds.py` (neu, im `tiler` registriert wie `area_statistics`): Body, Items per `ids`-Suche über `adapters`, Cache, Log. `api` darf alles außer `datasets`.
- Der Worker-Kern (`processing`) bleibt unberührt. `.importlinter` bleibt unverändert; `lint-imports` muss ohne Lockerung grün sein.

### 6.13 Tests und Abnahme

- **Rechnung gegen unabhängige Rechnung:** synthetische COGs (per Skript in `tests/fixtures` erzeugt, mit Übersichten `MODE`), Klassen in bekannten Mustern; der Anteil der Route gegen eine Zählung mit `numpy` direkt aus dem Muster, für 20 m und eine Übersicht; AOI teilweise außerhalb der Kachel, `MultiPolygon`, AOI ganz in No-Data (`null`), Klasse 1 im Nenner.
- **Stufenwahl:** Grenzfälle um 10 000 Pixel.
- **AOI nie in Log oder URL:** Logzeilen und Zugriffslog nach Koordinaten, Kennungen und Schlüssel durchsucht (wie NM4-19); Cache, der mit dem Schlüssel im Text wirft.
- **Obergrenze und Fehlbedienung:** 26 Kennungen `413`, doppelte, leere Liste, falscher Typ, Body zu groß, falscher Medientyp, AOI mit zu vielen Positionen, ungültige AOI, fehlende AOI.
- **Ohne Klassifizierung:** DEM `404`; Collection ohne `cloud_classes`; im Frontend (DS-03b) erscheint nichts, auch nicht ohne AOI.
- **Teilfehler:** eine unlesbare Szene, eine unbekannte Kennung; Fehlertext der Quelle mit Interna erscheint weder in Antwort noch Log.
- **Registry:** jede Prüfung aus §6.10.
- **DS-03b (vitest, Browser):** Wert, „…“, „—“; Sortierung von Gruppen; Filter mit ungemessenen Szenen; Abbruch bei neuer Suche; Möglichkeit fehlt ohne AOI und beim DEM; Prüfung in Chromium/Playwright der Sitzung, Hell/Dunkel, schmales Fenster.
- Je PR Prüfanleitung für Otto (DS-03a PowerShell 5.1, DS-03b Browser), Log-Zeile, vier Pflicht-Checks grün, `main` geholt.
- **Doku mit DS-03a:** `adr/0021` „§6 Nachtrag DS-03“, Zeile in `architekturplan.md` 5.1 (`earthx:mask.cloud_classes`).

### 6.14 Schnitt (Frage 6)

Schätzung: Backend ~250 Zeilen Code, ~350 Tests; Frontend ~200 Code, ~250 Tests; Doku ~60.

1. **DS-03a Backend in dieser Session nach Freigabe; DS-03b Frontend in einer neuen Session nach dem Merge von DS-02c und DS-03a** (die Oberfläche hängt an „Advanced search“). **(Empfehlung)**
2. DS-03b schon vor DS-02c, nur Wert und Sortierung in der Trefferliste; der Filter kommt mit DS-02c dazu.
3. Ein PR mit allem nach DS-02c.

### 6.15 Fragen an Otto

1. **Rechenstufe:** (1) gröbste Übersicht mit ≥ 10 000 Pixeln in der AOI, sonst 20 m **(Empfehlung)**; (2) immer 20 m; (3) fest 320 m.
2. **Schnittstelle:** (1) eigene Route, Filter und Sortierung im Frontend über die geladenen Treffer **(Empfehlung)**; (2) Filter in `/stac/search`; (3) erst 1, später 2 mit der öffentlichen API.
3. **Wolkenklassen:** (1) 8, 9, 10 wie `eo:cloud_cover` **(Empfehlung)**; (2) 3, 8, 9, 10 wie die Vorauswahl von `mask`; (3) zwei Werte, Wolken und Schatten.
4. **No data:** (1) Wert aus den gültigen Pixeln, ohne gültiges Pixel „—“, Datenanteil im Tooltip **(Empfehlung)**; (2) zusätzlich kein Wert unter 10 % Datenanteil.
5. **Überflug:** (1) Wert der Gruppe aus den Zählungen der Szenen, Sortierung nach Gruppen **(Empfehlung)**; (2) genau wie im Mosaik; (3) kein Gruppenwert, Sortierung nach dem kleinsten Szenenwert.
6. **Schnitt:** (1) DS-03a jetzt, DS-03b nach DS-02c **(Empfehlung)**; (2) DS-03b ohne Filter vor DS-02c; (3) ein PR nach DS-02c.

KE1–KE4 (§6.9) und die Registry-Form (§6.10) gelten, sofern Otto nicht widerspricht.

### 6.16 Messanhang [M]

Zeit je Szene, kalt, nacheinander, 16 Szenen (Median / 90. Perzentil in s; Bytes Median in KB):

| AOI | 20 m | 40 m | 80 m | 160 m | 320 m |
|---|---|---|---|---|---|
| 1 km | 0,54 / 0,68; 48 | 0,43 / 0,49; 48 | 0,40 / 0,44; 48 | 0,40 / 0,44; 96 | 0,30 / 0,33; 32 |
| 10 km | 0,64 / 0,75; 52 | 0,42 / 0,47; 40 | 0,41 / 0,47; 48 | 0,39 / 0,45; 96 | 0,31 / 0,36; 32 |
| 30 km | 0,74 / 0,85; 149 | 0,45 / 0,53; 77 | 0,43 / 0,47; 67 | 0,42 / 0,47; 48 | 0,31 / 0,34; 32 |
| 110 km | 1,62 / 2,01; 989 | 0,51 / 0,58; 400 | 0,43 / 0,52; 168 | 0,40 / 0,48; 96 | 0,31 / 0,40; 32 |

Szenen: je Region acht, gewählt über den Wolkenanteil der Szene (0–100 %), No-Data-Anteil unter 60 %; Kacheln u. a. 32TNT/32TPT/32UNU/32UPU (Alpen), 20LRQ/21LTJ (Amazonas), 31RGH/31RHH (Sahara), 32VNP/32VNN (Norwegen), 29SMD/29SND (Portugal), 45RTH/45RUH (Ganges). Daten unter der offenen Copernicus-Lizenz; nichts davon liegt im Repo.
