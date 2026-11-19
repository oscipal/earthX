# M5-58 — Laufende und vorläufige Daten

**Stand:** 18.11.2026, Plan **angenommen** (Otto, 18.11.2026: F1–F9 = 1, F5 mit Beleg; §9.2). PR 1 (allgemeiner Mechanismus, Probe `--current` zuerst) in diesem Draft-PR (§10); PR 2 (MeteoSchweiz) in einer neuen Session nach dem Merge.
**Stufe B.** Höchstens zwei PRs (M5-Plan §2 Punkt 11); Schnitt in §6, Frage F8.
**Aufgabe (Otto, 18.11.2026, noch nicht im M5-Plan):**

> Laufende und vorläufige Daten allgemein. Für alle Datensätze, deren Quelle aktuelle bzw. vorläufige Werte anbietet, werden diese mit aufgenommen; vorläufige Werte werden durch endgültige ersetzt, sobald die Quelle sie liefert. Allgemeine Regel (§6.5, Otto 18.11.): Datensätze, die die Quelle laufend aktualisiert, auch ohne neue Datei, werden ebenso aktualisiert – Änderung über ETag/Last-Modified/Hash erkennen, nur Betroffenes neu schreiben.

- **Umfang:** ein allgemeiner Mechanismus in Registry und `materialize` (Stand je Item, Ersetzungsregel, Änderungserkennung, Takt), kein Sonderweg je Quelle.
- **Erster Anwendungsfall:** `meteoswiss-daily-1km` und `meteoswiss-daily-precip-1km` aus M5-11: Dateien des laufenden Jahres, Niederschlag vorläufig `RprelimD` → endgültig `RhiresD` nach 3–6 Wochen (Otto); Nutzungsbedingung „kein wiederholtes Laden desselben Inhalts“.
- **Weitere Kandidaten** nur auflisten (§5), nicht umsetzen.
- Keine Live-Abrufe aus der Session (`adr/0002`); Otto lädt lokal, die Session nennt die Befehle (§7).

**Grundlagen:** `adr/0009` §7.3 (Fassung je Lauf, „delsert“), `adr/0029` §3.1, §5, §6 und F5, `adr/0025` §6.6 und F7 (bedingte Anfragen, Inhalts-Hash, Prüfdatum nicht in YAML), `adr/0032` (Pyramide je Fassung), M5-11 Plan §5.5 (`v=<updated>`), §11 (PR 2, [#380](https://github.com/oscipal/earthX/pull/380)), `KLAERUNGEN.md` B9, B10, B13, M5-Plan §2 Punkte 8, 9 und §6.5.
**Voraussetzung:** M5-11 PR 2 ([#380](https://github.com/oscipal/earthX/pull/380)) ist gemergt (18.11.2026); der Plan liest den Stand von `main` danach (Materialisierer `meteoswiss-grid`).

Belegstufen wie in `adr/0029`: **M** gemessen (dort bzw. von Otto), **P** am Quelltext gelesen, **P\*** in der Dokumentation der Quelle gelesen (opendatadocs.meteoswiss.ch, 18.11.2026), **S** Suchtreffer oder Mitteilung, **A** eigene Ableitung. Adressen von Dateien, Item-IDs und Prüfsummen der Quelle stehen nicht in diesem Dokument.

---

## 1. Ziel

1. **Allgemein (Registry, `materialize`):**
   - Jeder Eintrag sagt in der Registry, ob und wie oft seine Quelle sich ändert und welche Stände sie kennt (`updates`, §3.2).
   - Jedes Item eines Eintrags mit mehreren Ständen trägt seinen Stand (`earthx:state`, §3.3).
   - `materialize` kann je **Einheit der Quelle** (Datei, Listeneintrag) erkennen, ob sie sich geändert hat, und schreibt nur die betroffenen Items neu (§3.4–§3.6). Der heutige Lauf „alles oder nichts“ bleibt für Einträge, die ihn wollen.
   - Eine Ersetzungsregel entscheidet je Item und Asset, welcher Stand gilt (§3.6 Schritt 4).
2. **MeteoSchweiz:** die beiden Einträge laden zusätzlich die Tage des laufenden Jahres und die vorläufigen Tage, und ersetzen sie, sobald die Quelle Endgültiges liefert (§4).

**Nicht Teil:** der Takt als Prozess (`harvester`, M5-24; hier nur das Registry-Feld und Läufe von Hand, F6), Health-Checks und „Last checked“ (M5-24), Umsetzung der Kandidaten aus §5, föderierte Datensätze (Sentinel-1, Sentinel-2; deren Items liegen nicht in pgstac, §5), Monatswerte von MeteoSchweiz.

---

## 2. Ausgangslage

### 2.1 `materialize` heute [P]

| Stelle | Heute |
|---|---|
| `discovery/materialize.py::run_materialize` | Ein Lauf fragt den Adapter mit der letzten `source_version` aus `earthx_materialize_runs`. Antwort `unchanged` → nur eine Zeile im Lauf-Log. Antwort `loaded` → **alle** Items `upsert_items`, alle übrigen `delete_items_except` („delsert“, `adr/0009` §7.3), eine Transaktion. |
| Fassung eines Laufs | eine Zeichenkette je Lauf: bei MeteoSchweiz ETag des Archiv-Items, Auswahl und Hash über Name, Adresse, `file:checksum`, `updated` aller gewählten Dateien (M5-11 A16) |
| Folge bei einer Änderung | eine geänderte Datei → alle 230 bzw. 65 Jahresdateien neu verwiesen (rund 30 bzw. 9 min, M5-11 §11.7; „nur geänderte Dateien kommen mit M5-24“, M5-11 A4) |
| Zustand je Datei | keiner; die Items tragen je Asset `href` und das ETag in `earthx:refs` |
| Stand je Item | keiner; `properties.updated` = jüngstes Last-Modified der Dateien |
| `temporal_extent.end` | fest im YAML (`2026-01-01T05:59:59Z` bzw. `2025-12-31T23:59:59Z`); Coverage `fixed-grid` verlangt einen geschlossenen Zeitraum (`registry.py`, `fixed_grid_coverage.py`) |
| Frontend | Kachel-, TileJSON- und Statistik-URLs von Items mit `earthx:refs` tragen `v=<updated>` (M5-11 F3); das Datumsfeld nimmt ein offenes Ende als „heute“ (`dateBounds.ts`) |
| Pyramide | `request_overview`/`confirm_overview` hängen an der `source_version` des Laufs (`adr/0032` §5); nur GLO-30 und WorldCover |

### 2.2 Die Quelle MeteoSchweiz

| Was | Stand | Beleg |
|---|---|---|
| Items der Collection | 78: je Tag der letzten rund zwei Monate eines mit 5 Assets (vorläufig, mit `expires`), je Monat eines mit 16–25 Assets, dazu `archive-ch` | M (`adr/0029` §3.1) |
| Vorläufige Tageswerte | Items `CH at DD.MM.YYYY`, „available for the past 41 days, with the oldest items being deleted successively“ | P\* |
| Konsolidierte Tages- und Monatswerte | Items `CH at MM.YYYY`, „the past 14 months“; veröffentlicht „on the 10th and 26th of the following month, whereas the data from the 10th will be overwritten by the one from the 26th. Differences between the two versions are possible.“ | P\* |
| Archiv | `CH archive`, Jahresdateien; „A final re-processing of all the analyses of a year is undertaken in early February of the year following.“ | P\* |
| Ersetzen an Ort und Stelle | ja bei den Monatsdateien (10. → 26.); bei den Tages-Items nicht gesagt | P\*, A |
| Vorläufig → endgültig beim Niederschlag | `RprelimD` → `RhiresD` nach 3–6 Wochen | S (Otto) |
| Vorläufige Temperatur | ob `TabsD`, `TminD`, `TmaxD`, `SrelD` eine vorläufige Stufe haben, sagt die Doku nicht; die Tages-Items tragen 5 Assets | P\*, M |
| Tagesgrenzen von `RprelimD` | „accumulated from 06:00 UTC of day D to 06:00 UTC of day D+1“, in mm, gleich wie `RhiresD` (`ProdDoc_RprelimD`, MeteoSchweiz, https://www.meteoswiss.admin.ch/dam/jcr:86ca15d3-2b56-4753-84fb-135e40d6a5a1/ProdDoc_RprelimD.pdf; Beleg von Otto, 18.11.2026) | P\* (F5) |
| Validatoren | `file:checksum` und `updated` je Asset; ETag auf Items, `304` auf `If-None-Match`; ETag und Last-Modified auf Dateien | M (`adr/0029` §3.1, §4) |
| Empfehlung der Quelle | „We highly recommend to use preconditioning via the `If-Match` or `If-None-Match` headers … This reduces unnecessary traffic.“ Assets werden 2 h gecacht. Rückversuche mit Backoff und Jitter | P\* |
| Nutzung | „excessive use in terms of access frequency or data volume (in particular the high-frequency downloading of the same content) is prohibited“, sonst Sperre möglich | P\* |
| Namen | Die Probe sah außerhalb des Archivs `ogd-surface-derived-grid-last.<größe>_…` und `ogd-surface-derived-grid.rprelimd_ch01h…`; welches Item welche Namen trägt, ist nicht ausgewertet | M (M5-11 §10.7), A |
| Größe | Tagesdatei 1,1 MB, Monatsdatei mit Tageswerten 13 MB, Jahresdatei bis 200 MB | P\* |

### 2.3 Was offen ist und Otto misst (§7 Schritt 1)

Eine Erweiterung der Probe `meteoswiss-probe --current` (PR 1, vor PR 2) liest nur die Items außerhalb des Archivs und gibt aus, ohne Adressen und IDs:

- je Art (Tages-Item, Monats-Item) die Namensmuster der Assets mit Größe, Gitter, Zeitstempel und Zahl; damit, ob `-last` die Dateien der Monats-Items sind;
- ob die Tages-Items alle fünf Größen vorläufig tragen (z. B. `tabsd` neben `rprelimd`) und unter welchem Namen;
- Aufbau einer Tages- und einer Monatsdatei je Gitter wie `--layout` (Typ, Chunk, Füllwert, Zeitachse, CRS);
- `expires`, `updated`, `file:checksum` und ob die Item-Liste (`/items`) ein ETag trägt bzw. `304` antwortet;
- ein zweiter Aufruf mit `If-None-Match` je Item: Zahl der `304`.

Kosten: rund 60 Items je ein bedingter Abruf, dazu je Gitter eine Tages- und eine Monatsdatei mit 5–8 Abrufen; mit 1 s Abstand rund 2 min.

---

## 3. Vorschlag: der allgemeine Mechanismus

### 3.1 Begriffe

- **Einheit der Quelle:** das Kleinste, an dem die Quelle eine Änderung zeigt und aus dem `materialize` Items baut; bei MeteoSchweiz eine Datei (ein Asset eines Quell-Items), bei einem Bucket die Kachelliste, bei einer STAC-API eine Seite oder ein Item.
- **Beitrag:** was eine Einheit zu einem Item gibt, je Paar (Item-ID, Asset-Schlüssel). Eine Jahresdatei `TabsD` 2025 gibt 365 Beiträge zum Asset `TabsD` von 365 Tages-Items.
- **Stand:** `provisional` oder `final` (F3), je Einheit vom Adapter gesetzt, mit Rang `provisional` < `final`.

### 3.2 Registry: neues Pflichtfeld `updates`

```yaml
updates:
  # Wie oft die Quelle sich ändert: none | daily | weekly | monthly. Liest der `harvester` ab M5-24 als Takt;
  # bis dahin läuft `materialize` von Hand (F6).
  cadence: daily
  # Die Stände der Quelle in aufsteigendem Rang; `final` immer zuletzt. Nur [final], wenn die Quelle nichts Vorläufiges hat.
  states: [provisional, final]
  # whole: eine Fassung je Lauf wie heute (alles oder nichts). units: Änderung je Einheit, nur Betroffenes neu (§3.6).
  detect: units
```

- Pflicht in jedem vollen Eintrag, ohne Vorgabe (B10). Alle heutigen Einträge bekommen `cadence: none`, `states: [final]`, `detect: whole`; federierte Einträge ebenso (sie materialisieren nicht).
- Prüfungen beim Laden: `states` nicht leer, ohne Doppelte, endet mit `final`; `detect: units` nur bei `item_holding: materialized` und einem Adapter, der Einheiten liefert (`AdapterSpec` bekommt dafür einen eigenen Eintrag, §3.6); `cadence: none` verträgt kein `provisional`; ein Eintrag mit `provisional` hat einen Satz dazu in `limitations` (F1).
- Das Prüfdatum und der Zustand je Einheit stehen **nicht** im YAML (`adr/0025` §6.6), sondern in Postgres (§3.5).

### 3.3 Item: Stand und Verfall

- `properties.earthx:state`: `provisional` oder `final`, gesetzt bei jedem Item eines Eintrags mit mehr als einem Stand; der niedrigste Stand seiner Assets. Jedes Asset trägt seinen eigenen `earthx:state`.
- `properties.expires` (STAC Timestamps Extension), wo die Quelle es nennt (MeteoSchweiz: Tages-Items); nur zur Information, die Logik hängt nicht daran.
- `properties.updated` bleibt das jüngste Last-Modified der Beiträge; es ändert sich mit jedem Ersetzen und damit `v=` in den Kachel-URLs (M5-11 F3).
- `earthx:state` ist ein eigenes Feld; ein STAC-Standard für „vorläufig“ existiert nicht [S] (`processing:level` meint die Verarbeitungsstufe, nicht die Endgültigkeit).

### 3.4 Änderungserkennung je Einheit

In dieser Reihenfolge; die erste verfügbare Angabe entscheidet:

1. **Angaben der Liste** (`file:checksum`, `updated`, ETag im Listeneintrag): kein Abruf der Einheit.
2. **ETag:** bedingter Abruf mit `If-None-Match` → `304` = unverändert. Ein schwaches ETag genügt hier; zum Lesen verlangt `netcdf_refs` weiter ein starkes (`If-Match`).
3. **Last-Modified:** `If-Modified-Since`.
4. **Inhalts-Hash** (SHA-256) der Antwort, nur für Listen bis 8 MiB (Grenze von `gateway`), wie der Harvester (`adr/0025` F7).

Die Liste selbst (Quell-Items, Seiten) wird ebenso bedingt gefragt. Ein unverändertes Quell-Item heißt: keine seiner Einheiten wird angesehen. Das erfüllt die Nutzungsbedingung (§2.2): Derselbe Inhalt wird nie zweimal geladen; eine geänderte Datei kostet nur das Lesen ihres Kopfes (5–8 Abrufe zu 64 KiB), die Daten liest der `tiler` beim Anzeigen über den Chunk-Cache.

### 3.5 Zustand in Postgres

Neue Tabelle `public.earthx_materialize_unit` (Migration, Nummer bei der Umsetzung; 026–028 belegt #379):

| Spalte | Inhalt |
|---|---|
| `dataset_id`, `unit_key` | Schlüssel; `unit_key` vom Adapter (bei MeteoSchweiz der Assetname der Quelle) |
| `state` | `provisional` / `final` |
| `etag`, `last_modified`, `checksum`, `content_sha256` | die Validatoren aus §3.4, soweit vorhanden |
| `contributes` | die Paare (Item-ID, Asset-Schlüssel), zu denen die Einheit beiträgt (auch die, bei denen ein höherer Stand gewinnt) |
| `seen_at`, `changed_at` | zuletzt gesehen, zuletzt geändert |

- `earthx_materialize_runs` bekommt Zähler je Lauf: Einheiten neu, geändert, unverändert, weg; Items geschrieben, ersetzt (Stand gestiegen), gelöscht. `status` bleibt `loaded`/`unchanged`.
- Die Adresse einer Datei steht in den Items ohnehin; in Logzeilen kommen weder Adressen noch Schlüssel (M5-Plan §10).

### 3.6 Ablauf eines Laufs mit `detect: units`

In `discovery.materialize`, für jeden Adapter gleich; der Adapter liefert nur zwei Dinge (eigene Felder im `AdapterSpec`):

- `list_units(config, gateway, known)` → die Einheiten der Quelle mit Stand und Validatoren, bedingt gefragt nach §3.4;
- `build(config, gateway, units)` → die Beiträge der neuen und geänderten Einheiten (je Beitrag Asset und Gerüst des Items: Geometrie, Zeiten, Eigenschaften).

Der Kern:

1. Einheiten mit dem Zustand aus §3.5 vergleichen: neu, geändert, unverändert, weg.
2. `build` nur für neue und geänderte Einheiten.
3. Betroffene Items = die Paare aus `contributes` der neuen, geänderten und weggefallenen Einheiten.
4. **Ersetzungsregel** je Paar (Item-ID, Asset-Schlüssel):
   - Es gilt der Beitrag mit dem höchsten Stand.
   - Bei gleichem Stand gilt die Einheit mit dem jüngeren Last-Modified (bei MeteoSchweiz: die Jahresdatei aus der Endbearbeitung im Februar vor der Monatsdatei desselben Tages).
   - Ein niedrigerer Stand ersetzt nie einen höheren (eine späte vorläufige Datei überschreibt nichts Endgültiges).
   - Fällt die geltende Einheit weg, gilt die nächste verbliebene; deren Beitrag wird dafür neu gebaut. Ist keine übrig, fällt das Asset weg; ein Item ohne Assets wird gelöscht.
5. Betroffene Items aus pgstac lesen, Assets ersetzen, `earthx:state` und `updated` neu, `upsert_items` nur für diese, `pgstac.delete_item` für die leeren.
6. Zustand und Lauf-Log schreiben; eine Transaktion wie heute. Ein Lauf ohne geänderte Einheit ist `unchanged`.

`detect: whole` bleibt der heutige Weg, unverändert für alle übrigen Adapter; damit bleiben auch Pyramiden (`adr/0032`) an der Fassung je Lauf. Ein Eintrag mit `detect: units` und `overview: pyramid` wird beim Laden abgelehnt, bis eine Aufgabe das regelt.

### 3.7 Ersetzen vorläufig → endgültig (F2)

Vorschlag: **dieselbe Item-ID** (`<dataset_id>-<JJJJMMTT>`), nur Assets und Stand ändern sich.

- Zeitleiste, Auswahl und gespeicherte Ebenen zeigen weiter auf denselben Tag.
- Kacheln: neues `updated` → neues `v=` → neue URLs für Browser und später CDN. Der Chunk-Cache des `tiler` trennt über (URL, ETag, Offset, Länge); alte Chunks verfallen nach LRU.
- Eine gespeicherte Ebene behält ihr altes `v` (bekannte Grenze aus M5-11 §11.4); der `tiler` liest das Item frisch und zeigt damit die endgültigen Werte unter der alten URL. Was ein Browser vorher unter derselben URL gecacht hat, bleibt bis zum Ablauf seines Caches (M5-11 F3: der `tiler` liest `v` nicht).
- Jobs: Ein laufender Job auf vorläufigen Werten liest mit `If-Match`; ist die Datei ersetzt, endet er mit `source_changed` und „Run again“ (M5-11 PR 1). Ein fertiges Ergebnis bleibt; die Provenienz nennt je Eingabe ETag und Stand (`earthx:state` neben `input_version`). Dass „Run again“ das Item neu auflöst und nicht die alten Verweise schickt, prüft ein Test in PR 1.

### 3.8 Takt (F6)

- `updates.cadence` ist die Angabe für M5-24. Bis dahin startet Otto `materialize` von Hand.
- Ohne Lauf altern die vorläufigen Items: Nach 41 Tagen löscht die Quelle ihre Dateien, Kacheln solcher Tage enden dann mit `502` (`source_changed` bzw. `404`), bis der nächste Lauf sie ersetzt oder löscht.
- Ein täglicher Lauf ohne Änderung kostet bei MeteoSchweiz rund 60 bedingte Abrufe (ein Abruf je Quell-Item, §2.3) und keine Datei; das ist kein „high-frequency downloading of the same content“.

### 3.9 Offener Zeitraum

- Ein Eintrag mit `cadence` außer `none` hat `temporal_extent.end: null` (laufend). Die Collection nennt das Ende offen; das Datumsfeld reicht bis heute (`dateBounds.ts`, schon so).
- Coverage `fixed-grid` mit offenem Ende zählt bis zum Ende des jüngsten geladenen Items (eine Abfrage je Collection, gecacht wie die übrigen Coverage-Antworten); die Prüfung „geschlossener Zeitraum“ wird zu „Anfang gesetzt, Ende gesetzt oder laufend“.

---

## 4. Erster Anwendungsfall: MeteoSchweiz

### 4.1 Einheiten und Stände

| Quell-Item | Einheit | Stand | Ersetzt an Ort und Stelle |
|---|---|---|---|
| `CH archive` | Jahresdatei je Größe | `final` | ja, bei der Endbearbeitung im Februar (neues ETag, `file:checksum`) |
| `CH at MM.YYYY` | Monatsdatei mit Tageswerten je Größe | `final` (F3) | ja, 10. → 26. des Folgemonats |
| `CH at DD.MM.YYYY` | Tagesdatei je Größe | `provisional` | nicht gesagt; die Erkennung deckt beides |

- Archiv und Monatsdatei geben Beiträge zu denselben Tagen; nach §3.6 Schritt 4 gilt die jüngere. Die 14 Monate überlappen sich mit dem Archiv des Vorjahrs; das ist gewollt und kostet nur Köpfe.
- Gewählt werden weiter nur `ch01r` bzw. `ch01h` und die Größen aus `band_units`; die Namensmuster der Tages- und Monatsdateien legt die Probe fest (§2.3), danach stehen sie wie `ARCHIVE_NAME` im Code (M5-11 A14).

### 4.2 Niederschlag: `RprelimD` als `RhiresD` (F4)

Vorschlag: Das Asset heißt immer `RhiresD`, auch wenn es aus `RprelimD` stammt; der Stand steht am Asset (`earthx:state: provisional`) und das Produkt der Quelle als `earthx:source_product: RprelimD`.

- Band math (`RhiresD > 20`), Darstellung, Download und Bewertungs-Set bleiben über alle Tage gleich.
- Im Data catalogue bleibt ein Band `RhiresD`; der Satz in `limitations` sagt, dass die letzten Wochen vorläufig sind (F1).

### 4.3 Tagesgrenzen der vorläufigen Produkte (F5)

- `RprelimD`: **belegt** (Otto, 18.11.2026, F5): „accumulated from 06:00 UTC of day D to 06:00 UTC of day D+1“, in mm, gleich wie `RhiresD`. Quelle: `ProdDoc_RprelimD` von MeteoSchweiz, https://www.meteoswiss.admin.ch/dam/jcr:86ca15d3-2b56-4753-84fb-135e40d6a5a1/ProdDoc_RprelimD.pdf. Ein vorläufiger Niederschlagstag deckt damit genau den Zeitraum des endgültigen Items desselben Tages; das Ersetzen unter derselben Item-ID (F2) verschiebt nichts.
- Vorläufige Temperatur (falls die Probe sie zeigt): nicht belegt, ob `ProdDoc_TabsD` auch für die Echtzeitanalyse gilt. Bis zum Beleg lädt PR 2 keine vorläufigen Tage dieser Größen; Monats- und Archivdateien sind belegt (gleiche Produkte wie M5-11).

### 4.4 Übernahme des Bestands (F9)

Die rund 47 500 Items aus M5-11 sind geladen. Vorschlag für den ersten Lauf mit `detect: units`: Der Zustand je Jahresdatei wird aus den Items gefüllt (`href`, ETag aus `earthx:refs`), dann ein bedingter Abruf je Datei (`HEAD` mit `If-None-Match`): `304` übernimmt sie ohne Neuverweis. 295 Abrufe, mit 1 s Abstand rund 5 min, statt rund 2 400 Abrufen und 40 min.

### 4.5 Registry-Einträge

- `updates: {cadence: daily, states: [provisional, final], detect: units}`.
- `temporal_extent.end: null`; `description` und `limitations` ohne „Only completed years are loaded“, dafür (Wortlaut im PR, Otto bestätigt): „Values of the last weeks are provisional and are replaced by the final values as soon as MeteoSwiss publishes them.“ und „Values of the past 14 months may still change; the final re-processing of a year follows in February of the next year.“
- Der Eintrag `-precip` nennt die Tagesgrenzen von `RprelimD`, sobald belegt.

### 4.6 Tests (ohne Netz)

Synthetisches Quell-Archiv mit drei Arten von Quell-Items über den lokalen Server aus M5-11 (`mini_netcdf`):

| Fall | Erwartung |
|---|---|
| erster Lauf, alles neu | Items aller Tage; vorläufige mit `earthx:state: provisional` |
| zweiter Lauf ohne Änderung | `unchanged`; je Quell-Item ein bedingter Abruf, keine Datei gelesen |
| Monatsdatei am 26. ersetzt (neues ETag/Checksum) | nur die Tage dieses Monats und dieser Größe neu geschrieben; übrige Items unberührt (`updated` gleich) |
| endgültige Datei kommt | vorläufige Assets ersetzt, gleiche Item-ID, `earthx:state: final`, neues `updated` |
| späte vorläufige Datei nach der endgültigen | ersetzt nichts |
| vorläufiges Quell-Item weg, Endgültiges noch nicht da | Asset und ggf. Item gelöscht |
| Archivdatei im Februar neu | gilt vor der Monatsdatei (jüngeres Last-Modified) |
| Quelle ohne ETag/Checksum (synthetischer Adapter) | Inhalts-Hash entscheidet |
| Bestand übernehmen | `HEAD` mit `If-None-Match`, `304` → kein Neuverweis |
| Abbruch mitten im Lauf | nichts geschrieben, Zustand unverändert |
| Registry | `updates` fehlt, falsch geordnet, `units` bei federiertem Eintrag, `provisional` mit `cadence: none`, `units` mit Pyramide → abgelehnt |
| Coverage `fixed-grid` mit offenem Ende | zählt bis zum jüngsten Item |
| „Run again“ nach `source_changed` | löst das Item neu auf |

---

## 5. Weitere Kandidaten (nur Liste, nicht umgesetzt)

| Datensatz / Quelle | Was sich laufend ändert | Passt auf den Mechanismus |
|---|---|---|
| Sentinel-1 GRD (Earth Search, federiert) | Fassungen NRT-3h und Fast-24h desselben Datatakes (Befund #343 §12.8, vorgemerkt in M5-Plan §6.2) | Stand aus der Zeitnähe des Produkts; föderiert, also ein Filter oder eine Bevorzugung in der Suche, nicht `materialize` |
| Sentinel-2 L2A (Earth Search, federiert) | Neuprozessierung mit neuer Processing Baseline | wie oben, eher „Fassung“ als „vorläufig“ |
| DWD HYRAS-DE | Datei des laufenden Jahres täglich verlängert, Vormonat am Monatsanfang und zur Monatsmitte neu gerechnet (`adr/0029` §6) | ja, Einheit Jahresdatei, `detect: units` |
| swissALTI3D | Kacheln werden jährlich in neuen Ständen nachgeführt (M5-08 `item_states`) | ja, Einheit Kachel statt ganzer Lauf (heute rund 17 min je Lauf) |
| BEV ALS-DGM | neuer Stichtag hält den Lauf an (M5-09) | Takt `monthly`, sonst wie heute |
| GeoSphere Austria (SPARTACUS, INCA; M5-21) | Analysen mit Nachlieferung | zu prüfen beim Onboarding |
| ERA5 / ERA5T (nicht in M5) | ERA5T vorläufig, nach 2–3 Monaten endgültig | ja, falls je aufgenommen |
| Copernicus DEM, WorldCover | statisch | `cadence: none` |

---

## 6. Schnitt (F8)

| PR | Inhalt | geschätzt (ohne Tests, Fixtures, YAML) |
|---|---|---|
| 1 (dieser Draft-PR) | Plan, ADR-Entwurf (F7), Probe `--current` (zuerst, damit Otto messen kann), Registry-Feld `updates` in allen Einträgen, Migration (Zustand je Einheit, Zähler), Kern `detect: units` in `discovery.materialize`, `earthx:state`, Coverage mit offenem Ende, Test mit synthetischem Adapter | rund 400 Zeilen |
| 2 (neue Session nach dem Merge) | MeteoSchweiz: `list_units`/`build` für Tages-, Monats- und Archivdateien, `RprelimD` → `RhiresD`, Übernahme des Bestands, Einträge, Tooltip im Frontend (F1), Provenienz mit Stand | rund 300 Zeilen |

Branch dieses PRs: `claude/brave-maxwell-buo3bh` von `main` nach dem Merge von #380.

---

## 7. Was Otto lokal ausführt (nach der Umsetzung)

Dieselbe Zeile in PowerShell und bash, aus der Repo-Wurzel. Jetzt, mit dem Plan allein, ist nichts auszuführen.

**Schritt 1 — Probe der laufenden Dateien** (PR 1, sobald umgesetzt; nur `gateway`, Ausgabe ohne Adressen, darf in den PR):

```powershell
git fetch origin claude/brave-maxwell-buo3bh
```

```powershell
git checkout claude/brave-maxwell-buo3bh
```

```powershell
docker compose run --build --rm meteoswiss-probe --current
```

**Schritt 2 — Lauf mit dem neuen Kern** (PR 2; übernimmt beim ersten Mal den Bestand, §4.4):

```powershell
docker compose run --build --rm materialize meteoswiss-daily-1km
```

```powershell
docker compose run --rm materialize meteoswiss-daily-precip-1km
```

**Schritt 3 — zweiter Lauf ohne Änderung** (erwartet `unchanged`, nur bedingte Abrufe):

```powershell
docker compose run --rm materialize meteoswiss-daily-1km
```

**Schritt 4 — Stände und Zeitraum:**

```powershell
"select collection, content->'properties'->>'earthx:state' as state, count(*), min(datetime), max(end_datetime) from pgstac.items where collection like 'meteoswiss-%' group by 1, 2 order by 1, 2;" | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
```

**Schritt 5 — einige Tage später derselbe Lauf:** Die vorläufigen Tage, für die inzwischen Endgültiges vorliegt, wechseln auf `final`; die Ausgabe nennt „replaced“. Schritt 4 erneut.

**Schritt 6 — im Browser:** jüngster Tag in der Zeitleiste, Tooltip „vorläufig“ (je nach F1), Band math auf `RhiresD` über einen vorläufigen und einen endgültigen Tag.

---

## 8. Risiken

- **Stände über Quell-Items hinweg:** Die Zuordnung Tag ↔ Datei hängt an Namen, die die Probe erst zeigt. Ändert MeteoSchweiz sie, scheitert der Lauf ausdrücklich (wie M5-11), statt Tage falsch zuzuordnen.
- **Lücke zwischen Verfall und Endgültigem:** Liefert die Quelle das Endgültige später als nach 41 Tagen, fehlen Tage vorübergehend (§3.6 Schritt 4); das ist der Stand der Quelle.
- **Viele Items je Lauf:** Eine neue Jahresdatei im Februar schreibt rund 365 Items je Größe neu; das ist der heutige Umfang eines Teils eines Laufs.
- **Gespeicherte Ebenen mit altem `v`:** siehe §3.7; kein falsches Bild, nur ein Browser-Cache bis zum Ablauf.
- **`detect: units` verdoppelt Wege in `materialize`:** Beide Wege bleiben, bis jeder Adapter Einheiten liefert; das wäre eine eigene Aufgabe (Kandidaten §5).

---

## 9. Fragen an Otto

Antwort am Handy reicht als „F1 1, F2 1, …“.

**F1 — Kennzeichnung „vorläufig“ im Frontend (§2 Punkt 9: keine Marken)?**
1. Satz in `limitations` im Data catalogue und Tooltip „Provisional values“ am Datum eines vorläufigen Tages (Suchtreffer, Zeitleiste); keine sichtbare Marke **(Empfehlung)**
2. Nur der Satz im Data catalogue
3. Nur der Tooltip

**F2 — Ersetzen vorläufig → endgültig?**
1. Gleiche Item-ID, Stand im Item (`earthx:state`); neues `updated` → neues `v=` in den Kachel-URLs; Chunk-Cache trennt über das ETag; fertige Jobs bleiben, ihre Provenienz nennt den Stand (§3.7) **(Empfehlung)**
2. Neue Item-ID je Stand (`…-JJJJMMTT-provisional`), das vorläufige Item wird gelöscht

**F3 — Stände?**
1. Zwei: `provisional`, `final`; was danach noch geändert wird (Monatsdatei am 26., Endbearbeitung im Februar), erkennt die allgemeine Regel über ETag/Checksum **(Empfehlung)**
2. Drei: `provisional`, `consolidated` (Monats-Items), `final` (Archiv)

**F4 — Band des vorläufigen Niederschlags?**
1. Asset und Band heißen `RhiresD` wie das endgültige Produkt, das Produkt der Quelle steht als `earthx:source_product: RprelimD` am Asset (§4.2) **(Empfehlung)**
2. Eigenes Band `RprelimD`; Band math und Darstellung wechseln mit dem Stand

**F5 — Tagesgrenzen der vorläufigen Produkte (Beleg)?**
1. Du legst die Sätze aus `ProdDoc_RprelimD` (und, falls die Probe vorläufige Temperatur zeigt, den Beleg dafür) in den PR, wie bei M5-11 §11.1; bis dahin lädt PR 2 keine vorläufigen Tage dieser Größe **(Empfehlung)**
2. Host `www.meteoswiss.admin.ch` für die Cloud-Umgebung freigeben, die Session liest die PDFs selbst
3. Ohne Beleg wie `RhiresD` (06–06 UTC) annehmen

**F6 — Takt bis M5-24?**
1. Von Hand: `updates.cadence: daily` steht im Eintrag für M5-24; du startest `materialize`, wann du willst (§3.8: ohne Lauf verfallen vorläufige Tage nach 41 Tagen) **(Empfehlung)**
2. Wie 1, dazu eine Anleitung für die Windows-Aufgabenplanung bei dir (nichts im Repo)

**F7 — ADR nötig?**
1. Ja, kurzer Entwurf `adr/0038-laufende-und-vorlaeufige-daten.md` in PR 1: neues Registry-Feld, Stand im Item, Zustand je Einheit in Postgres, Ausnahme vom „delsert“ aus `adr/0009` §7.3, Ablösung von `adr/0029` F5 **(Empfehlung)**
2. Nein, Nachträge in `adr/0009`, `adr/0029` und `adr/0025` genügen

**F8 — Schnitt?**
1. Zwei PRs wie §6: PR 1 dieser Draft-PR (allgemeiner Mechanismus, Probe, ADR), PR 2 MeteoSchweiz in einer neuen Session nach dem Merge **(Empfehlung)**
2. Ein PR mit allem (rund 700 Zeilen ohne Tests)

**F9 — Erster Lauf auf dem Bestand aus M5-11?**
1. Zustand aus den Items übernehmen, je Jahresdatei ein bedingter `HEAD` (295 Abrufe, rund 5 min), nur Geänderte neu verweisen (§4.4) **(Empfehlung)**
2. Alles einmal neu verweisen (rund 2 400 Abrufe, rund 40 min)

### 9.1 Auslegungen (gelten, wenn du nicht widersprichst)

- **A1:** Namen: Registry-Feld `updates` (`cadence`, `states`, `detect`), Item-Feld `earthx:state`, Asset-Feld `earthx:source_product`, Tabelle `earthx_materialize_unit`.
- **A2:** Alle heutigen Einträge bekommen `cadence: none`, `states: [final]`, `detect: whole`; sie verhalten sich unverändert. Die Kandidaten aus §5 bekommen ihre Werte mit ihrer eigenen Aufgabe.
- **A3:** Bei gleichem Stand gilt die Einheit mit dem jüngeren Last-Modified (§3.6 Schritt 4).
- **A4:** Fällt eine Einheit weg und bleibt für ein Asset kein Beitrag, fällt das Asset weg; ein Item ohne Assets wird gelöscht.
- **A5:** Ein laufender Eintrag hat `temporal_extent.end: null`; das Datumsfeld reicht bis heute, die Coverage bis zum jüngsten Item (§3.9).
- **A6:** `expires` der Quelle wird ins Item übernommen, steuert aber nichts.
- **A7:** `detect: units` mit `overview: pyramid` ist bis auf Weiteres abgelehnt (§3.6).
- **A8:** Die Probe `--current` liegt wie `--layout` in `scripts/m5-11-meteoswiss/probe.py` und kommt nicht ins Image.

### 9.2 Antworten von Otto (18.11.2026)

| Frage | Antwort |
|---|---|
| F1 | 1: Satz in `limitations` und Tooltip „Provisional values“ am Datum, keine Marke |
| F2 | 1: gleiche Item-ID, Stand im Item, neues `v=` |
| F3 | 1: zwei Stände, `provisional` und `final` |
| F4 | 1: Band `RhiresD`, Produkt der Quelle als `earthx:source_product: RprelimD` |
| F5 | belegt: `ProdDoc_RprelimD` (https://www.meteoswiss.admin.ch/dam/jcr:86ca15d3-2b56-4753-84fb-135e40d6a5a1/ProdDoc_RprelimD.pdf), Niederschlag „accumulated from 06:00 UTC of day D to 06:00 UTC of day D+1“, in mm, gleich wie `RhiresD` (§2.2, §4.3) |
| F6 | 1: Takt von Hand bis M5-24 |
| F7 | 1: Entwurf `adr/0038` in PR 1 |
| F8 | 1: PR 1 allgemeiner Mechanismus mit Probe `--current` zuerst; PR 2 MeteoSchweiz in einer neuen Session nach dem Merge |
| F9 | 1: Bestand über einen bedingten `HEAD` je Jahresdatei übernehmen |
| A1–A8 | gelten |

---

## 10. Umsetzung PR 1 (18.11.2026)

### 10.1 Was gebaut ist

| Stelle | Inhalt |
|---|---|
| `scripts/m5-11-meteoswiss/probe.py` | `--current` (zuerst, §2.3): Items außerhalb des Archivs nach Art (Tag, Monat), Eigenschaften (`expires`, `updated` …), Namensmuster und Größen je Präfix, Antwort auf `If-None-Match` je Item und je Seite der Liste, Kopf einer Datei je Art, Gitter und Größe; Ausgabe ohne Adressen, IDs und ETags |
| `catalog/registry.py`, alle neun Einträge | `UpdatesInfo` (`cadence`, `states`, `detect`) als Pflichtfeld `updates`; Prüfungen aus §3.2; alle Einträge `none` / `[final]` / `whole` (A2); `fixed-grid` mit offenem Ende nur bei laufender Quelle |
| `catalog/migrations/029_materialize_units.sql` | `earthx_materialize_group`, `earthx_materialize_unit`, Zähler in `earthx_materialize_runs` |
| `catalog/source_units.py` | Formen (`SourceUnit`, `UnitListing`, `Contribution`, `BuiltUnit`, `StoredUnit`, `Validators`) und Zugriff auf die Tabellen und auf Items je ID |
| `adapters/spec.py` | Feld `units` im `AdapterSpec` (`list_units`, `build`); heute bei allen Adaptern `None` |
| `discovery/materialize_units.py` | der Lauf je Einheit (§3.6): Erkennung nach §3.4, Ersetzungsregel, Neubau der nächsten Einheit, nur betroffene Items |
| `discovery/materialize.py` | `detect: units` nimmt diesen Weg; Ausgabe „N units new, M changed …; R replaced by a higher state“ |
| `catalog/fixed_grid_coverage.py`, `api/coverage_route.py`, `catalog/pgstac.py` | Coverage mit offenem Ende bis zum jüngsten Item (`latest_item_end`) |
| `docs/adr/0038-laufende-und-vorlaeufige-daten.md` | Entwurf (F7) |

### 10.2 Auslegungen (gelten, wenn du nicht widersprichst)

- **A9:** Zwei Tabellen statt einer (§3.5): Der Validator je Gruppe (Quell-Item, Seite) braucht eine eigene Zeile; sonst ließe sich eine Gruppe nicht bedingt fragen.
- **A10:** `--force` gilt für `detect: units` nicht; es entscheidet der Zustand je Einheit. Alles neu verlangt, den Zustand des Eintrags zu löschen (Otto, mit SQL, nicht im Code).
- **A11:** Ein Item wird nur geschrieben, wenn sich sein Inhalt ändert. Ein Adapter schreibt deshalb den Stand der Datei ins Asset (bei MeteoSchweiz das ETag in `earthx:refs`); sonst bliebe ein Neuverweis ohne Wirkung auf `updated` und `v=`.
- **A12:** `updated` eines Items ist das jüngste `updated` seiner Assets; ein Adapter setzt es je Asset.
- **A13:** Ob ein Adapter Einheiten liefert, prüft der Lauf (`UnsupportedSource`), nicht das Laden der Registry; so hält es `adapters.spec` schon für `materialize` („ob ein Eintrag materialisierbar ist, fragt `discovery`“).
- **A14:** Ein Lauf ist `unchanged`, wenn keine Einheit neu, geändert oder weg ist; die Validatoren der Gruppen werden trotzdem gespeichert. Die `source_version` eines solchen Laufs ist ein Hash über diese Validatoren und dient nur dem Lauf-Log.
- **A15:** Die Coverage mit offenem Ende fragt die Datenbank je Anfrage ohne eigenen Cache (`max(end_datetime)` einer Collection).

### 10.3 Tests

| Datei | Fälle |
|---|---|
| `tests/catalog/test_updates.py` | Pflichtfeld in jedem Eintrag; Reihenfolge und Ende der Stände; `none` ohne `provisional`; `units` nur materialisiert, nicht mit Pyramide; `provisional` verlangt `limitations`; offenes Ende nur laufend |
| `tests/integration/test_materialize_units.py` (echtes pgstac) | erster Lauf mit Stand je Tag; zweiter Lauf nur bedingte Listenfragen, kein Abruf einer Datei; endgültig ersetzt vorläufig unter derselben ID (`replaced` 1); späte vorläufige Datei ersetzt nichts; vorläufige Datei weg ohne Endgültiges → Tag gelöscht; jüngere von zwei endgültigen gilt, nach ihrem Wegfall wird die ältere neu gebaut; Änderung über Checksum der Liste (nur die Tage dieser Datei), über `HEAD` mit ETag, `304` ohne Neubau, ohne Validator über den Hash; Abbruch schreibt nichts; Einheit außerhalb der Hosts, fremder Stand, Adapter ohne Einheiten, Eintrag `whole`; Lauf-Log mit Zählern; jüngstes Ende |
| `tests/catalog/test_fixed_grid_coverage.py` | offenes Ende bis zum jüngsten Item; vor dem ersten Lauf nichts; geschlossenes Ende geht vor; Route ohne Datenbank → `503` |
| `tests/earthx/api/test_intake.py` | „Run again“ löst das Item neu auf: nach dem Ersetzen die Verweise und das ETag der endgültigen Datei |
| `tests/test_m5_11_meteoswiss_probe.py` | `--current` nach Art, Muster, `304`, Köpfe; keine Adresse, ID oder ETag in der Ausgabe |

### 10.4 Was Otto jetzt ausführen kann

§7 Schritt 1 (Probe `--current`); die Ausgabe gehört in diesen PR und legt die Namen der Tages- und Monatsdateien für PR 2 fest. `materialize` und `catalog-load` wenden Migration 029 beim nächsten Start selbst an.

**Wichtig für lokale Prototyp-Einträge** (`backend/catalog/prototype/`, nicht im Repo): Auch sie brauchen jetzt den Block `updates`, sonst lädt die Registry nicht:

```yaml
updates:
  cadence: none
  states: [final]
  detect: whole
```

### 10.5 Umfang

Rund 850 Zeilen ohne Tests, YAML und Doku (Probe rund 110, Kern rund 310, Formen und Tabellen rund 240, Registry rund 80, Coverage rund 30), dazu rund 740 Zeilen Tests. Über dem Richtwert von 400; der Kern lässt sich ohne Formen, Tabellen und Registry nicht testen, und die Probe sollte zuerst laufen.

### 10.6 Review vor dem Bericht und Antwort zu den Migrationen (18.11.2026)

**Behoben** (je ein Test, vorher rot):

- Eine unveränderte Datei, die nur jünger wird (gleiche Checksum, neues Last-Modified), kann Halterin eines Assets werden; ihre Assets werden jetzt neu entschieden. Vorher trug das Item weiter die alte Datei, und nach deren Wegfall verwies es auf eine gelöschte.
- Ein Neubau der nächsten Einheit, der weniger Assets beiträgt als vorher, entscheidet auch diese neu (bis sich nichts mehr bewegt).
- Gespeichert werden die Validatoren in der Form der Liste, gelesene nur ergänzend. Sonst verglich der nächste Lauf ein ETag ohne Anführungszeichen mit einem mit und baute die Datei jedes Mal neu.
- Ein Server, der `If-None-Match` überhört und `200` mit demselben ETag schickt, gilt als unverändert.
- Ein Last-Modified im ISO-Format (STAC `updated`) zählt für die Regel „jünger“.
- Eine Gruppe, die nie gesehen wurde, kann nicht „unverändert“ sein (ihre Einheiten würden nie gebaut).
- Die Probe nennt eine Ablehnung eines Items nur mit dem Status, nie mit dem Text der Quelle.
- Ein Test committete auf die gemeinsame Test-Datenbank; er schreibt jetzt nur in seiner eigenen, zurückgerollten Transaktion.

**Bleibt, für PR 2 bzw. später festgehalten:**

- Fällt ein Asset weg, bleiben die Eigenschaften seines Beitrags am Item (z. B. `expires`). Bei MeteoSchweiz tragen alle Beiträge eines Tages dasselbe Gerüst; PR 2 prüft das.
- Zwei gleichzeitige Läufe desselben Datensatzes sperrt nichts, wie schon bei `detect: whole`; das gehört zum Takt (M5-24).
- `latest_item_end` nimmt das Ende des jüngsten Items. PR 2 schreibt Items je Tag, nie je Monat; sonst zählte die Coverage bis zum Monatsende.

**Migrationen (Frage Otto, 18.11.2026):** Der Läufer (`catalog/schema.py::apply_migrations`) wendet jede Datei an, deren Nummer noch nicht gebucht ist, in Nummernfolge, unabhängig davon, ob eine höhere schon angewendet ist. Wird #383 vor #379 gemergt, hat eine Datenbank erst 029 und bekommt 026–028 beim nächsten Start dazu. Die Inhalte hängen nicht voneinander ab (029 ändert nur `earthx_materialize_runs` aus 004 und legt eigene Tabellen an). Neu belegt durch `test_a_lower_number_that_arrives_later_is_applied_too`; keine Änderung am Läufer nötig. Die Migrations-Tests kennen 029 jetzt (Liste der Dateien, Tabellen zum Löschen); #379 muss dort beim Zusammenführen seine drei Zeilen dazunehmen.

---

## 11. Probe `--current` (Otto, 18.11.2026) und Festlegungen für PR 2

### 11.1 Befund [M]

| Was | Ergebnis |
|---|---|
| Item-Liste | 1 Seite, **kein ETag, kein Last-Modified**; sie trägt jedes Item ganz |
| Items außerhalb des Archivs | 77: 59 Tages-Items, 11 Monats-Items, 7 Items ohne Tagesdateien (nur Monats- und Jahreswerte, Rekorde) |
| Tages-Items | je 5 Dateien eines Tages: `rprelimd` (`ch01h`), `sreld`, `tabsd`, `tmaxd`, `tmind` (`ch01r`); Präfix `ogd-surface-derived-grid.`; `expires` 2026-11-19 bis 2027-01-16 |
| Monats-Items | Präfix `ogd-surface-derived-grid-last.`; je eine Datei eines Monats mit Tageswerten für `rhiresd` (`ch01h`), `sreld`, `tabsd`, `tmaxd`, `tmind` (`ch01r`), dazu Monatswerte, Anomalien und Rekorde (nicht gelesen); `expires` 2027-02-01 bis 2027-12-01 |
| Je Item | starkes ETag, `304` auf `If-None-Match`; `datetime`, `created`, `updated`, `expires` |
| Je Datei | `file:checksum` und `updated` (alle 516 Dateien) |
| Köpfe | wie das Archiv: Float32, Chunk ein Tag ohne Filter, Füllwert −999.99, EPSG:2056, Gitter 240 × 370 bzw. 265 × 370, Schritte um 00:00 ohne `time_bnds`; Variable der vorläufigen Niederschlagsdatei `RprelimD` (mm), sonst `SrelD`, `TabsD`, `TmaxD`, `TminD` wie im Archiv |

Die Doku nennt 41 Tage für die vorläufigen Items; die Liste trug am Messtag 59. Maßgeblich ist für die Plattform nicht die Zahl, sondern ob ein Item gelistet ist (§11.4).

### 11.2 Welche Datei welchen Stand hat (für alle Größen)

| Quell-Item | Dateien | Stand | Beleg [P\*], `opendatadocs.meteoswiss.ch/c-climate-data/c3-ground-based-climate-data` |
|---|---|---|---|
| `CH at DD.MM.YYYY` (Tages-Item, Präfix `ogd-surface-derived-grid.`) | `RprelimD`, `SrelD`, `TabsD`, `TmaxD`, `TminD` eines Tages | **`provisional`**, alle fünf Größen | „The real-time daily analyses (preliminary) are available in items `CH at DD.MM.YYYY` with DD.MM.YYYY indicating the day for which the analysis is valid.“ – „analyses for the most recent past (e.g. yesterday's precipitation) are initially calculated before data collection and quality control have been completed. At this stage, these are preliminary analyses.“ |
| `CH at MM.YYYY` (Monats-Item, Präfix `ogd-surface-derived-grid-last.`) | `RhiresD`, `SrelD`, `TabsD`, `TmaxD`, `TminD` eines Monats | **`final`**, alle fünf Größen | „Consolidated versions of the analyses are produced later in several post-processing steps using more complete and thoroughly checked station observations.“ – „Consolidated daily and monthly analyses of the past 14 months are available in items `CH at MM.YYYY`.“ – „The data will be published on the 10th and 26th of the following month, whereas the data from the 10th will be overwritten by the one from the 26th.“ |
| `CH archive` | Jahresdateien | **`final`** | „A final re-processing of all the analyses of a year is undertaken in early February of the year following.“ – „`CH archive` is the key item to look for fully consolidated climate data …“ |

- Die Doku unterscheidet „preliminary“ und „consolidated“ je **Item**, nicht je Größe: Die Temperaturen und `SrelD` eines Tages-Items sind ebenso vorläufig wie der Niederschlag. Nur der Niederschlag trägt dafür einen eigenen Produktnamen (`RprelimD`); die übrigen behalten ihren Namen (F4 betrifft nur `RprelimD` → Band `RhiresD`).
- Eine konsolidierte Monatsdatei kann am 26. noch einmal überschrieben und im Februar durch die Jahresdatei ersetzt werden. Beides ist kein Standwechsel, sondern eine Änderung an Ort und Stelle (`file:checksum`) bzw. ein jüngerer Beitrag gleichen Stands (Regel „jünger“, `adr/0038` §3.4): F3 = zwei Stände bleibt.
- **Tagesgrenzen der vorläufigen Temperaturen (A16):** Die Tagesdatei trägt die Variable `TabsD` (bzw. `TminD`, `TmaxD`, `SrelD`), also dasselbe Produkt, dessen Tag `ProdDoc_TabsD` bzw. `ProdDoc_SrelD` festlegt (00–24 UTC, M5-11 §11.1), mit demselben Stempel 00:00 UTC. PR 2 nimmt diese Grenzen; „vorläufig“ ändert die Rechnung, nicht den Tag. `RprelimD` 06–06 UTC (F5). **Bestätigt von Otto (19.11.2026):** vorläufige `TabsD`, `TminD`, `TmaxD` und `SrelD` 00–24 UTC wie das Archiv.

### 11.3 Wie `expires` genutzt wird

- `expires` sagt, wann die Quelle ein Item löscht, nicht wann Endgültiges kommt. **Es löst nichts aus:** Ersetzt wird, sobald die Monatsdatei den Tag trägt (Regel höherer Stand); gelöscht, sobald die Datei nicht mehr gelistet ist (§3.6 Schritt 4).
- **Übernommen wird es am Asset:** PR 2 schreibt `expires` des Quell-Items an jedes Asset, das daraus stammt; der Kern setzt `properties.expires` eines Items auf das früheste `expires` seiner Assets und **entfernt es**, wenn kein Asset mehr eines trägt. Nach dem Ersetzen durch Endgültiges (Monats- oder Jahresdatei) trägt ein Tag also kein `expires` mehr. Monats-Items tragen ihr `expires` ebenfalls; ihre Tage verschwinden aber nicht, weil vorher die Jahresdatei im Archiv erscheint (Februar, vor dem Ablauf der 14 Monate) und gilt.
- Die Lücke aus §8 (vorläufig gelöscht, Endgültiges noch nicht da) ist mit 59 Tagen Vorlauf gegen Veröffentlichung am 10. bzw. 26. des Folgemonats nicht zu erwarten; träte sie ein, fällt der Tag weg, bis Endgültiges kommt.
- Die Zusammenfassung von `expires` gehört in den Kern (wie `updated`, A12); sie ist mit dieser Festlegung in PR 1 umgesetzt.

### 11.4 Die Liste ohne ETag

- Die Liste (`/items`) antwortet ohne ETag und Last-Modified, also ohne bedingte Anfrage (§3.4 Punkt 4). **Entschieden wird über den Inhalt:** SHA-256 des Körpers der Liste, gespeichert als Validator einer eigenen Gruppe „Liste“. Gleicher Hash → alle Gruppen unverändert, der Lauf endet nach **einem** Abruf.
- Ändert sich der Hash, ist **jede Gruppe ein Quell-Item** mit dem SHA-256 seines JSON aus der Liste als Validator (die Liste trägt jedes Item ganz; kein Abruf je Item). Die ETags der Items (`304`) werden nicht gebraucht.
- Die Dateien eines geänderten Items entscheidet `file:checksum` aus der Liste (§3.4 Punkt 1): kein `HEAD`, kein Abruf einer Datei, die sich nicht geändert hat.
- Gewählt werden nur Dateien der Größen des Eintrags auf seinem Gitter mit den drei Präfixen aus §11.2; Items ohne solche Dateien sind keine Gruppe.
- Kosten eines Tageslaufs: ein Abruf der Liste (rund 2 MB, das Archiv-Item eingeschlossen), dazu je neuer Tages- bzw. geänderter Monatsdatei 5–8 Abrufe für die Verweise. Derselbe Inhalt wird damit höchstens einmal am Tag geladen, und nur die Liste; die Nutzungsbedingung („high-frequency downloading of the same content“) ist eingehalten.
- Das braucht im Kern nichts Neues: „Liste“ ist eine Gruppe ohne Einheiten, deren Validator der Adapter liefert und vergleicht.

### 11.5 Antworten von Otto (19.11.2026)

- A16 bestätigt: vorläufige Temperaturen und `SrelD` 00–24 UTC wie das Archiv.
- Der Prototyp-Ordner enthält nur die README; der Block `updates` ist dort nicht nachzutragen.
- Otto prüft lokal, dass die bestehenden Datensätze unverändert laufen; Merge nach grüner CI. PR 2 (MeteoSchweiz) in einer neuen Session.

---

## 12. Umsetzung PR 2: MeteoSchweiz (19.11.2026)

Draft-PR [#385](https://github.com/oscipal/earthX/pull/385), Branch `claude/loving-mccarthy-euyx17` von `main` nach dem Merge von #383. Grundlage: F1–F9, A16 und die Festlegungen aus §11.

### 12.1 Was gebaut ist

| Stelle | Inhalt |
|---|---|
| `discovery/meteoswiss_grid.py` | `list_units`/`build_units` statt des Laufs „alles oder nichts“: liest die ganze Item-Liste (Seiten zu 100, `next` gefolgt), Gruppe „Liste“ mit SHA-256 der Seiten, je Quell-Item SHA-256 seines JSON, je Datei `file:checksum` und `updated` aus der Liste (§11.4); drei Präfixe mit Stand nach §11.2; `rprelimd` nur in Tages-Items und nur als Asset `RhiresD` mit `earthx:source_product: RprelimD` (F4); je Asset `updated` (Last-Modified der Datei) und `expires` des Quell-Items (§11.3); Prüfung der Spanne je Art (ein Tag, ein Monat, das Jahr des Namens) |
| `discovery/materialize_units.py` | Übernahme des Bestands (F9): erster Lauf ohne Zustand nimmt das ETag aus `earthx:refs` der gespeicherten Assets, `HEAD` mit `If-None-Match`, `304` → kein Neuverweis; die Items werden einmal geschrieben, damit sie ihren Stand tragen; ein gespeichertes Asset, dessen Datei nicht mehr gelistet ist, fällt weg (A24). Nach einem Neubau gilt das ETag der neu gelesenen Datei, nicht das gespeicherte. Halter je Paar in einem Durchgang statt je Paar über alle Einheiten (bei rund 47 500 Items sonst zu langsam) |
| `catalog/source_units.py`, Migration `031_materialize_unit_expires.sql` | `expires` je Einheit gespeichert (A17) und `stored_assets` für die Übernahme |
| `discovery/materialize.py` | `MATERIALIZE_SPECS` mit `units` für `meteoswiss-grid`; der Weg `detect: whole` für MeteoSchweiz entfällt |
| beide YAML-Einträge | `updates: {daily, [provisional, final], units}`, `temporal_extent.end: null`, Endpunkt = Item-Liste, `limitations` mit den beiden Sätzen aus §4.5 (Otto bestätigt), Beschreibung ohne „Only completed years“ |
| `processing/recipe.py`, `api/intake.py` | Provenienz: `state` je aufgelöster Eingabe neben `version`, aus `earthx:state` des Assets; fehlt bei Datensätzen mit einem Stand (Rezepte und Hashes von vorher bleiben gleich, A21) |
| Frontend `provisional.ts`, `ResultsPanel.tsx`, `TimeSlider.tsx` | Trefferliste: Warndreieck neben der Uhrzeit eines vorläufigen Treffers, Text „Provisional values“ am Dreieck (Otto, 19.11.2026, statt des Tooltips an der Uhrzeit). Tooltip „Provisional values“ in der Zeitleiste am gezeigten Datum, an den Nachbarn und an den Enden („Last time step: provisional values“); auf jeder Tipp-Stufe. Nicht am Kopf einer Gruppe: Dort verbietet UI-04 Teil 3a jeden Tooltip (`uiRules.test.ts`) |
| `tests_live/test_meteoswiss_grid_smoke.py` | prüft die Item-Liste wie der Adapter: Jahresdateien lückenlos bis höchstens zwei Jahre zurück, Monats- und Tagesdateien je Größe, Aufbau der jüngsten Datei je Art über `build_units` |

### 12.2 Auslegungen (bestätigt von Otto, 19.11.2026)

- **A17:** `expires` wird je Einheit in Postgres gehalten (Migration 031; 030 ist der Keyset-Stand aus M5-19, #379). Ohne das schriebe ein Neubau aus dem gespeicherten Zustand (`adr/0038` §3.4 Punkt 4, z. B. ein vorläufiger Tag nach Wegfall einer Monatsdatei) kein `expires` ans Asset.
- **A18:** Die Liste wird mit `limit=100` gefragt und `next` gefolgt, höchstens 20 Seiten; der Hash geht über alle Seiten. Heute ist es eine Seite (§11.1).
- **A19:** Jahresdateien zählen ab dem ersten Jahr von `temporal_extent.start`, ohne Obergrenze (das Ende ist offen). Eine Archivdatei, die nicht genau ein Jahr ist, oder eine Datei außerhalb der `asset_hosts` wird übergangen und als Warnung gezählt (ohne Namen), wie `unknown` in M5-11.
- **A20:** Die Auswahl des Eintrags (Größen, erstes Jahr) gehört in jeden Validator. Eine andere Auswahl listet daher alles neu, wie `selection` in M5-11.
- **A21:** Der Stand steht in der Provenienz als `state` je aufgelöster Eingabe (`ResolvedInput`), nicht in `InputVersion`: Die Version bleibt die des Inhalts, der Stand ist eine Aussage über ihn.
- **A22:** Ein Fehler beim Bauen nennt Art, Größe und Datum der Datei, nie Namen oder Adresse.
- **A24:** Beim Übernehmen fällt ein gespeichertes Asset weg, dessen Datei die Liste nicht mehr nennt (es sei denn, eine andere Einheit hält es jetzt). Sonst bliebe es ohne Einheit und zeigte auf eine gelöschte Datei.
- **A25:** Ob ein Tag bzw. Monat zum Stempel im Dateinamen passt und ob die Datei die Variable ihres Namens trägt, wird nicht geprüft: Die Zeitachse der Datei entscheidet über den Tag, die Bedeutung der Stempel ist nicht gemessen, und M5-11 prüfte die Variable auch nicht. Geprüft wird die Spanne je Art (ein Tag, ein Monat, das Jahr des Namens).
- **A26:** Ändert sich nur `expires` eines Quell-Items (Prüfsummen gleich), steht das neue `expires` im Zustand, das Asset behält das alte bis zum nächsten Neubau der Datei. `expires` steuert nichts (§11.3); ein Neubau nur dafür kostete 5–8 Abrufe je Datei.
- **A23:** Der Lauf `detect: whole` für MeteoSchweiz ist entfernt, nicht nur abgeschaltet; die Tests von Download, Bändern und synthetischer Kette bauen ihre Items über `list_units`/`build_units` und die Zusammenführung des Kerns (`assemble_item`, dafür öffentlich).

### 12.3 Tests

| Datei | Fälle |
|---|---|
| `tests/earthx/discovery/test_meteoswiss_grid.py` | Gruppen und Stände je Präfix; Validatoren und `expires` aus der Liste; eine Anfrage, keine Datei; `RprelimD` als `RhiresD` nur in Tages-Items; gleiche Liste → `unchanged` nach einer Anfrage; neuer Tag listet nur seine Dateien; andere Auswahl listet alles; Jahre vor dem Start; keine Jahresdatei bzw. fremder Host übergangen; Seiten gefolgt; Ablehnungen (zwei Dateien einer Größe, keine Datei, keine Item-Collection, Liste ohne Ende, fremde Größe, zwei Gitter); Items je Tag, Tagesgrenzen 00–24 und 06–06 auch vorläufig, Asset mit Verweisen, `updated`, `expires`, `earthx:source_product`; Ablehnungen beim Bauen (Mitternacht, anderes Jahr, zwei Monate, zwei Tage, anderes Gitter, Layout ohne Adresse, Gitter außerhalb, fremde Einheit) |
| `tests/integration/test_materialize_meteoswiss.py` (echtes pgstac, ganzer Befehlsweg) | gelistete Datei mit `404` → übergangen, Rest geschrieben, `missing` 1, im nächsten Lauf nur diese Datei erneut gefragt, nach Auslieferung gebaut, danach wieder eine Anfrage (F10 = 1); Monatsdatei nicht ausgeliefert → ihre Tage vorerst weg; Jahresdatei mit `404` beim Übernehmen; Asset einer nicht mehr gelisteten Datei fällt beim Übernehmen weg; neues ETag nach Neubau gespeichert; erster Lauf mit Stand je Tag; **Tageslauf ohne Änderung = eine Anfrage** (`GET` der Liste) und Lauf-Log `unchanged`; neuer Tag liest nur seine Datei; Monatsdatei ersetzt den vorläufigen Tag unter derselben ID (`replaced` 1, kein `expires`, kein `earthx:source_product`); Monatsdatei am 26. schreibt nur ihre Tage; Archiv aus dem Februar gilt vor dem Monat; vorläufiger Tag weg ohne Endgültiges → gelöscht; Übernahme: `HEAD` mit `If-None-Match`, `304`, Stand `final` geschrieben; geänderte Jahresdatei neu verwiesen |
| `tests/earthx/api/test_intake.py` | `state` in der Provenienz bei vorläufigem Asset; ohne Stand kein Feld; unbekannter Stand bleibt weg |
| `frontend/src/components/TimeSlider.test.tsx`, `ResultsPanel.test.tsx` | Zeitleiste: Tooltip am vorläufigen Datum (gezeigt, Nachbar, Ende), keiner am endgültigen. Trefferliste: Warndreieck mit Text neben der Uhrzeit eines vorläufigen Treffers, keines bei einem endgültigen, nichts am Gruppenkopf |
| `tests/test_live_smoke_dry_run.py` | Double der Item-Liste mit Archiv-, Monats- und Tagesdateien |

### 12.4 Was Otto lokal ausführt

PowerShell, aus der Repo-Wurzel. `materialize` startet `catalog-load` vorher selbst (neue Beschreibung, offenes Ende, `limitations`) und wendet Migration 031 an.

**Schritt 1 — Branch holen:**

```powershell
git fetch origin claude/loving-mccarthy-euyx17
```

```powershell
git checkout claude/loving-mccarthy-euyx17
```

**Schritt 2 — erster Lauf je Eintrag** (übernimmt den Bestand: je Jahresdatei ein `HEAD`, dazu Monats- und Tagesdateien neu; bei 1 s Abstand rund 30 min für die Temperaturen, rund 8 min für den Niederschlag):

```powershell
docker compose run --build --rm materialize meteoswiss-daily-1km
```

```powershell
docker compose run --rm materialize meteoswiss-daily-precip-1km
```

Erwartet je eine Zeile `loaded; N units new, 0 changed, M unchanged, 0 gone, 0 not served (asked again next run); K items written, 0 replaced by a higher state, 0 deleted` mit `M` = Zahl der Jahresdateien (230 bzw. 65) und `K` rund 23 700 plus die Tage der Monats- und Tagesdateien.

**Schritt 3 — ein Tageslauf ohne Änderung = eine Anfrage:** derselbe Lauf noch einmal, die Ausgabe in einer Variablen; dann die Zeilen `gateway request` zählen (eine je Anfrage, `gateway/client.py`):

```powershell
docker compose run --rm materialize meteoswiss-daily-1km | Tee-Object -Variable lauf
```

```powershell
($lauf | Select-String 'gateway request').Count
```

Erwartet: `unchanged; 0 units new, 0 changed, … unchanged, 0 gone, 0 not served …; 0 items written …` und die Zahl **1**. Nennt ein Lauf „not served“ > 0, fragt der nächste Lauf diese Dateien erneut; dann ist die Zahl 1 plus je Datei die Anfragen für sie. Ist dazwischen ein neuer Tag erschienen, ist es `loaded` mit wenigen neuen Einheiten; dann den Lauf gleich noch einmal, er ist danach `unchanged` mit 1.

**Schritt 4 — Stände und Zeitraum:**

```powershell
"select collection, content->'properties'->>'earthx:state' as state, count(*), min(datetime), max(end_datetime) from pgstac.items where collection like 'meteoswiss-%' group by 1, 2 order by 1, 2;" | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
```

Erwartet je Eintrag zwei Zeilen, `final` und `provisional`, keine leere; `max(end_datetime)` der vorläufigen Zeile in den letzten Tagen.

**Schritt 5 — einige Tage später** (nach dem 10. oder 26. des Monats) Schritt 2 erneut: Die Ausgabe nennt `replaced by a higher state` > 0; Schritt 4 zeigt weniger vorläufige Tage.

**Schritt 6 — im Browser** (`docker compose up --build`, dann wie gewohnt öffnen):

1. Data catalogue, beide Einträge: die beiden Sätze in den Limitations; Zeitraum ohne Ende.
2. Suche `meteoswiss-daily-precip-1km` über einen Ort in der Schweiz, Zeitraum die letzten acht Wochen: In der Trefferliste steht neben der Uhrzeit (`06:00:00Z`) eines der jüngsten Tage ein Warndreieck, beim Überfahren „Provisional values“; ein Tag vor rund sechs Wochen hat keines; der Gruppenkopf mit dem Datum zeigt nichts. In der Zeitleiste dasselbe am gezeigten Datum und am rechten Ende („Last time step: provisional values“). Keine sichtbare Marke.
3. Ein vorläufiger Tag auf der Karte: Kacheln erscheinen; Band `RhiresD`, gleiche Farbskala wie ein endgültiger Tag.
4. Band math `RhiresD > 20` über einen vorläufigen und einen endgültigen Tag: beide rechnen; im `recipe.json` des Jobs steht bei der vorläufigen Eingabe `"state": "provisional"`.
5. Dasselbe kurz für `meteoswiss-daily-1km` (`TabsD`): Tooltip an den jüngsten Tagen.

### 12.5 Frage an Otto

**F10 — Eine gelistete Datei fehlt bei der Quelle (`404`/`410`)?** Heute bricht der ganze Lauf ab und schreibt nichts; der nächste Lauf versucht es wieder. M5-11 duldete bis 1 % fehlende Jahresdateien. Scheitert eine Tagesdatei dauerhaft (gelistet, aber nicht hochgeladen oder schon gelöscht), käme bis zur Korrektur der Quelle auch kein anderer neuer Tag herein.
1. Die Datei übergehen und als Warnung zählen (wie A19), ohne Adresse; sie gilt als nicht gelistet und wird im nächsten Lauf wieder versucht; der Lauf schreibt alles andere **(Empfehlung)**
2. So lassen: Der Lauf scheitert als Ganzes

**Antwort Otto (19.11.2026): F10 = 1; A17–A26 gelten; der Umfang über dem Richtwert ist hingenommen.** Umgesetzt im Kern, für jeden Adapter gleich: Antwortet eine gelistete Einheit beim `HEAD` oder beim Bauen mit `404` oder `410`, gilt sie in diesem Lauf als nicht gelistet (was sie hielt, fällt vorerst weg), und ihre Gruppe behält keinen Validator. Der nächste Lauf liest die Liste deshalb wieder aus und fragt nur diese Datei erneut; die übrigen Dateien der Gruppe entscheidet ihre Prüfsumme ohne Abruf. Die Ausgabe nennt „N not served (asked again next run)“, das Lauf-Log zählt sie in `missing`.

**Migration:** M5-19 PR 2 (#379) bringt eine eigene `030` und wird vorher gemergt; die Migration dieses PRs heißt deshalb `031_materialize_unit_expires.sql` (Otto, 19.11.2026).

### 12.6 Umfang

Rund 330 Zeilen ohne Tests, YAML und Doku (Adapter rund 230, Kern rund 60, Formen und Migration rund 40, Provenienz rund 15, Frontend rund 30), dazu rund 600 Zeilen Tests. Der Adapter ersetzt den Lauf aus M5-11 (rund 150 Zeilen entfernt).
