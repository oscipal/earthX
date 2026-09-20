# Synthetische Earth-Search-Antworten

Diese Dateien sind **von Hand geschrieben**, nicht aufgezeichnet. Sie bilden die
Formen nach, die `docs/adr/0005-foederierte-item-suche.md` §3 an der echten Quelle
gemessen hat — Antwortrumpf mit `numberMatched`/`context`, `next`-Link als POST-Link
**mit Rumpf**, die Fehlerformen aus §3.5 —, enthalten aber keine echten Metadaten:
IDs, Zeiten, Geometrien und Asset-Adressen sind erfunden und klein gehalten.

**Warum synthetisch:** Otto hat am 19.09.2026 entschieden, dass **dauerhaft nicht
aufgezeichnet wird** (`docs/plans/m1-06-earth-search-adapter.md` §9 F6). Damit stellt
sich die offene Lizenzfrage zu den Earth-Search-Metadaten (`adr/0005` §8 Punkt 1) für
Fixtures nicht mehr, und `ENTSCHEIDUNGEN_2026-09-18.md` §4 ist ohne weitere Prüfung
eingehalten. Wer hier eine Datei ergänzt, schreibt sie also von Hand.

**Was sie deshalb nicht können:** belegen, dass die Quelle noch so antwortet. Genau
dafür gibt es den zeitgesteuerten Live-Smoke-Test (`backend/tests_live/`, T-D laut
`adr/0002` §2).

## Aggregation (M2-05)

`aggregate_complete.json` und `aggregate_truncated.json` bilden die Form nach, die
`GET /aggregate` am 20.09.2026 zurückgab und die in `plans/m2-05-coverage.md` §3.1
mit einem Bucket je Aggregation abgedruckt ist: eine Liste `aggregations` mit
`total_count` als `value` und den beiden `frequency_distribution`-Aggregationen als
`buckets` mit `key` und `frequency`, der Gitterschlüssel wörtlich als `z/x/y`, die
Histogramm-Schlüssel als Instant mit `Z` und drei Nachkommastellen.

Die Zahlen sind klein und erfunden. Der Unterschied zwischen den beiden Dateien ist
der Fall, auf den es ankommt: In `aggregate_truncated.json` ist die Summe der Zellen
kleiner als `total_count`, und `overflow` meldet trotzdem `0` — genau so, wie die
echte Quelle auf z8 antwortet. Die Vollständigkeitsprobe (Regel V, `adr/0004` §5) muss
das erkennen, ohne `overflow` anzusehen.
## `item_asset_hosts.json`

Ebenfalls von Hand geschrieben, für den Lesepfad aus M2-04. Echt ist daran genau
**ein** Wert: der Asset-Host `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com`,
den `docs/adr/0006-kachel-pfad.md` §3.7 an der Quelle gemessen und im Dokument
festgehalten hat. Item-ID, Pfad, Zeit und Ausdehnung sind erfunden.

Der Asset `elsewhere` zeigt bewusst auf `sentinel-cogs…amazonaws.com` — den Host der
**älteren** Collection (§3.7). Er steht nicht in der Registry und muss deshalb an
`gateway` scheitern; ohne ihn ließe sich nicht zeigen, dass die Allowlist aus der
Registry wirklich zählt und nicht bloß jeden AWS-Bucket durchlässt.
