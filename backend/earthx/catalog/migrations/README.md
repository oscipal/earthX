# Eigene Migrationen

Hier liegen die SQL-Migrationen, die EarthX **neben** pgstac braucht. pgstac bringt
sein eigenes Schema und seine eigene Migration mit (`pypgstac migrate`, in compose der
Dienst `pgstac-migrate`); was hier liegt, gehört uns.

**Was hier liegt:** `002_search_cache.sql` — der Anwendungs-Cache aus E4, angelegt in
**M1-06** für die föderierte Item-Suche. In M1-04 war das Verzeichnis leer, weil
Collections in pgstac liegen; die Nummerierung beginnt deshalb bei `002` (die `001`
war die Buchführungstabelle, bevor sie zum Läufer wanderte, siehe unten).

`006_jobs.sql` — die Warteschlange der Jobs aus M4-08a (`adr/0013` §5.1, §6.3):
`earthx_recipe`, `earthx_run`, `earthx_job` und die Zeile `earthx_job_limits` mit Deckel
und Grenze je Host. Die Tabellen gehören dem Modul `jobs`, das sie nur mit SQL
anfasst; sie liegen hier, weil `jobs` `catalog` nicht importieren darf und die
Buchführung des Läufers eine einzige sein soll. Jeder Fremdschlüssel ist
`RESTRICT` und hat einen Index.

`007_run_attachments.sql` — die Spalte `earthx_run.attachments` aus M4-11a: die
Begleitdateien eines Export-Jobs (`ATTRIBUTION.txt`, `citation.bib`, `aoi.geojson`), die
`api` baut und `jobs` ungelesen an den Lauf weitergibt.

`008_run_disk.sql` — die Spalte `earthx_run.disk_bytes` aus M4-11a: der geschätzte
Platzbedarf eines Laufs im Arbeitsordner, den der Aufseher vor dem Start prüft.

`010_job_scene_aoi.sql` — die Spalte `earthx_job.scene_aoi` aus M4-30: ob ein Auftrag ganze
Szenen ohne Fläche nannte, sein Rezept also die Vereinigung der Footprints als AOI trägt.
`aoi.geojson` im ZIP des Jobs sagt es; `api` findet es bei der Annahme, `jobs` speichert es ungelesen.

`011_job_aoi_provenance.sql` — die Spalte `earthx_job.aoi_provenance` aus M4-30: woher die Orts-AOI
eines Raster-Auftrags stammt (Attribution, Lizenz, Quelle). Je Job, nicht je Lauf, nicht im Rezept;
`jobs` speichert sie ungelesen, `api` schreibt sie ins ZIP des Jobs.

`012_permalink.sql` — die Tabelle `earthx_permalink` aus M4-19e: Auftrag und Ansicht hinter einer
zufälligen Kennung, die Frist fest 30 Tage ab Erstellung, dazu der SHA-256 des Löschschlüssels. Kein
Fremdschlüssel; `api` schreibt und liest über `jobs/permalinks.py`, der stündliche Aufräumer löscht.

`013_job_acquisition_years.sql` — die Spalten `earthx_job.acquired_first_year` und `acquired_last_year` aus
NM4-01: die Aufnahmejahre der Szenen eines Auftrags, aus denen die Attribution beim Abruf gebaut wird
(nie aus der Uhr). Je Job, nicht je Lauf, nicht im Rezept; `jobs` speichert sie ungelesen.

`014_bundle.sql` — die Tabelle `earthx_bundle` aus UI-01e: die `jobID`s hinter „Download all (ZIP)“ unter einer
zufälligen Kennung, die Frist das früheste Ende der Jobs, fest ab Erstellung. Keine AOI, kein Titel, keine Bytes;
`api` schreibt und liest über `jobs/bundles.py`, der stündliche Aufräumer löscht.

`016_dataset_search.sql` — die Tabelle `earthx_dataset_search` aus M5-22b: der Index der Datensatzsuche neben
pgstac, eine Zeile je Registry-Eintrag mit den vier Teilen des Suchtexts, einem `tsvector` in `simple`, `german` und
`english`, dem Text für Trigramme, der Box als vier Zahlen (kein PostGIS nötig) und der zeitlichen Ausdehnung. Legt
`unaccent` und `pg_trgm` an. `catalog-load` schreibt sie, `api` prüft sie beim Start.

`017_mosaic_selection.sql` — die Tabelle `earthx_mosaic_selection` aus M5-30b Teil 3 (`adr/0032` §10.2): die Auswahl hinter
einer Mosaik-Kachel-URL unter der ID, die der Hash ihres Inhalts ist (Datensatz, Assets, Item-IDs), dazu Reihenfolge, Umrisse
und Ausdehnung für die Kacheln. Frist 7 Tage, ein erneutes Anlegen verlängert sie; keine AOI. `api` schreibt und liest über
`catalog/mosaic_selection.py`, der stündliche Aufräumer von `jobs` löscht.

`018_overview.sql` — die Tabellen der Übersichtspyramide aus M5-30b Teil 8b (`adr/0032` §5.2, §5.3): `earthx_overview_request`
(„dieser Datensatz hat jetzt diese Fassung der Quelle“, geschrieben von `materialize` über `catalog`) und `earthx_overview` (eine
Zeile je Datensatz und Fassung: Status `building`/`ready`/`failed` mit Frist, Fehlerart, Hashes der Basiskacheln, `checked_at`,
`confirmed_at`; geschrieben von `jobs` nur mit SQL). Dazu die Funktion `earthx_overview_version` (die 16 Hexziffern der Fassung im
Objektschlüssel).

`019_overview_upkeep.sql` — die Tabelle `earthx_overview_upkeep` aus M5-38: eine Zeile je Pflegeaufgabe der Pyramiden (`extend`,
`sweep`) mit Zug-Nummer, Worker, Frist und frühestem nächsten Zug. Ein Worker nimmt den Zug, bevor er verlängert oder aufräumt;
die anderen lassen die Runde aus. Eine abgelaufene Frist wird übernommen. Geschrieben von `jobs` nur mit SQL.

`020_overview_omitted.sql` — die Tabelle `earthx_overview_omitted` (M5-30b, `adr/0032` Nachtrag 15.11.2026): je ausgelassener Basiskachel einer Pyramide eine Zeile (`x/y`, Fehlerart, Klasse, kurzer Grund ohne Adresse, Versuche, Zeit des letzten Versuchs). Eine Datei, die nach den Wiederholungen unlesbar bleibt, lässt nur ihre Basiskachel aus, die Pyramide wird `ready`, die stündliche Runde liest die Kachel erneut. Dazu erlaubt die Prüfung von `earthx_overview_upkeep.task` die Aufgabe `retry` und die Migration legt deren Zeile an (frei, `next_at` = jetzt); die Wiederholung nimmt Züge wie Verlängern und Aufräumen (019), ein Worker zugleich. Dazu die Tabelle `earthx_overview_host` (eine Zeile je Host der Quellen: `worker`, `lease_until`, `turn`): Die Wiederholung leiht sich die Hosts, von denen sie liest, für die Dauer des Lesens; `claim` lässt einen Host mit lebender Leihe in Ruhe, und `take_hosts` einen Host, von dem ein Bau liest, beides unter derselben Advisory-Sperre. Eine abgelaufene Leihe wird übernommen. Geschrieben von `jobs` nur mit SQL.

`021_listed_entry.sql` — die Tabellen gelisteter Einträge aus M5-40 (`adr/0033`, `docs/plans/m5/m5-40-gelistete-in-postgres.md`
§5.1): `earthx_listed_entry` (eine Zeile je gelistetem Eintrag mit Zustand, Herkunft je Eintrag und Grabstein, partielle
Indizes für Seiten nach Titel und die Filter Fläche, Zeit, Region und Kategorie, Schlüssel mit `COLLATE "C"`),
`earthx_region` und `earthx_region_part` (Grenzen aus `backend/catalog/regions.json`, in Stücke geschnitten). Geschrieben
von `catalog-load`, gelesen von `api` je Seite.

`022_source_host.sql` — Zeiger, Unterbrecher und Plätze je Host aus M5-37 (`docs/plans/m5/m5-37-zeiger-je-host.md`
§3): `earthx_source_host` (eine Zeile je Host: frühester Beginn der nächsten Anfrage, Fehler in Folge, Pausen) und
`earthx_source_lease` (ein Platz je laufender Anfrage, nummeriert bis zur Grenze, mit Frist und Herzschlag). Für
`materialize`, den Harvester und den Pyramidenbau über alle Instanzen; geschrieben je Anfrage auf einer eigenen
Verbindung im Autocommit.

Die Buchführungstabelle `earthx_migrations` gehört nicht hierher, sondern dem Läufer
(`earthx/catalog/schema.py`) und wird von ihm angelegt. Sonst müsste jedes
Migrationsverzeichnis sie erneut mitbringen.

## Regeln

- Dateiname `<nnn>_<name>.sql`, dreistellig und fortlaufend: `002_search_cache.sql`.
- Eine angewandte Migration wird **nie** geändert. Der Läufer merkt sich eine
  Prüfsumme und verweigert den Dienst, wenn die Datei sich danach noch bewegt hat —
  eine nachträgliche Änderung ließe Datenbanken stillschweigend auseinanderlaufen.
  Stattdessen eine neue Datei schreiben.
- Datei und Buchungszeile laufen in einer Transaktion. Eine halb angewandte Migration
  kann deshalb nicht als erledigt gelten.
