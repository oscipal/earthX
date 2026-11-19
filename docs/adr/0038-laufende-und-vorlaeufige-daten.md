# ADR 0038 — Laufende und vorläufige Daten

- **Status:** **Entwurf** (Otto, 18.11.2026, M5-58 F7 = 1). Die Optionen unten sind mit den Antworten zum Plan entschieden (F1–F9 = 1); angenommen ist der ADR erst mit dem Merge von PR 1.
- **Datum:** 2026-11-18.
- **Aufgabe:** M5-58, Plan `docs/plans/m5/m5-58-laufende-daten.md`.
- **Vorab fest (Otto, 18.11.2026):** Datensätze, deren Quelle aktuelle bzw. vorläufige Werte anbietet, nehmen diese mit auf; Vorläufiges wird durch Endgültiges ersetzt, sobald die Quelle es liefert. Was die Quelle laufend ändert, auch ohne neue Datei, wird ebenso nachgeführt: Änderung über ETag, Last-Modified oder Hash erkennen, nur Betroffenes neu schreiben. Ein Mechanismus, kein Sonderweg je Quelle.
- **Grundlage:** `adr/0009` §7.3 (Fassung je Lauf, „delsert“), `adr/0025` §6.6 und F7, `adr/0029` §3.1, §6, F5, `adr/0032` §5 (Pyramide je Fassung), `KLAERUNGEN.md` B9, B10, B13; M5-11 F3 (`v=<updated>`).
- **Betroffen:** Registry (`catalog`), `adapters` (Protokoll), `discovery.materialize`, Migration in `catalog`, Coverage „festes Gitter“; Frontend erst mit PR 2 (Tooltip).

Belegstufen wie in `adr/0029`: **M** gemessen, **P** am Quelltext gelesen, **P\*** in der Doku der Quelle gelesen, **A** eigene Ableitung.

---

## 1. Kontext

- `materialize` kennt heute nur „alles oder nichts“: Eine Fassung je Lauf (z. B. ETag einer Kachelliste) entscheidet `unchanged` oder `loaded`; bei `loaded` werden alle Items geschrieben und alle übrigen gelöscht (`adr/0009` §7.3) [P].
- Für statische Quellen (GLO-30, WorldCover) passt das. Für Quellen, die sich laufend ändern, nicht: Bei MeteoSchweiz verwiese eine einzige geänderte Datei alle 230 Jahresdateien neu, rund 30 min (M5-11 §11.7) [M].
- MeteoSchweiz liefert drei Stände desselben Tages: vorläufige Tagesdateien (41 Tage), konsolidierte Monatsdateien (14 Monate, am 26. des Folgemonats überschrieben) und das Archiv (Endbearbeitung im Februar) [P\*]. Die Nutzungsbedingungen verbieten das wiederholte Laden desselben Inhalts [P\*].
- DWD HYRAS, swissALTI3D, BEV und später ERA5T zeigen dasselbe Muster in anderer Form (Plan §5).

## 2. Kriterien

1. Ein Mechanismus für alle materialisierten Quellen; die Quelle steuert nur, was sie selbst weiß (Einheiten, Stand, Validatoren).
2. Kein Abruf, wo die Quelle schon sagt, dass nichts geändert ist; nie derselbe Inhalt zweimal.
3. Nur betroffene Items werden geschrieben; ein Lauf bleibt eine Transaktion.
4. Eine Zeitleiste, eine Auswahl, eine gespeicherte Ebene bleiben über einen Standwechsel gültig.
5. Kein Zustand in YAML, der sich täglich ändert (`adr/0025` §6.6); Worker-Kern bleibt zustandslos (B9).
6. Heutige Einträge verhalten sich unverändert.

## 3. Entscheidung

### 3.1 Registry: `updates`

Pflichtfeld jedes vollen Eintrags, ohne Vorgabe (B10):

| Feld | Werte | Bedeutung |
|---|---|---|
| `cadence` | `none`, `daily`, `weekly`, `monthly` | wie oft die Quelle sich ändert; der Takt des `harvester` ab M5-24, bis dahin Läufe von Hand (F6) |
| `states` | `[final]` oder `[provisional, final]` | die Stände der Quelle in aufsteigendem Rang (F3: zwei Stände) |
| `detect` | `whole`, `units` | eine Fassung je Lauf wie bisher, oder Änderung je Einheit der Quelle |

Regeln beim Laden: `states` endet mit `final`, ohne Doppelte, aufsteigend; `cadence: none` verträgt kein `provisional`; `units` nur bei `item_holding: materialized` und nicht mit `overview: pyramid` (die Pyramide hängt an der Fassung je Lauf, `adr/0032` §5); ein Eintrag mit `provisional` nennt das in `limitations` (F1). Ein laufender Eintrag (`cadence` ≠ `none`) darf `temporal_extent.end` offen lassen.

### 3.2 Item: Stand

- `properties.earthx:state` (`provisional` | `final`) bei jedem Item eines Eintrags mit zwei Ständen: der niedrigste Stand seiner Assets. Jedes Asset trägt seinen eigenen `earthx:state`.
- Ein Standard für „vorläufig“ gibt es in STAC nicht (`processing:level` meint die Verarbeitungsstufe). `expires` (Timestamps Extension) steht am Asset, wo die Quelle es für dessen Herkunft nennt; das Item trägt das früheste und keines mehr, sobald kein Asset eines trägt (nach dem Ersetzen durch Endgültiges). Es steuert nichts: Ersetzt wird beim Eintreffen des höheren Stands, gelöscht beim Wegfall der Einheit (Plan §11.3).
- Ersetzen unter **derselben Item-ID** (F2). `properties.updated` ändert sich und damit `v=` in den Kachel-URLs (M5-11 F3); der Chunk-Cache trennt über das ETag.

### 3.3 Änderungserkennung je Einheit (`detect: units`)

Eine **Einheit** ist das Kleinste, an dem die Quelle eine Änderung zeigt (eine Datei, ein Listeneintrag); eine **Gruppe** das Listendokument, das sie nennt (ein Quell-Item, eine Seite). Der Adapter liefert zwei Funktionen:

- `list_units`: die Gruppen der Quelle, bedingt gefragt (`If-None-Match` mit dem gespeicherten Validator) oder, wo die Quelle kein ETag nennt, über den SHA-256 ihres Inhalts entschieden (MeteoSchweiz: die Liste, Plan §11.4); für jede geänderte Gruppe ihre Einheiten mit Stand und Validatoren. Eine unveränderte Gruppe behält ihre gespeicherten Einheiten.
- `build`: die **Beiträge** neuer und geänderter Einheiten, je Paar (Item-ID, Asset-Schlüssel) ein Asset und das Gerüst des Items.

Der Kern in `discovery.materialize` entscheidet je Einheit, in dieser Reihenfolge, wobei die erste Angabe gilt, die auf beiden Seiten vorliegt:

1. Angaben der Liste (`file:checksum`, ETag, `updated`) gegen den gespeicherten Stand — kein Abruf;
2. `HEAD` mit `If-None-Match` auf das gespeicherte ETag;
3. `HEAD` mit `If-Modified-Since` auf das gespeicherte Last-Modified;
4. SHA-256 der Antwort (nur bis zur Grenze von `gateway`, 8 MiB).

Ein Wechsel des Stands zählt als Änderung.

### 3.4 Ersetzungsregel

Je Paar (Item-ID, Asset-Schlüssel), über alle Einheiten, die dazu beitragen:

1. Der höhere Stand gilt.
2. Bei gleichem Stand gilt die Einheit mit dem jüngeren Last-Modified (bei MeteoSchweiz: die Jahresdatei aus der Endbearbeitung vor der Monatsdatei).
3. Ein niedrigerer Stand ersetzt nie einen höheren.
4. Fällt die geltende Einheit weg, gilt die nächste verbliebene; ihr Beitrag wird neu gebaut. Bleibt keine, fällt das Asset weg; ein Item ohne Assets wird gelöscht.

Geschrieben werden nur Items, in denen sich ein Asset ändert; alles in einer Transaktion mit dem Zustand.

### 3.5 Zustand in Postgres

- `earthx_materialize_group` (Datensatz, Gruppe, Validator) und `earthx_materialize_unit` (Datensatz, Einheit, Gruppe, Adresse, Stand, Validatoren, Beiträge als Liste von Paaren, gesehen/geändert am).
- `earthx_materialize_runs` zählt je Lauf Einheiten neu, geändert, unverändert, weg und ersetzte Items (Stand gestiegen).
- Nichts davon steht in YAML; ein Lauf ohne Änderung schreibt nur die Zeile im Lauf-Log.

### 3.6 Zeitraum und Coverage

Ein laufender Eintrag hat `temporal_extent.end: null`. Die Collection nennt das Ende offen (das Datumsfeld reicht bis heute). Die Coverage „festes Gitter“ zählt dann bis zum Ende des jüngsten geladenen Items.

### 3.7 Frontend

Keine Marke (M5-Plan §2 Punkt 9, F1): ein Satz in `limitations` im Data catalogue und ein Tooltip „Provisional values“ am Datum eines vorläufigen Tages (PR 2). **Geändert (Otto, 19.11.2026, beim Review von PR 2):** In der Trefferliste steht neben der Uhrzeit eines vorläufigen Tages ein Warndreieck (die Komponente `Tip` mit Ton `warn`, der Text am Dreieck) statt eines Tooltips an der Uhrzeit.

## 4. Verworfene Optionen

- **Neue Item-ID je Stand** (F2 Option 2): Auswahl, gespeicherte Ebenen und Zeitleiste zeigten nach dem Ersetzen ins Leere; zwei Items desselben Tages zur selben Zeit wären möglich.
- **Drei Stände** mit `consolidated` (F3 Option 2): Die Monatsdateien werden selbst noch überschrieben; was sich danach ändert, deckt die Änderungserkennung, ein dritter Rang bringt nichts.
- **Alles je Lauf neu** (heute): verletzt Kriterium 2 und 3 bei jeder laufenden Quelle.
- **Zustand je Datei aus den Items lesen** statt eigener Tabelle: Gruppen-Validatoren und Beiträge unterlegener Stände stehen in keinem Item.

## 5. Folgen

- `adr/0009` §7.3 („delsert“) gilt weiter für `detect: whole`; für `detect: units` ersetzt §3.4 das Löschen aller übrigen Items.
- `adr/0029` F5 („nur abgeschlossene Jahre“) ist für MeteoSchweiz mit M5-58 PR 2 abgelöst.
- `adr/0025` §6.6: Der `harvester` (M5-24) liest `updates.cadence`; der Zustand je Einheit liegt neben dessen Tabellen.
- Föderierte Quellen (Sentinel-1 NRT/Fast-24h, Sentinel-2-Baselines) sind nicht erfasst: Ihre Items liegen nicht in pgstac; dafür braucht es einen eigenen Weg in der Suche (Plan §5).
- Ein Eintrag mit `detect: units` und `overview: pyramid` ist abgelehnt, bis eine Aufgabe Pyramiden je Einheit regelt.
